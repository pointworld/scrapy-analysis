## 对于每个下载器中间件而言，可以对定义一个或多个如下方法：
##
## process_request(request, spider) -> None | Response | Request | Raise IgnoreRequest
##   对于每一个流经下载器中间件（engine -->>-- downloader）的请求，都会调用该方法
##   其返回值有如下情况：
##     1. None - 交由 process_request 方法链中的下一个方法继续处理，最后再交由下载处理器处理
##     2. Response - Scrapy 将不会再调用其他下载器中间件的 process_request 或 process_exeception 方法，
##        相应的下载处理器也不会被调用。而下载器中间件中定义的一系列 process_response 方法将会被执行
##     3. Request - 处理链将终止，Scrapy 会将该 Request 重新交给调度器调度
##     4. Raise an IgnoreRequest exception -  process_exception 方法链将会被执行；
##        如果该异常仍然存在，则会被该请求中的 errback 函数处理；如果最后该
##        异常还是没有被处理，则该请求会被忽略，也不会记录到日志中
##
## process_response(request, response, spider) -> Response | Request | Raise IgnoreRequest
##   对于每一个流经下载器中间件（downloader -->>-- engine）的响应，都会调用该方法
##   其返回值有如下情况：
##     1. Response - 交由 process_response 方法链继续处理
##     2. Request - process_response 方法链将终止，Scrapy 会将该 Request 重新交给调度器重新调度
##     3. Raise an IgnoreRequest exception - 该请求中的 errback 函数将被调用，如果最后该
##        异常还是没有被处理，则该请求会被忽略，也不会记录到日志中
##
## process_exception(request, exeception, spider) -> None | Response | Request
##   当下载处理器或 process_request 方法抛出异常时，将会被处理链中的该方法处理
##   其返回值有如下情况：
##     1. None - 异常将继续被处理链处理，如果仍然存在异常，则默认异常处理将被开启
##     2. Response - 交由 process_response 方法链处理
##     3. Request - 交由调度器重新调度