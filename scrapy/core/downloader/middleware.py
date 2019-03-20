"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""
import six

from twisted.internet import defer

from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list


class DownloaderMiddlewareManager(MiddlewareManager):
    ## 下载器中间件管理器

    component_name = 'downloader middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        ## 从配置 DOWNLOADER_MIDDLEWARES_BASE 和 DOWNLOADER_MIDDLEWARES 中获取所有下载器中间件
        return build_component_list(
            settings.getwithbase('DOWNLOADER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        ## 定义下载器中间件中处理请求、响应、异常时需要执行的一连串方法
        if hasattr(mw, 'process_request'):
            ## 处理请求的方法向双端队列的右侧追加
            self.methods['process_request'].append(mw.process_request)
        if hasattr(mw, 'process_response'):
            ## 处理响应的方法向双端队列的左侧追加
            self.methods['process_response'].appendleft(mw.process_response)
        if hasattr(mw, 'process_exception'):
            ## 处理异常的方法向双端队列的左侧追加
            self.methods['process_exception'].appendleft(mw.process_exception)

    def download(self, download_func, request, spider):
        @defer.inlineCallbacks
        def process_request(request):
            for method in self.methods['process_request']:
                response = yield method(request=request, spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                        'Middleware %s.process_request must return None, Response or Request, got %s' % \
                        (six.get_method_self(method).__class__.__name__, response.__class__.__name__)
                if response:
                    defer.returnValue(response)
            defer.returnValue((yield download_func(request=request,spider=spider)))

        @defer.inlineCallbacks
        def process_response(response):
            assert response is not None, 'Received None in process_response'
            if isinstance(response, Request):
                defer.returnValue(response)

            for method in self.methods['process_response']:
                response = yield method(request=request, response=response,
                                        spider=spider)
                assert isinstance(response, (Response, Request)), \
                    'Middleware %s.process_response must return Response or Request, got %s' % \
                    (six.get_method_self(method).__class__.__name__, type(response))
                if isinstance(response, Request):
                    defer.returnValue(response)
            defer.returnValue(response)

        @defer.inlineCallbacks
        def process_exception(_failure):
            exception = _failure.value
            for method in self.methods['process_exception']:
                response = yield method(request=request, exception=exception,
                                        spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                    'Middleware %s.process_exception must return None, Response or Request, got %s' % \
                    (six.get_method_self(method).__class__.__name__, type(response))
                if response:
                    defer.returnValue(response)
            defer.returnValue(_failure)

        deferred = mustbe_deferred(process_request, request)
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
