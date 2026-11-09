"""原OpenAPI严格字段及树展开的纯回归；不替代数据库/平台验收。"""

import copy
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.launch_contract import MAX_CONFIG_BYTES, parse_plan
from orbit_api.launch_expansion import (
    ad_slots,
    budget_totals,
    campaign_name,
    expanded_counts,
    naming_date,
)
from orbit_api.template_contract import parse_template, template_draft


def uid(number):
    return str(UUID(int=number))


def draft():
    return {
        "name": "",
        "ownership": {"owner_user_id": uid(1), "owner_team_id": uid(2)},
        "account_ids": [],
        "campaigns": [],
        "identity_bindings": [],
        "asset_ids": [],
        "allow_repeat": False,
        "activate_after_create": False,
        "execution_mode": "META_API",
    }


def tree():
    value = draft()
    value["account_ids"] = [uid(5), uid(4)]
    value["campaigns"] = [
        {
            "local_id": uid(10),
            "copies": 2,
            "adsets": [
                {"local_id": uid(11), "copies": 3, "ads": [{"local_id": uid(12), "copies": 4}]}
            ],
        }
    ]
    return value


def parse(value):
    return parse_plan(json.dumps(value, ensure_ascii=False).encode())


def ad(value):
    return value["campaigns"][0]["adsets"][0]["ads"][0]


def group(value):
    return value["campaigns"][0]["adsets"][0]


def budget(owner="CAMPAIGN", amount="0.100000", currency="USD"):
    return {
        "owner": owner,
        "type": "DAILY",
        "amount": amount,
        "currency": currency,
        "spend_cap": None,
    }


def test_empty_draft_preserves_sparse_fields_without_fake_business_defaults():
    value = parse(draft())
    assert value["channel_id"] is None
    assert "workflow_version" not in value
    assert value["campaigns"] == []
    assert "state" not in value


@pytest.mark.parametrize(
    "field,value", [("copies", True), ("copies", "1"), ("copies", 1.0), ("title", None)]
)
def test_strict_types_reject_coercion_and_optional_nonnullable(field, value):
    plan = tree()
    ad(plan)[field] = value
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.status == 400
    assert info.value.pointer.endswith("/" + field)


@pytest.mark.parametrize(
    "field,value",
    [
        ("copies", 0),
        ("copies", 51),
        ("asset_type", "AUDIO"),
        ("title", "😀" * 101),
        ("url_tags", "?a=b"),
        ("url_tags", "a"),
        ("url", "https://127.0.0.1/x"),
        ("url", "http://example.com"),
        ("cta", "\u200b"),
    ],
)
def test_nested_field_bounds_and_safe_error_pointer(field, value):
    plan = tree()
    ad(plan)[field] = value
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.status == 422
    assert info.value.pointer == "/campaigns/0/adsets/0/ads/0/" + field


def test_nfc_codepoint_boundaries_and_multiline_body():
    plan = tree()
    ad(plan).update(title="e\u0301" * 100, body="第一行\n第二行", description="")
    result = ad(parse(plan))
    assert result["title"] == "é" * 100
    assert result["body"] == "第一行\n第二行"
    assert result["description"] == ""


def test_unknown_field_pointer_and_no_echo():
    plan = tree()
    ad(plan)["x/y~z"] = "secret-must-never-echo"
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert (info.value.status, info.value.code) == (400, "UNKNOWN_FIELD")
    assert info.value.pointer.endswith("/x~1y~0z")
    assert "secret" not in info.value.message


@pytest.mark.parametrize(
    "field,value",
    [
        ("country_codes", ["ZZ"]),
        ("country_codes", ["US", "US"]),
        ("country_codes", ["us"]),
        ("country_codes", []),
        ("locales", ["en_US"]),
        ("age_min", 17),
        ("age_max", 66),
        ("start_time", "2026-01-01T10:00:00"),
        ("end_time", "2026-02-30T00:00:00Z"),
    ],
)
def test_group_country_age_locale_and_offset_contract(field, value):
    plan = tree()
    group(plan)[field] = value
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.status == 422
    assert info.value.pointer.startswith("/campaigns/0/adsets/0/" + field)


def test_age_and_time_order_use_offsets():
    plan = tree()
    group(plan).update(age_min=65, age_max=18)
    with pytest.raises(OrbitError):
        parse(plan)
    group(plan).update(
        age_min=18,
        age_max=65,
        start_time="2026-01-01T10:00:00+08:00",
        end_time="2026-01-01T01:59:00Z",
    )
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.pointer.endswith("/end_time")


@pytest.mark.parametrize("amount", ["0", "-1", "1e2", "01", "1.1234567", "1000000.000001", "NaN"])
def test_budget_decimal_bounds(amount):
    plan = tree()
    plan["campaigns"][0]["budget"] = budget(amount=amount)
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.status == 422
    assert info.value.pointer.endswith("/budget/amount")


def test_budget_owner_and_mutually_exclusive_levels():
    plan = tree()
    plan["campaigns"][0]["budget"] = budget(owner="ADSET")
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.pointer.endswith("/budget/owner")
    plan["campaigns"][0]["budget"] = budget()
    group(plan)["budget"] = budget(owner="ADSET")
    with pytest.raises(OrbitError):
        parse(plan)


def test_uuid_normalization_precedes_duplicate_and_cross_level_checks():
    plan = tree()
    plan["account_ids"] = [uid(0xABCDEF), uid(0xABCDEF).upper()]
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.pointer == "/account_ids"
    plan = tree()
    ad(plan)["local_id"] = group(plan)["local_id"]
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.pointer.endswith("/ads/0/local_id")


def test_identity_references_are_plan_local_without_claiming_platform_ownership():
    plan = tree()
    plan["identity_bindings"] = [
        {
            "account_id": uid(4),
            "page_id": "123",
            "groups": [
                {
                    "adset_local_id": uid(11),
                    "pixel_id": "456",
                    "conversion_event": "PURCHASE",
                    "application_id": None,
                    "object_store_url": None,
                }
            ],
            "ad_overrides": [{"ad_local_id": uid(12), "page_id": "789"}],
        }
    ]
    assert parse(plan)["identity_bindings"][0]["page_id"] == "123"
    plan["identity_bindings"][0]["groups"][0]["adset_local_id"] = uid(99)
    with pytest.raises(OrbitError) as info:
        parse(plan)
    assert info.value.pointer.endswith("/groups/0/adset_local_id")


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"{}", 400),
        (b'{"name":"a","name":"b"}', 400),
        (b"NaN", 400),
        (b"\xff", 400),
        (b" " * (MAX_CONFIG_BYTES + 1), 413),
    ],
)
def test_json_boundary_duplicate_keys_and_nonfinite(raw, status):
    with pytest.raises(OrbitError) as info:
        parse_plan(raw)
    assert info.value.status == status


def test_expansion_is_per_branch_and_lexical_ordered_without_cross_product():
    plan = parse(tree())
    counts = expanded_counts(plan)
    assert (counts.campaign_count, counts.adset_count, counts.ad_count) == (4, 12, 48)
    slots = ad_slots(plan)
    assert len(slots) == len({item.key for item in slots}) == 48
    assert slots == sorted(slots)
    assert slots[0].account_id == uid(4)
    assert slots[-1].ad_copy == 4
    # 新增独立分支只增加自己的副本，不与第一分支相乘。
    second = copy.deepcopy(plan["campaigns"][0])
    second.update(local_id=uid(20), copies=1, adsets=[])
    plan["campaigns"].append(second)
    assert expanded_counts(plan).ad_count == 48
    assert expanded_counts(plan).campaign_count == 6


def test_expansion_rejects_massive_tree_before_allocating_slots():
    plan = tree()
    plan["account_ids"] = [uid(i + 100) for i in range(500)]
    with pytest.raises(OrbitError) as info:
        ad_slots(plan)
    assert info.value.code == "PLAN_NODE_LIMIT"


def test_budget_totals_decimal_real_owner_and_currency_separation():
    plan = tree()
    plan["campaigns"][0]["budget"] = budget()
    assert budget_totals(parse(plan)) == [{"amount": "0.400000", "currency": "USD"}]
    del plan["campaigns"][0]["budget"]
    group(plan)["budget"] = budget(owner="ADSET", amount="0.25", currency="JPY")
    assert budget_totals(parse(plan)) == [{"amount": "3.00", "currency": "JPY"}]


def test_naming_shanghai_midnight_and_fallback_without_silent_truncation():
    before = naming_date(datetime(2026, 11, 8, 15, 59, 59, tzinfo=UTC))
    after = naming_date(datetime(2026, 11, 8, 16, 0, 0, tzinfo=UTC))
    assert str(before) == "2026-11-08" and str(after) == "2026-11-09"
    assert (
        campaign_name(
            channel_name="",
            channel_code="CODE",
            nickname="",
            full_name="投手",
            day=after,
            sequence=7,
        )
        == "CODE_投手_20261109_0007"
    )
    with pytest.raises(ValueError):
        naming_date(datetime(2026, 11, 8))
    with pytest.raises(ValueError):
        campaign_name(
            channel_name="A",
            channel_code="A",
            nickname="B",
            full_name="B",
            day=after,
            sequence=True,
        )


def test_template_strips_all_external_context_and_clones_ids_without_mutation():
    plan = parse(tree())
    template = {
        "name": " 模板 ",
        "description": "",
        "visibility": "PRIVATE",
        "recipient_user_ids": [],
        "campaigns": plan["campaigns"],
    }
    template = parse_template(json.dumps(template).encode())
    result = template_draft(template, plan["ownership"])
    assert result["account_ids"] == result["asset_ids"] == result["identity_bindings"] == []
    assert result["channel_id"] is None and result["activate_after_create"] is False
    assert "allocation_id" not in result
    assert result["campaigns"][0]["local_id"] != template["campaigns"][0]["local_id"]
    assert template["campaigns"][0]["local_id"] == uid(10)
    result["campaigns"][0]["adsets"].clear()
    assert template["campaigns"][0]["adsets"]


def test_template_rejects_account_leak_and_private_recipients():
    template = {
        "name": "模板",
        "description": "",
        "visibility": "PRIVATE",
        "recipient_user_ids": [uid(1)],
        "campaigns": tree()["campaigns"],
    }
    with pytest.raises(OrbitError) as info:
        parse_template(json.dumps(template).encode())
    assert info.value.pointer == "/recipient_user_ids"
    template["recipient_user_ids"] = []
    template["account_ids"] = [uid(4)]
    with pytest.raises(OrbitError) as info:
        parse_template(json.dumps(template).encode())
    assert info.value.code == "UNKNOWN_FIELD"


def test_snapshot_and_explicit_account_ids_are_mutually_exclusive_original_workflow():
    value = tree() | {"account_scope_snapshot_id": uid(99)}
    with pytest.raises(OrbitError) as info:
        parse(value)
    assert info.value.status == 422 and info.value.code == "FIELD_VALIDATION_FAILED"
    assert info.value.pointer == "/account_ids"


def test_template_long_description_retains_lf_and_forbids_hidden_controls():
    value = {
        "name": "多行说明",
        "description": "第一行\n第二行",
        "visibility": "PRIVATE",
        "recipient_user_ids": [],
        "campaigns": tree()["campaigns"],
    }
    assert parse_template(json.dumps(value).encode())["description"] == "第一行\n第二行"
    value["description"] = "第一行\u200b第二行"
    with pytest.raises(OrbitError) as info:
        parse_template(json.dumps(value).encode())
    assert info.value.pointer == "/description"


@pytest.mark.parametrize(
    "transform",
    [
        lambda value: value.replace("-", ""),
        lambda value: "{" + value + "}",
        lambda value: "urn:uuid:" + value,
    ],
)
def test_uuid_wire_format_never_accepts_noncanonical_alias_syntax(transform):
    value = draft()
    value["ownership"]["owner_user_id"] = transform(uid(0xABCDEF))
    with pytest.raises(OrbitError) as info:
        parse(value)
    assert info.value.status == 422
    assert info.value.pointer == "/ownership/owner_user_id"


def test_uppercase_canonical_uuid_normalizes_to_same_identity():
    value = draft()
    value["ownership"]["owner_user_id"] = uid(0xABCDEF).upper()
    assert parse(value)["ownership"]["owner_user_id"] == uid(0xABCDEF)
