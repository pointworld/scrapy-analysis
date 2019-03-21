import os
import sys
import numbers
from operator import itemgetter

import six
from six.moves.configparser import SafeConfigParser

from scrapy.settings import BaseSettings
from scrapy.utils.deprecate import update_classpath
from scrapy.utils.python import without_none_values


def build_component_list(compdict, custom=None, convert=update_classpath):
    """Compose a component list from a { class: order } dictionary."""

    def _check_components(complist):
        if len({convert(c) for c in complist}) != len(complist):
            raise ValueError('Some paths in {!r} convert to the same object, '
                             'please update your settings'.format(complist))

    def _map_keys(compdict):
        if isinstance(compdict, BaseSettings):
            compbs = BaseSettings()
            for k, v in six.iteritems(compdict):
                prio = compdict.getpriority(k)
                if compbs.getpriority(convert(k)) == prio:
                    raise ValueError('Some paths in {!r} convert to the same '
                                     'object, please update your settings'
                                     ''.format(list(compdict.keys())))
                else:
                    compbs.set(convert(k), v, priority=prio)
            return compbs
        else:
            _check_components(compdict)
            return {convert(k): v for k, v in six.iteritems(compdict)}

    def _validate_values(compdict):
        """Fail if a value in the components dict is not a real number or None."""
        for name, value in six.iteritems(compdict):
            if value is not None and not isinstance(value, numbers.Real):
                raise ValueError('Invalid value {} for component {}, please provide ' \
                                 'a real number or None instead'.format(value, name))

    # BEGIN Backward compatibility for old (base, custom) call signature
    if isinstance(custom, (list, tuple)):
        _check_components(custom)
        return type(custom)(convert(c) for c in custom)

    if custom is not None:
        compdict.update(custom)
    # END Backward compatibility

    _validate_values(compdict)
    compdict = without_none_values(_map_keys(compdict))
    return [k for k, v in sorted(six.iteritems(compdict), key=itemgetter(1))]


def arglist_to_dict(arglist):
    """Convert a list of arguments like ['arg1=val1', 'arg2=val2', ...] to a
    dict
    """
    ## 将类似于 ['arg1=val1', 'arg2=val2', ...] 的参数列表转换为字典类型
    return dict(x.split('=', 1) for x in arglist)


def closest_scrapy_cfg(path='.', prevpath=None):
    """Return the path to the closest scrapy.cfg file by traversing the current
    directory and its parents
    """
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, 'scrapy.cfg')
    if os.path.exists(cfgfile):
        return cfgfile
    return closest_scrapy_cfg(os.path.dirname(path), path)


def init_env(project='default', set_syspath=True):
    """Initialize environment to use command-line tool from inside a project
    dir. This sets the Scrapy settings module and modifies the Python path to
    be able to locate the project module.
    """
    ## 初始化项目环境：
    ## 在项目目录内，通过命令行工具，基于配置文件 scrapy.cfg 初始化项目环境
    ## 找到用户配置模块（settings），设置到环境变量的 SCRAPY_SETTINGS_MODULE 中
    ## 将项目基路径加入到 Python 模块的解析路径集中

    ## 获取配置解析器的实例（解析 .cfg 配置文件）
    cfg = get_config()
    ## 检查配置解析器实例的 settings 节中是否存在指定的 project 项
    if cfg.has_option('settings', project):
        ## 将 Scrapy 中的设置模块添加到系统环境变量中
        os.environ['SCRAPY_SETTINGS_MODULE'] = cfg.get('settings', project)
    ## 从当前项目所在目录依次向上一级目录查找 scrapy 配置文件的路径，返回最近的一个
    closest = closest_scrapy_cfg()
    if closest:
        ## 将配置文件（scrapy.cfg）所在的目录路径设置为项目目录（项目基路径）
        projdir = os.path.dirname(closest)
        if set_syspath and projdir not in sys.path:
            ## 将项目基路径加入到 Python 模块的解析路径集中
            sys.path.append(projdir)


def get_config(use_closest=True):
    """Get Scrapy config file as a SafeConfigParser"""

    ## 获取 Scrapy 配置文件可能的路径列表: ['/etc/scrapy.cfg', ...]
    sources = get_sources(use_closest)
    ## 实例化一个配置解析器
    ## 该模块是用来解析配置文件的，配置文件中的内容可以包含一个或多个节（section）
    ## 若传入的参数是多个配置文件的列表，会从左往右依次读取，后面的值会覆盖前面的值
    ## 每个节可以有多个参数（键=值）或（键:值）
    ## 使用配置文件的好处是使程序更加灵活，将变化抽离出来，单独管理
    ## Python 3.2 之后，该模块被更名为 ConfigParser
    cfg = SafeConfigParser()
    ## 读取 sources 列表中的所有配置文件（以 .cfg 结尾），将文件中的配置按一定的
    ## 格式存储到配置解析器实例 cfg 的相关属性中
    cfg.read(sources)
    return cfg


def get_sources(use_closest=True):
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or \
        os.path.expanduser('~/.config')
    sources = ['/etc/scrapy.cfg', r'c:\scrapy\scrapy.cfg',
               xdg_config_home + '/scrapy.cfg',
               os.path.expanduser('~/.scrapy.cfg')]
    if use_closest:
        sources.append(closest_scrapy_cfg())
    return sources
