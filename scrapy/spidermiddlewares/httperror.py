"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
import logging

from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super(HttpError, self).__init__(*args, **kwargs)


class HttpErrorMiddleware(object):
    ## 过滤掉不成功（或错误）的 HTTP 响应，这样爬虫就不会处理这些响应
    ## 因为这些响应会增加开销，消耗更多的资源，从而使爬虫逻辑变得更复杂
    ##
    ## 正常情况下会被处理的状态码在 [200, 300) 之间
    ## 如果想处理这个范围外的响应，可以通过：
    ## 1. 在自定义的爬虫类中指定 handle_httpstatus_list 属性，值为你想处理的其他状态码的列表
    ## 2. 或在配置中设置 HTTPERROR_ALLOWED_CODES 项
    ## 3. 或在 Request.meta 中
    ##    - 指定 handle_httpstatus_list
    ##    - 或将 handle_httpstatus_all 设为 True

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.handle_httpstatus_all = settings.getbool('HTTPERROR_ALLOW_ALL')
        self.handle_httpstatus_list = settings.getlist('HTTPERROR_ALLOWED_CODES')

    def process_spider_input(self, response, spider):
        if 200 <= response.status < 300:  # common case
            return
        meta = response.meta
        if 'handle_httpstatus_all' in meta:
            return
        if 'handle_httpstatus_list' in meta:
            allowed_statuses = meta['handle_httpstatus_list']
        elif self.handle_httpstatus_all:
            return
        else:
            allowed_statuses = getattr(spider, 'handle_httpstatus_list', self.handle_httpstatus_list)
        if response.status in allowed_statuses:
            return
        raise HttpError(response, 'Ignoring non-200 response')

    def process_spider_exception(self, response, exception, spider):
        if isinstance(exception, HttpError):
            spider.crawler.stats.inc_value('httperror/response_ignored_count')
            spider.crawler.stats.inc_value(
                'httperror/response_ignored_status_count/%s' % response.status
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {'response': response}, extra={'spider': spider},
            )
            return []
