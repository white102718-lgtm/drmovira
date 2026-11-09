# -*- coding: utf-8 -*-
"""
@File:common_util.py
@Author:wty
@Time:2020/1/9 10:55
"""
import hashlib
import inspect
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, ContextManager, Optional, Union

from weakref import WeakSet



def count_time(func):
    """
    直接在要计算运行时间的方法上@count_time即可,python装饰器详情见菜鸟教程
    :param func:
    :return:
    """
    from functools import wraps

    # 加上wraps(func)防止传进来的方法被def的wrapper替换掉,这样方法.__name__打印的就不会是wrapper了
    @wraps(func)
    # 加上args等是为了不影响外部传参和返回结果
    def wrapper(*args, **kwargs):
        clock = time.perf_counter()
        func_return = func(*args, **kwargs)
        print(func.__name__, time.perf_counter() - clock)
        return func_return

    return wrapper


def count_time_accumulate(func, t=[0]):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        clock = time.perf_counter()
        func_return = func(*args, **kwargs)
        t[0] += time.perf_counter() - clock
        print(func.__name__, t[0])
        return func_return

    return wrapper


def singleton(cls):
    _instances = {}

    def _singleton(*args, **kwargs):
        if cls not in _instances:
            _instances[cls] = cls(*args, **kwargs)
        return _instances[cls]

    return _singleton


def get_list_row_col(col1, col2, list_, row1=None, row2=None):
    # [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]
    # get_list_row_col(1, 3, a)
    # [[2, 3], [2, 3], [2, 3], [2, 3], [2, 3], [2, 3], [2, 3]]
    row1 = 0 if row1 is None else row1
    row2 = len(list_) if row2 is None else row2
    return [list_[r][col1:col2] for r in range(row1, row2)]


def get_dir_dir(path):
    if os.path.exists(path) and os.path.isdir(path):
        dir_list_part = os.listdir(path)
        dir_list = [path + os.sep + i for i in dir_list_part]
        dir_list = [dir for dir in dir_list if os.path.isdir(dir) and os.listdir(dir)]
        return dir_list
    else:
        print("输入不是文件夹")
        return


def time_format(t, current="t-", target="s", style="second"):
    """
    :param t: one time type string or int.
    :param current: (t-:'%Y-%m-%d %H:%M:%S')(t:'%Y%m%d%H%M%S')(s:timestamp:1596530367)
    :param target:
    :param style: day:%Y-%m-%d   hour:'%Y-%m-%d %H' ...
    """
    style_func = {"day": 1, "hour": 3, "minute": 5, "second": None}
    style_arr = ["%Y-%m-%d", " ", "%H", ":", "%M", ":", "%S"]
    style_ = "".join(style_arr[: style_func.get(style)])
    style = style_.replace("-", "").replace(":", "").replace(" ", "")
    current_func = {
        "t-": lambda x: time.strptime(x, style_),
        "s": lambda x: time.localtime(x),
        "t": lambda x: time.strptime(x, style),
    }
    target_func = {
        "t-": lambda x: time.strftime(style_, x),
        "s": lambda x: int(time.mktime(x)),
        "t": lambda x: time.strftime(style, x),
    }
    result = target_func.get(target)(current_func.get(current)(t))
    return result


def get_dir_files(dir_file, contain=None, mode="in", filter_empty=False):
    """Path().rglob(*.xml)
    :param dir_file: 目录 D:/xml_dir/part
    :param contain: 文件后缀/文件过滤字符
    :param mode: end,in   表示过滤方式
    :param filter_empty: 过滤空文件
    :return: 目录下所有的包含后缀的文件，没有后缀则是所有文件
    """
    file_list = []
    for root, dirs, files in os.walk(dir_file):
        for file in files:
            file = root + os.sep + file
            # 如果包含要过滤的文件条件
            if contain and (
                not (mode == "end" and file.endswith(contain))
                and not (mode == "in" and contain in file)
            ):
                continue
            file_list.append(file)
    if filter_empty:
        for file in file_list:
            if os.path.getsize(file) == 0:
                file_list.remove(file)
    if not file_list:
        print("未找到文件夹", dir_file)
    return file_list


def get_md5(s, start=None, end=None):
    """
    :param s: 字符串或列表
    :param start: 返回的md5值要从哪截取
    :param end: 返回的md5值截取到哪
    :return:字符串或列表
    """
    if isinstance(s, list):
        return list(
            map(lambda a: hashlib.md5(str(a).encode("utf8")).hexdigest()[start:end], s)
        )
    else:
        return hashlib.md5(str(s).encode("utf8")).hexdigest()[start:end]


def get_file_ctime(f, format_="%Y%m%d%H%M%S"):  # '%Y-%m-%d %H:%M:%S'
    """
    :param f: 路径
    :param format_: 指定为None返回时间戳
    :return:
    """
    getmtime = os.path.getctime(f)
    if format_:
        return time.strftime(format_, time.localtime(getmtime))
    else:
        return getmtime


def get_current_path():
    p_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return p_path


def open_(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            read = f.read()
        return read
    except Exception:
        with open(file_path, "r", encoding="gbk") as f:
            read = f.read()
        return read


def get_time_between(
    start=None, end=None, style="days", interval=1, out_format="seconds"
):
    from datetime import datetime, timedelta

    from dateutil.parser import parse

    now = datetime.now()
    start_time = parse(start) if start is not None else now
    end_time = parse(end) if end is not None else now
    current_time = start_time
    style_format = {"days": 1, "hours": 3, "minutes": 5, "seconds": 7}
    if out_format in style_format:
        out_format = "".join(
            ["%Y-%m-%d", " ", "%H", ":", "%M", ":", "%S"][: style_format[out_format]]
        )

    while True:
        yield current_time.strftime(out_format)
        current_time += timedelta(**{style: interval})
        if current_time >= end_time:
            yield end_time.strftime(out_format)
            break


def distinct_list(data_list):
    result = []
    [result.append(d) for d in data_list if d not in result]
    return result


def get_last_file(path, contain=None, mode="in", filter_empty=False):
    # 参数同get_dir_files
    try:
        file_list = get_dir_files(
            path, contain, mode, filter_empty
        )  # 获取当前目录文件列表
        # 时间戳进行倒序排序
        file_list.sort(
            key=lambda fp: os.path.getmtime(fp) if not os.path.isdir(fp) else 0
        )
        return file_list[-1]
    except FileNotFoundError as fnf:
        print(fnf)


def count_run_times(return_num=False, clear=None):
    """
    用于统计方法运行次数
    :param return_num: 是否返回运行的次数
    :param clear: 在运行次数为多少时清零
    :return: 原函数返回值,运行次数(可选)
    """

    def ct(func):
        num = 0

        def call_func(*args, **kwargs):
            func_return = func(*args, **kwargs)
            nonlocal num
            if num is clear:
                num = 0
            num = num + 1
            print(num)
            if return_num:
                return func_return, num
            return func_return

        return call_func

    return ct


def get_host_ip():
    import socket

    socket_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_socket.connect(("8.8.8.8", 80))
    return socket_socket.getsockname()[0]


def pickle_op(file="a.pkl", data=None):
    from pickle import dump, load

    s = "rb" if data is None else "wb"
    with open(file, s) as f:
        result = dump(data, f) if data is not None else load(f)
    return result if data is None else None


def flat(d, keep_parent=False):
    for key, value in d.items():
        if isinstance(value, dict):
            for k, v in flat(value):
                if keep_parent:
                    k = f"{key}_{k}"
                yield k, v
        else:
            yield key, value


def flat_dict(data, keep_parent=False):
    return {k: v for k, v in flat(data, keep_parent)}


def flat_list_dict(data):
    return [flat_dict(d) for d in data]


def create_factory(cls):
    class Factory(cls):
        instance = {}
        is_init = False

        def __new__(cls, name, *args, **kwargs):
            """根据kwargs中的name参数创建cls实例,如果name实例存在则返回,不存在则创建"""
            if cls.instance.get(name) is None:
                cls.instance[name] = super().__new__(cls)
            else:
                cls.is_init = True
            return cls.instance[name]

        def __init__(self, name, *args, **kwargs):
            if Factory.is_init:
                Factory.is_init = False
                return
            print("factory init")
            super().__init__(*args, **kwargs)

    return Factory


class ProgressBar(object):
    # 没有加线程锁, 可能有问题, 参考tqdm的实现
    _instances = WeakSet()

    def __init__(
        self,
        iterable,
        description="",
        length=None,
        print_param=True,
        wrap=False,
        out_file=False,
    ):
        self._data = iterable
        self._description = description
        self._length = length
        self._print_param = print_param
        self._wrap = wrap
        self._out_file = out_file
        self._first_param = None
        self._last_param = None
        self._start = time.perf_counter()
        self._bar_length = 30
        if self._length is None and getattr(self._data, "__len__", None):
            self._length = len(self._data)
        self.refresh(0, "")

    def refresh(self, index, item):
        if index == 1:
            self._first_param = item
        bar = f'[{" " * 20}]'
        percentage = "?%"
        total = "?"
        if self._length:
            percent = index / self._length
            bar_prefix_length = int(percent * self._bar_length)
            bar = f"[{'=' * bar_prefix_length}{' ' * (self._bar_length - bar_prefix_length)}]"
            percentage = f"{percent * 100:.2f}%"
            total = str(self._length)
        duration = time.perf_counter() - self._start
        prefix = "\r"
        if len(self._instances) > 1 or self._wrap:
            prefix = "\n"
        ad = f"平均耗时:{duration / index:.2f}s" if index else ""
        td = f"总耗时:{duration:.2f}s" if index else ""
        current_param = f"参数:[{item}]" if index and self._print_param else ""
        text = f"{self._description}{bar} {percentage} {index}/{total} {ad} {td} {current_param}"
        if self._out_file:
            logging.error(text)
        else:
            print(prefix + text, end="", flush=True)
        self._last_param = item

    def __iter__(self):
        for i, item in enumerate(self._data, 1):
            yield item
            self.refresh(i, item)
        if self._print_param:
            text = f" 第一参数:{self._first_param} 最后参数:{self._last_param} 结束"
            if self._out_file:
                logging.error(text)
            else:
                print(text)

    def __new__(cls, *args, **kwargs):
        instance = object.__new__(cls)
        cls._instances.add(instance)
        return instance


def analyze_time(func, show_all=False, console=False):
    from pyinstrument import Profiler

    profiler = Profiler()

    def wrapper(*args, **kwargs):
        profiler.start()
        func_return = func(*args, **kwargs)
        profiler.stop()
        if console:
            profiler.print(
                unicode=True,
                color=True,
                show_all=show_all,
            )
        else:
            logging.info(
                profiler.output_text(
                    unicode=True,
                    color=True,
                    show_all=show_all,
                )
            )
        return func_return

    return wrapper


def hum_convert(value, return_all=False):
    units = ["B", "KB", "MB", "GB"]  # 'TB','PB'
    size = 1024.0
    result = []
    for i in range(len(units)):
        result.append(f"{round(value, 2)}{units[i]}")
        if not return_all and (value / size) < 1:
            return result.pop(-1)

        value = value / size
    return result


def get_var_name(var):
    for fi in reversed(inspect.stack()):
        names = [
            var_name
            for var_name, var_val in fi.frame.f_locals.items()
            if var_val is var
        ]
        if len(names) > 0:
            return names


def construct_dict(values):
    """
    根据一组变量自动生成变量名对应的数值, 在pycharm debug的时候会有变量名错误的情况
    如果有相同值的变量,则返回先出现的变量名
    :param values: list [a, b, c]
    :return: dict {'a':xxx, 'b':xxx, 'c':xxx}
    """
    tmp = {}
    for value in values:
        tmp_key = get_var_name(value)
        for key in tmp_key:
            if key not in tmp:
                tmp[key] = value
                break
    return tmp


def is_float(value: str):
    flag = True
    try:
        float(value)
    except ValueError:
        flag = False
    return flag


def auto_type(value: str):
    if value.isdigit():
        value = int(value)
    elif value.isalnum():
        pass
    elif is_float(value):
        value = float(value)
    return value


files = [Path(file).name for file in get_dir_files(Path(__file__).parent, "py", "end")]
files = {file for file in files if not file.startswith("__")}

#
# @app.before_request
# def start_timer():
#     request.start_time = time.time()
#     pr = cProfile.Profile()
#     pr.enable()
#     request.pr = pr
#
#
# @app.after_request
# def log_request(response):
#     total_time = time.time() - request.start_time
#     logging.info(f"耗时{total_time :.2f}秒")
#     pr = request.pr
#     pr.disable()
#     if total_time > 30:
#         s = io.StringIO()
#         p = pstats.Stats(pr, stream=s)
#         p.strip_dirs().sort_stats(pstats.SortKey.CUMULATIVE).print_stats(250)
#         split = s.getvalue().split("\n")
#         header = split[0].strip() + "\n" + split[5]
#         body = [cost for cost in split[6:56] if any(file in cost for file in files)]
#         logging.warning(header + "\n".join([""] + body))
#     return response


def get_error():
    error = traceback.format_exc()
    split = error.split("\n")
    _ = split.pop()
    key_error = split.pop()
    errors = []
    delete_num = 0
    for row in reversed(split):
        if row.startswith(f'  File "{Path(__file__).parent.parent}'):
            delete_num = 0
            errors.append(row)
        elif "site-packages" in row:
            errors = errors[:-delete_num]
            delete_num = 0
        else:
            delete_num += 1
            errors.append(row)
    errors = errors[:12]
    errors.insert(0, key_error)
    return errors[::-1]


def handle_error(
    error_message: Optional[Union[str, Callable[[], str]]] = None,
    reraise: bool = False,
    default_return: Any = None,
    log_level: int = logging.ERROR,
    include_func_name: bool = True,
) -> Callable:
    """
    通用错误处理装饰器

    用于包装函数，自动捕获异常并记录详细的错误日志（包括完整的堆栈追踪）

    :param error_message: 自定义错误消息，如果为None则使用默认消息
    :param reraise: 是否在记录日志后重新抛出异常，默认False
    :param default_return: 当异常发生且不重新抛出时的返回值，默认None
    :param log_level: 日志级别，默认ERROR
    :param include_func_name: 是否在错误消息前添加"函数 xxx"，默认True
    :return: 装饰后的函数

    示例:
        # 基本用法 - 捕获异常并记录，不中断流程
        @handle_error(error_message="处理用户数据失败")
        def process_user_data():
            pass

    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                # 构建错误消息
                base_msg = error_message if error_message else "执行失败"
                msg = f"函数 {func.__name__} {base_msg}" if include_func_name else base_msg

                # 记录日志，包含完整的堆栈追踪
                logging.log(log_level, msg, exc_info=True)

                # 根据配置决定是否重新抛出异常
                if reraise:
                    raise

                return default_return

        return wrapper

    return decorator


def error_context(
    error_message: Union[str, Callable[[], str]],
    reraise: bool = False,
    log_level: int = logging.ERROR,
) -> ContextManager[None]:
    """
    错误处理上下文管理器

    用于在代码块中捕获异常并记录日志

    :param error_message: 错误消息（字符串或callable）
    :param reraise: 是否重新抛出异常
    :param log_level: 日志级别

    示例:
        # 记录后重新抛出
        with error_context("关键操作失败", reraise=True):
            critical_operation()

        # 使用 lambda 访问作用域内的变量
        payload = []
        with error_context(lambda: f"af数据报错!\\n{payload}"):
            payload = fetch_data()
            process_data(payload)
    """
    from contextlib import contextmanager

    @contextmanager
    def _error_context():
        try:
            yield
        except Exception:
            # 如果 error_message 是 callable，则调用它获取消息
            msg = error_message() if callable(error_message) else error_message
            logging.log(log_level, msg, exc_info=True)
            if reraise:
                raise

    return _error_context()


def fb_api_retry(func):
    """
    Facebook API 重试装饰器
    用于处理 Facebook API 的临时性错误（HTTP 500）
    重试策略：最多3次，每次间隔10秒
    """
    from functools import wraps
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_fixed,
        retry_if_exception,
        before_sleep_log,
    )
    from facebook_business.exceptions import FacebookRequestError
    import requests.exceptions

    def is_facebook_transient_error(exception):
        """判断是否为Facebook临时性错误（500错误 / 网络超时 / 连接异常）"""
        if isinstance(
            exception,
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
        ):
            return True
        if isinstance(exception, FacebookRequestError):
            if hasattr(exception, 'http_status') and exception.http_status() == 500:
                return True
            if hasattr(exception, 'body'):
                error_data = exception.body().get('error', {})
                if error_data.get('is_transient', False):
                    return True
        return False

    @wraps(func)
    @retry(
        retry=retry_if_exception(is_facebook_transient_error),
        wait=wait_fixed(10),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logging.getLogger(), logging.WARNING),
        reraise=True,
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


if __name__ == "__main__":
    print(
        list(get_time_between("2023-10-09 17:12:00", "2023-10-10 00:00:00", "hours", 3))
    )
    pass
