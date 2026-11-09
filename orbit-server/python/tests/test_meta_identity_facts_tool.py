"""组合专项工具的安全与响应协议纯测，不代替真实SQL/Meta或网络锁观测。"""

import inspect
from types import SimpleNamespace

import httpx
import pytest
from tools.meta_observation_registry_checks import (
    IDENTITY_FACT_OBSERVATION_CASES,
    IDENTITY_PRINCIPAL_BINDING_CASES,
    META_OBSERVATION_REGISTRY_CASES,
    guard_meta_registry_target,
    identity_fact_protocol_response,
    run_meta_observation_registry_checks,
)


def request(path, *, fields="id", after=None, **kwargs):
    params = {"fields": fields}
    if path.endswith("assigned_users"):
        params |= {"business": "42", "limit": "200"}
        if after is not None:
            params["after"] = after
    return httpx.Request(
        "GET",
        "https://graph.facebook.com/v25.0/" + path,
        params=params,
        headers={"Authorization": "Bearer fixture-tool-secret"},
        **kwargs,
    )


def test_new_flag_is_opt_in_and_case_groups_are_separate_and_unique():
    signature = inspect.signature(run_meta_observation_registry_checks)
    assert signature.parameters["include_identity_facts"].default is False
    assert signature.parameters["include_identity_facts"].kind is inspect.Parameter.KEYWORD_ONLY
    assert len(META_OBSERVATION_REGISTRY_CASES) == 14
    assert len(IDENTITY_FACT_OBSERVATION_CASES) == 5
    assert len(set(META_OBSERVATION_REGISTRY_CASES + IDENTITY_FACT_OBSERVATION_CASES)) == 19
    assert len(IDENTITY_PRINCIPAL_BINDING_CASES) == 6
    assert (
        len(
            set(
                META_OBSERVATION_REGISTRY_CASES
                + IDENTITY_FACT_OBSERVATION_CASES
                + IDENTITY_PRINCIPAL_BINDING_CASES
            )
        )
        == 25
    )


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("production.invalid", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_not_uuid"),
    ],
)
def test_tool_rejects_nonisolated_target_before_any_cursor(host, port, database):
    admin = SimpleNamespace(host=host, port=port)
    with pytest.raises(ValueError):
        guard_meta_registry_target(admin, database)


@pytest.mark.parametrize("path", ["me", "009", "008", "007", "009/assigned_users"])
def test_controlled_identity_responses_are_explicit_facts_not_authority(path):
    fields = "id,business,user_type" if path.endswith("assigned_users") else "id"
    status, body = identity_fact_protocol_response(
        request(path, fields=fields), "fixture-tool-secret", "normal"
    )
    assert status == 200
    assert not {"usable", "verified", "capability_version", "execution_authorized"}.intersection(
        body
    )
    if path == "me":
        assert body["id"] == "17" and body["id"] != "7"
    elif path == "009":
        assert body["name"] == "页" * 4096 and body["can_post"] is False
    elif path == "008":
        assert body["name"] is None and body["is_restricted_use"] is True
    elif path == "007":
        assert body["name"] == "" and body["iphone_app_store_id"] == "001234"
        assert len(body["ios_bundle_id"]) == 2
    else:
        assert "tasks" not in body["data"][0]


def test_paging_fixture_requires_opaque_cursor_and_never_forwards_next_secret():
    fields = "id,business,user_type"
    _status, first = identity_fact_protocol_response(
        request("009/assigned_users", fields=fields),
        "fixture-tool-secret",
        "pagination",
    )
    assert "DO_NOT_FORWARD" in first["paging"]["next"]
    after = first["paging"]["cursors"]["after"]
    second_request = request("009/assigned_users", fields=fields, after=after)
    _status, second = identity_fact_protocol_response(
        second_request, "fixture-tool-secret", "pagination"
    )
    assert second["data"][0]["id"] != first["data"][0]["id"]
    assert "DO_NOT_FORWARD" not in str(second_request.url)
    _status, incomplete = identity_fact_protocol_response(
        request("009/assigned_users", fields=fields),
        "fixture-tool-secret",
        "incomplete",
    )
    assert "next" in incomplete["paging"] and "cursors" not in incomplete["paging"]


def test_permission_fixture_has_real_http_failure_and_missing_is_not_false():
    status, _body = identity_fact_protocol_response(
        request("me"), "fixture-tool-secret", "permission"
    )
    assert status == 403
    status, body = identity_fact_protocol_response(request("009"), "fixture-tool-secret", "missing")
    assert status == 200 and body == {"id": "009"}


def test_principal_match_fixture_is_separate_from_old_unbound_me_observation():
    status, original = identity_fact_protocol_response(
        request("me"), "fixture-tool-secret", "normal"
    )
    matched_status, matched = identity_fact_protocol_response(
        request("me"),
        "fixture-tool-secret",
        "principal_match",
    )
    assert status == matched_status == 200
    assert original == {"id": "17"} and matched == {"id": "7"}
    assert not {"usable", "verified", "principal_type_verified"}.intersection(matched)


@pytest.mark.parametrize("bad", ["method", "host", "auth", "token_url"])
def test_protocol_fixture_rejects_forbidden_request_shapes(bad):
    method, target, headers = (
        "GET",
        "https://graph.facebook.com/v25.0/me?fields=id",
        {
            "Authorization": "Bearer fixture-tool-secret",
        },
    )
    if bad == "method":
        method = "POST"
    elif bad == "host":
        target = "https://evil.example/v25.0/me?fields=id"
    elif bad == "auth":
        headers = {}
    else:
        target += "&access_token=fixture-tool-secret"
    with pytest.raises(AssertionError):
        identity_fact_protocol_response(
            httpx.Request(method, target, headers=headers), "fixture-tool-secret", "normal"
        )
