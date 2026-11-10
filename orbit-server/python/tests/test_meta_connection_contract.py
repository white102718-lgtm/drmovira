"""Meta读取授权边界：错误返回地址、权限与签名不能通过。"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest


def contract():
    from orbit_api import meta_connection_contract

    return meta_connection_contract


@pytest.mark.parametrize(
    "target",
    ["https://evil.test", "//evil.test", "/\\evil", "/%2f%2fevil", "/a\n", "/api/v1/auth/logout"],
)
def test_return_path_rejects_external_and_api(target):
    with pytest.raises(ValueError):
        contract().return_path(target)


def test_return_path_keeps_internal_query():
    assert (
        contract().return_path("/orbit/accounts?meta=connected") == "/orbit/accounts?meta=connected"
    )


def test_app_requires_explicit_version_and_read_scope_only():
    module = contract()
    with pytest.raises(ValueError):
        module.MetaApplication("123", "secret", "", "456")
    app = module.MetaApplication("123", "secret", "v24.0", "456")
    url = app.authorize_url("random-state")
    assert "ads_management" not in url
    assert "secret" not in repr(app)
    assert "drmovira.com" in url


def test_token_validation_rejects_wrong_app_or_missing_grant():
    m = contract()
    app = m.MetaApplication("123", "secret", "v24.0", "456")
    now = datetime.now(UTC)
    valid = dict(
        app_id="123",
        user_id="42",
        is_valid=True,
        scopes=["ads_read"],
        expires_at=int(now.timestamp()) + 3600,
        data_access_expires_at=int(now.timestamp()) + 7200,
    )
    assert m.validate_grant(valid, app, now).principal_id == "42"
    for change in (
        {"app_id": "999"},
        {"scopes": []},
        {"is_valid": False},
        {"expires_at": 1},
        {"user_id": ""},
    ):
        with pytest.raises(ValueError):
            m.validate_grant(valid | change, app, now)


def test_signed_callback_requires_exact_hmac_and_recent_issue():
    m = contract()
    now = datetime.now(UTC)

    def enc(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    body = enc(
        json.dumps(
            {"algorithm": "HMAC-SHA256", "user_id": "42", "issued_at": int(now.timestamp())}
        ).encode()
    )
    signature = enc(hmac.new(b"secret", body.encode(), hashlib.sha256).digest())
    assert m.signed_request(signature + "." + body, "secret", now)["user_id"] == "42"
    with pytest.raises(ValueError):
        m.signed_request(signature + "." + body, "other", now)


@pytest.mark.parametrize("ids", [[], ["act_123"], ["123", "123"], [123], ["123"] * 501])
def test_selected_accounts_require_unique_server_ids(ids):
    with pytest.raises(ValueError):
        contract().selected_accounts(ids)


def test_selected_account_ids_preserve_string_precision():
    assert contract().selected_accounts(["1234567890123456789"]) == ("1234567890123456789",)


@pytest.mark.parametrize("scopes", [["ads_read", {}], ["ads_read", 1], ["ads_read", None]])
def test_invalid_grant_scope_types_fail_closed_without_typeerror(scopes):
    m = contract()
    data = dict(
        app_id="123",
        user_id="42",
        is_valid=True,
        scopes=scopes,
        expires_at=253402300000,
        data_access_expires_at=253402300000,
    )
    with pytest.raises(ValueError):
        m.validate_grant(
            data, m.MetaApplication("123", "secret", "v24.0", "456"), datetime.now(UTC)
        )


def test_signed_callback_json_array_and_duplicate_fields_rejected_safely():
    m = contract()

    def signed(raw):
        body = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        sig = (
            base64.urlsafe_b64encode(hmac.new(b"secret", body.encode(), hashlib.sha256).digest())
            .decode()
            .rstrip("=")
        )
        return sig + "." + body

    now = datetime.now(UTC)
    for raw in (
        "[]",
        '{"algorithm":"HMAC-SHA256","user_id":"42","user_id":"43","issued_at":'
        + str(int(now.timestamp()))
        + "}",
    ):
        with pytest.raises(ValueError):
            m.signed_request(signed(raw), "secret", now)
