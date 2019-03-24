"""
Download timeout middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from scrapy import signals


class DownloadTimeoutMiddleware(object):
    ## 下载超时中间件
    ## 用来为待下载的请求添加下载超时控制
    ## 可以在 spiders 中，通过 DOWNLOAD_TIMEOUT 或 download_timeout 属性控制
    ## 默认 DOWNLOAD_TIMEOUT 的值为 180s （3min）
    ## 也可以在待发送请求的 meta 中设置 download_timeout 属性，来进行控制
    ## 注意：该 request.meta 字段中的数据是在 Scrapy 内部用的

    def __init__(self, timeout=180):
        self._timeout = timeout

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings.getfloat('DOWNLOAD_TIMEOUT'))
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        self._timeout = getattr(spider, 'download_timeout', self._timeout)

    def process_request(self, request, spider):
        if self._timeout:
            request.meta.setdefault('download_timeout', self._timeout)
