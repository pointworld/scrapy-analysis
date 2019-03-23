import six
import signal
import logging
import warnings

import sys
from twisted.internet import reactor, defer
from zope.interface.verify import verifyClass, DoesNotImplement

from scrapy import Spider
from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.interfaces import ISpiderLoader
from scrapy.extension import ExtensionManager
from scrapy.settings import overridden_settings, Settings
from scrapy.signalmanager import SignalManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy.utils.log import (
    LogCounterHandler, configure_logging, log_scrapy_info,
    get_scrapy_root_handler, install_scrapy_root_handler)
from scrapy import signals

logger = logging.getLogger(__name__)


class Crawler(object):

    def __init__(self, spidercls, settings=None):
        ## crawler 对象必须用 scrapy.spiders.Spider 的子类和一个 scrapy.settings.Settings
        ## 对象来实例化

        if isinstance(spidercls, Spider):
            raise ValueError(
                'The spidercls argument must be a class, not an object')

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)

        ## 自定义爬虫类
        self.spidercls = spidercls
        ## crawler 的配置管理器，用来为插件和中间件提供访问该 crawler 的 Scrapy 配置的入口
        self.settings = settings.copy()
        ## 根据自定义爬虫类中的可能定义的 custom_settigns 属性更新配置
        ## 优先级为 spider
        self.spidercls.update_settings(self.settings)

        ## 这里得到的只是被覆盖过的配置项，并将其转换为字典
        d = dict(overridden_settings(self.settings))
        logger.info("Overridden settings: %(settings)r", {'settings': d})

        ## crawler 的信号管理器，被插件和中间件用来将它们自身集成到 Scrapy 功能中
        self.signals = SignalManager(self)
        ## crawler 的 stats 收集器，用来从插件和中间件中记录它们的行为和访问其他插件收集到的数据
        self.stats = load_object(self.settings['STATS_CLASS'])(self)

        ## 用于对爬虫运行过程中产生的日志的级别数量，进行统计
        handler = LogCounterHandler(self, level=self.settings.get('LOG_LEVEL'))
        logging.root.addHandler(handler)
        if get_scrapy_root_handler() is not None:
            # scrapy root handler already installed: update it with new settings
            install_scrapy_root_handler(self.settings)
        # lambda is assigned to Crawler attribute because this way it is not
        # garbage collected after leaving __init__ scope
        self.__remove_handler = lambda: logging.root.removeHandler(handler)
        ## 为 engine_stopped 信号注册 __remove_handler 处理器
        ## 当产生引擎停止信号时，将会由 __remove_handler 处理器进行处理
        self.signals.connect(self.__remove_handler, signals.engine_stopped)

        lf_cls = load_object(self.settings['LOG_FORMATTER'])
        ## 初始化日志格式化器实例
        self.logformatter = lf_cls.from_crawler(self)
        ## 用来追踪可用插件的插件管理器
        self.extensions = ExtensionManager.from_crawler(self)

        self.settings.freeze()
        ## 标志爬虫运行状态
        self.crawling = False
        ## 当前正在爬取的 spider
        self.spider = None
        ## 执行引擎，用来协调调度器、下载器、spiders 之间的爬取逻辑
        self.engine = None

    @property
    def spiders(self):
        if not hasattr(self, '_spiders'):
            warnings.warn("Crawler.spiders is deprecated, use "
                          "CrawlerRunner.spider_loader or instantiate "
                          "scrapy.spiderloader.SpiderLoader with your "
                          "settings.",
                          category=ScrapyDeprecationWarning, stacklevel=2)
            self._spiders = _get_spider_loader(self.settings.frozencopy())
        return self._spiders

    @defer.inlineCallbacks
    def crawl(self, *args, **kwargs):
        ## Starts the crawler by instantiating its spider class with the given
        ## args and kwargs arguments, while setting the execution engine in motion.

        assert not self.crawling, "Crawling already taking place"
        ## 将爬虫运行状态置为 True
        self.crawling = True

        try:
            ## 创建爬虫实例
            self.spider = self._create_spider(*args, **kwargs)
            ## 创建引擎
            self.engine = self._create_engine()
            ## 调用爬虫实例的 start_requests 方法，获取种子 URL（请求对象）
            start_requests = iter(self.spider.start_requests())
            ## 执行引擎的 open_spider 方法，传入爬虫实例和初始请求对象，交由引擎调度
            yield self.engine.open_spider(self.spider, start_requests)
            yield defer.maybeDeferred(self.engine.start)
        except Exception:
            # In Python 2 reraising an exception after yield discards
            # the original traceback (see https://bugs.python.org/issue7563),
            # so sys.exc_info() workaround is used.
            # This workaround also works in Python 3, but it is not needed,
            # and it is slower, so in Python 3 we use native `raise`.
            if six.PY2:
                exc_info = sys.exc_info()

            self.crawling = False
            if self.engine is not None:
                yield self.engine.close()

            if six.PY2:
                six.reraise(*exc_info)
            raise

    def _create_spider(self, *args, **kwargs):
        ## 调用之定义爬虫类的 from_crawler 方法实例化爬虫类
        return self.spidercls.from_crawler(self, *args, **kwargs)

    def _create_engine(self):
        ## 返回一个执行引擎类的实例
        return ExecutionEngine(self, lambda _: self.stop())

    @defer.inlineCallbacks
    def stop(self):
        if self.crawling:
            self.crawling = False
            yield defer.maybeDeferred(self.engine.stop)


class CrawlerRunner(object):
    """
    This is a convenient helper class that keeps track of, manages and runs
    crawlers inside an already setup Twisted `reactor`_.

    The CrawlerRunner object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.
    """
    ## 这是一个帮助器类，用来在一个已经建立好的 Twisted reactor 中，追踪、管理和运行爬虫

    ## 由 crawl 方法启动的爬虫集合，该值只能读取
    crawlers = property(
        lambda self: self._crawlers,
        doc="Set of :class:`crawlers <scrapy.crawler.Crawler>` started by "
            ":meth:`crawl` and managed by this class."
    )

    def __init__(self, settings=None):
        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        ## 配置
        self.settings = settings
        ## 获取爬虫加载器，用来根据爬虫名加载爬虫类
        self.spider_loader = _get_spider_loader(settings)
        ## 爬虫集合
        self._crawlers = set()
        self._active = set()
        self.bootstrap_failed = False

    @property
    def spiders(self):
        warnings.warn("CrawlerRunner.spiders attribute is renamed to "
                      "CrawlerRunner.spider_loader.",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        return self.spider_loader

    def crawl(self, crawler_or_spidercls, *args, **kwargs):
        """
        Run a crawler with the provided arguments.

        It will call the given Crawler's :meth:`~Crawler.crawl` method, while
        keeping track of it so it can be stopped later.

        If ``crawler_or_spidercls`` isn't a :class:`~scrapy.crawler.Crawler`
        instance, this method will try to create one using this parameter as
        the spider class given to it.

        Returns a deferred that is fired when the crawling is finished.

        :param crawler_or_spidercls: already created crawler, or a spider class
            or spider's name inside the project to create it
        :type crawler_or_spidercls: :class:`~scrapy.crawler.Crawler` instance,
            :class:`~scrapy.spiders.Spider` subclass or string

        :param list args: arguments to initialize the spider

        :param dict kwargs: keyword arguments to initialize the spider
        """
        ## 用给定的参数运行一个 crawler
        ## 会调用 Crawler 中的 crawl 方法，同时追踪它，以便之后停止它

        if isinstance(crawler_or_spidercls, Spider):
            raise ValueError(
                'The crawler_or_spidercls argument cannot be a spider object, '
                'it must be a spider class (or a Crawler object)')
        ## 创建 crawler 实例
        crawler = self.create_crawler(crawler_or_spidercls)
        return self._crawl(crawler, *args, **kwargs)

    def _crawl(self, crawler, *args, **kwargs):
        ## 向 crawlers 集合中添加 crawler
        self.crawlers.add(crawler)
        ## 调用 Crawler 类中的 crawl 方法
        d = crawler.crawl(*args, **kwargs)
        self._active.add(d)

        def _done(result):
            ## 从 crawlers 集合中丢弃掉一个 crawler
            self.crawlers.discard(crawler)
            self._active.discard(d)
            self.bootstrap_failed |= not getattr(crawler, 'spider', None)
            return result

        return d.addBoth(_done)

    def create_crawler(self, crawler_or_spidercls):
        """
        Return a :class:`~scrapy.crawler.Crawler` object.

        * If ``crawler_or_spidercls`` is a Crawler, it is returned as-is.
        * If ``crawler_or_spidercls`` is a Spider subclass, a new Crawler
          is constructed for it.
        * If ``crawler_or_spidercls`` is a string, this function finds
          a spider with this name in a Scrapy project (using spider loader),
          then creates a Crawler instance for it.
        """
        ## 返回一个 crawler 实例

        if isinstance(crawler_or_spidercls, Spider):
            raise ValueError(
                'The crawler_or_spidercls argument cannot be a spider object, '
                'it must be a spider class (or a Crawler object)')
        if isinstance(crawler_or_spidercls, Crawler):
            return crawler_or_spidercls
        return self._create_crawler(crawler_or_spidercls)

    def _create_crawler(self, spidercls):
        ## 如果参数 spidercls 是字符串，则从 spider_loader 中加载这个 Spider 子类
        if isinstance(spidercls, six.string_types):
            spidercls = self.spider_loader.load(spidercls)
        ## 根据该 spidercls 和配置创建一个 Crawler 实例
        return Crawler(spidercls, self.settings)

    def stop(self):
        """
        Stops simultaneously all the crawling jobs taking place.

        Returns a deferred that is fired when they all have ended.
        """
        ## 同时停止所有正在运行的爬取任务
        return defer.DeferredList([c.stop() for c in list(self.crawlers)])

    @defer.inlineCallbacks
    def join(self):
        """
        join()

        Returns a deferred that is fired when all managed :attr:`crawlers` have
        completed their executions.
        """
        while self._active:
            yield defer.DeferredList(self._active)


class CrawlerProcess(CrawlerRunner):
    """
    A class to run multiple scrapy crawlers in a process simultaneously.

    This class extends :class:`~scrapy.crawler.CrawlerRunner` by adding support
    for starting a Twisted `reactor`_ and handling shutdown signals, like the
    keyboard interrupt command Ctrl-C. It also configures top-level logging.

    This utility should be a better fit than
    :class:`~scrapy.crawler.CrawlerRunner` if you aren't running another
    Twisted `reactor`_ within your application.

    The CrawlerProcess object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    :param install_root_handler: whether to install root logging handler
        (default: True)

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.
    """
    ## 在一个进程中同时运行多个 crawler
    ## 该类继承自 CrawlerRunner，能够支持启动一个 Twisted reactor 和处理 shutdown 信号
    ## 同时也配置了 logging 服务

    def __init__(self, settings=None, install_root_handler=True):
        ## 父类初始化
        super(CrawlerProcess, self).__init__(settings)
        ## 处理 shutdown 信号
        install_shutdown_handlers(self._signal_shutdown)
        ## 为 Scrapy 配置默认的日志服务
        configure_logging(self.settings, install_root_handler)
        ## 输出 scrapy 的相关信息（启动状态，版本...）
        log_scrapy_info(self.settings)

    def _signal_shutdown(self, signum, _):
        ## shutdown 信号的处理器

        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        logger.info("Received %(signame)s, shutting down gracefully. Send again to force ",
                    {'signame': signame})
        reactor.callFromThread(self._graceful_stop_reactor)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        logger.info('Received %(signame)s twice, forcing unclean shutdown',
                    {'signame': signame})
        reactor.callFromThread(self._stop_reactor)

    def start(self, stop_after_crawl=True):
        """
        This method starts a Twisted `reactor`_, adjusts its pool size to
        :setting:`REACTOR_THREADPOOL_MAXSIZE`, and installs a DNS cache based
        on :setting:`DNSCACHE_ENABLED` and :setting:`DNSCACHE_SIZE`.

        If ``stop_after_crawl`` is True, the reactor will be stopped after all
        crawlers have finished, using :meth:`join`.

        :param boolean stop_after_crawl: stop or not the reactor when all
            crawlers have finished
        """
        if stop_after_crawl:
            d = self.join()
            # Don't start the reactor if the deferreds are already fired
            if d.called:
                return
            d.addBoth(self._stop_reactor)

        ## 为 reactor 安装解析器
        ## 是 Twisted 模块的事件管理器，只要把需要执行的事件方法注册到 reactor 中，然后
        ## 调用它的 run 方法，它就会帮你执行注册好的事件方法，如果遇到网络 IO 等待，它会
        ## 自动帮你切换可执行的事件方法，非常高效
        reactor.installResolver(self._get_dns_resolver())
        ## 获取线程池
        tp = reactor.getThreadPool()
        ## 调整 reactor 的线程池大小（通过修改 REACTOR_THREADPOOL_MAXSIZE 调整）
        tp.adjustPoolsize(maxthreads=self.settings.getint('REACTOR_THREADPOOL_MAXSIZE'))
        ## 添加系统事件触发器
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        ## 开始执行
        reactor.run(installSignalHandlers=False)  # blocking call

    def _get_dns_resolver(self):
        if self.settings.getbool('DNSCACHE_ENABLED'):
            cache_size = self.settings.getint('DNSCACHE_SIZE')
        else:
            cache_size = 0
        return CachingThreadedResolver(
            reactor=reactor,
            cache_size=cache_size,
            timeout=self.settings.getfloat('DNS_TIMEOUT')
        )

    def _graceful_stop_reactor(self):
        d = self.stop()
        d.addBoth(self._stop_reactor)
        return d

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError:  # raised if already stopped or in shutdown stage
            pass


def _get_spider_loader(settings):
    """ Get SpiderLoader instance from settings """
    ## 爬虫加载器会加载所有的爬虫脚本，最后生成一个 { spider_name: spider_cls, ...} 的字典

    if settings.get('SPIDER_MANAGER_CLASS'):
        warnings.warn(
            'SPIDER_MANAGER_CLASS option is deprecated. '
            'Please use SPIDER_LOADER_CLASS.',
            category=ScrapyDeprecationWarning, stacklevel=2
        )
    ## 爬虫加载器类的路径
    cls_path = settings.get('SPIDER_MANAGER_CLASS',
                            settings.get('SPIDER_LOADER_CLASS'))
    ## 根据路径获取爬虫加载器类
    loader_cls = load_object(cls_path)
    try:
        verifyClass(ISpiderLoader, loader_cls)
    except DoesNotImplement:
        warnings.warn(
            'SPIDER_LOADER_CLASS (previously named SPIDER_MANAGER_CLASS) does '
            'not fully implement scrapy.interfaces.ISpiderLoader interface. '
            'Please add all missing methods to avoid unexpected runtime errors.',
            category=ScrapyDeprecationWarning, stacklevel=2
        )
    ## 用配置实例化爬虫加载器类并返回
    return loader_cls.from_settings(settings.frozencopy())
