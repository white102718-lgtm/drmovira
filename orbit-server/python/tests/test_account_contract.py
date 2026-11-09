"""账户原始导入边界与状态合同；纯逻辑不能代替平台、数据库或浏览器验收。"""

import json
from datetime import UTC, datetime

import pytest

from orbit_api.account_contract import batch_summary, parse_import, tokenize
from orbit_api.account_metadata import (
    UnavailableAccountAdapter,
    metadata,
    timezone_payload,
    unknown_observation,
)
from orbit_api.errors import OrbitError


def test_original_tokens_keep_leading_zero_positions_and_first_duplicate_zero():
    rows = tokenize(" act_000123，000123;12\r\n\t34 12")
    assert [row["normalized_id"] for row in rows] == ["000123", "000123", "12", "34", "12"]
    assert [row["state"] for row in rows] == [
        "WAITING",
        "DUPLICATE",
        "WAITING",
        "WAITING",
        "DUPLICATE",
    ]
    assert rows[1]["duplicate_of"] == 0 and rows[4]["duplicate_of"] == 2
    assert [(row["line_no"], row["column"]) for row in rows] == [
        (1, 2),
        (1, 13),
        (1, 20),
        (2, 2),
        (2, 5),
    ]


def test_limit_is_checked_before_deduplication():
    with pytest.raises(OrbitError) as error:
        tokenize("1 " * 501)
    assert error.value.code == "IMPORT_TOO_MANY_TOKENS"
    assert len(tokenize("1 " * 500)) == 500


def test_input_limit_counts_unicode_codepoints_including_invalid_rows():
    assert tokenize("😀" * 20000)[0]["raw_display"] == "😀" * 128
    with pytest.raises(OrbitError) as error:
        tokenize("😀" * 20001)
    assert error.value.code == "IMPORT_TEXT_LIMIT"


def test_lone_surrogate_is_rejected_before_object_or_database_encoding():
    with pytest.raises(OrbitError) as error:
        tokenize("1\ud800")
    assert error.value.code == "IMPORT_TEXT_INVALID"


@pytest.mark.parametrize("value", ["", " \r\n，；", 123, None])
def test_empty_or_non_string_import_is_rejected(value):
    with pytest.raises(OrbitError):
        tokenize(value)


@pytest.mark.parametrize(
    "value", ["ACT_123", "act_act_1", "１２３", "1.0", "-1", "1e3", "1" * 33, "act_", "1\u200b2"]
)
def test_invalid_tokens_remain_explainable_without_becoming_platform_calls(value):
    row = tokenize(value)[0]
    assert row["state"] == "INVALID" and row["normalized_id"] is None


def test_extension_is_explicit_and_does_not_accept_actor_or_tenant_injection():
    value = {
        "vendor_id": "10000000-0000-4000-8000-000000000001",
        "owner_user_id": "10000000-0000-4000-8000-000000000002",
        "owner_team_id": "10000000-0000-4000-8000-000000000003",
        "account_ids_text": "act_00001",
    }
    assert parse_import(json.dumps(value).encode()).account_ids_text == "act_00001"
    with pytest.raises(OrbitError) as error:
        parse_import(json.dumps(value | {"tenant_id": value["vendor_id"]}).encode())
    assert error.value.status == 400


@pytest.mark.parametrize(
    "states,expected",
    [
        (["SUCCEEDED", "ALREADY_EXISTS", "DUPLICATE"], "SUCCEEDED"),
        (["SUCCEEDED", "INVALID"], "PARTIAL_SUCCESS"),
        (["ALREADY_EXISTS", "FORBIDDEN"], "PARTIAL_SUCCESS"),
        (["INVALID", "DUPLICATE"], "FAILED"),
        (["WAITING", "SUCCEEDED"], "RUNNING"),
        (["FETCHING", "INVALID"], "RUNNING"),
    ],
)
def test_batch_summary_never_equates_acceptance_and_success(states, expected):
    assert batch_summary(states)["state"] == expected
    assert batch_summary(["WAITING"], started=False)["state"] == "QUEUED"


def test_metadata_preserves_platform_name_and_distinguishes_storage_id_limit():
    value = {
        "external_id": "0" * 64,
        "name": "  平台原始名称  ",
        "currency": "USD",
        "timezone_id": "America/New_York",
        "account_status": "ACTIVE",
        "auth_status": "AUTHORIZED",
        "observed_at": datetime(2026, 11, 8, tzinfo=UTC),
    }
    result = metadata(value, "0" * 64, frozenset({"USD"}))
    assert result.name == value["name"] and result.external_id == "0" * 64
    assert tokenize("0" * 64)[0]["state"] == "INVALID"
    for field, invalid in [
        ("external_id", 12),
        ("currency", "ZZZ"),
        ("timezone_id", "UTC-5"),
        ("observed_at", datetime(2026, 1, 1)),
    ]:
        with pytest.raises(OrbitError):
            metadata(value | {field: invalid}, "0" * 64, frozenset({"USD"}))


def test_timezone_offset_uses_reference_instant_and_dst_not_fixed_offset():
    summer = timezone_payload("America/New_York", datetime(2026, 7, 1, tzinfo=UTC))
    winter = timezone_payload("America/New_York", datetime(2026, 12, 1, tzinfo=UTC))
    assert summer["offset_at"] == "-04:00" and winter["offset_at"] == "-05:00"
    with pytest.raises(ValueError):
        timezone_payload("UTC", datetime(2026, 1, 1))


async def test_unconfigured_connector_never_returns_fake_success_or_zero_balance():
    with pytest.raises(OrbitError) as error:
        await UnavailableAccountAdapter().fetch_metadata("001")
    assert error.value.code == "ACCOUNT_CONNECTOR_UNVERIFIED"
    value = unknown_observation("USD")
    assert value["amount"] is None and value["status"] == "UNSYNCED"
