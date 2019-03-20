from collections import defaultdict, deque
import logging
import pprint

from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.defer import process_parallel, process_chain, process_chain_both

logger = logging.getLogger(__name__)


class MiddlewareManager(object):
    """Base class for implementing middleware managers"""
    ## 中间件管理器：所有中间件的基类
    ## 中间件的职责：
    ## 当请求或响应从某个组件流向另一个组件时，会经过一系列中间件，每个中间件都定义了自己
    ## 的处理流程，相当于一个个管道，输入时可以针对数据进行处理，然后送达到另一个组件，
    ## 另一个组件处理完逻辑后，又经过这一系列中间件，这些中间件可再针对这个响应结果进行
    ## 处理，最终输出

    ## 组件名
    component_name = 'foo middleware'

    def __init__(self, *middlewares):
        ## 存放可用的中间件实例的列表
        self.middlewares = middlewares
        ## 定义中间件方法，用一个双端队列来存储
        self.methods = defaultdict(deque)
        for mw in middlewares:
            self._add_middleware(mw)

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        ## 具体有哪些中间件类，有子类定义
        raise NotImplementedError

    @classmethod
    def from_settings(cls, settings, crawler=None):
        ## 基于爬虫对象和配置创建中间件实例

        ## 调用子类的 _get_mwlist_from_settings 方法，从配置中获取所有中间件路径的列表
        mwlist = cls._get_mwlist_from_settings(settings)
        ## 存放可用的中间件类的实例
        middlewares = []
        ## 存放可用的中间件类的路径
        enabled = []
        for clspath in mwlist:
            try:
                ## 根据中间件类路径加载中间件类
                mwcls = load_object(clspath)
                ## 基于配置为爬虫对象创建中间件类的实例
                mw = create_instance(mwcls, settings, crawler)
                middlewares.append(mw)
                enabled.append(clspath)
            except NotConfigured as e:
                if e.args:
                    clsname = clspath.split('.')[-1]
                    logger.warning("Disabled %(clsname)s: %(eargs)s",
                                   {'clsname': clsname, 'eargs': e.args[0]},
                                   extra={'crawler': crawler})

        logger.info("Enabled %(componentname)ss:\n%(enabledlist)s",
                    {'componentname': cls.component_name,
                     'enabledlist': pprint.pformat(enabled)},
                    extra={'crawler': crawler})
        ## 调用构造方法
        return cls(*middlewares)

    @classmethod
    def from_crawler(cls, crawler):
        ## 调用 self.from_settings 方法
        return cls.from_settings(crawler.settings, crawler)

    def _add_middleware(self, mw):
        ## 定义中间件中打开爬虫和关闭爬虫时需要执行的一连串方法
        if hasattr(mw, 'open_spider'):
            self.methods['open_spider'].append(mw.open_spider)
        if hasattr(mw, 'close_spider'):
            self.methods['close_spider'].appendleft(mw.close_spider)

    def _process_parallel(self, methodname, obj, *args):
        return process_parallel(self.methods[methodname], obj, *args)

    def _process_chain(self, methodname, obj, *args):
        return process_chain(self.methods[methodname], obj, *args)

    def _process_chain_both(self, cb_methodname, eb_methodname, obj, *args):
        return process_chain_both(self.methods[cb_methodname], \
            self.methods[eb_methodname], obj, *args)

    def open_spider(self, spider):
        return self._process_parallel('open_spider', spider)

    def close_spider(self, spider):
        return self._process_parallel('close_spider', spider)
