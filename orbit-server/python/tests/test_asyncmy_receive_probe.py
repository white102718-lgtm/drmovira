"""标准库真实helper与原驱动/限定兼容对照，无MySQL/SQL/安装文件改动。"""

import asyncio
import json

import pytest
from config import asyncmy_compat as compat
from tools.launch_allocation_asyncmy_receive_probe import (
    binary_payload,
    buffer_probe,
    feed_data_probe,
    protocol_factories,
)


def test_actual_stdlib_helper_reproduces_original_5mib_buffer_error_without_database():
    baseline, _ = protocol_factories()
    result = asyncio.run(feed_data_probe(baseline))
    assert baseline.get_buffer is compat._ORIGINAL_GET_BUFFER
    assert result["failure_type"] == "BufferError"
    assert result["complete"] is False
    assert 0 < result["received_bytes"] < result["expected_bytes"]
    assert result["official_helper_exercised"] is True
    assert result["real_transport_exercised"] is False
    assert result["database_used"] is False


@pytest.mark.parametrize("size", [1, 4096, 65536, 262144, 262145, 5 * 1024 * 1024])
def test_compat_actual_helper_preserves_every_binary_byte(size):
    result = asyncio.run(feed_data_probe(compat.ExportSafeMySQLProtocol, payload_bytes=size))
    assert result["complete"] is True
    assert result["binary_exact"] is True
    assert result["received_bytes"] == size
    assert result["failure_type"] is None


def test_original_and_safe_direct_held_view_boundaries_are_distinguished():
    baseline, safe = protocol_factories()
    original = asyncio.run(buffer_probe(baseline))
    fixed = asyncio.run(buffer_probe(safe))
    assert original["held_view_resize_failed"] is True
    assert original["released_view_resize_failed"] is False
    assert fixed["held_view_resize_failed"] is False
    assert fixed["released_view_resize_failed"] is False


def test_actual_helper_partial_buffer_then_64k_over_32k_space_requires_safe_fallback():
    async def run(factory):
        protocol = factory(asyncio.get_running_loop())
        first = binary_payload(len(protocol.buffer) - 32768)
        second = binary_payload(65536)
        asyncio.protocols._feed_data_to_buffered_proto(protocol, first)
        assert len(protocol.buffer) - protocol.length == 32768
        asyncio.protocols._feed_data_to_buffered_proto(protocol, second)
        return bytes(protocol.buffer[protocol.pos : protocol.length]) == first + second

    baseline, safe = protocol_factories()
    with pytest.raises(BufferError):
        asyncio.run(run(baseline))
    assert asyncio.run(run(safe)) is True


def test_held_view_survives_compaction_and_safe_growth_without_losing_unconsumed_bytes():
    async def run():
        protocol = compat.ExportSafeMySQLProtocol(asyncio.get_running_loop())
        initial = len(protocol.buffer)
        first, second = binary_payload(initial), binary_payload(initial)
        asyncio.protocols._feed_data_to_buffered_proto(protocol, first)
        old_buffer = protocol.buffer
        held = memoryview(old_buffer)
        consumed = initial // 4
        protocol.pos = consumed
        try:
            asyncio.protocols._feed_data_to_buffered_proto(protocol, second)
            assert protocol.pos == 0
            assert protocol.buffer is not old_buffer
            assert held.obj is old_buffer and len(held) == initial
            assert bytes(protocol.buffer[: protocol.length]) == first[consumed:] + second
        finally:
            held.release()

    asyncio.run(run())


def test_fully_consumed_large_buffer_can_shrink_with_an_old_export_still_alive():
    async def run():
        protocol = compat.ExportSafeMySQLProtocol(asyncio.get_running_loop())
        small_size = len(protocol.buffer)
        payload = binary_payload(5 * 1024 * 1024)
        asyncio.protocols._feed_data_to_buffered_proto(protocol, payload)
        assert len(protocol.buffer) > small_size * 4
        old_buffer = protocol.buffer
        held = memoryview(old_buffer)
        protocol.pos = protocol.length
        try:
            asyncio.protocols._feed_data_to_buffered_proto(protocol, b"\x00\xff\x80")
            assert len(protocol.buffer) == small_size
            assert protocol.buffer is not old_buffer
            assert bytes(protocol.buffer[: protocol.length]) == b"\x00\xff\x80"
            assert bytes(held[:256]) == bytes(range(256))
        finally:
            held.release()

    asyncio.run(run())


def test_many_partial_consume_receive_cycles_keep_bytes_and_all_old_exports_valid():
    async def run():
        protocol = compat.ExportSafeMySQLProtocol(asyncio.get_running_loop())
        expected, held = b"", []
        try:
            for index in range(12):
                consumed = len(expected) // 3
                protocol.pos += consumed
                expected = expected[consumed:]
                data = binary_payload(65536 + index * 73)
                held.append(memoryview(protocol.buffer))
                asyncio.protocols._feed_data_to_buffered_proto(protocol, data)
                expected += data
                assert bytes(protocol.buffer[protocol.pos : protocol.length]) == expected
                assert all(len(view) > 0 for view in held)
        finally:
            for view in held:
                view.release()

    asyncio.run(run())


def test_actual_installer_state_explicitly_changes_original_class_method(monkeypatch):
    # 不依赖config.database是否被其他测试导入；只在本测试进程内安装并在结束恢复。
    with monkeypatch.context() as isolated:
        isolated.setattr(compat._ORIGINAL_PROTOCOL, "get_buffer", compat._ORIGINAL_GET_BUFFER)
        assert compat._ORIGINAL_PROTOCOL.get_buffer is compat._ORIGINAL_GET_BUFFER
        actual_supported = compat.sys.platform == "win32" and compat.version("asyncmy") == "0.2.16"
        assert compat.install_windows_asyncmy_compat() is actual_supported
        if actual_supported:
            assert compat._ORIGINAL_PROTOCOL.get_buffer is compat._export_safe_get_buffer
            assert asyncio.run(feed_data_probe(compat._ORIGINAL_PROTOCOL))["binary_exact"] is True
            assert compat.install_windows_asyncmy_compat() is True
            # 安装后原baseline仍确实调用原方法，不能误拿已经修复的类证明复现。
            baseline, _ = protocol_factories()
            assert asyncio.run(feed_data_probe(baseline))["failure_type"] == "BufferError"
        else:
            assert compat._ORIGINAL_PROTOCOL.get_buffer is compat._ORIGINAL_GET_BUFFER


@pytest.mark.parametrize(
    "platform,version", [("linux", "0.2.16"), ("win32", "0.2.15"), ("win32", "0.2.17")]
)
def test_installer_does_not_change_unsupported_platform_or_version(monkeypatch, platform, version):
    with monkeypatch.context() as isolated:
        isolated.setattr(compat._ORIGINAL_PROTOCOL, "get_buffer", compat._ORIGINAL_GET_BUFFER)
        isolated.setattr(compat.sys, "platform", platform)
        isolated.setattr(compat, "version", lambda _name: version)
        assert compat.install_windows_asyncmy_compat() is False
        assert compat._ORIGINAL_PROTOCOL.get_buffer is compat._ORIGINAL_GET_BUFFER


def test_probe_result_is_only_small_fixed_metadata_no_binary_or_sql_output(capsys):
    result = asyncio.run(feed_data_probe(compat.ExportSafeMySQLProtocol))
    assert len(json.dumps(result)) < 1000
    assert capsys.readouterr().out == ""
    assert not any(isinstance(value, bytes | bytearray | memoryview) for value in result.values())
