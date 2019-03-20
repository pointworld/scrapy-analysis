from __future__ import print_function
import sys, os
import optparse
import cProfile
import inspect
import pkg_resources

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.misc import walk_modules
from scrapy.utils.project import inside_project, get_project_settings
from scrapy.utils.python import garbage_collect
from scrapy.settings.deprecated import check_deprecated_settings

def _iter_command_classes(module_name):
    # TODO: add `name` attribute to commands and and merge this function with
    # scrapy.utils.spider.iter_spider_classes
    ## 迭代这个包下的所有模块，找到 ScrapyCommand 类的子类 Command
    ## 这个过程主要是，导入commands文件夹下的所有模块，生成 { cmd_name: cmd, ... }
    ## 字典集合，如果用户在配置文件中配置了自定义的命令类，也追加进去。也就是说，
    ## 自己也可以编写自己的命令类，然后追加到配置文件中，之后就可以使用自己自定义
    ## 的命令了
    for module in walk_modules(module_name):
        for obj in vars(module).values():
            if inspect.isclass(obj) and \
                    issubclass(obj, ScrapyCommand) and \
                    obj.__module__ == module.__name__ and \
                    not obj == ScrapyCommand:
                yield obj

def _get_commands_from_module(module, inproject):
    d = {}
    ## 找到这个模块下所有的命令类 (ScrapyCommand 子类)
    for cmd in _iter_command_classes(module):
        if inproject or not cmd.requires_project:
            ## 生成 {cmd_name: cmd} 字典
            cmdname = cmd.__module__.split('.')[-1]
            d[cmdname] = cmd()
    ## 返回一个由命令名字和命令对象组成的字典
    return d

def _get_commands_from_entry_points(inproject, group='scrapy.commands'):
    cmds = {}
    for entry_point in pkg_resources.iter_entry_points(group):
        obj = entry_point.load()
        if inspect.isclass(obj):
            cmds[entry_point.name] = obj()
        else:
            raise Exception("Invalid entry point %s" % entry_point.name)
    return cmds

def _get_commands_dict(settings, inproject):
    ## 导入 commands 文件夹下的所有模块，生成 {cmd_name: cmd, ...} 字典
    cmds = _get_commands_from_module('scrapy.commands', inproject)
    cmds.update(_get_commands_from_entry_points(inproject))
    cmds_module = settings['COMMANDS_MODULE']
    if cmds_module:
        cmds.update(_get_commands_from_module(cmds_module, inproject))
    return cmds

def _pop_command_name(argv):
    i = 0
    for arg in argv[1:]:
        if not arg.startswith('-'):
            del argv[i]
            return arg
        i += 1

def _print_header(settings, inproject):
    if inproject:
        print("Scrapy %s - project: %s\n" % (scrapy.__version__, \
            settings['BOT_NAME']))
    else:
        print("Scrapy %s - no active project\n" % scrapy.__version__)

def _print_commands(settings, inproject):
    _print_header(settings, inproject)
    print("Usage:")
    print("  scrapy <command> [options] [args]\n")
    print("Available commands:")
    cmds = _get_commands_dict(settings, inproject)
    for cmdname, cmdclass in sorted(cmds.items()):
        print("  %-13s %s" % (cmdname, cmdclass.short_desc()))
    if not inproject:
        print()
        print("  [ more ]      More commands available when run from project directory")
    print()
    print('Use "scrapy <command> -h" to see more info about a command')

def _print_unknown_command(settings, cmdname, inproject):
    _print_header(settings, inproject)
    print("Unknown command: %s\n" % cmdname)
    print('Use "scrapy" to see available commands')

def _run_print_help(parser, func, *a, **kw):
    try:
        func(*a, **kw)
    except UsageError as e:
        if str(e):
            parser.error(str(e))
        if e.print_help:
            parser.print_help()
        sys.exit(2)

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv

    # --- backward compatibility for scrapy.conf.settings singleton ---
    if settings is None and 'scrapy.conf' in sys.modules:
        from scrapy import conf
        if hasattr(conf, 'settings'):
            settings = conf.settings
    # ------------------------------------------------------------------

    if settings is None:
        ## 获取项目配置
        ## 根据环境变量和 scrapy.cfg 初始化环境，最终生成一个 Settings 实例
        settings = get_project_settings()
        # set EDITOR from environment if available
        try:
            editor = os.environ['EDITOR']
        except KeyError: pass
        else:
            settings['EDITOR'] = editor
    ## 校验弃用的配置项
    check_deprecated_settings(settings)

    # --- backward compatibility for scrapy.conf.settings singleton ---
    import warnings
    from scrapy.exceptions import ScrapyDeprecationWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ScrapyDeprecationWarning)
        from scrapy import conf
        conf.settings = settings
    # ------------------------------------------------------------------

    ## 执行环境是否在项目中
    inproject = inside_project()
    ## 读取 commands 文件夹，把所有的命令类转换为 {cmd_name: cmd_instance} 的字典
    cmds = _get_commands_dict(settings, inproject)
    ## 从命令行参数中解析出执行的是哪个命令
    ## 例如，若命令行中执行的命令是 scrapy crawl xxx，这里的 cmdname 就是 'crawl'
    cmdname = _pop_command_name(argv)
    ## optparse 模块，可以让程序员能轻松设计出简单明了、易于使用、符合标准的 Unix
    ## 命令例程式的帮助文档
    parser = optparse.OptionParser(formatter=optparse.TitledHelpFormatter(), \
        conflict_handler='resolve')
    ## 如果 cmdname 为空，则打印所有命令的帮助信息，并退出 Python 程序
    if not cmdname:
        _print_commands(settings, inproject)
        sys.exit(0)
    ## 如果 cmdname 不为空，但不在 cmds 字典的键中，则打印未知命令错误，并异常退出程序
    elif cmdname not in cmds:
        _print_unknown_command(settings, cmdname, inproject)
        sys.exit(2)

    ## 根据命令名称找到对应的命令实例
    cmd = cmds[cmdname]
    parser.usage = "scrapy %s %s" % (cmdname, cmd.syntax())
    parser.description = cmd.long_desc()
    ## 设置项目配置和级别为 command
    settings.setdict(cmd.default_settings, priority='command')
    cmd.settings = settings
    ## 添加解析规则
    cmd.add_options(parser)
    ## 解析命令参数，并交由 Scrapy 命令实例处理
    opts, args = parser.parse_args(args=argv[1:])
    _run_print_help(parser, cmd.process_options, args, opts)

    ## 初始化 CrawlerProcess 实例，并赋值给命令实例的 crawler_process 属性
    cmd.crawler_process = CrawlerProcess(settings)
    ## 执行命令实例的 run 方法
    ## 如果运行命令是 scrapy crawl <spider_name>，则运行的就是
    ## commands/crawl.py 的 run 方法
    _run_print_help(parser, _run_command, cmd, args, opts)
    sys.exit(cmd.exitcode)

def _run_command(cmd, args, opts):
    if opts.profile:
        _run_command_profiled(cmd, args, opts)
    else:
        cmd.run(args, opts)

def _run_command_profiled(cmd, args, opts):
    if opts.profile:
        sys.stderr.write("scrapy: writing cProfile stats to %r\n" % opts.profile)
    loc = locals()
    p = cProfile.Profile()
    p.runctx('cmd.run(args, opts)', globals(), loc)
    if opts.profile:
        p.dump_stats(opts.profile)

if __name__ == '__main__':
    try:
        execute()
    finally:
        # Twisted prints errors in DebugInfo.__del__, but PyPy does not run gc.collect()
        # on exit: http://doc.pypy.org/en/latest/cpython_differences.html?highlight=gc.collect#differences-related-to-garbage-collection-strategies
        garbage_collect()
