"""执行机只读探测合同；mock回执不能作为真实AdsPower能力验收。"""

import asyncio
from unittest.mock import patch

import httpx
import pytest


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.1:50325",
        "http://2130706433:50325",
        "http://user:secret@127.0.0.1:50325",
        "http://127.0.0.1:50325?key=secret",
        "http://127.0.0.1:50325#fragment",
        " http://localhost:50325",
        "http://localhost:050325",
        "http://localhost:50325/../",
    ],
)
def test_endpoint_rejects_noncanonical_or_unapproved_targets(endpoint):
    from orbit_agent.adspower_status import ProbeError, canonical_endpoint

    with pytest.raises(ProbeError) as failure:
        canonical_endpoint(endpoint)
    assert failure.value.code == "ENDPOINT_REJECTED"
    assert "secret" not in str(failure.value)


def test_localhost_is_pinned_to_literal_loopback_and_port_allowlist():
    from orbit_agent.adspower_status import canonical_endpoint

    assert canonical_endpoint("http://localhost:50325/") == "http://127.0.0.1:50325"
    assert (
        canonical_endpoint("http://127.0.0.1:50326", allowed_ports={50326})
        == "http://127.0.0.1:50326"
    )


async def probe(handler, **kwargs):
    from orbit_agent.adspower_status import probe_status

    original = httpx.AsyncClient

    def factory(**options):
        assert options["trust_env"] is False
        assert options["follow_redirects"] is False
        return original(**options, transport=httpx.MockTransport(handler))

    with patch("orbit_agent.adspower_status.httpx.AsyncClient", factory):
        return await probe_status(**kwargs)


async def test_only_status_get_reports_availability_without_platform_capabilities():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "http://127.0.0.1:50325/status"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, json={"code": 0, "msg": "success", "extra": "do-not-echo"})

    result = await probe(handler)
    assert result == {
        "api_status": "AVAILABLE",
        "profile_status": "UNKNOWN",
        "meta_login_status": "UNKNOWN",
        "execution_capability": "UNVERIFIED",
    }
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response,code",
    [
        (
            httpx.Response(302, headers={"location": "https://example.com/secret"}),
            "REDIRECT_REJECTED",
        ),
        (httpx.Response(401, text="private auth detail"), "AUTHENTICATION_REQUIRED"),
        (httpx.Response(500, text="private body"), "HTTP_STATUS_REJECTED"),
        (httpx.Response(200, json={"code": True}), "RESPONSE_INVALID"),
        (httpx.Response(200, json={"code": 1, "msg": "private reason"}), "API_UNAVAILABLE"),
        (httpx.Response(200, content=b"x" * 4097), "RESPONSE_TOO_LARGE"),
        (httpx.Response(200, content=b'{"code":0,"code":1}'), "RESPONSE_INVALID"),
    ],
)
async def test_errors_are_bounded_safe_and_never_return_remote_messages(response, code):
    from orbit_agent.adspower_status import ProbeError

    with pytest.raises(ProbeError) as failure:
        await probe(lambda request: response)
    assert failure.value.code == code
    assert "private" not in str(failure.value)
    assert "secret" not in str(failure.value)


async def test_total_timeout_covers_slow_response():
    from orbit_agent.adspower_status import ProbeError

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"code": 0})

    with pytest.raises(ProbeError) as failure:
        await probe(handler, timeout_seconds=0.01)
    assert failure.value.code == "PROBE_TIMEOUT"


async def test_key_is_only_loaded_from_private_regular_file_and_never_echoed(tmp_path):
    key = tmp_path / "api-key"
    key.write_text("fixture-only-key\n")
    key.chmod(0o600)

    def handler(request):
        assert request.headers["authorization"] == "Bearer fixture-only-key"
        return httpx.Response(200, json={"code": 0})

    result = await probe(handler, api_key_file=key)
    assert "fixture-only-key" not in repr(result)


@pytest.mark.parametrize("unsafe", ["permissions", "symlink", "newline", "large"])
def test_unsafe_key_files_fail_without_exposing_contents(tmp_path, unsafe):
    from orbit_agent.adspower_status import ProbeError, read_api_key

    key = tmp_path / "key"
    key.write_text("private-value")
    key.chmod(0o600)
    if unsafe == "permissions":
        key.chmod(0o644)
    elif unsafe == "symlink":
        link = tmp_path / "link"
        link.symlink_to(key)
        key = link
    elif unsafe == "newline":
        key.write_text("private-value\nHeader: injected")
    else:
        key.write_text("p" * 4097)
    with pytest.raises(ProbeError) as failure:
        read_api_key(key)
    assert "private-value" not in str(failure.value)


async def test_chunked_body_without_length_is_bounded_and_closed():
    from orbit_agent.adspower_status import ProbeError

    class Stream(httpx.AsyncByteStream):
        closed = False
        reads = 0

        async def __aiter__(self):
            for _ in range(100):
                self.reads += 1
                yield b"x" * 2048

        async def aclose(self):
            self.closed = True

    stream = Stream()
    with pytest.raises(ProbeError) as failure:
        await probe(lambda request: httpx.Response(200, stream=stream))
    assert failure.value.code == "RESPONSE_TOO_LARGE"
    assert stream.closed and stream.reads <= 4


async def test_compressed_body_rejected_before_reading():
    from orbit_agent.adspower_status import ProbeError

    class Unreadable(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("不得读取压缩响应")
            yield b""

    with pytest.raises(ProbeError) as failure:
        await probe(
            lambda request: httpx.Response(
                200, headers={"content-encoding": "gzip"}, stream=Unreadable()
            )
        )
    assert failure.value.code == "RESPONSE_ENCODING_REJECTED"


async def test_connection_failure_never_echoes_exception_or_credentials():
    from orbit_agent.adspower_status import ProbeError

    def handler(request):
        raise httpx.ConnectError("private token in upstream exception", request=request)

    with pytest.raises(ProbeError) as failure:
        await probe(handler)
    assert str(failure.value) == "CONNECTION_FAILED"
    assert failure.value.__suppress_context__


@pytest.mark.parametrize("timeout", [0, -1, 11, float("inf"), float("nan"), True])
async def test_timeout_configuration_is_bounded(timeout):
    from orbit_agent.adspower_status import ProbeError

    with pytest.raises(ProbeError) as failure:
        await probe(lambda request: pytest.fail("非法超时不应发送请求"), timeout_seconds=timeout)
    assert failure.value.code == "TIMEOUT_REJECTED"


def test_cli_defaults_to_status_and_serializes_only_safe_failure(monkeypatch, capsys):
    from orbit_agent import adspower_status as module

    async def fail(endpoint, **kwargs):
        assert endpoint == "http://127.0.0.1:50325"
        assert kwargs["api_key_file"] is None
        raise module.ProbeError("CONNECTION_FAILED")

    monkeypatch.setattr(module, "probe_status", fail)
    assert module.main([]) == 1
    captured = capsys.readouterr()
    assert '"error_code": "CONNECTION_FAILED"' in captured.out
    assert captured.err == ""


async def test_status_uses_custom_https_api_base_path():
    def handler(request):
        assert str(request.url) == "https://device.example:5443/adspower/status"
        return httpx.Response(200, json={"code": 0})

    result = await probe(handler, endpoint="https://device.example:5443/adspower/")
    assert result["api_status"] == "AVAILABLE"
