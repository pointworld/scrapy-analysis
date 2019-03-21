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
        ## 在下载过程中，首先先找到所有定义好的下载器中间件，包括内置的和自己定义的
        ## 下载前会先依次执行下载器中间件的 process_request 方法，对 request 进行
        ## 加工、处理、校验等操作，然后发起真正的网络下载，即执行传递过来的 download_func 方法
        ## 在这里是下载器的 _enqueue_request 方法

        @defer.inlineCallbacks
        def process_request(request):
            ## 如果下载器中间件有定义 process_request 方法，则依次执行
            ## 每个中间件顺序执行

            for method in self.methods['process_request']:
                response = yield method(request=request, spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                        'Middleware %s.process_request must return None, Response or Request, got %s' % \
                        (six.get_method_self(method).__class__.__name__, response.__class__.__name__)
                ## 如果下载器中间件有返回值，则直接返回该结果
                if response:
                    defer.returnValue(response)
            ## 如果下载器中间件没有返回值，则执行注册进来的方法，也就是下载器的 _enqueue_request 方法
            defer.returnValue((yield download_func(request=request,spider=spider)))

        @defer.inlineCallbacks
        def process_response(response):
            ## 如果下载成功，会依次执行下载器中间件的 process_reponse 方法进行处理
            ## 每个中间件倒序执行

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
            ## 在下载过程中，如果发生异常情况，会依次调用下载器中间件的 process_exception 方法处理
            ## 每个中间件倒序执行

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

        ## 注册回调
        deferred = mustbe_deferred(process_request, request)
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
