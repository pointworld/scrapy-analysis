import os
import six
import logging
from collections import defaultdict

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.python import to_native_str

logger = logging.getLogger(__name__)


class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""
    ## 该中间件支持处理需要 cookies 的网站
    ## 该中间件会追踪由服务器发送回来的 cookies，并将它们发送给后续来自该 spider 的请求（就像浏览器一样）
    ## 以下配置项可以用来配置该中间件：
    ##   COOKIES_ENABLED - 默认 True
    ##   COOKIES_DEBUG - 默认 False

    def __init__(self, debug=False):
        self.jars = defaultdict(CookieJar)
        self.debug = debug

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings.getbool('COOKIES_DEBUG'))

    def process_request(self, request, spider):
        ## 注意：如果 request.meta['dont_merge_cookies'] 值为 True，则该请求不会有 cookies 发送
        ## 到服务器

        if request.meta.get('dont_merge_cookies', False):
            return

        ## 从请求头的 meta 中获取 cookiejar
        cookiejarkey = request.meta.get("cookiejar")
        ## 根据 cookiejarkey 从 jars 列表中获取对应的 jar
        jar = self.jars[cookiejarkey]
        ## 将 request 对象中 cookies 属性的值，经过处理后得到形如如下的值
        ## 一个 Cookie 对象列表，值形如：[{'name': 'xxx', 'value': 'xxx', 'domain': xxx, ...}, ...]
        cookies = self._get_request_cookies(jar, request)
        ## 遍历每个 Cookie 对象，将 cookie 设置到 jar 对象（CookieJar）的 _cookies 属性中
        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        # set Cookie header
        ## 删除请求头中原有的 Cookie 字段
        request.headers.pop('Cookie', None)
        ## 将新的 Cookie 值添加到请求头的 Cookie 字段中
        ## request.headers 对象中 Cookie 字段的值形如：['key1=val1; key2=val2; ...']
        ## 真实请求中，cookies 是存放在请求头的 Cookie 字段中，并以类似 'key1=val1; key2=val2; ...'
        ## 这种格式的值发送给服务器的
        ## 这里先把它放到列表中
        jar.add_cookie_header(request)
        self._debug_cookie(request, spider)

    def process_response(self, request, response, spider):
        ## 注意：如果 request.meta['dont_merge_cookies'] 值为 True，则服务器发送回来的此次响应中
        ## 的 cookies 不会和现有 cookies 做合并

        if request.meta.get('dont_merge_cookies', False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        jar.extract_cookies(response, request)
        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in request.headers.getlist('Cookie')]
            if cl:
                cookies = "\n".join("Cookie: {}\n".format(c) for c in cl)
                msg = "Sending cookies to: {}\n{}".format(request, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in response.headers.getlist('Set-Cookie')]
            if cl:
                cookies = "\n".join("Set-Cookie: {}\n".format(c) for c in cl)
                msg = "Received cookies from: {}\n{}".format(response, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _format_cookie(self, cookie):
        ## 格式化 cookie，返回 cookie 字符串，形如：'user=point' 或 'user=point; Path=xxx; ...'

        # build cookie string
        cookie_str = '%s=%s' % (cookie['name'], cookie['value'])

        if cookie.get('path', None):
            cookie_str += '; Path=%s' % cookie['path']
        if cookie.get('domain', None):
            cookie_str += '; Domain=%s' % cookie['domain']

        return cookie_str

    def _get_request_cookies(self, jar, request):
        ## 将 request 对象中 cookies 属性的值，经过处理后得到形如如下的值，并返回该值
        ## [{'name': 'xxx', 'value': 'xxx', 'domain': xxx, ...}, ...]

        ## 如果请求头中的 cookies 字段是一个字典，则将其转换为列表的形式
        ## 例如：[{'name': xx, 'value': xx}, ...]
        if isinstance(request.cookies, dict):
            cookie_list = [{'name': k, 'value': v} for k, v in \
                    six.iteritems(request.cookies)]
        else:
            cookie_list = request.cookies

        ## 形如：['user=point; Path=xxx', ...]
        cookies = [self._format_cookie(x) for x in cookie_list]
        ## 模拟服务器端向客户端设置 cookie
        headers = {'Set-Cookie': cookies}
        ## 根据参数构造 Scrapy 的响应
        response = Response(request.url, headers=headers)

        ## 返回一个 Cookie 对象列表，值形如：[{'name': 'xxx', 'value': 'xxx', 'domain': xxx, ...}, ...]
        return jar.make_cookies(response, request)
