"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list

class ItemPipelineManager(MiddlewareManager):
    ## item 管道中间件管理器

    component_name = 'item pipeline'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        ## 从配置 ITEM_PIPELINES_BASE 和 ITEM_PIPELINES 中获取所有的管道类列表
        return build_component_list(settings.getwithbase('ITEM_PIPELINES'))

    def _add_middleware(self, pipe):
        ## 定义 item 管道的一系列处理方法
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(pipe.process_item)

    def process_item(self, item, spider):
        ## 依次调用所有子类的 process_item 方法
        return self._process_chain('process_item', item, spider)
