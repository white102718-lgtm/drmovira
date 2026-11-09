"""人员组织DTO按原合同逐字段验证；不把纯校验通过当作人员页面完成。"""

import json
from pathlib import Path

import pytest

from orbit_api.errors import OrbitError
from orbit_api.identity_contract import parse_identity_write

TEAM = "00000000-0000-0000-0000-000000000001"
ROLE = "00000000-0000-0000-0000-000000000002"


@pytest.mark.parametrize("bad", [None, 1, True, [], {}])
@pytest.mark.parametrize("kind,field", [("TEAM", "status"), ("USER", "data_role")])
def test_non_string_enum_is_structure_error_not_invalid_string_value(kind, field, bad):
    value = {"name": "测试团队", "status": "ENABLED"} if kind == "TEAM" else user()
    value[field] = bad
    with pytest.raises(OrbitError) as error:
        parse(kind, value)
    assert error.value.status == 400 and error.value.pointer == "/" + field


def user():
    return {
        "display_name": "用户姓名",
        "nickname": "昵称",
        "email": "user@example.org",
        "team_id": TEAM,
        "role_ids": [ROLE],
        "data_role": "USER",
        "managed_team_ids": [],
        "status": "INVITED",
    }


def parse(kind, value):
    return parse_identity_write(kind, json.dumps(value, ensure_ascii=True).encode())


def test_phone_extends_user_write_without_losing_any_original_field():
    schema = json.loads(
        (
            Path(__file__).parents[2] / "docs/orbit/baseline/contracts/openapi-current.json"
        ).read_text(encoding="utf-8")
    )
    original = schema["components"]["schemas"]["UserWrite"]
    value = user() | {"phone": " +86 138-0000-0000 "}
    result = parse("USER", value)
    assert set(result.model_dump()) == set(original["properties"]) | {"phone"}
    assert result.phone == "+86 138-0000-0000"
    assert parse("USER", user()).phone == ""


@pytest.mark.parametrize("field", list(user()))
def test_every_original_user_field_stays_required(field):
    value = user()
    value.pop(field)
    with pytest.raises(OrbitError) as error:
        parse("USER", value)
    assert error.value.status == 400
    assert error.value.pointer == "/" + field


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("display_name", "😀" * 51),
        ("nickname", "n" * 51),
        ("phone", "1" * 33),
        ("email", "not-an-email"),
        ("email", "user@example.org\n"),
        ("team_id", "not-a-uuid"),
        ("role_ids", []),
        ("role_ids", [ROLE] * 21),
        ("role_ids", [ROLE, ROLE.upper()]),
        ("managed_team_ids", [TEAM] * 501),
        ("data_role", "ADMIN"),
        ("status", "ACTIVE"),
    ],
)
def test_user_boundaries_enums_and_references(field, invalid):
    with pytest.raises(OrbitError) as error:
        parse("USER", user() | {field: invalid})
    assert error.value.status == 422
    assert error.value.pointer.startswith("/" + field)


def test_nfc_unicode_and_email_domain_normalization_preserve_valid_contacts():
    result = parse(
        "USER",
        user()
        | {"display_name": " e\u0301" * 10, "nickname": "😀" * 50, "email": "User@EXAMPLE.ORG"},
    )
    assert "\u0301" not in result.display_name
    assert result.nickname == "😀" * 50
    assert result.email == "User@example.org"


def test_uuid_set_duplicates_are_checked_after_case_normalization():
    identifier = "abcdef00-0000-0000-0000-000000000001"
    with pytest.raises(OrbitError) as error:
        parse("USER", user() | {"role_ids": [identifier, identifier.upper()]})
    assert error.value.code == "DUPLICATE_VALUE"
    assert error.value.pointer == "/role_ids/1"


def test_data_roles_do_not_implicitly_grant_managed_teams():
    with pytest.raises(OrbitError):
        parse("USER", user() | {"managed_team_ids": [TEAM]})
    assert parse("USER", user() | {"data_role": "TEAM_ADMIN"}).managed_team_ids == []


@pytest.mark.parametrize(
    "kind,body",
    [
        ("USER", user() | {"tenant_id": TEAM}),
        ("USER", user() | {"actor_id": TEAM}),
        ("USER", user() | {"identity_status": "VERIFIED"}),
        ("USER", user() | {"password": "fixture-must-not-accept"}),
        ("TEAM", {"name": "团队", "status": "ENABLED", "id": TEAM}),
        ("ROLE", {"name": "角色", "menu_codes": [], "permission_codes": [], "revision": 2}),
    ],
)
def test_readonly_identity_and_login_fields_cannot_be_injected(kind, body):
    with pytest.raises(OrbitError) as error:
        parse(kind, body)
    assert error.value.status == 400 and error.value.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize("name", ["", "x\n", "😀" * 101])
def test_team_name_boundaries(name):
    with pytest.raises(OrbitError):
        parse("TEAM", {"name": name, "status": "ENABLED"})
    assert parse("TEAM", {"name": "😀" * 100, "status": "DISABLED"}).name == "😀" * 100


@pytest.mark.parametrize("permission", ["*:*:*", "requests.approve", "products.edit", "made.up"])
def test_roles_never_restore_retired_actions_or_native_wildcards(permission):
    with pytest.raises(OrbitError) as error:
        parse("ROLE", {"name": "角色", "menu_codes": ["system"], "permission_codes": [permission]})
    assert error.value.code == "PERMISSION_UNKNOWN"


def test_role_union_can_split_menu_and_action_between_roles():
    assert parse(
        "ROLE", {"name": "菜单角色", "menu_codes": ["system"], "permission_codes": []}
    ).menu_codes == ["system"]
    assert parse(
        "ROLE", {"name": "动作角色", "menu_codes": [], "permission_codes": ["system.users.manage"]}
    ).permission_codes == ["system.users.manage"]


def test_duplicate_json_keys_cannot_change_administrative_state():
    with pytest.raises(OrbitError) as error:
        parse_identity_write("TEAM", b'{"name":"x","status":"ENABLED","status":"DISABLED"}')
    assert error.value.status == 400
