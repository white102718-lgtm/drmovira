"""asyncmy 0.2.16 在 Windows BufferedProtocol 大包接收中的限定兼容。

CPython 的 BufferedProtocol 适配器在下一次 get_buffer 调用时可能仍持有
上一次的 memoryview；此时原驱动 bytearray.extend 会抛 BufferError。
仅在确实出现导出视图冲突时复制缓冲区，保留原驱动的压缩、扩容和解析逻辑。
不改变事件循环策略、包大小限制、SQL 协议或第三方安装文件。
"""

import sys
from importlib.metadata import version

from asyncmy import connection

_ORIGINAL_PROTOCOL = connection._MySQLProtocol
_ORIGINAL_GET_BUFFER = _ORIGINAL_PROTOCOL.get_buffer
_SUPPORTED_VERSION = '0.2.16'


def _export_safe_get_buffer(self: _ORIGINAL_PROTOCOL, sizehint: int) -> memoryview:
    """保留原协议方法；仅导出冲突时更换数组，不释放调用者持有的视图。"""
    try:
        return _ORIGINAL_GET_BUFFER(self, sizehint)
    except BufferError:
        # 原方法已完成同长度压缩/位置更新；完整复制保留尚未消费的数据。
        self.buffer = bytearray(self.buffer)
        return _ORIGINAL_GET_BUFFER(self, sizehint)


class ExportSafeMySQLProtocol(_ORIGINAL_PROTOCOL):
    """供独立测试直接对照原方法和兼容方法。"""

    get_buffer = _export_safe_get_buffer


def install_windows_asyncmy_compat() -> bool:
    """仅为锁定版本/平台安装一次；其他平台沿用原协议，不修改 asyncio。"""
    if sys.platform != 'win32' or version('asyncmy') != _SUPPORTED_VERSION:
        return False
    if _ORIGINAL_PROTOCOL.get_buffer is _export_safe_get_buffer:
        return True
    if _ORIGINAL_PROTOCOL.get_buffer is not _ORIGINAL_GET_BUFFER:
        raise RuntimeError('asyncmy protocol has an unexpected replacement')
    # 原类和已有实例统一使用兼容方法；不改第三方文件或 asyncio 全局实现。
    _ORIGINAL_PROTOCOL.get_buffer = _export_safe_get_buffer
    return True
