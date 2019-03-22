"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
import logging
from time import time

from twisted.internet import defer, task
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.scraper import Scraper
from scrapy.exceptions import DontCloseSpider
from scrapy.http import Response, Request
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import CallLaterOnce
from scrapy.utils.log import logformatter_adapter, failure_to_exc_info

logger = logging.getLogger(__name__)


class Slot(object):

    def __init__(self, start_requests, close_if_idle, nextcall, scheduler):
        self.closing = False
        self.inprogress = set() # requests in progress
        self.start_requests = iter(start_requests)
        self.close_if_idle = close_if_idle
        self.nextcall = nextcall
        self.scheduler = scheduler
        self.heartbeat = task.LoopingCall(nextcall.schedule)

    def add_request(self, request):
        self.inprogress.add(request)

    def remove_request(self, request):
        self.inprogress.remove(request)
        self._maybe_fire_closing()

    def close(self):
        self.closing = defer.Deferred()
        self._maybe_fire_closing()
        return self.closing

    def _maybe_fire_closing(self):
        if self.closing and not self.inprogress:
            if self.nextcall:
                self.nextcall.cancel()
                if self.heartbeat.running:
                    self.heartbeat.stop()
            self.closing.callback(None)


class ExecutionEngine(object):

    def __init__(self, crawler, spider_closed_callback):
        ## 将爬虫实例存储在执行引擎实例中
        self.crawler = crawler
        ## 将爬虫实例所对应的配置也存储在执行引擎实例中
        self.settings = crawler.settings
        ## 信号
        self.signals = crawler.signals
        ## 日志格式化器
        self.logformatter = crawler.logformatter
        self.slot = None
        self.spider = None
        ## 是否正在运行
        self.running = False
        ## 是否已暂停执行
        self.paused = False
        ## 从配置文件中加载调度器类
        self.scheduler_cls = load_object(self.settings['SCHEDULER'])
        ## 从配置文件中加载下载器类
        downloader_cls = load_object(self.settings['DOWNLOADER'])
        ## 实例化下载器
        self.downloader = downloader_cls(crawler)
        ## 实例化 scraper，它是引擎连接爬虫类（Spider）和管道类（Pipeline）的桥梁
        self.scraper = Scraper(crawler)
        ## 指定爬虫关闭的回调函数
        self._spider_closed_callback = spider_closed_callback

    @defer.inlineCallbacks
    def start(self):
        """Start the execution engine"""
        assert not self.running, "Engine already running"
        self.start_time = time()
        yield self.signals.send_catch_log_deferred(signal=signals.engine_started)
        self.running = True
        self._closewait = defer.Deferred()
        yield self._closewait

    def stop(self):
        """Stop the execution engine gracefully"""
        assert self.running, "Engine not running"
        self.running = False
        dfd = self._close_all_spiders()
        return dfd.addBoth(lambda _: self._finish_stopping_engine())

    def close(self):
        """Close the execution engine gracefully.

        If it has already been started, stop it. In all cases, close all spiders
        and the downloader.
        """
        if self.running:
            # Will also close spiders and downloader
            return self.stop()
        elif self.open_spiders:
            # Will also close downloader
            return self._close_all_spiders()
        else:
            return defer.succeed(self.downloader.close())

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def _next_request(self, spider):
        ## 该方法会被循环调度

        slot = self.slot
        if not slot:
            return

        if self.paused:
            return

        ## 是否撤销
        while not self._needs_backout(spider):
            ## 从 scheduler 中获取下一个 request
            ## 注意：第一次获取时，是没有的，也就是会 break 出来
            ## 从而执行下面的逻辑
            if not self._next_request_from_scheduler(spider):
                break

        ## 如果 start_requests 有数据且不需要撤销
        if slot.start_requests and not self._needs_backout(spider):
            try:
                ## 获取下一个种子请求
                request = next(slot.start_requests)
            except StopIteration:
                slot.start_requests = None
            except Exception:
                slot.start_requests = None
                logger.error('Error while obtaining start requests',
                             exc_info=True, extra={'spider': spider})
            else:
                ## 调用 crawl， 实际是把 request 放入 scheduler 的队列中
                self.crawl(request, spider)

        ## 如果爬虫是空闲的则关闭爬虫
        if self.spider_is_idle(spider) and slot.close_if_idle:
            self._spider_idle(spider)

    def _needs_backout(self, spider):
        ## 是否需要撤销，取决于 4 个条件
        ## 1. engine 是否在运行
        ## 2. slot 是否关闭
        ## 3. 下载器网络下载是否超过预设
        ## 4. scraper 处理输出是否超过预设

        slot = self.slot
        return not self.running \
            or slot.closing \
            or self.downloader.needs_backout() \
            or self.scraper.slot.needs_backout()

    def _next_request_from_scheduler(self, spider):
        slot = self.slot
        ## 从调度器中获取下一个请求
        request = slot.scheduler.next_request()
        if not request:
            return
        ## 下载
        d = self._download(request, spider)

        ## 为下载结果添加回调，下载结果可能是 Request、Response、Failure

        d.addBoth(self._handle_downloader_output, request, spider)
        d.addErrback(lambda f: logger.info('Error while handling downloader output',
                                           exc_info=failure_to_exc_info(f),
                                           extra={'spider': spider}))
        d.addBoth(lambda _: slot.remove_request(request))
        d.addErrback(lambda f: logger.info('Error while removing request from slot',
                                           exc_info=failure_to_exc_info(f),
                                           extra={'spider': spider}))
        d.addBoth(lambda _: slot.nextcall.schedule())
        d.addErrback(lambda f: logger.info('Error while scheduling new request',
                                           exc_info=failure_to_exc_info(f),
                                           extra={'spider': spider}))
        return d

    def _handle_downloader_output(self, response, request, spider):
        ## 下载结果 response 必须是 Request、Response、Failure 之一
        assert isinstance(response, (Request, Response, Failure)), response
        # downloader middleware can return requests (for example, redirects)
        ## 如果下载结果是 Request，则再次调用 crawl，执行 Scheduler 的入队逻辑
        if isinstance(response, Request):
            self.crawl(response, spider)
            return
        # response is a Response or Failure
        ## 如果下载结果是 Response 或 Failure，则交给 scrapy 的 enqueue_scrape 方法进一步处理
        ## 主要是与 spiders 和 pipelines 交互
        d = self.scraper.enqueue_scrape(response, request, spider)
        d.addErrback(lambda f: logger.error('Error while enqueuing downloader output',
                                            exc_info=failure_to_exc_info(f),
                                            extra={'spider': spider}))
        return d

    def spider_is_idle(self, spider):
        if not self.scraper.slot.is_idle():
            # scraper is not idle
            return False

        if self.downloader.active:
            # downloader has pending requests
            return False

        if self.slot.start_requests is not None:
            # not all start requests are handled
            return False

        if self.slot.scheduler.has_pending_requests():
            # scheduler has pending requests
            return False

        return True

    @property
    def open_spiders(self):
        return [self.spider] if self.spider else []

    def has_capacity(self):
        """Does the engine have capacity to handle more spiders"""
        return not bool(self.slot)

    def crawl(self, request, spider):
        assert spider in self.open_spiders, \
            "Spider %r not opened when crawling: %s" % (spider.name, request)
        ## 将请求放入调度器队列
        self.schedule(request, spider)
        ## 调用 nextcall 的 schedule 方法，进行下一次调度
        self.slot.nextcall.schedule()

    def schedule(self, request, spider):
        self.signals.send_catch_log(signal=signals.request_scheduled,
                request=request, spider=spider)
        ## 调用调度器的 enqueue_request 方法，将请求放入调度器队列
        if not self.slot.scheduler.enqueue_request(request):
            self.signals.send_catch_log(signal=signals.request_dropped,
                                        request=request, spider=spider)

    def download(self, request, spider):
        d = self._download(request, spider)
        d.addBoth(self._downloaded, self.slot, request, spider)
        return d

    def _downloaded(self, response, slot, request, spider):
        slot.remove_request(request)
        return self.download(response, spider) \
                if isinstance(response, Request) else response

    def _download(self, request, spider):
        slot = self.slot
        slot.add_request(request)
        ## 下载成功的回调，返回处理过的响应
        def _on_success(response):
            assert isinstance(response, (Response, Request))
            if isinstance(response, Response):
                ## 将请求放入响应对象的 request 属性中
                response.request = request # tie request to response received
                logkws = self.logformatter.crawled(request, response, spider)
                logger.log(*logformatter_adapter(logkws), extra={'spider': spider})
                self.signals.send_catch_log(signal=signals.response_received, \
                    response=response, request=request, spider=spider)
            return response

        ## 下载完成的回调，继续下一次调度
        def _on_complete(_):
            slot.nextcall.schedule()
            return _

        ## 调用下载器进行下载
        dwld = self.downloader.fetch(request, spider)
        ## 注册下载成功的回调
        dwld.addCallbacks(_on_success)
        ## 注册下载完成的回调
        dwld.addBoth(_on_complete)
        return dwld

    @defer.inlineCallbacks
    def open_spider(self, spider, start_requests=(), close_if_idle=True):
        assert self.has_capacity(), "No free spider slot when opening %r" % \
            spider.name
        logger.info("Spider opened", extra={'spider': spider})
        ## 注册 _next_request 调度方法，循环调度
        nextcall = CallLaterOnce(self._next_request, spider)
        ## 初始化调度器类
        scheduler = self.scheduler_cls.from_crawler(self.crawler)
        ## 调用爬虫中间件的 process_start_requests 方法处理种子请求
        ## 可以定义多个爬虫中间件，每个类都重写该方法，爬虫在调度之前会分别调用你定义好的
        ## 爬虫中间件，来分别处理起始请求，功能独立而且维护起来更加清晰
        start_requests = yield self.scraper.spidermw.process_start_requests(start_requests, spider)
        ## 封装 slot 对象
        slot = Slot(start_requests, close_if_idle, nextcall, scheduler)
        self.slot = slot
        self.spider = spider
        ## 调用调度器的 open 方法
        yield scheduler.open(spider)
        ## 调用 scraper 的 open_spider 方法
        yield self.scraper.open_spider(spider)
        self.crawler.stats.open_spider(spider)
        yield self.signals.send_catch_log_deferred(signals.spider_opened, spider=spider)
        ## 发起调度
        slot.nextcall.schedule()
        slot.heartbeat.start(5)

    def _spider_idle(self, spider):
        """Called when a spider gets idle. This function is called when there
        are no remaining pages to download or schedule. It can be called
        multiple times. If some extension raises a DontCloseSpider exception
        (in the spider_idle signal handler) the spider is not closed until the
        next loop and this function is guaranteed to be called (at least) once
        again for this spider.
        """
        res = self.signals.send_catch_log(signal=signals.spider_idle, \
            spider=spider, dont_log=DontCloseSpider)
        if any(isinstance(x, Failure) and isinstance(x.value, DontCloseSpider) \
                for _, x in res):
            return

        if self.spider_is_idle(spider):
            self.close_spider(spider, reason='finished')

    def close_spider(self, spider, reason='cancelled'):
        """Close (cancel) spider and clear all its outstanding requests"""

        slot = self.slot
        if slot.closing:
            return slot.closing
        logger.info("Closing spider (%(reason)s)",
                    {'reason': reason},
                    extra={'spider': spider})

        dfd = slot.close()

        def log_failure(msg):
            def errback(failure):
                logger.error(
                    msg,
                    exc_info=failure_to_exc_info(failure),
                    extra={'spider': spider}
                )
            return errback

        dfd.addBoth(lambda _: self.downloader.close())
        dfd.addErrback(log_failure('Downloader close failure'))

        dfd.addBoth(lambda _: self.scraper.close_spider(spider))
        dfd.addErrback(log_failure('Scraper close failure'))

        dfd.addBoth(lambda _: slot.scheduler.close(reason))
        dfd.addErrback(log_failure('Scheduler close failure'))

        dfd.addBoth(lambda _: self.signals.send_catch_log_deferred(
            signal=signals.spider_closed, spider=spider, reason=reason))
        dfd.addErrback(log_failure('Error while sending spider_close signal'))

        dfd.addBoth(lambda _: self.crawler.stats.close_spider(spider, reason=reason))
        dfd.addErrback(log_failure('Stats close failure'))

        dfd.addBoth(lambda _: logger.info("Spider closed (%(reason)s)",
                                          {'reason': reason},
                                          extra={'spider': spider}))

        dfd.addBoth(lambda _: setattr(self, 'slot', None))
        dfd.addErrback(log_failure('Error while unassigning slot'))

        dfd.addBoth(lambda _: setattr(self, 'spider', None))
        dfd.addErrback(log_failure('Error while unassigning spider'))

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))

        return dfd

    def _close_all_spiders(self):
        dfds = [self.close_spider(s, reason='shutdown') for s in self.open_spiders]
        dlist = defer.DeferredList(dfds)
        return dlist

    @defer.inlineCallbacks
    def _finish_stopping_engine(self):
        yield self.signals.send_catch_log_deferred(signal=signals.engine_stopped)
        self._closewait.callback(None)
