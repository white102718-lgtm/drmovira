import json
import pytest
from orbit_api.errors import OrbitError
from orbit_api.user_credentials import parse_local_user, parse_password_reset


def payload():
    return dict(
        display_name="测试人员",
        nickname="投手",
        email="person@example.com",
        phone="+8613800000000",
        team_id="10000000-0000-4000-8000-000000000001",
        role_ids=["10000000-0000-4000-8000-000000000002"],
        data_role="USER",
        managed_team_ids=[],
        status="ENABLED",
        password="TestPass123!",
    )


def test_local_user_can_start_enabled_with_private_password():
    value = parse_local_user(json.dumps(payload()).encode())
    assert value.status == "ENABLED"
    assert value.phone == "+8613800000000"
    assert "TestPass123!" not in repr(value)
    assert "password" not in value.model_dump()
    assert value.password.get_secret_value() == "TestPass123!"


@pytest.mark.parametrize(
    "change",
    [
        {"password": ""},
        {"password": "short"},
        {"password": "a" * 65},
        {"password": "中" * 30},
        {"password": "a" * 10 + "\ud800"},
        {"phone": "invalid"},
        {"status": "INVITED"},
    ],
)
def test_invalid_local_user_rejected(change):
    with pytest.raises(OrbitError):
        parse_local_user(json.dumps(payload() | change).encode())


def test_password_reset_strict_and_never_echoes_secret():
    value = parse_password_reset(b'{"password":"AnotherPass123!"}')
    assert "AnotherPass123!" not in repr(value)
    assert value.model_dump() == {}
    for body in [{"password": 123}, {"password": "AnotherPass123!", "tenant_id": "foreign"}, {}]:
        with pytest.raises(OrbitError):
            parse_password_reset(json.dumps(body).encode())
