from email.utils import formatdate
from twisted.internet import defer
from twisted.internet.error import TimeoutError, DNSLookupError, \
        ConnectionRefusedError, ConnectionDone, ConnectError, \
        ConnectionLost, TCPTimedOutError
from twisted.web.client import ResponseFailed
from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.misc import load_object


class HttpCacheMiddleware(object):
    ## HTTP 缓存中间件：该中间件为所有 HTTP request 和 Response 提供底层缓存支持
    ## 其由 cache 存储后端及 cache 策略组成
    ## Scrapy 提供了两种 HTTP 缓存存储后端：
    ##    Filesystem storage backend （默认）
    ##    DBM storage backend
    ## Scrapy 提供了两种缓存策略
    ##    RFC2616 策略
    ##    Dummy 策略（默认）
    ##
    ## Dummy 策略：
    ## 该策略不考虑任何 HTTP Cache-Control 指令，每个 request 及其对应的 response 都会被缓存
    ## 当相同的 request 发生时，其不发送任何数据，直接返回 response
    ## 该策略对于测试 spider 非常有用，其能使 spider 运行更快（不需要每次等待下载完成），同时
    ## 在没有网络连接时也能测试。其目的是为了能够回放 spider 的运行过程，使之与之前的运行过程一模一样

    DOWNLOAD_EXCEPTIONS = (defer.TimeoutError, TimeoutError, DNSLookupError,
                           ConnectionRefusedError, ConnectionDone, ConnectError,
                           ConnectionLost, TCPTimedOutError, ResponseFailed,
                           IOError)

    def __init__(self, settings, stats):
        if not settings.getbool('HTTPCACHE_ENABLED'):
            raise NotConfigured
        ## 缓存策略
        self.policy = load_object(settings['HTTPCACHE_POLICY'])(settings)
        ## 缓存存储方式
        self.storage = load_object(settings['HTTPCACHE_STORAGE'])(settings)
        self.ignore_missing = settings.getbool('HTTPCACHE_IGNORE_MISSING')
        ## 统计
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.storage.open_spider(spider)

    def spider_closed(self, spider):
        self.storage.close_spider(spider)

    def process_request(self, request, spider):
        if request.meta.get('dont_cache', False):
            return

        # Skip uncacheable requests
        ## 跳过不缓存的请求
        if not self.policy.should_cache_request(request):
            request.meta['_dont_cache'] = True  # flag as uncacheable
            return

        # Look for cached response and check if expired
        ## 查询被缓存的响应，并检查其是否过期
        cachedresponse = self.storage.retrieve_response(spider, request)
        if cachedresponse is None:
            self.stats.inc_value('httpcache/miss', spider=spider)
            if self.ignore_missing:
                self.stats.inc_value('httpcache/ignore', spider=spider)
                raise IgnoreRequest("Ignored request not in cache: %s" % request)
            return  # first time request

        # Return cached response only if not expired
        ## 如果没有过期，则返回被缓存的响应
        cachedresponse.flags.append('cached')
        if self.policy.is_cached_response_fresh(cachedresponse, request):
            self.stats.inc_value('httpcache/hit', spider=spider)
            return cachedresponse

        # Keep a reference to cached response to avoid a second cache lookup on
        # process_response hook
        request.meta['cached_response'] = cachedresponse

    def process_response(self, request, response, spider):
        if request.meta.get('dont_cache', False):
            return response

        # Skip cached responses and uncacheable requests
        ## 跳过已被缓存的响应和不可缓存的请求
        if 'cached' in response.flags or '_dont_cache' in request.meta:
            request.meta.pop('_dont_cache', None)
            return response

        # RFC2616 requires origin server to set Date header,
        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.18
        if 'Date' not in response.headers:
            response.headers['Date'] = formatdate(usegmt=1)

        # Do not validate first-hand responses
        cachedresponse = request.meta.pop('cached_response', None)
        if cachedresponse is None:
            self.stats.inc_value('httpcache/firsthand', spider=spider)
            self._cache_response(spider, response, request, cachedresponse)
            return response

        if self.policy.is_cached_response_valid(cachedresponse, response, request):
            self.stats.inc_value('httpcache/revalidate', spider=spider)
            return cachedresponse

        self.stats.inc_value('httpcache/invalidate', spider=spider)
        self._cache_response(spider, response, request, cachedresponse)
        return response

    def process_exception(self, request, exception, spider):
        cachedresponse = request.meta.pop('cached_response', None)
        if cachedresponse is not None and isinstance(exception, self.DOWNLOAD_EXCEPTIONS):
            self.stats.inc_value('httpcache/errorrecovery', spider=spider)
            return cachedresponse

    def _cache_response(self, spider, response, request, cachedresponse):
        if self.policy.should_cache_response(response, request):
            self.stats.inc_value('httpcache/store', spider=spider)
            self.storage.store_response(spider, request, response)
        else:
            self.stats.inc_value('httpcache/uncacheable', spider=spider)
