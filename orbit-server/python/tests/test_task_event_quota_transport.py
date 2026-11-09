"""真实httpx/httpcore HTTP1迭代生命周期；内存网络替身，不计服务端配额验收。"""

import gc
import sys
from pathlib import Path

import httpcore
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from task_event_boundary_checks import confirm_keepalive, hold_idle_stream  # noqa: E402
from task_event_stream_checks import hold_idle_streams  # noqa: E402


class TrackingBackend(httpcore.MockBackend):
    def __init__(self, fail_at=None):
        chunk = b": keepalive\n\n"
        # 未结束的HTTP1 chunked流；由真实httpcore处理GeneratorExit关闭，非MockTransport。
        super().__init__(
            [
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
                b"Content-Type: text/event-stream\r\n\r\n"
                + format(len(chunk), "x").encode()
                + b"\r\n"
                + chunk
                + b"\r\n"
            ]
        )
        self.streams, self.fail_at = [], fail_at

    def connect_tcp(self, *args, **kwargs):
        stream = super().connect_tcp(*args, **kwargs)
        self.streams.append(stream)
        if len(self.streams) == self.fail_at:
            stream._buffer = [b"HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n"]
        return stream


def client_for(backend):
    transport = httpx.HTTPTransport()
    transport._pool.close()
    transport._pool = httpcore.ConnectionPool(network_backend=backend)
    return httpx.Client(transport=transport, base_url="http://fixture.invalid")


def test_temporary_iterator_closes_network_while_response_still_appears_open():
    backend = TrackingBackend()
    with client_for(backend) as client, client.stream("GET", "/events") as response:
        assert next(response.iter_lines()) == ": keepalive"
        gc.collect()
        assert backend.streams[0]._closed
        assert not response.is_closed  # 仅检查Response不是可靠的连接存续证明。


def test_all_four_real_httpcore_streams_stay_open_until_fifth_check_finishes():
    backend = TrackingBackend()
    with client_for(backend) as client:
        with pytest.raises(RuntimeError, match="controlled-fifth-check"):
            with hold_idle_streams(client, "/events", {}) as held:
                gc.collect()
                assert len(held) == len(backend.streams) == 4
                assert not any(stream._closed for stream in backend.streams)
                # 第五断言失败也必须释放全部连接；不模拟服务端429为成功验收。
                raise RuntimeError("controlled-fifth-check")
        assert all(stream._closed for stream in backend.streams)


def test_partial_open_failure_releases_already_open_responses_and_iterators():
    backend = TrackingBackend(fail_at=2)
    with client_for(backend) as client:
        with pytest.raises(AssertionError) as failure:
            with hold_idle_streams(client, "/events", {}):
                raise AssertionError("should-not-yield")
        assert failure.value.args == ({"actual": 503, "expected": 200},)
        assert len(backend.streams) == 2
        assert all(stream._closed for stream in backend.streams)


def test_idle_sampling_keeps_iterator_and_reads_again_before_disconnect():
    backend = TrackingBackend()
    chunk = b": keepalive\n\n"
    backend._buffer.append(format(len(chunk), "x").encode() + b"\r\n" + chunk + b"\r\n")
    with client_for(backend) as client:
        with hold_idle_stream(client, "/events", {}) as lines:
            gc.collect()
            assert not backend.streams[0]._closed
            confirm_keepalive(lines)
            assert not backend.streams[0]._closed
        assert backend.streams[0]._closed
