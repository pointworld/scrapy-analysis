"""Set User-Agent header per spider or use a default value from settings"""

from scrapy import signals


class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""
    ## 用户代理中间件
    ## 为请求设置用户代理
    ## 会尝试用配置中取 USER_AGENT 的值，或在 spider 中取 user_agent 的值
    ## 如果取不到，则默认使用 'Scrapy' 作为用户代理

    def __init__(self, user_agent='Scrapy'):
        self.user_agent = user_agent

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings['USER_AGENT'])
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        self.user_agent = getattr(spider, 'user_agent', self.user_agent)

    def process_request(self, request, spider):
        if self.user_agent:
            request.headers.setdefault(b'User-Agent', self.user_agent)
