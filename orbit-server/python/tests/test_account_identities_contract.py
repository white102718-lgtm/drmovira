"""身份结构原合同专项；不替代真实账户可用性、权限或平台采集验收。"""

from copy import deepcopy

import pytest

from orbit_api.account_identities_contract import identities
from orbit_api.errors import OrbitError

ACCOUNT = "10000000-0000-4000-8000-000000000001"


def payload():
    return {
        "account_id": ACCOUNT,
        "resources": [
            {
                "external_id": "000123",
                "name": "",
                "kind": "PAGE",
                "usable": False,
                "reason_code": "ACCOUNT_NOT_AUTHORIZED",
            }
        ],
        "capability_version": "controlled-observation-v1",
        "observed_at": "2026-11-08T12:00:00+08:00",
    }


def test_original_four_fields_preserve_leading_zero_and_empty_name():
    value = identities(payload(), expected_account_id=ACCOUNT)
    assert set(value) == {"account_id", "resources", "capability_version", "observed_at"}
    assert value["resources"][0]["external_id"] == "000123"
    assert value["resources"][0]["name"] == ""
    assert value["observed_at"] == "2026-11-08T04:00:00.000Z"


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", None),
        ("account_id", "not-uuid"),
        ("account_id", "10000000-0000-4000-8000-000000000002"),
        ("resources", {}),
        ("resources", [None] * 5001),
        ("capability_version", ""),
        ("capability_version", "v" * 65),
        ("capability_version", 1),
        ("observed_at", "2026-11-08T12:00:00"),
        ("observed_at", "2026-02-30T12:00:00Z"),
    ],
)
def test_top_level_invalid_fields_do_not_coerce(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(OrbitError) as failure:
        identities(data, expected_account_id=ACCOUNT)
    assert failure.value.status == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("external_id", "１２３"),
        ("external_id", 123),
        ("external_id", "1" * 65),
        ("external_id", "act_123"),
        ("name", "x" * 256),
        ("name", "\ud800"),
        ("kind", "BM"),
        ("kind", []),
        ("usable", 1),
        ("usable", "true"),
        ("reason_code", ""),
        ("reason_code", "r" * 65),
    ],
)
def test_resource_invalid_fields_do_not_coerce_or_infer(field, value):
    data = payload()
    data["resources"][0][field] = value
    with pytest.raises(OrbitError) as failure:
        identities(data, expected_account_id=ACCOUNT)
    assert failure.value.status == 422


def test_unknown_and_missing_fields_are_rejected_including_secrets():
    for target in ("root", "resource"):
        for operation in ("extra", "missing"):
            data = payload()
            value = data if target == "root" else data["resources"][0]
            if operation == "extra":
                value["token"] = "fixture-only-never-public"
            else:
                value.pop("account_id" if target == "root" else "name")
            with pytest.raises(OrbitError):
                identities(data, expected_account_id=ACCOUNT)


def test_empty_collection_is_only_structurally_valid_not_proof_of_sync():
    data = payload()
    data["resources"] = []
    assert identities(data, expected_account_id=ACCOUNT)["resources"] == []


def test_duplicates_reject_within_kind_but_identical_ids_across_kinds_are_distinct():
    data = payload()
    data["resources"].append(deepcopy(data["resources"][0]))
    with pytest.raises(OrbitError) as failure:
        identities(data, expected_account_id=ACCOUNT)
    assert failure.value.code == "DUPLICATE_VALUE"
    data["resources"][1]["kind"] = "PIXEL"
    assert len(identities(data, expected_account_id=ACCOUNT)["resources"]) == 2
