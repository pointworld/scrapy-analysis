from __future__ import absolute_import
import random
import warnings
from time import time
from datetime import datetime
from collections import deque

import six
from twisted.internet import reactor, defer, task

from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.httpobj import urlparse_cached
from scrapy.resolver import dnscache
from scrapy import signals
from .middleware import DownloaderMiddlewareManager
from .handlers import DownloadHandlers


class Slot(object):
    """Downloader slot"""

    def __init__(self, concurrency, delay, randomize_delay):
        self.concurrency = concurrency
        self.delay = delay
        self.randomize_delay = randomize_delay

        self.active = set()
        self.queue = deque()
        self.transferring = set()
        self.lastseen = 0
        self.latercall = None

    def free_transfer_slots(self):
        return self.concurrency - len(self.transferring)

    def download_delay(self):
        if self.randomize_delay:
            return random.uniform(0.5 * self.delay, 1.5 * self.delay)
        return self.delay

    def close(self):
        if self.latercall and self.latercall.active():
            self.latercall.cancel()

    def __repr__(self):
        cls_name = self.__class__.__name__
        return "%s(concurrency=%r, delay=%0.2f, randomize_delay=%r)" % (
            cls_name, self.concurrency, self.delay, self.randomize_delay)

    def __str__(self):
        return (
            "<downloader.Slot concurrency=%r delay=%0.2f randomize_delay=%r "
            "len(active)=%d len(queue)=%d len(transferring)=%d lastseen=%s>" % (
                self.concurrency, self.delay, self.randomize_delay,
                len(self.active), len(self.queue), len(self.transferring),
                datetime.fromtimestamp(self.lastseen).isoformat()
            )
        )


def _get_concurrency_delay(concurrency, spider, settings):
    delay = settings.getfloat('DOWNLOAD_DELAY')
    if hasattr(spider, 'DOWNLOAD_DELAY'):
        warnings.warn("%s.DOWNLOAD_DELAY attribute is deprecated, use %s.download_delay instead" %
                      (type(spider).__name__, type(spider).__name__))
        delay = spider.DOWNLOAD_DELAY
    if hasattr(spider, 'download_delay'):
        delay = spider.download_delay

    if hasattr(spider, 'max_concurrent_requests'):
        concurrency = spider.max_concurrent_requests

    return concurrency, delay


class Downloader(object):
    ## 下载器：管理各种资源对应的下载器，在真正发起网络请求时，选取对应的下载器进行资源下载

    def __init__(self, crawler):
        ## 从爬虫对象中获取配置对象
        self.settings = crawler.settings
        ## 信号
        self.signals = crawler.signals
        self.slots = {}
        self.active = set()
        ## 初始化下载处理器
        self.handlers = DownloadHandlers(crawler)
        ## 从配置中获取设置的请求并发数
        self.total_concurrency = self.settings.getint('CONCURRENT_REQUESTS')
        ## 同一域名的请求并发数
        self.domain_concurrency = self.settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        ## 同一 IP 的请求并发数
        self.ip_concurrency = self.settings.getint('CONCURRENT_REQUESTS_PER_IP')
        ## 随机延迟下载时间
        self.randomize_delay = self.settings.getbool('RANDOMIZE_DOWNLOAD_DELAY')
        ## 初始化下载器中间件管理器
        self.middleware = DownloaderMiddlewareManager.from_crawler(crawler)
        self._slot_gc_loop = task.LoopingCall(self._slot_gc)
        self._slot_gc_loop.start(60)

    def fetch(self, request, spider):
        def _deactivate(response):
            ## 下载完成后删除此记录
            self.active.remove(request)
            return response

        ## 下载完成前记录处理中的请求
        self.active.add(request)
        ## 调用下载器中间件的 download 方法，并注册下载成功的回调 self._enqueue_request
        dfd = self.middleware.download(self._enqueue_request, request, spider)
        ## 注册结束回调
        return dfd.addBoth(_deactivate)

    def needs_backout(self):
        return len(self.active) >= self.total_concurrency

    def _get_slot(self, request, spider):
        key = self._get_slot_key(request, spider)
        if key not in self.slots:
            conc = self.ip_concurrency if self.ip_concurrency else self.domain_concurrency
            conc, delay = _get_concurrency_delay(conc, spider, self.settings)
            self.slots[key] = Slot(conc, delay, self.randomize_delay)

        return key, self.slots[key]

    def _get_slot_key(self, request, spider):
        if 'download_slot' in request.meta:
            return request.meta['download_slot']

        key = urlparse_cached(request).hostname or ''
        if self.ip_concurrency:
            key = dnscache.get(key, key)

        return key

    def _enqueue_request(self, request, spider):
        ## 将 request 加入下载请求队列

        key, slot = self._get_slot(request, spider)
        request.meta['download_slot'] = key

        def _deactivate(response):
            slot.active.remove(request)
            return response

        slot.active.add(request)
        self.signals.send_catch_log(signal=signals.request_reached_downloader,
                                    request=request,
                                    spider=spider)
        deferred = defer.Deferred().addBoth(_deactivate)
        ## 下载队列
        slot.queue.append((request, deferred))
        ## 处理下载队列
        self._process_queue(spider, slot)
        return deferred

    def _process_queue(self, spider, slot):
        if slot.latercall and slot.latercall.active():
            return

        # Delay queue processing if a download_delay is configured
        now = time()
        delay = slot.download_delay()
        if delay:
            penalty = delay - now + slot.lastseen
            if penalty > 0:
                slot.latercall = reactor.callLater(penalty, self._process_queue, spider, slot)
                return

        # Process enqueued requests if there are free slots to transfer for this slot
        ## 处理下载队列
        while slot.queue and slot.free_transfer_slots() > 0:
            slot.lastseen = now
            ## 从下载队列中取出下载请求
            request, deferred = slot.queue.popleft()
            ## 开始下载
            dfd = self._download(slot, request, spider)
            dfd.chainDeferred(deferred)
            # prevent burst if inter-request delays were configured
            ## 延迟
            if delay:
                self._process_queue(spider, slot)
                break

    def _download(self, slot, request, spider):
        # The order is very important for the following deferreds. Do not change!

        # 1. Create the download deferred
        ## 创建一个下载延迟，参数 self.handlers.download_request 是真正发起下载请求的方法
        dfd = mustbe_deferred(self.handlers.download_request, request, spider)

        # 2. Notify response_downloaded listeners about the recent download
        # before querying queue for next request
        def _downloaded(response):
            self.signals.send_catch_log(signal=signals.response_downloaded,
                                        response=response,
                                        request=request,
                                        spider=spider)
            return response
        ## 注册回调
        dfd.addCallback(_downloaded)

        # 3. After response arrives,  remove the request from transferring
        # state to free up the transferring slot so it can be used by the
        # following requests (perhaps those which came from the downloader
        # middleware itself)
        slot.transferring.add(request)

        def finish_transferring(_):
            slot.transferring.remove(request)
            self._process_queue(spider, slot)
            return _

        return dfd.addBoth(finish_transferring)

    def close(self):
        self._slot_gc_loop.stop()
        for slot in six.itervalues(self.slots):
            slot.close()

    def _slot_gc(self, age=60):
        mintime = time() - age
        for key, slot in list(self.slots.items()):
            if not slot.active and slot.lastseen + slot.delay < mintime:
                self.slots.pop(key).close()
