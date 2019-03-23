"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""
## 在 Scrapy 中，当某些事件发生时，Scrapy 会使用信号来发送通知。
## 我们可以在项目中通过捕获这些信号，来实现一些其他任务，或者扩展 Scrapy 的功能。

## 引擎已开始
engine_started = object()
## 引擎已停止（例如，当抓取任务已完成时）
engine_stopped = object()
## spider 已开启
spider_opened = object()
## 爬虫闲置
spider_idle = object()
## 爬虫已关闭
spider_closed = object()
## 爬虫出错
spider_error = object()
## 请求已调度
request_scheduled = object()
## 请求已丢弃
request_dropped = object()
## 请求已到达下载器
request_reached_downloader = object()
## 引擎接收到一个来自下载器的响应
response_received = object()
## 响应已下载
response_downloaded = object()
## item 已抓取
item_scraped = object()
## item 已丢弃
item_dropped = object()
## item 错误
item_error = object()

# for backward compatibility
stats_spider_opened = spider_opened
stats_spider_closing = spider_closed
stats_spider_closed = spider_closed

item_passed = item_scraped

request_received = request_scheduled
