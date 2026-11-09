"""真实代称字段边界及严格范围纯测试；不替代真实数据库/HTTP验收。"""

import json

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.reference_access import assert_write_ownership
from orbit_api.vendor_alias_contract import parse_vendor_alias, vendor_ids
from orbit_api.vendor_alias_store import public_alias


def parse(alias, **changes):
    return parse_vendor_alias(
        json.dumps({"alias": alias, "reason": "维护真实代称", **changes}).encode()
    )


@pytest.mark.parametrize("alias", [None, "户商", "户" * 30, "😀" * 30])
def test_alias_nullable_or_thirty_unicode_codepoints(alias):
    assert parse(alias)["alias"] == alias


def test_nfc_before_length_and_explicit_trim():
    assert parse(" e\u0301 ")["alias"] == "é"
    assert parse("e\u0301" * 30)["alias"] == "é" * 30


@pytest.mark.parametrize("alias", ["", "  ", "户" * 31, "😀" * 31, "a\n", "a\u200b", "a\ud800"])
def test_alias_rejects_empty_overflow_and_control_characters(alias):
    with pytest.raises(OrbitError) as caught:
        parse(alias)
    assert caught.value.status == 422 and caught.value.pointer == "/alias"


@pytest.mark.parametrize("alias", [False, 3, [], {}])
def test_alias_wrong_type_is_structure_error(alias):
    with pytest.raises(OrbitError) as caught:
        parse(alias)
    assert caught.value.status == 400 and caught.value.pointer == "/alias"


def test_unknown_field_does_not_extend_original_reference_schema():
    with pytest.raises(OrbitError) as caught:
        parse("真实值", name="不能冒充名称")
    assert caught.value.code == "UNKNOWN_FIELD" and caught.value.pointer == "/name"


def test_unknown_alias_get_baseline_has_no_fabricated_maintenance_time():
    assert public_alias("vendor") == {
        "vendor_id": "vendor",
        "alias": None,
        "revision": 1,
        "updated_at": None,
    }


@pytest.mark.parametrize("count", [1, 200])
def test_batch_ids_one_to_two_hundred(count):
    values = [f"10000000-0000-4000-8000-{i:012d}" for i in range(count)]
    assert vendor_ids(",".join(values)) == values


@pytest.mark.parametrize(
    "value", ["", "invalid", ",", ",".join(["10000000-0000-4000-8000-000000000001"] * 2)]
)
def test_batch_invalid_or_duplicate_ids_reject(value):
    with pytest.raises(OrbitError):
        vendor_ids(value)


@pytest.mark.parametrize(
    "role,managed,owners,allowed",
    [
        ("USER", [], ["self"], True),
        ("USER", [], ["self", "peer"], False),
        ("TEAM_ADMIN", [], ["self"], True),
        ("TEAM_ADMIN", [], ["self", "peer"], False),
        ("TEAM_ADMIN", ["team"], ["self", "peer"], True),
        ("SUPER_ADMIN", [], ["peer"], True),
    ],
)
def test_maintenance_does_not_treat_shared_readability_as_write_authority(
    role, managed, owners, allowed
):
    context = BusinessContext(1, "tenant", role, "self", "team")
    ownership = {"owner_team_id": "team", "data_owner_user_ids": owners}
    if allowed:
        assert_write_ownership(context, managed, ownership)
    else:
        with pytest.raises(OrbitError) as caught:
            assert_write_ownership(context, managed, ownership)
        assert caught.value.status == 403
