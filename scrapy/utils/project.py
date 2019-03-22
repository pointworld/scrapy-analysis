import os
from six.moves import cPickle as pickle
import warnings

from importlib import import_module
from os.path import join, dirname, abspath, isabs, exists

from scrapy.utils.conf import closest_scrapy_cfg, get_config, init_env
from scrapy.settings import Settings
from scrapy.exceptions import NotConfigured

ENVVAR = 'SCRAPY_SETTINGS_MODULE'
DATADIR_CFG_SECTION = 'datadir'


def inside_project():
    ## 从系统环境变量中获取项目设置模块 'XXX.settings'
    scrapy_module = os.environ.get('SCRAPY_SETTINGS_MODULE')
    if scrapy_module is not None:
        try:
            ## 导入项目设置模块
            import_module(scrapy_module)
        except ImportError as exc:
            warnings.warn("Cannot import scrapy settings module %s: %s" % (scrapy_module, exc))
        else:
            return True
    ## 如果系统环境变量中没有，就近查找 scrapy.cfg，找得到就认为是在项目环境中
    ## scrapy 命令有的是依赖项目运行的，有的命令则是全局的，不依赖项目的。这里
    ## 主要通过就近查找 scrapy.cfg 文件来确定是否在项目环境中
    return bool(closest_scrapy_cfg())


def project_data_dir(project='default'):
    """Return the current project data dir, creating it if it doesn't exist"""
    if not inside_project():
        raise NotConfigured("Not inside a project")
    cfg = get_config()
    if cfg.has_option(DATADIR_CFG_SECTION, project):
        d = cfg.get(DATADIR_CFG_SECTION, project)
    else:
        scrapy_cfg = closest_scrapy_cfg()
        if not scrapy_cfg:
            raise NotConfigured("Unable to find scrapy.cfg file to infer project data dir")
        d = abspath(join(dirname(scrapy_cfg), '.scrapy'))
    if not exists(d):
        os.makedirs(d)
    return d


def data_path(path, createdir=False):
    """
    Return the given path joined with the .scrapy data directory.
    If given an absolute path, return it unmodified.
    """
    if not isabs(path):
        if inside_project():
            path = join(project_data_dir(), path)
        else:
            path = join('.scrapy', path)
    if createdir and not exists(path):
        os.makedirs(path)
    return path


def get_project_settings():
    ## 环境变量中是否有 SCRAPY_SETTINGS_MODULE 配置
    if ENVVAR not in os.environ:
        ## 从环境变量中获取 SCRAPY_PROJECT，若无则默认返回 'default'
        project = os.environ.get('SCRAPY_PROJECT', 'default')
        ## 初始化项目环境：
        ## 在项目目录内，通过命令行工具，基于配置文件 scrapy.cfg 初始化项目环境
        ## 找到用户配置模块（settings），设置到环境变量 SCRAPY_SETTINGS_MODULE 中
        ## 将项目基路径加入到 Python 模块的解析路径集中
        init_env(project)

    ## 加载默认配置文件 default_settings.py，生成 settings 实例
    ## 用于存储 scrapy 内置组件的配置（默认配置），是可定制的
    ## 这里得到的是默认配置，默认配置的优先级为 default
    settings = Settings()
    ## 获取用户配置文件（settings.py）的路径
    settings_module_path = os.environ.get(ENVVAR)
    if settings_module_path:
        ## 基于 settings.py 文件的路径加载用户配置
        ## 更新配置：用用户配置更新默认配置
        ## 用户配置的优先级为 project
        settings.setmodule(settings_module_path, priority='project')

    # XXX: remove this hack
    pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE")
    if pickled_settings:
        settings.setdict(pickle.loads(pickled_settings), priority='project')

    # XXX: deprecate and remove this functionality
    env_overrides = {k[7:]: v for k, v in os.environ.items() if
                     k.startswith('SCRAPY_')}
    if env_overrides:
        settings.setdict(env_overrides, priority='project')

    ## 返回配置对象
    return settings
