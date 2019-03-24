"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header

from scrapy import signals


class HttpAuthMiddleware(object):
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""
    ## 设置基本 HTTP 授权头，即：
    ## 如果 spider 中设置了 http_user 和 http_pass，则将这两个属性值经过一定的处理
    ## 并通过 base64 编码后，添加到请求头中，作为 Authorization 字段的值

    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        usr = getattr(spider, 'http_user', '')
        pwd = getattr(spider, 'http_pass', '')
        if usr or pwd:
            self.auth = basic_auth_header(usr, pwd)

    def process_request(self, request, spider):
        auth = getattr(self, 'auth', None)
        if auth and b'Authorization' not in request.headers:
            request.headers[b'Authorization'] = auth
