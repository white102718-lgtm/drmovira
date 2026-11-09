"""只读适配器传输边界；全部生成凭据，不访问真实OpenAI/Claude网络。"""

import httpx
import pytest

from orbit_api.connection_probe import (
    BLOCKED,
    FAILED,
    GRAPH_VERIFIED,
    VERIFIED,
    ModelConnectionProbe,
)


@pytest.mark.parametrize("section", ["META_APP", "META_BM"])
async def test_meta_fixed_object_get_never_places_credential_in_query(section):
    def transport(request):
        assert request.method == "GET"
        assert str(request.url) == "https://graph.facebook.com/v25.0/000123?fields=id%2Cname"
        credential = "000123|fixture-key" if section == "META_APP" else "fixture-key"
        assert request.headers["authorization"] == "Bearer " + credential
        return httpx.Response(200, json={"id": "000123", "name": "只读夹具"})

    probe = ModelConnectionProbe(transport=httpx.MockTransport(transport))
    result = await probe.run(
        section,
        True,
        {"appId": "000123", "businessId": "000123", "graphVersion": "v25.0"},
        "fixture-key",
    )
    assert result == GRAPH_VERIFIED


@pytest.mark.parametrize(
    "response", [{"id": "wrong-object"}, {"id": "123", "error": {"message": "fixture-key"}}]
)
async def test_meta_wrong_object_and_error_envelope_never_verified(response):
    probe = ModelConnectionProbe(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    )
    assert (
        await probe.run("META_BM", True, {"businessId": "123", "graphVersion": "v25.0"}, "key")
        == FAILED
    )


@pytest.mark.parametrize("section", ["AI_GPT", "AI_CLAUDE"])
async def test_model_probe_uses_only_fixed_official_get_and_headers(section):
    seen = []

    def transport(request):
        seen.append(request)
        expected = "api.openai.com" if section == "AI_GPT" else "api.anthropic.com"
        assert request.url.host == expected and request.url.scheme == "https"
        assert request.method == "GET" and not request.content and not request.url.query
        assert request.headers["authorization"] == "Bearer fixture-secret"
        assert "fixture-secret" not in str(request.url)
        if section == "AI_CLAUDE":
            assert request.headers["anthropic-version"] == "2026-10-21"
            assert request.headers["anthropic-workspace-id"] == "wrkspc_fixture"
        return httpx.Response(
            200, json={"id": "resolved-model", "object": "model", "type": "model"}
        )

    probe = ModelConnectionProbe(transport=httpx.MockTransport(transport))
    result = await probe.run(
        section,
        True,
        {
            "model": "alias/with?unsafe#characters",
            "apiVersion": "2026-10-21",
            "workspaceId": "wrkspc_fixture",
        },
        "fixture-secret",
    )
    assert result == VERIFIED and len(seen) == 1
    assert b"%2F" in seen[0].url.raw_path


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 404, 429, 500])
async def test_error_and_redirect_never_follow_or_echo_response(status):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://evil.invalid/leak"},
            text="fixture-secret raw provider error",
        )

    result = await ModelConnectionProbe(transport=httpx.MockTransport(transport)).run(
        "AI_GPT", True, {"model": "test"}, "fixture-secret"
    )
    assert result == FAILED and len(calls) == 1
    assert "fixture-secret" not in repr(result)


@pytest.mark.parametrize(
    "value", [[], {}, {"id": 1}, {"id": "", "object": "model"}, {"id": "a", "object": "other"}]
)
async def test_http_200_is_not_enough_for_verified(value):
    probe = ModelConnectionProbe(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=value))
    )
    assert await probe.run("AI_GPT", True, {"model": "test"}, "fixture-secret") == FAILED


async def test_response_size_malformed_and_timeout_are_safe():
    responses = [
        httpx.Response(200, text="not json"),
        httpx.Response(200, content=b"x" * 65_537, headers={"content-type": "application/json"}),
    ]
    for response in responses:
        probe = ModelConnectionProbe(transport=httpx.MockTransport(lambda _, r=response: r))
        assert await probe.run("AI_GPT", True, {"model": "test"}, "fixture-secret") == FAILED

    def timeout(request):
        raise httpx.ReadTimeout("fixture-secret must never leak", request=request)

    probe = ModelConnectionProbe(transport=httpx.MockTransport(timeout))
    assert await probe.run("AI_GPT", True, {"model": "test"}, "fixture-secret") == FAILED


@pytest.mark.parametrize(
    "section,enabled,settings,key",
    [
        ("OIDC", True, {"model": "test"}, "key"),
        ("AI_GPT", False, {"model": "test"}, "key"),
        ("AI_GPT", True, {"model": ".."}, "key"),
        ("AI_GPT", True, {"model": "test"}, None),
        ("AI_CLAUDE", True, {"model": "test", "apiVersion": "invalid"}, "key"),
    ],
)
async def test_ineligible_probe_never_sends_request(section, enabled, settings, key):
    def forbidden(_):
        raise AssertionError("不具备条件时不能发送请求")

    probe = ModelConnectionProbe(transport=httpx.MockTransport(forbidden))
    assert await probe.run(section, enabled, settings, key) == BLOCKED
