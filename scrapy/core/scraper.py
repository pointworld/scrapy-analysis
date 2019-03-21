"""This module implements the Scraper component which parses responses and
extracts information from them"""

import logging
from collections import deque

from twisted.python.failure import Failure
from twisted.internet import defer

from scrapy.utils.defer import defer_result, defer_succeed, parallel, iter_errback
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.misc import load_object
from scrapy.utils.log import logformatter_adapter, failure_to_exc_info
from scrapy.exceptions import CloseSpider, DropItem, IgnoreRequest
from scrapy import signals
from scrapy.http import Request, Response
from scrapy.item import BaseItem
from scrapy.core.spidermw import SpiderMiddlewareManager
from scrapy.utils.request import referer_str

logger = logging.getLogger(__name__)


class Slot(object):
    """Scraper slot (one per running spider)"""

    MIN_RESPONSE_SIZE = 1024

    def __init__(self, max_active_size=5000000):
        self.max_active_size = max_active_size
        self.queue = deque()
        self.active = set()
        self.active_size = 0
        self.itemproc_size = 0
        self.closing = None

    def add_response_request(self, response, request):
        deferred = defer.Deferred()
        self.queue.append((response, request, deferred))
        if isinstance(response, Response):
            self.active_size += max(len(response.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size += self.MIN_RESPONSE_SIZE
        return deferred

    def next_response_request_deferred(self):
        response, request, deferred = self.queue.popleft()
        self.active.add(request)
        return response, request, deferred

    def finish_response(self, response, request):
        self.active.remove(request)
        if isinstance(response, Response):
            self.active_size -= max(len(response.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size -= self.MIN_RESPONSE_SIZE

    def is_idle(self):
        return not (self.queue or self.active)

    def needs_backout(self):
        return self.active_size > self.max_active_size


class Scraper(object):
    ## 这个类其实是处于 Engine、Spiders、Pipeline 之间，是连通这 3 个组件的桥梁

    def __init__(self, crawler):
        self.slot = None
        ## 实例化爬虫中间件管理器
        self.spidermw = SpiderMiddlewareManager.from_crawler(crawler)
        ## 从配置中加载 Pipeline 处理器类
        itemproc_cls = load_object(crawler.settings['ITEM_PROCESSOR'])
        ## 实例化 Pipeline 处理器
        self.itemproc = itemproc_cls.from_crawler(crawler)
        ## 从配置中获取同时处理 item 的并发数
        self.concurrent_items = crawler.settings.getint('CONCURRENT_ITEMS')
        self.crawler = crawler
        self.signals = crawler.signals
        self.logformatter = crawler.logformatter

    @defer.inlineCallbacks
    def open_spider(self, spider):
        """Open the given spider for scraping and allocate resources for it"""
        ## 打开一个给定的爬虫，用于抓取和分配资源

        self.slot = Slot()
        ## 调用所有 pipeline 的 open_spider 方法
        ## 这里的工作主要是 scraper 调用所用 pipeline 的 open_spider 方法，即，如果我们
        ## 定义了多个 pipeline 输出类，重写 open_spider 方法，以完成每个 pipeline 处理
        ## 输出的初始化工作
        yield self.itemproc.open_spider(spider)

    def close_spider(self, spider):
        """Close a spider being scraped and release its resources"""
        ## 关闭一个被爬取过的爬虫，释放他的资源

        slot = self.slot
        slot.closing = defer.Deferred()
        slot.closing.addCallback(self.itemproc.close_spider)
        self._check_if_closing(spider, slot)
        return slot.closing

    def is_idle(self):
        """Return True if there isn't any more spiders to process"""
        return not self.slot

    def _check_if_closing(self, spider, slot):
        if slot.closing and slot.is_idle():
            slot.closing.callback(spider)

    def enqueue_scrape(self, response, request, spider):
        slot = self.slot
        ## 将结果加入到 scraper 的处理队列中
        dfd = slot.add_response_request(response, request)
        ## 注册回调
        def finish_scraping(_):
            slot.finish_response(response, request)
            self._check_if_closing(spider, slot)
            self._scrape_next(spider, slot)
            return _
        dfd.addBoth(finish_scraping)
        dfd.addErrback(
            lambda f: logger.error('Scraper bug processing %(request)s',
                                   {'request': request},
                                   exc_info=failure_to_exc_info(f),
                                   extra={'spider': spider}))
        self._scrape_next(spider, slot)
        return dfd

    def _scrape_next(self, spider, slot):
        while slot.queue:
            ## 从 scraper 处理队列中获取一个待处理的任务
            response, request, deferred = slot.next_response_request_deferred()
            self._scrape(response, request, spider).chainDeferred(deferred)

    def _scrape(self, response, request, spider):
        """Handle the downloaded response or failure through the spider
        callback/errback"""
        assert isinstance(response, (Response, Failure))

        ## 调用 _scrape2 继续处理
        dfd = self._scrape2(response, request, spider) # returns spiders processed output
        ## 注册异常回调
        dfd.addErrback(self.handle_spider_error, request, response, spider)
        ## 注册出口回调
        dfd.addCallback(self.handle_spider_output, request, response, spider)
        return dfd

    def _scrape2(self, request_result, request, spider):
        """Handle the different cases of request's result been a Response or a
        Failure"""
        ## 如果结果不是 Failure 的实例，则调用爬虫中间件管理器的 scrape_response 方法处理
        if not isinstance(request_result, Failure):
            return self.spidermw.scrape_response(
                self.call_spider, request_result, request, spider)
        ## 否则，调用 call_spider 处理
        else:
            # FIXME: don't ignore errors in spider middleware
            dfd = self.call_spider(request_result, request, spider)
            return dfd.addErrback(
                self._log_download_errors, request_result, request, spider)

    def call_spider(self, result, request, spider):
        ## 回调爬虫模块

        result.request = request
        dfd = defer_result(result)
        ## 注册回调，如果回调未定义则调用爬虫模块的 parse 方法
        dfd.addCallbacks(request.callback or spider.parse, request.errback)
        return dfd.addCallback(iterate_spider_output)

    def handle_spider_error(self, _failure, request, response, spider):
        exc = _failure.value
        if isinstance(exc, CloseSpider):
            self.crawler.engine.close_spider(spider, exc.reason or 'cancelled')
            return
        logger.error(
            "Spider error processing %(request)s (referer: %(referer)s)",
            {'request': request, 'referer': referer_str(request)},
            exc_info=failure_to_exc_info(_failure),
            extra={'spider': spider}
        )
        self.signals.send_catch_log(
            signal=signals.spider_error,
            failure=_failure, response=response,
            spider=spider
        )
        self.crawler.stats.inc_value(
            "spider_exceptions/%s" % _failure.value.__class__.__name__,
            spider=spider
        )

    def handle_spider_output(self, result, request, response, spider):
        ## 处理爬虫输出结果

        if not result:
            return defer_succeed(None)
        it = iter_errback(result, self.handle_spider_error, request, response, spider)
        dfd = parallel(it, self.concurrent_items,
            self._process_spidermw_output, request, response, spider)
        return dfd

    def _process_spidermw_output(self, output, request, response, spider):
        """Process each Request/Item (given in the output parameter) returned
        from the given spider
        """
        ## 处理 spider 模块返回的每一个 Request/Item

        if isinstance(output, Request):
            ## 如果结果是 Request，则通过引擎交给调度器入请求队列
            self.crawler.engine.crawl(request=output, spider=spider)
        elif isinstance(output, (BaseItem, dict)):
            ## 如果结果是 BaseItem/dict

            self.slot.itemproc_size += 1
            ## 调用 pipeline 管理器，依次执行 process_item
            dfd = self.itemproc.process_item(output, spider)
            dfd.addBoth(self._itemproc_finished, output, response, spider)
            return dfd
        elif output is None:
            pass
        else:
            typename = type(output).__name__
            logger.error('Spider must return Request, BaseItem, dict or None, '
                         'got %(typename)r in %(request)s',
                         {'request': request, 'typename': typename},
                         extra={'spider': spider})

    def _log_download_errors(self, spider_failure, download_failure, request, spider):
        """Log and silence errors that come from the engine (typically download
        errors that got propagated thru here)
        """
        if (isinstance(download_failure, Failure) and
                not download_failure.check(IgnoreRequest)):
            if download_failure.frames:
                logger.error('Error downloading %(request)s',
                             {'request': request},
                             exc_info=failure_to_exc_info(download_failure),
                             extra={'spider': spider})
            else:
                errmsg = download_failure.getErrorMessage()
                if errmsg:
                    logger.error('Error downloading %(request)s: %(errmsg)s',
                                 {'request': request, 'errmsg': errmsg},
                                 extra={'spider': spider})

        if spider_failure is not download_failure:
            return spider_failure

    def _itemproc_finished(self, output, item, response, spider):
        """ItemProcessor finished for the given ``item`` and returned ``output``
        """
        self.slot.itemproc_size -= 1
        if isinstance(output, Failure):
            ex = output.value
            ## 如果在 pipeline 处理中抛 DropItem 异常，则忽略处理结果
            ## 从这里可以看到，如果想在 Pipeline 中丢弃某个结果，直接抛出 DropItem 异常即可
            ## scrapy 会进行相应的处理
            if isinstance(ex, DropItem):
                logkws = self.logformatter.dropped(item, ex, response, spider)
                logger.log(*logformatter_adapter(logkws), extra={'spider': spider})
                return self.signals.send_catch_log_deferred(
                    signal=signals.item_dropped, item=item, response=response,
                    spider=spider, exception=output.value)
            else:
                logger.error('Error processing %(item)s', {'item': item},
                             exc_info=failure_to_exc_info(output),
                             extra={'spider': spider})
                return self.signals.send_catch_log_deferred(
                    signal=signals.item_error, item=item, response=response,
                    spider=spider, failure=output)
        else:
            logkws = self.logformatter.scraped(output, response, spider)
            logger.log(*logformatter_adapter(logkws), extra={'spider': spider})
            return self.signals.send_catch_log_deferred(
                signal=signals.item_scraped, item=output, response=response,
                spider=spider)

