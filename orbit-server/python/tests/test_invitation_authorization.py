"""邀请凭据只允许在独立正文中传递，不扩充原AuthorizationStart或接收浏览器身份。"""

import json

import pytest

from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import parse_invitation_authorization_start


def test_invitation_authorization_keeps_token_out_of_repr():
    token = "i" * 43
    value = parse_invitation_authorization_start(
        json.dumps(
            {
                "invitation_token": token,
                "return_to": "/orbit/system/users",
            }
        ).encode()
    )
    assert value.invitation_token == token and value.return_to == "/orbit/system/users"
    assert token not in repr(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"invitation_token": "i" * 43},
        {"invitation_token": 42, "return_to": "/index"},
        {"invitation_token": "i" * 43, "return_to": 42},
        {"invitation_token": "i" * 43, "return_to": "/index", "actor_id": 1},
        {"invitation_token": "i" * 43, "return_to": "/index", "tenant_id": "tenant"},
    ],
)
def test_invitation_authorization_rejects_missing_unknown_and_invalid_types(value):
    with pytest.raises(OrbitError) as error:
        parse_invitation_authorization_start(json.dumps(value).encode())
    assert error.value.status == 400


@pytest.mark.parametrize("token", ["", "i" * 42, "i" * 44, "非" * 43, " " * 43])
def test_invitation_authorization_rejects_invalid_opaque_tokens_without_echo(token):
    with pytest.raises(OrbitError) as error:
        parse_invitation_authorization_start(
            json.dumps({"invitation_token": token, "return_to": "/"}).encode()
        )
    assert error.value.code == "INVITATION_INVALID"
    assert not token or token not in str(error.value)


def test_invitation_authorization_rejects_duplicate_body_large_body_and_external_return():
    for body, status in [
        (b'{"invitation_token":"first","invitation_token":"second","return_to":"/"}', 400),
        (b" " * 4097, 413),
        (json.dumps({"invitation_token": "i" * 43, "return_to": "//evil.example"}).encode(), 422),
    ]:
        with pytest.raises(OrbitError) as error:
            parse_invitation_authorization_start(body)
        assert error.value.status == status
