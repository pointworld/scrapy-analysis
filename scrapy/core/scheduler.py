import os
import json
import logging
from os.path import join, exists

from scrapy.utils.reqser import request_to_dict, request_from_dict
from scrapy.utils.misc import load_object, create_instance
from scrapy.utils.job import job_dir

logger = logging.getLogger(__name__)


class Scheduler(object):

    def __init__(self, dupefilter, jobdir=None, dqclass=None, mqclass=None,
                 logunser=False, stats=None, pqclass=None):
        ## 调度器的初始化主要做了两件事：
        ## 1. 实例化请求指纹过滤器（用来过滤重复请求，可自己重写替换之）
        ## 2. 定义各种不同类型的任务队列（基于优先级、磁盘、内存的任务队列）

        ## 指纹过滤器
        self.df = dupefilter
        ## 任务队列文件夹，如果没有定义 jobdir，那么则使用的是内存队列
        self.dqdir = self._dqdir(jobdir)
        ## 优先级任务队列类
        self.pqclass = pqclass
        ## 基于磁盘的任务队列类：在配置文件中可配置存储路径，每次执行后会把任务队列保存到磁盘上
        self.dqclass = dqclass
        ## 基于内存的任务队列类：在内存中存储，下次启动则消失
        self.mqclass = mqclass
        ## 日志是否序列化
        self.logunser = logunser
        ## 统计
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        ## 根据一个爬虫对象实例化一个调度器类

        ## 配置文件
        settings = crawler.settings
        ## 从配置文件中获取指纹过滤器类
        dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        ##根据配置和爬虫对象创建一个指纹过滤器（用来过滤重复请求）
        dupefilter = create_instance(dupefilter_cls, settings, crawler)
        ## 从配置文件中依次获取基于优先级、基于磁盘任务、基于内存的任务队列类
        pqclass = load_object(settings['SCHEDULER_PRIORITY_QUEUE'])
        dqclass = load_object(settings['SCHEDULER_DISK_QUEUE'])
        mqclass = load_object(settings['SCHEDULER_MEMORY_QUEUE'])
        ## 日志是否序列化
        logunser = settings.getbool('LOG_UNSERIALIZABLE_REQUESTS', settings.getbool('SCHEDULER_DEBUG'))
        ## 返回一个调度器实例
        return cls(dupefilter, jobdir=job_dir(settings), logunser=logunser,
                   stats=crawler.stats, pqclass=pqclass, dqclass=dqclass, mqclass=mqclass)

    def has_pending_requests(self):
        return len(self) > 0

    def open(self, spider):
        self.spider = spider
        ## 实例化一个基于优先级的任务队列
        self.mqs = self.pqclass(self._newmq)
        ## 如果存在 dqdir 则实例化一个基于磁盘的任务队列
        self.dqs = self._dq() if self.dqdir else None
        ## 调用请求指纹过滤器的 open 方法
        return self.df.open()

    def close(self, reason):
        if self.dqs:
            prios = self.dqs.close()
            with open(join(self.dqdir, 'active.json'), 'w') as f:
                json.dump(prios, f)
        return self.df.close(reason)

    def enqueue_request(self, request):
        ## 若请求允许被过滤且在请求指纹中已存在该请求，则返回 False
        if not request.dont_filter and self.df.request_seen(request):
            self.df.log(request, self.spider)
            return False
        ## 磁盘队列是否入队成功
        dqok = self._dqpush(request)
        if dqok:
            self.stats.inc_value('scheduler/enqueued/disk', spider=self.spider)
        else:
            ## 没有定义磁盘队列，则使用内存队列
            self._mqpush(request)
            self.stats.inc_value('scheduler/enqueued/memory', spider=self.spider)
        self.stats.inc_value('scheduler/enqueued', spider=self.spider)
        return True

    def next_request(self):
        request = self.mqs.pop()
        if request:
            self.stats.inc_value('scheduler/dequeued/memory', spider=self.spider)
        else:
            request = self._dqpop()
            if request:
                self.stats.inc_value('scheduler/dequeued/disk', spider=self.spider)
        if request:
            self.stats.inc_value('scheduler/dequeued', spider=self.spider)
        return request

    def __len__(self):
        return len(self.dqs) + len(self.mqs) if self.dqs else len(self.mqs)

    def _dqpush(self, request):
        ## 是否定义磁盘队列
        if self.dqs is None:
            return
        try:
            ## 将 request 对象转换为字典
            reqd = request_to_dict(request, self.spider)
            ## 放入磁盘队列
            self.dqs.push(reqd, -request.priority)
        except ValueError as e:  # non serializable request
            if self.logunser:
                msg = ("Unable to serialize request: %(request)s - reason:"
                       " %(reason)s - no more unserializable requests will be"
                       " logged (stats being collected)")
                logger.warning(msg, {'request': request, 'reason': e},
                               exc_info=True, extra={'spider': self.spider})
                self.logunser = False
            self.stats.inc_value('scheduler/unserializable',
                                 spider=self.spider)
            return
        else:
            return True

    def _mqpush(self, request):
        ## 放入内存队列
        self.mqs.push(request, -request.priority)

    def _dqpop(self):
        if self.dqs:
            d = self.dqs.pop()
            if d:
                return request_from_dict(d, self.spider)

    def _newmq(self, priority):
        return self.mqclass()

    def _newdq(self, priority):
        return self.dqclass(join(self.dqdir, 'p%s' % priority))

    def _dq(self):
        ## 实例化一个磁盘任务队列

        activef = join(self.dqdir, 'active.json')
        if exists(activef):
            with open(activef) as f:
                prios = json.load(f)
        else:
            prios = ()
        q = self.pqclass(self._newdq, startprios=prios)
        if q:
            logger.info("Resuming crawl (%(queuesize)d requests scheduled)",
                        {'queuesize': len(q)}, extra={'spider': self.spider})
        return q

    def _dqdir(self, jobdir):
        if jobdir:
            dqdir = join(jobdir, 'requests.queue')
            if not exists(dqdir):
                os.makedirs(dqdir)
            return dqdir
