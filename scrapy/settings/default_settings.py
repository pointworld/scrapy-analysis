"""
This module contains the default values for all settings used by Scrapy.

For more information about these settings you can read the settings
documentation in docs/topics/settings.rst

Scrapy developers, if you add a setting here remember to:

* add it in alphabetical order
* group similar settings without leaving blank lines
* add its documentation to the available settings documentation
  (docs/topics/settings.rst)

"""

import sys
from importlib import import_module
from os.path import join, abspath, dirname

import six

AJAXCRAWL_ENABLED = False

AUTOTHROTTLE_ENABLED = False
AUTOTHROTTLE_DEBUG = False
AUTOTHROTTLE_MAX_DELAY = 60.0
AUTOTHROTTLE_START_DELAY = 5.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

## 项目名
BOT_NAME = 'scrapybot'

## 关闭爬虫的触发条件配置
CLOSESPIDER_TIMEOUT = 0
CLOSESPIDER_PAGECOUNT = 0
CLOSESPIDER_ITEMCOUNT = 0
CLOSESPIDER_ERRORCOUNT = 0

COMMANDS_MODULE = ''

COMPRESSION_ENABLED = True

## Item 处理器（管道）能处理的每个响应的 items 的最大并发量
CONCURRENT_ITEMS = 100

## Scrapy 下载器发起请求的最大并发量
CONCURRENT_REQUESTS = 16
## 任何一个域，所能发起请求的最大并发量
CONCURRENT_REQUESTS_PER_DOMAIN = 8
## 任何一个 IP，所能发起请求的最大并发量
CONCURRENT_REQUESTS_PER_IP = 0

COOKIES_ENABLED = True
COOKIES_DEBUG = False

## 在 Scrapy shell 中，用来实例化 items 的默认类
DEFAULT_ITEM_CLASS = 'scrapy.item.Item'

## Scrapy 发送 HTTP 请求时默认的请求头
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en',
}

## 对于每一个网站，所能允许爬取的最大深度，若值为 0，则表示没有限制
DEPTH_LIMIT = 0
DEPTH_STATS_VERBOSE = False
DEPTH_PRIORITY = 0

## 是否在内存中启用 DNS 缓存，加快 DNS 查询速度
DNSCACHE_ENABLED = True
## DNS 缓存的最大值
DNSCACHE_SIZE = 10000
## 处理 DNS 查询的超时时间（以秒为单位）
DNS_TIMEOUT = 60

## 下载延迟，下载器在下载同一网站的连续页面时，应该等待的时间
## 一般用来限制爬取速度，避免对服务器造成压力
DOWNLOAD_DELAY = 0

## 用户可自定义协议对应的下载处理器
DOWNLOAD_HANDLERS = {}
## 协议对应的默认下载处理器
DOWNLOAD_HANDLERS_BASE = {
    'data': 'scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler',
    'file': 'scrapy.core.downloader.handlers.file.FileDownloadHandler',
    'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    's3': 'scrapy.core.downloader.handlers.s3.S3DownloadHandler',
    'ftp': 'scrapy.core.downloader.handlers.ftp.FTPDownloadHandler',
}

## 在下载超时之前，下载器应该等待的事件
DOWNLOAD_TIMEOUT = 180      # 3mins

## 下载器能够下载的最大响应字节数
DOWNLOAD_MAXSIZE = 1024*1024*1024   # 1024m
## 当响应内容的大小超过某个值时，发出警告
DOWNLOAD_WARNSIZE = 32*1024*1024    # 32m

DOWNLOAD_FAIL_ON_DATALOSS = True

## 用于爬取的下载器
DOWNLOADER = 'scrapy.core.downloader.Downloader'

DOWNLOADER_HTTPCLIENTFACTORY = 'scrapy.core.downloader.webclient.ScrapyHTTPClientFactory'
DOWNLOADER_CLIENTCONTEXTFACTORY = 'scrapy.core.downloader.contextfactory.ScrapyClientContextFactory'
DOWNLOADER_CLIENT_TLS_METHOD = 'TLS' # Use highest TLS/SSL protocol version supported by the platform,
                                     # also allowing negotiation

## 下载器中间件
DOWNLOADER_MIDDLEWARES = {}

## 默认的下载器中间件
DOWNLOADER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': 100,
    'scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware': 300,
    'scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware': 350,
    'scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware': 400,
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': 500,
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 550,
    'scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware': 560,
    'scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware': 580,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 590,
    'scrapy.downloadermiddlewares.redirect.RedirectMiddleware': 600,
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700,
    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 750,
    'scrapy.downloadermiddlewares.stats.DownloaderStats': 850,
    'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware': 900,
    # Downloader side
}

DOWNLOADER_STATS = True

## 用于检测和过滤重复请求的类
DUPEFILTER_CLASS = 'scrapy.dupefilters.RFPDupeFilter'

## 当使用 edit 命令编辑 spiders 时，默认使用的编辑器
EDITOR = 'vi'
if sys.platform == 'win32':
    EDITOR = '%s -m idlelib.idle'

## 可用插件
EXTENSIONS = {}

## 默认可用的插件
EXTENSIONS_BASE = {
    'scrapy.extensions.corestats.CoreStats': 0,
    'scrapy.extensions.telnet.TelnetConsole': 0,
    'scrapy.extensions.memusage.MemoryUsage': 0,
    'scrapy.extensions.memdebug.MemoryDebugger': 0,
    'scrapy.extensions.closespider.CloseSpider': 0,
    'scrapy.extensions.feedexport.FeedExporter': 0,
    'scrapy.extensions.logstats.LogStats': 0,
    'scrapy.extensions.spiderstate.SpiderState': 0,
    'scrapy.extensions.throttle.AutoThrottle': 0,
}

## 数据导出的相关设置
FEED_TEMPDIR = None
FEED_URI = None
FEED_URI_PARAMS = None  # a function to extend uri arguments
FEED_FORMAT = 'jsonlines'
FEED_STORE_EMPTY = False
FEED_EXPORT_ENCODING = None
FEED_EXPORT_FIELDS = None
FEED_STORAGES = {}
FEED_STORAGES_BASE = {
    '': 'scrapy.extensions.feedexport.FileFeedStorage',
    'file': 'scrapy.extensions.feedexport.FileFeedStorage',
    'stdout': 'scrapy.extensions.feedexport.StdoutFeedStorage',
    's3': 'scrapy.extensions.feedexport.S3FeedStorage',
    'ftp': 'scrapy.extensions.feedexport.FTPFeedStorage',
}
FEED_EXPORTERS = {}
FEED_EXPORTERS_BASE = {
    'json': 'scrapy.exporters.JsonItemExporter',
    'jsonlines': 'scrapy.exporters.JsonLinesItemExporter',
    'jl': 'scrapy.exporters.JsonLinesItemExporter',
    'csv': 'scrapy.exporters.CsvItemExporter',
    'xml': 'scrapy.exporters.XmlItemExporter',
    'marshal': 'scrapy.exporters.MarshalItemExporter',
    'pickle': 'scrapy.exporters.PickleItemExporter',
}
FEED_EXPORT_INDENT = 0

## 文件储存的相关设置

FILES_STORE_S3_ACL = 'private'
FILES_STORE_GCS_ACL = ''

## 上传数据到 FTP 服务器上的相关设置

FTP_USER = 'anonymous'
FTP_PASSWORD = 'guest'
FTP_PASSIVE_MODE = True

## HTTP 缓存相关配置（供离线访问）

HTTPCACHE_ENABLED = False
HTTPCACHE_DIR = 'httpcache'
HTTPCACHE_IGNORE_MISSING = False
HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_ALWAYS_STORE = False
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_IGNORE_SCHEMES = ['file']
HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS = []
HTTPCACHE_DBM_MODULE = 'anydbm' if six.PY2 else 'dbm'
HTTPCACHE_POLICY = 'scrapy.extensions.httpcache.DummyPolicy'
HTTPCACHE_GZIP = False

## HTTP 代理相关设置
HTTPPROXY_ENABLED = True
HTTPPROXY_AUTH_ENCODING = 'latin-1'

## 图片储存的相关设置
IMAGES_STORE_S3_ACL = 'private'
IMAGES_STORE_GCS_ACL = ''

## item 处理器
ITEM_PROCESSOR = 'scrapy.pipelines.ItemPipelineManager'

## item 管道
ITEM_PIPELINES = {}
## item 默认的管道
ITEM_PIPELINES_BASE = {}

## 日志处理的相关设置

## 是否启用日志
LOG_ENABLED = True
## 日志文件的编码
LOG_ENCODING = 'utf-8'
## 日志格式化器
LOG_FORMATTER = 'scrapy.logformatter.LogFormatter'
## 日志的格式
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
## 日志的时间格式
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'
## 日志的输出设置
LOG_STDOUT = False
## 日志级别
LOG_LEVEL = 'DEBUG'
## 日志输出的文件
LOG_FILE = None
LOG_SHORT_NAMES = False

## 是否开启调度器的 DEBUG 模式
SCHEDULER_DEBUG = False
## 日志统计时间间隔：LOGSTATS 会间隔性统计 items 和 pages 抓取的数量，默认是 60s，
## 若抓取时间不长的话可以设置短一点，合理配置
LOGSTATS_INTERVAL = 60.0

## 邮件服务相关配置

MAIL_HOST = 'localhost'
MAIL_PORT = 25
MAIL_FROM = 'scrapy@localhost'
MAIL_PASS = None
MAIL_USER = None

## 内存相关配置

MEMDEBUG_ENABLED = False        # enable memory debugging
MEMDEBUG_NOTIFY = []            # send memory debugging report by mail at engine shutdown

MEMUSAGE_CHECK_INTERVAL_SECONDS = 60.0
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_WARNING_MB = 0

METAREFRESH_ENABLED = True
METAREFRESH_MAXDELAY = 100

NEWSPIDER_MODULE = ''

## 是否开启随机下载延迟
RANDOMIZE_DOWNLOAD_DELAY = True

REACTOR_THREADPOOL_MAXSIZE = 10

## 重定向的相关配置

REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 20  # uses Firefox default setting
REDIRECT_PRIORITY_ADJUST = +2

REFERER_ENABLED = True
REFERRER_POLICY = 'scrapy.spidermiddlewares.referer.DefaultReferrerPolicy'

## 重发请求的相关配置

RETRY_ENABLED = True
RETRY_TIMES = 2  # initial response + 2 retries = 3 requests
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408]
RETRY_PRIORITY_ADJUST = -1

## 是否遵守 robots 协议
ROBOTSTXT_OBEY = False

## 调度器调度的相关策略配置：默认是深度优先采集（后进先出），可以更改为广度优先采集

SCHEDULER = 'scrapy.core.scheduler.Scheduler'
## 基于磁盘的任务队列：后进先出
SCHEDULER_DISK_QUEUE = 'scrapy.squeues.PickleLifoDiskQueue'
## 基于内存的任务队列：后进先出
SCHEDULER_MEMORY_QUEUE = 'scrapy.squeues.LifoMemoryQueue'
## 基于优先级的任务队列
SCHEDULER_PRIORITY_QUEUE = 'queuelib.PriorityQueue'

SPIDER_LOADER_CLASS = 'scrapy.spiderloader.SpiderLoader'
SPIDER_LOADER_WARN_ONLY = False

## 爬虫中间件（位于我们写的爬虫与 Scrapy 引擎之间）
SPIDER_MIDDLEWARES = {}

## 默认的爬虫中间件
SPIDER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.spidermiddlewares.httperror.HttpErrorMiddleware': 50,
    'scrapy.spidermiddlewares.offsite.OffsiteMiddleware': 500,
    'scrapy.spidermiddlewares.referer.RefererMiddleware': 700,
    'scrapy.spidermiddlewares.urllength.UrlLengthMiddleware': 800,
    'scrapy.spidermiddlewares.depth.DepthMiddleware': 900,
    # Spider side
}

SPIDER_MODULES = []

STATS_CLASS = 'scrapy.statscollectors.MemoryStatsCollector'
STATS_DUMP = True

STATSMAILER_RCPTS = []

TEMPLATES_DIR = abspath(join(dirname(__file__), '..', 'templates'))

## URL 长度限制
URLLENGTH_LIMIT = 2083

## 用户代理
USER_AGENT = 'Scrapy/%s (+https://scrapy.org)' % import_module('scrapy').__version__

## TELNET 控制台相关配置

TELNETCONSOLE_ENABLED = 1
TELNETCONSOLE_PORT = [6023, 6073]
TELNETCONSOLE_HOST = '127.0.0.1'
TELNETCONSOLE_USERNAME = 'scrapy'
TELNETCONSOLE_PASSWORD = None

SPIDER_CONTRACTS = {}
SPIDER_CONTRACTS_BASE = {
    'scrapy.contracts.default.UrlContract': 1,
    'scrapy.contracts.default.ReturnsContract': 2,
    'scrapy.contracts.default.ScrapesContract': 3,
}
