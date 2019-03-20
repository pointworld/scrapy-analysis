"""Download handlers for different schemes"""

import logging
from twisted.internet import defer
import six
from scrapy.exceptions import NotSupported, NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.python import without_none_values
from scrapy import signals


logger = logging.getLogger(__name__)


class DownloadHandlers(object):
    ## 下载处理器

    def __init__(self, crawler):
        self._crawler = crawler
        ## 存储在实例化时可接受的协议
        self._schemes = {}  # stores acceptable schemes on instancing
        ## 存储协议对应的处理器
        self._handlers = {}  # stores instanced handlers for schemes
        self._notconfigured = {}  # remembers failed handlers
        ## 从配置中找到 DOWNLOAD_HANDLERS_BASE，构造下载处理器
        ## 注意：这里是调用 getwithbase 方法，取的是配置中的 XXXX_BASE 配置
        handlers = without_none_values(
            crawler.settings.getwithbase('DOWNLOAD_HANDLERS'))
        ##  存储协议对应的类路径，后面用于实例化
        for scheme, clspath in six.iteritems(handlers):
            self._schemes[scheme] = clspath
            self._load_handler(scheme, skip_lazy=True)

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, scheme):
        """Lazy-load the downloadhandler for a scheme
        only on the first request for that scheme.
        """
        if scheme in self._handlers:
            return self._handlers[scheme]
        if scheme in self._notconfigured:
            return None
        if scheme not in self._schemes:
            self._notconfigured[scheme] = 'no handler available for that scheme'
            return None

        return self._load_handler(scheme)

    def _load_handler(self, scheme, skip_lazy=False):
        path = self._schemes[scheme]
        try:
            dhcls = load_object(path)
            if skip_lazy and getattr(dhcls, 'lazy', True):
                return None
            dh = dhcls(self._crawler.settings)
        except NotConfigured as ex:
            self._notconfigured[scheme] = str(ex)
            return None
        except Exception as ex:
            logger.error('Loading "%(clspath)s" for scheme "%(scheme)s"',
                         {"clspath": path, "scheme": scheme},
                         exc_info=True, extra={'crawler': self._crawler})
            self._notconfigured[scheme] = str(ex)
            return None
        else:
            self._handlers[scheme] = dh
            return dh

    def download_request(self, request, spider):
        scheme = urlparse_cached(request).scheme
        handler = self._get_handler(scheme)
        if not handler:
            raise NotSupported("Unsupported URL scheme '%s': %s" %
                               (scheme, self._notconfigured[scheme]))
        return handler.download_request(request, spider)

    @defer.inlineCallbacks
    def _close(self, *_a, **_kw):
        for dh in self._handlers.values():
            if hasattr(dh, 'close'):
                yield dh.close()
