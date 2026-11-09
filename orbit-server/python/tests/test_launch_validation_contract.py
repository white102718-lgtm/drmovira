"""纯预检冻结协议：独立小树oracle，不查询数据库/平台，不证明生产authority。"""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.launch_expansion import Counts, ad_slots, campaign_slots
from orbit_api.launch_validation_contract import (
    freeze_validation,
    is_current,
    parse_validation_action,
    utc_milliseconds,
    validation_response,
)


def uid(value):
    return str(UUID(int=value))


def fixture(accounts=2, ad_copies=2):
    plan = {
        "name": "纯冻结夹具",
        "ownership": {"owner_user_id": uid(90), "owner_team_id": uid(91)},
        "account_ids": [uid(100 + n) for n in range(accounts)],
        "campaigns": [
            {
                "local_id": uid(1),
                "copies": 1,
                "budget": {
                    "owner": "CAMPAIGN",
                    "type": "DAILY",
                    "amount": "12.3400",
                    "currency": "USD",
                    "spend_cap": None,
                },
                "adsets": [
                    {
                        "local_id": uid(2),
                        "copies": 1,
                        "start_time": "2026-11-08T18:00:00+08:00",
                        "ads": [{"local_id": uid(3), "copies": ad_copies, "title": "真实配置标题"}],
                    }
                ],
            }
        ],
        "asset_ids": [uid(200)],
        "identity_bindings": [
            {
                "account_id": uid(100 + n),
                "page_id": str(1000 + n),
                "groups": [
                    {
                        "adset_local_id": uid(2),
                        "pixel_id": str(2000 + n),
                        "conversion_event": "PURCHASE",
                        "application_id": None,
                        "object_store_url": None,
                    }
                ],
                "ad_overrides": [{"ad_local_id": uid(3), "page_id": str(3000 + n)}],
            }
            for n in range(accounts)
        ],
        "allow_repeat": True,
        "activate_after_create": False,
        "execution_mode": "META_API",
    }
    allocation = {
        "id": uid(300),
        "plan_id": uid(301),
        "plan_revision": 7,
        "state": "SUCCEEDED",
        "task_id": None,
        "algorithm_version": "allocation-v1",
        "seed": 0,
        "items": [
            {
                "slot_key": slot.key,
                "account_id": slot.account_id,
                "asset_id": uid(200),
                "asset_revision": 4,
            }
            for slot in ad_slots(plan)
        ],
        "warnings": [],
        "input_hash": "a" * 64,
    }
    names = {
        "id": uid(302),
        "plan_revision": 7,
        "naming_date": "2026-11-08",
        "items": [
            {
                "slot_key": "/".join(map(str, slot)),
                "name": f"渠道_真实投手_20261108_{n + 1:04d}",
                "sequence": str(n + 1),
            }
            for n, slot in enumerate(campaign_slots(plan))
        ],
    }
    return plan, {
        "plan_id": uid(301),
        "source_revision": 7,
        "allocation": allocation,
        "name_reservation": names,
        "capability_version": "cap-source-3",
        "policy_version": "policy-source-4",
        "scope_version": 9,
        "channel_snapshot": {"id": uid(400), "name": "真实渠道快照", "revision": 2},
        "product_snapshot": {"id": uid(401), "revision": 3},
        "currency": "USD",
        "total_dag_node_count": 40,
        "validated_at": datetime(2026, 11, 8, 8, 0, 0, 123456, tzinfo=UTC),
    }


def freeze(plan=None, args=None):
    if plan is None:
        plan, args = fixture()
    return freeze_validation(plan, **args)


def test_streamed_full_tree_final_names_assets_identity_and_independent_json_hash(monkeypatch):
    captured = []
    real_sha = hashlib.sha256

    class Digest:
        def update(self, value):
            captured.append(value)

        def hexdigest(self):
            return real_sha(b"".join(captured)).hexdigest()

    monkeypatch.setattr("orbit_api.launch_validation_contract.hashlib.sha256", Digest)
    result = freeze()
    document = json.loads(b"".join(captured))
    assert (
        result.hash
        == real_sha(
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert document["schema_version"] == 1 and document["plan_revision"] == 7
    assert not {"source_revision", "head_revision", "graph_hash"}.intersection(document)
    tree = document["expanded_tree"]
    assert [row["kind"] for row in tree] == ["CAMPAIGN", "ADSET", "AD", "AD"] * 2
    assert tree[0]["name"] == "渠道_真实投手_20261108_0001"
    assert tree[2]["asset"] == {"asset_id": uid(200), "asset_revision": 4}
    assert tree[2]["identity"]["page_id"] == "3000"
    assert tree[6]["identity"]["page_id"] == "3001"
    assert tree[2]["identity"]["pixel_id"] == "2000"
    assert tree[1]["configuration"]["start_time"] == "2026-11-08T10:00:00.000Z"
    assert tree[0]["configuration"]["budget"]["amount"] == "12.34"
    assert (result.counts, result.budget_totals) == (Counts(2, 2, 4), (("USD", "24.68"),))


def test_sets_and_mapping_order_invariant_but_tree_sibling_order_is_semantic():
    plan, args = fixture()
    expected = freeze(plan, args).hash
    plan["account_ids"].reverse()
    plan["identity_bindings"].reverse()
    args["allocation"]["items"].reverse()
    args["name_reservation"]["items"].reverse()
    assert freeze(plan, args).hash == expected
    # 新兄弟广告拥有自己的身份override及分配，不以local_id排序掩盖语义顺序。
    plan["campaigns"][0]["adsets"][0]["ads"].append(
        {"local_id": uid(4), "copies": 1, "title": "第二个"}
    )
    for slot in ad_slots(plan):
        if slot.ad_id == uid(4):
            args["allocation"]["items"].append(
                {
                    "slot_key": slot.key,
                    "account_id": slot.account_id,
                    "asset_id": uid(200),
                    "asset_revision": 4,
                }
            )
    before = freeze(plan, args).hash
    plan["campaigns"][0]["adsets"][0]["ads"].reverse()
    assert freeze(plan, args).hash != before


@pytest.mark.parametrize(
    "change",
    [
        "name",
        "asset_revision",
        "page",
        "title",
        "allocation_id",
        "policy",
        "scope",
        "product",
        "currency",
        "activate",
    ],
)
def test_each_execution_source_changes_digest(change):
    plan, args = fixture()
    expected = freeze(plan, args).hash
    if change == "name":
        args["name_reservation"]["items"][0]["name"] += "更新"
    elif change == "asset_revision":
        for row in args["allocation"]["items"]:
            row["asset_revision"] += 1
    elif change == "page":
        plan["identity_bindings"][0]["ad_overrides"][0]["page_id"] = "9999"
    elif change == "title":
        plan["campaigns"][0]["adsets"][0]["ads"][0]["title"] += "更新"
    elif change == "allocation_id":
        args["allocation"]["id"] = uid(999)
    elif change == "policy":
        args["policy_version"] += "-next"
    elif change == "scope":
        args["scope_version"] += 1
    elif change == "product":
        args["product_snapshot"]["revision"] += 1
    elif change == "currency":
        args["currency"] = "EUR"
        plan["campaigns"][0]["budget"]["currency"] = "EUR"
    else:
        plan["activate_after_create"] = True
    assert freeze(plan, args).hash != expected


def test_decimal_and_utc_representations_are_canonical():
    plan, args = fixture()
    expected = freeze(plan, args).hash
    plan["campaigns"][0]["budget"]["amount"] = "12.34"
    plan["campaigns"][0]["adsets"][0]["start_time"] = "2026-11-08T10:00:00.000Z"
    assert freeze(plan, args).hash == expected


def test_freeze_has_no_mutable_alias_and_no_authority_flag():
    plan, args = fixture()
    record = freeze(plan, args)
    result = validation_response(record)
    plan.clear()
    args["allocation"]["items"].clear()
    args["channel_snapshot"]["name"] = "修改"
    result["budget_totals"][0]["amount"] = "0"
    assert validation_response(record)["budget_totals"][0]["amount"] == "24.68"
    assert not hasattr(record, "verified") and not hasattr(record, "execution_authorized")
    with pytest.raises(FrozenInstanceError):
        record.hash = "f" * 64


@pytest.mark.parametrize(
    "damage",
    [
        "missing_asset",
        "extra_asset",
        "duplicate_slot",
        "wrong_account",
        "missing_name",
        "wrong_name_slot",
        "source",
        "name_source",
        "plan",
        "identity",
        "group_identity",
        "mixed_asset_version",
        "pending",
        "unknown_field",
    ],
)
def test_incomplete_or_wrong_frozen_reference_is_rejected(damage):
    plan, args = fixture()
    allocation, names = args["allocation"], args["name_reservation"]
    if damage == "missing_asset":
        allocation["items"].pop()
    elif damage == "extra_asset":
        allocation["items"].append(copy.deepcopy(allocation["items"][0]))
    elif damage == "duplicate_slot":
        allocation["items"][1] = copy.deepcopy(allocation["items"][0])
    elif damage == "wrong_account":
        allocation["items"][0]["account_id"] = uid(101)
    elif damage == "missing_name":
        names["items"].pop()
    elif damage == "wrong_name_slot":
        names["items"][0]["slot_key"] = "not-an-expanded-campaign"
    elif damage == "source":
        allocation["plan_revision"] += 1
    elif damage == "name_source":
        names["plan_revision"] += 1
    elif damage == "plan":
        allocation["plan_id"] = uid(999)
    elif damage == "identity":
        plan["identity_bindings"].pop()
    elif damage == "group_identity":
        plan["identity_bindings"][0]["groups"] = []
    elif damage == "mixed_asset_version":
        allocation["items"][0]["asset_revision"] += 1
    elif damage == "pending":
        allocation["state"] = "RUNNING"
    else:
        allocation["verified"] = True
    with pytest.raises(OrbitError) as captured:
        freeze(plan, args)
    assert captured.value.status in {400, 422}


def test_ttl_equality_shanghai_midnight_and_future_time():
    plan, args = fixture()
    record = freeze(plan, args)
    assert record.validated_at.microsecond == 123000
    assert is_current(record, record.expires_at - timedelta(milliseconds=1))
    assert not is_current(record, record.expires_at)
    assert not is_current(record, record.validated_at - timedelta(milliseconds=1))
    args["validated_at"] = datetime(2026, 11, 8, 15, 59, 59, 999000, tzinfo=UTC)
    record = freeze(plan, args)
    assert is_current(record, args["validated_at"])
    assert not is_current(record, datetime(2026, 11, 8, 16, tzinfo=UTC))
    with pytest.raises(ValueError):
        is_current(record, datetime(2026, 11, 8, 16))
    assert utc_milliseconds(datetime(2026, 11, 8, tzinfo=UTC)) == "2026-11-08T00:00:00.000Z"


def test_response_strict_ten_fields_and_invalid_keeps_real_summary():
    record = freeze()
    result = validation_response(record)
    assert set(result) == {
        "valid",
        "hash",
        "expires_at",
        "errors",
        "campaign_count",
        "adset_count",
        "ad_count",
        "budget_totals",
        "scope_version",
        "total_dag_node_count",
    }
    error = {
        "path": "/campaigns/0",
        "code": "CAPABILITY_UNVERIFIED",
        "message": "真实业务条件未满足",
        "constraint": "",
    }
    invalid = validation_response(
        errors=[error],
        counts=Counts(2, 2, 4),
        totals=(("USD", "24.68"),),
        scope_version=9,
        total_dag_node_count=40,
    )
    assert not invalid["valid"] and invalid["hash"] is None and invalid["expires_at"] is None
    assert invalid["ad_count"] == 4 and invalid["budget_totals"] == result["budget_totals"]
    error["message"] = "外部修改"
    assert invalid["errors"][0]["message"] != error["message"]
    with pytest.raises(ValueError):
        validation_response()


@pytest.mark.parametrize(
    "action,payload",
    [
        ("validate", {"allocation_id": uid(1), "name_reservation_id": uid(2)}),
        ("execute", {"hash": "a" * 64, "activate_ack": False}),
    ],
)
def test_original_action_parsers_and_unknown_field(action, payload):
    assert parse_validation_action(json.dumps(payload).encode(), action) == payload
    payload["source_revision"] = 1
    with pytest.raises(OrbitError) as captured:
        parse_validation_action(json.dumps(payload).encode(), action)
    assert captured.value.code == "UNKNOWN_FIELD"


def test_expansion_limits_before_allocating_cartesian_tree():
    plan, args = fixture(accounts=500, ad_copies=1)
    plan["campaigns"][0]["adsets"][0]["ads"][0]["copies"] = 50
    with pytest.raises(OrbitError) as captured:
        freeze(plan, args)
    assert captured.value.code == "PLAN_NODE_LIMIT"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_revision", True),
        ("scope_version", 0),
        ("total_dag_node_count", 100001),
        ("currency", "usd"),
    ],
)
def test_strict_safe_boundaries(field, value):
    plan, args = fixture()
    args[field] = value
    with pytest.raises(OrbitError) as captured:
        freeze(plan, args)
    assert captured.value.code == "FIELD_VALIDATION_FAILED"


def test_ten_thousand_ads_stream_small_tokens_without_retaining_execution_tree(monkeypatch):
    plan, args = fixture(accounts=200, ad_copies=50)
    args["total_dag_node_count"] = 100000
    real_sha, metrics = hashlib.sha256, {"bytes": 0, "largest": 0}

    class Digest:
        def __init__(self):
            self.digest = real_sha()

        def update(self, value):
            metrics["bytes"] += len(value)
            metrics["largest"] = max(metrics["largest"], len(value))
            self.digest.update(value)

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr("orbit_api.launch_validation_contract.hashlib.sha256", Digest)
    record = freeze(plan, args)
    assert record.counts == Counts(200, 200, 10000)
    assert metrics["bytes"] > 2 * 1024 * 1024
    assert metrics["largest"] < 4096
    assert "expanded_tree" not in record.__dict__ and "plan" not in record.__dict__


@pytest.mark.parametrize(
    "damage",
    [
        "amount_float",
        "amount_exponent",
        "currency",
        "duplicate_currency",
        "count_bool",
        "errors_unknown",
        "errors_path",
        "errors_null",
    ],
)
def test_response_original_money_counts_and_field_errors_boundaries(damage):
    values = {
        "errors": [
            {
                "path": "/name",
                "code": "BUSINESS_INVALID",
                "message": "真实业务错误",
                "constraint": "",
            }
        ],
        "counts": Counts(1, 1, 1),
        "totals": [("USD", "1.00")],
        "scope_version": 1,
        "total_dag_node_count": 10,
    }
    if damage == "amount_float":
        values["totals"] = [("USD", 1.2)]
    elif damage == "amount_exponent":
        values["totals"] = [("USD", "1e2")]
    elif damage == "currency":
        values["totals"] = [("usd", "1")]
    elif damage == "duplicate_currency":
        values["totals"] *= 2
    elif damage == "count_bool":
        values["counts"] = Counts(True, 1, 1)
    elif damage == "errors_unknown":
        values["errors"][0]["unknown"] = "no"
    elif damage == "errors_path":
        values["errors"][0]["path"] = "name"
    else:
        values["errors"][0]["message"] = None
    with pytest.raises(OrbitError) as captured:
        validation_response(**values)
    assert captured.value.code == "FIELD_VALIDATION_FAILED"


def test_missing_authority_is_not_solved_by_self_declared_snapshot_verified():
    plan, args = fixture()
    args["channel_snapshot"]["verified"] = True
    record = freeze(plan, args)
    # 这里仅允许普通JSON输入改变摘要，没有权限/Task/provider返回值。
    assert len(record.hash) == 64
    assert set(record.__dict__) == {
        "hash",
        "source_revision",
        "counts",
        "budget_totals",
        "scope_version",
        "total_dag_node_count",
        "validated_at",
        "expires_at",
        "naming_date",
    }


def test_snapshot_keys_do_not_accidentally_use_plan_set_or_money_semantics():
    plan, args = fixture()
    args["product_snapshot"]["country_codes"] = ["B", "A"]
    args["product_snapshot"]["amount"] = "literal-product-text"
    args["product_snapshot"]["expanded_tree"] = "literal-product-text"
    expected = freeze(plan, args).hash
    args["product_snapshot"]["country_codes"].reverse()
    assert freeze(plan, args).hash != expected


@pytest.mark.parametrize(
    "damage",
    [
        "stale_day",
        "duplicate_sequence",
        "zero_sequence",
        "currency_mismatch",
        "pool_too_large",
        "repeat_forbidden",
        "dag_count",
        "bytes_limit",
    ],
)
def test_cross_reference_and_size_boundaries(damage):
    plan, args = fixture()
    if damage == "stale_day":
        args["name_reservation"]["naming_date"] = "2026-11-07"
    elif damage == "duplicate_sequence":
        args["name_reservation"]["items"][1]["sequence"] = "01"
    elif damage == "zero_sequence":
        args["name_reservation"]["items"][0]["sequence"] = "0"
    elif damage == "currency_mismatch":
        args["currency"] = "EUR"
    elif damage == "pool_too_large":
        plan["asset_ids"] += [uid(700 + n) for n in range(4)]
    elif damage == "repeat_forbidden":
        plan["allow_repeat"] = False
    elif damage == "dag_count":
        args["total_dag_node_count"] = 1
    else:
        plan = b" " * (5 * 1024 * 1024 + 1)
    with pytest.raises(OrbitError) as captured:
        freeze(plan, args)
    assert captured.value.status in {413, 422}
