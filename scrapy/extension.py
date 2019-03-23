"""
The Extension Manager

See documentation in docs/topics/extensions.rst
"""
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list

class ExtensionManager(MiddlewareManager):
    ## 插件管理器主要用来加载和追踪已安装的插件
    ## 其可以通过配置文件中的 EXTENSIONS 配置项来配置

    component_name = 'extension'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('EXTENSIONS'))
