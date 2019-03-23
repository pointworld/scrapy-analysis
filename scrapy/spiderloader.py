# -*- coding: utf-8 -*-
from __future__ import absolute_import
from collections import defaultdict
import traceback
import warnings

from zope.interface import implementer

from scrapy.interfaces import ISpiderLoader
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes


@implementer(ISpiderLoader)
class SpiderLoader(object):
    """
    SpiderLoader is a class which locates and loads spiders
    in a Scrapy project.
    """
    ## 该类主要用于在 Scrapy 项目中定位和加载 spiders

    def __init__(self, settings):
        ## 根据配置文件获取存放 spider 模块的路径
        self.spider_modules = settings.getlist('SPIDER_MODULES')
        self.warn_only = settings.getbool('SPIDER_LOADER_WARN_ONLY')
        ## 用于储存 spider 名与 spider 类的映射
        self._spiders = {}
        ## 用于储存 spider 名字与 ['spider 模块名', 'spider 类名'] 的映射
        self._found = defaultdict(list)
        ## 加载所有 spiders
        self._load_all_spiders()

    def _check_name_duplicates(self):
        dupes = ["\n".join("  {cls} named {name!r} (in {module})".format(
                                module=mod, cls=cls, name=name)
                           for (mod, cls) in locations)
                 for name, locations in self._found.items()
                 if len(locations)>1]
        if dupes:
            msg = ("There are several spiders with the same name:\n\n"
                   "{}\n\n  This can cause unexpected behavior.".format(
                        "\n\n".join(dupes)))
            warnings.warn(msg, UserWarning)

    def _load_spiders(self, module):
        for spcls in iter_spider_classes(module):
            self._found[spcls.name].append((module.__name__, spcls.__name__))
            self._spiders[spcls.name] = spcls

    def _load_all_spiders(self):
        ## 组装成 {spider_name: spider_cls, ...} 的字典

        for name in self.spider_modules:
            try:
                for module in walk_modules(name):
                    self._load_spiders(module)
            except ImportError as e:
                if self.warn_only:
                    msg = ("\n{tb}Could not load spiders from module '{modname}'. "
                           "See above traceback for details.".format(
                                modname=name, tb=traceback.format_exc()))
                    warnings.warn(msg, RuntimeWarning)
                else:
                    raise
        self._check_name_duplicates()

    @classmethod
    def from_settings(cls, settings):
        ## 基于配置创建 Spider 加载器的实例
        return cls(settings)

    def load(self, spider_name):
        """
        Return the Spider class for the given spider name. If the spider
        name is not found, raise a KeyError.
        """
        ## 根据给定的名字返回对应的 Spider 类

        try:
            return self._spiders[spider_name]
        except KeyError:
            raise KeyError("Spider not found: {}".format(spider_name))

    def find_by_request(self, request):
        """
        Return the list of spider names that can handle the given request.
        """
        ## 返回可以被给定请求处理的 spiders 名字的列表
        return [name for name, cls in self._spiders.items()
                if cls.handles_request(request)]

    def list(self):
        """
        Return a list with the names of all spiders available in the project.
        """
        ## 返回项目中所有可用的 spiders 名字组成的列表
        return list(self._spiders.keys())
