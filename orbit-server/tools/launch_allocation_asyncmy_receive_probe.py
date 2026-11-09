"""无数据库的大包复现：默认标准库真实馈送helper；TCP仅用自有随机端口。"""

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import sys
import time
from pathlib import Path


def protocol_factories():
    """显式保留原方法baseline；即使框架已安装补丁也不把已修复类误当原版。"""
    module = sys.modules.get("config.asyncmy_compat")
    if module is None:
        path = Path(__file__).resolve().parents[1] / "python/ruoyi_fastapi/config/asyncmy_compat.py"
        spec = importlib.util.spec_from_file_location("orbit_receive_probe_compat", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    class BaselineProtocol(module._ORIGINAL_PROTOCOL):
        get_buffer = module._ORIGINAL_GET_BUFFER

    return BaselineProtocol, module.ExportSafeMySQLProtocol


def binary_payload(size):
    if type(size) is not int or not 1 <= size <= 8 * 1024 * 1024:
        raise ValueError("复现输入只允许1字节至8MiB")
    return (bytes(range(256)) * ((size + 255) // 256))[:size]


async def feed_data_probe(protocol_factory=None, *, payload_bytes=5 * 1024 * 1024):
    """调用stdlib官方helper，保留真实上轮buf引用生命周期，不模拟其拷贝循环。"""
    protocol_factory = protocol_factory or protocol_factories()[0]
    protocol = protocol_factory(asyncio.get_running_loop())
    payload = binary_payload(payload_bytes)
    failure = None
    try:
        asyncio.protocols._feed_data_to_buffered_proto(protocol, payload)
    except BufferError:
        failure = "BufferError"
    received = bytes(protocol.buffer[protocol.pos : protocol.length])
    return {
        "mode": "stdlib-feed-data-helper",
        "expected_bytes": payload_bytes,
        "received_bytes": len(received),
        "complete": received == payload,
        "binary_exact": received == payload,
        "failure_type": failure,
        "official_helper_exercised": True,
        "real_transport_exercised": False,
        "database_used": False,
    }


async def buffer_probe(protocol_factory=None):
    """仅证明导出view与原位扩容冲突，不据此声称实际transport必然保留view。"""
    loop = asyncio.get_running_loop()
    protocol = (protocol_factory or protocol_factories()[0])(loop)
    view = protocol.get_buffer(-1)
    initial = len(view)
    protocol.buffer_updated(initial)
    held_failed = False
    try:
        next_view = protocol.get_buffer(-1)
    except BufferError:
        held_failed = True
    else:
        next_view.release()
    view.release()
    released_failed = False
    try:
        next_view = protocol.get_buffer(-1)
    except BufferError:
        released_failed = True
    else:
        next_view.release()
    return {
        "mode": "buffer-only",
        "initial_buffer_bytes": initial,
        "held_view_resize_failed": held_failed,
        "released_view_resize_failed": released_failed,
        "real_transport_exercised": False,
        "database_used": False,
    }


async def tcp_probe(protocol_factory=None, *, gated=False):
    """仅在显式--tcp时启动短命随机端口发送固定5MiB；没有MySQL握手/SQL。"""
    loop = asyncio.get_running_loop()
    payload_bytes = 5 * 1024 * 1024
    observed_errors = []
    previous_handler = loop.get_exception_handler()
    start = time.monotonic()
    payload = binary_payload(payload_bytes)
    protocol = (protocol_factory or protocol_factories()[0])(loop)
    first_gate, second_gate = asyncio.Event(), asyncio.Event()
    prefill = len(protocol.buffer) - 32768
    if gated and prefill < 0:
        raise ValueError("原接收buffer过小，当前受控边界不适用")
    remaining_before_gate = None
    send_tasks = set()

    def exception_handler(_loop, context):
        error = context.get("exception")
        observed_errors.append(type(error).__name__ if error else "CallbackFailure")

    async def send(_reader, writer):
        send_tasks.add(asyncio.current_task())
        try:
            offset = 0
            if gated:
                writer.write(payload[:prefill])
                await writer.drain()
                await first_gate.wait()
                writer.write(payload[prefill : prefill + 65536])
                await writer.drain()
                await second_gate.wait()
                offset = prefill + 65536
            while offset < payload_bytes and protocol.exc is None:
                writer.write(payload[offset : offset + 65536])
                await writer.drain()
                offset += 65536
        except (OSError, RuntimeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    transport = None
    server = None
    loop.set_exception_handler(exception_handler)
    failure = None
    try:
        server = await asyncio.start_server(send, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        transport, _ = await loop.create_connection(lambda: protocol, "127.0.0.1", port)

        async def receive():
            nonlocal remaining_before_gate
            if gated:
                while protocol.length - protocol.pos < prefill and not protocol.eof:
                    await protocol.wait_for_data(prefill)
                remaining_before_gate = len(protocol.buffer) - protocol.length
                first_gate.set()
                try:
                    target = prefill + 65536
                    while protocol.length - protocol.pos < target and not protocol.eof:
                        await protocol.wait_for_data(target)
                finally:
                    second_gate.set()
            while protocol.length - protocol.pos < payload_bytes:
                if protocol.eof or protocol.exc is not None:
                    break
                await protocol.wait_for_data(payload_bytes)

        try:
            await asyncio.wait_for(receive(), timeout=8)
        except TimeoutError:
            failure = "ReceiveTimeout"
        if protocol.exc is not None:
            failure = type(protocol.exc).__name__
        return {
            "mode": "event-gated-loopback-tcp" if gated else "ephemeral-loopback-tcp",
            "event_loop": type(loop).__name__,
            "expected_bytes": payload_bytes,
            "received_bytes": protocol.length - protocol.pos,
            "complete": protocol.length - protocol.pos == payload_bytes,
            "binary_exact": bytes(protocol.buffer[protocol.pos : protocol.length]) == payload,
            "failure_type": failure,
            "callback_error_types": sorted(set(observed_errors)),
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "real_transport_exercised": True,
            "database_used": False,
            "remaining_before_gate": remaining_before_gate,
            "tcp_buffer_error_reproduced": failure == "BufferError"
            or "BufferError" in observed_errors,
        }
    finally:
        if transport is not None:
            transport.close()
        first_gate.set()
        second_gate.set()
        if server is not None:
            server.close()
            await server.wait_closed()
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
        loop.set_exception_handler(previous_handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tcp", action="store_true")
    group.add_argument("--tcp-gated", action="store_true")
    group.add_argument("--buffer", action="store_true")
    parser.add_argument("--compat", action="store_true")
    arguments = parser.parse_args()
    factory = protocol_factories()[1 if arguments.compat else 0]
    if arguments.tcp or arguments.tcp_gated:
        operation = tcp_probe(factory, gated=arguments.tcp_gated)
    elif arguments.buffer:
        operation = buffer_probe(factory)
    else:
        operation = feed_data_probe(factory)
    result = asyncio.run(operation)
    print(json.dumps({"asyncmy_version": importlib.metadata.version("asyncmy"), **result}))


if __name__ == "__main__":
    main()
