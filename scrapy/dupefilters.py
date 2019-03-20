from __future__ import print_function
import os
import logging

from scrapy.utils.job import job_dir
from scrapy.utils.request import referer_str, request_fingerprint

class BaseDupeFilter(object):

    @classmethod
    def from_settings(cls, settings):
        return cls()

    def request_seen(self, request):
        return False

    def open(self):  # can return deferred
        pass

    def close(self, reason):  # can return a deferred
        pass

    def log(self, request, spider):  # log that a request has been filtered
        pass


class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""
    ## 请求指纹过滤器：过滤重复请求，可自定义过滤规则

    def __init__(self, path=None, debug=False):
        self.file = None
        ## 指纹集合，使用 set 进行去重
        self.fingerprints = set()
        ## 日志去重是否开启
        self.logdupes = True
        ## 是否开启 debug 模式
        self.debug = debug
        ## 日志处理器
        self.logger = logging.getLogger(__name__)
        ## 若存在路径，可将请求或的指纹存入磁盘文件
        if path:
            self.file = open(os.path.join(path, 'requests.seen'), 'a+')
            self.file.seek(0)
            self.fingerprints.update(x.rstrip() for x in self.file)

    @classmethod
    def from_settings(cls, settings):
        ## 基于配置创建一个请求指纹过滤器的实例

        debug = settings.getbool('DUPEFILTER_DEBUG')
        return cls(job_dir(settings), debug)

    def request_seen(self, request):
        ## 根据请求创建一个请求指纹
        fp = self.request_fingerprint(request)
        ## 如果该请求指纹存在于指纹集合中，则返回 True
        if fp in self.fingerprints:
            return True
        ## 否则将该指纹加入到指纹集合中
        self.fingerprints.add(fp)
        ## 如果存在文件，则同时将该指纹写入到文件中
        if self.file:
            self.file.write(fp + os.linesep)

    def request_fingerprint(self, request):
        ## 根据请求创建指纹
        return request_fingerprint(request)

    def close(self, reason):
        if self.file:
            self.file.close()

    def log(self, request, spider):
        if self.debug:
            msg = "Filtered duplicate request: %(request)s (referer: %(referer)s)"
            args = {'request': request, 'referer': referer_str(request) }
            self.logger.debug(msg, args, extra={'spider': spider})
        elif self.logdupes:
            msg = ("Filtered duplicate request: %(request)s"
                   " - no more duplicates will be shown"
                   " (see DUPEFILTER_DEBUG to show all duplicates)")
            self.logger.debug(msg, {'request': request}, extra={'spider': spider})
            self.logdupes = False

        spider.crawler.stats.inc_value('dupefilter/filtered', spider=spider)
