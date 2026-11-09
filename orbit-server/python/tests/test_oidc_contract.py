"""认证入口结构、同站返回地址及分用途凭据摘要；不代表登录流程已完成。"""

import json

import pytest

from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import credential_digest, opaque_token, parse_authorization_start


@pytest.mark.parametrize(
    "path", ["/index", "/orbit/system/users?q=中文", "/a?q=100%25", "/user/profile#x"]
)
def test_authorization_preserves_local_return_destination(path):
    assert parse_authorization_start(json.dumps({"return_to": path}).encode()).return_to == path


def test_authorization_nfc_and_trim_do_not_change_other_request_fields():
    assert parse_authorization_start(b'{"return_to":" /Cafe\\u0301 "}').return_to == "/Café"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"{}",
        b'{"return_to":1}',
        b'{"return_to":null}',
        b'{"return_to":"/","return_to":"/index"}',
        b'{"return_to":"/","actor_id":1}',
        b'{"return_to":"/","tenant_id":"forged"}',
    ],
)
def test_authorization_invalid_structure_or_identity_injection_is_rejected(raw):
    with pytest.raises(OrbitError) as error:
        parse_authorization_start(raw)
    assert error.value.status == 400


@pytest.mark.parametrize(
    "path",
    [
        "",
        "relative",
        "https://evil.example/",
        "//evil.example",
        "\\evil",
        "/\\evil",
        "/%2f%2fevil.example",
        "/%252f%252fevil.example",
        "/%255cevil",
        "/%0a",
        "/\u202e",
        "/bad%XX",
        "/%FF",
        "/" + "x" * 255,
    ],
)
def test_authorization_rejects_unsafe_or_oversize_return_destination(path):
    with pytest.raises(OrbitError) as error:
        parse_authorization_start(json.dumps({"return_to": path}).encode())
    assert error.value.status == 422


def test_authorization_bounds_body_and_json_depth():
    with pytest.raises(OrbitError) as error:
        parse_authorization_start(b" " * 4097)
    assert error.value.status == 413
    nested = b'{"return_to":' + b"[" * 1100 + b"0" + b"]" * 1100 + b"}"
    with pytest.raises(OrbitError) as error:
        parse_authorization_start(nested)
    assert error.value.status == 400


def test_opaque_credentials_are_unique_bounded_and_bound_to_purpose():
    values = {opaque_token() for _ in range(256)}
    assert len(values) == 256 and all(len(value) == 43 for value in values)
    value = values.pop()
    purposes = ["SESSION", "AUTHORIZATION_STATE", "BROWSER_BINDING", "INVITATION"]
    assert len({credential_digest(purpose, value) for purpose in purposes}) == 4
    assert len(credential_digest("SESSION", value)) == 32
    for invalid in ("", "a" * 44, "a" * 42 + "=", "用户名", None):
        with pytest.raises(OrbitError):
            credential_digest("SESSION", invalid)
    with pytest.raises(ValueError):
        credential_digest("UNKNOWN", value)
