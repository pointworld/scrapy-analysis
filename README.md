# Scrapy 源码学习


## Scrapy 中使用到的设计模式

### 观察者模式 - 信号处理


## crawler、scraper、spider 三者的区别

- Crawler (scrapy.crawler) is the main entry point to Scrapy API. It provides access to all Scrapy core components, and it's used to hook extensions functionality into Scrapy.

- Scraper (scrapy.core.scraper) component is responsible for parsing responses and extracting information from them. It's being run from the Engine, and it's used to run your spiders.

- scrapy.spiders is a module containing base Spider implementation (that you use to write your spiders), together with some common spiders available out of the box (like the CrawlSpider for ruleset-based crawling, the SitemapSpider for sitemap based crawling, or XMLFeedSpider for crawling the XML feeds).


## Scrapy 是一个基于配置驱动的框架

配置存在优先级，值越大优先级越高

SETTINGS_PRIORITIES = {
    'default': 0,
    'command': 10,
    'project': 20,
    'spider': 30,
    'cmdline': 40,
}


## Scrapy 源码目录结构

```text
.
└── scrapy
    ├── VERSION
    ├── __init__.py
    ├── __main__.py
    ├── _monkeypatches.py
    ├── cmdline.py
    ├── commands                                ## 命令包，存放命令模块
    │   ├── __init__.py
    │   ├── bench.py
    │   ├── check.py
    │   ├── crawl.py
    │   ├── edit.py
    │   ├── fetch.py
    │   ├── genspider.py
    │   ├── list.py
    │   ├── parse.py
    │   ├── runspider.py
    │   ├── settings.py
    │   ├── shell.py
    │   ├── startproject.py
    │   ├── version.py
    │   └── view.py
    ├── conf.py
    ├── contracts
    │   ├── __init__.py
    │   └── default.py
    ├── core
    │   ├── __init__.py
    │   ├── downloader
    │   │   ├── __init__.py
    │   │   ├── contextfactory.py
    │   │   ├── handlers
    │   │   │   ├── __init__.py
    │   │   │   ├── datauri.py
    │   │   │   ├── file.py
    │   │   │   ├── ftp.py
    │   │   │   ├── http.py
    │   │   │   ├── http10.py
    │   │   │   ├── http11.py
    │   │   │   └── s3.py
    │   │   ├── middleware.py
    │   │   ├── tls.py
    │   │   └── webclient.py
    │   ├── engine.py
    │   ├── scheduler.py
    │   ├── scraper.py
    │   └── spidermw.py
    ├── crawler.py
    ├── downloadermiddlewares
    │   ├── __init__.py
    │   ├── ajaxcrawl.py
    │   ├── chunked.py
    │   ├── cookies.py
    │   ├── decompression.py
    │   ├── defaultheaders.py
    │   ├── downloadtimeout.py
    │   ├── httpauth.py
    │   ├── httpcache.py
    │   ├── httpcompression.py
    │   ├── httpproxy.py
    │   ├── redirect.py
    │   ├── retry.py
    │   ├── robotstxt.py
    │   ├── stats.py
    │   └── useragent.py
    ├── dupefilters.py
    ├── exceptions.py
    ├── exporters.py
    ├── extension.py
    ├── extensions
    │   ├── __init__.py
    │   ├── closespider.py
    │   ├── corestats.py
    │   ├── debug.py
    │   ├── feedexport.py
    │   ├── httpcache.py
    │   ├── logstats.py
    │   ├── memdebug.py
    │   ├── memusage.py
    │   ├── spiderstate.py
    │   ├── statsmailer.py
    │   ├── telnet.py
    │   └── throttle.py
    ├── http
    │   ├── __init__.py
    │   ├── common.py
    │   ├── cookies.py
    │   ├── headers.py
    │   ├── request
    │   │   ├── __init__.py
    │   │   ├── form.py
    │   │   └── rpc.py
    │   └── response
    │       ├── __init__.py
    │       ├── html.py
    │       ├── text.py
    │       └── xml.py
    ├── interfaces.py
    ├── item.py
    ├── link.py
    ├── linkextractors
    │   ├── __init__.py
    │   ├── htmlparser.py
    │   ├── lxmlhtml.py
    │   ├── regex.py
    │   └── sgml.py
    ├── loader
    │   ├── __init__.py
    │   ├── common.py
    │   └── processors.py
    ├── log.py
    ├── logformatter.py
    ├── mail.py
    ├── middleware.py
    ├── mime.types
    ├── pipelines
    │   ├── __init__.py
    │   ├── files.py
    │   ├── images.py
    │   └── media.py
    ├── resolver.py
    ├── responsetypes.py
    ├── selector
    │   ├── __init__.py
    │   ├── csstranslator.py
    │   ├── lxmlsel.py
    │   └── unified.py
    ├── settings
    │   ├── __init__.py
    │   ├── default_settings.py
    │   └── deprecated.py
    ├── shell.py
    ├── signalmanager.py
    ├── signals.py
    ├── spiderloader.py
    ├── spidermiddlewares
    │   ├── __init__.py
    │   ├── depth.py
    │   ├── httperror.py
    │   ├── offsite.py
    │   ├── referer.py
    │   └── urllength.py
    ├── spiders
    │   ├── __init__.py
    │   ├── crawl.py
    │   ├── feed.py
    │   ├── init.py
    │   └── sitemap.py
    ├── squeues.py
    ├── statscollectors.py
    ├── telnet.py
    ├── templates
    │   ├── project
    │   │   ├── module
    │   │   │   ├── __init__.py
    │   │   │   ├── items.py.tmpl
    │   │   │   ├── middlewares.py.tmpl
    │   │   │   ├── pipelines.py.tmpl
    │   │   │   ├── settings.py.tmpl
    │   │   │   └── spiders
    │   │   │       └── __init__.py
    │   │   └── scrapy.cfg
    │   └── spiders
    │       ├── basic.tmpl
    │       ├── crawl.tmpl
    │       ├── csvfeed.tmpl
    │       └── xmlfeed.tmpl
    ├── utils                                  ## 工具包，存放相关工具模块 
    │   ├── __init__.py
    │   ├── benchserver.py
    │   ├── boto.py
    │   ├── conf.py
    │   ├── console.py
    │   ├── datatypes.py
    │   ├── decorators.py
    │   ├── defer.py
    │   ├── deprecate.py
    │   ├── display.py
    │   ├── engine.py
    │   ├── ftp.py
    │   ├── gz.py
    │   ├── http.py
    │   ├── httpobj.py
    │   ├── iterators.py
    │   ├── job.py
    │   ├── log.py
    │   ├── markup.py
    │   ├── misc.py
    │   ├── multipart.py
    │   ├── ossignal.py
    │   ├── project.py
    │   ├── python.py
    │   ├── reactor.py
    │   ├── reqser.py
    │   ├── request.py
    │   ├── response.py
    │   ├── serialize.py
    │   ├── signal.py
    │   ├── sitemap.py
    │   ├── spider.py
    │   ├── template.py
    │   ├── test.py
    │   ├── testproc.py
    │   ├── testsite.py
    │   ├── trackref.py
    │   ├── url.py
    │   └── versions.py
    └── xlib
        ├── __init__.py
        ├── pydispatch.py
        └── tx.py
```