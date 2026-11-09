"""500身份夹具与精确集合反例；不充当真实HTTP/数据库上限验收。"""

import importlib
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def checks(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("channel_owners_500_checks")


def test_five_hundred_targets_and_one_control_have_distinct_identity_keys(checks):
    values = checks.owner_fixtures(uuid.uuid4(), "isolated-team", 2000000)
    assert len(values) == 501
    for key in ("id", "subject", "native", "name"):
        assert len({row[key] for row in values}) == 501
    assert {row["team"] for row in values} == {"isolated-team"}
    assert [row["native"] for row in values] == list(range(2000000, 2000501))


def test_fixture_namespace_can_reproduce_exact_uuid_manifest(checks):
    namespace = uuid.uuid4()
    assert checks.owner_fixtures(namespace, "team", 1000) == checks.owner_fixtures(
        namespace, "team", 1000
    )
    assert (
        checks.owner_fixtures(namespace, "team", 1000)[0]["id"]
        != checks.owner_fixtures(uuid.uuid4(), "team", 1000)[0]["id"]
    )


def test_manifest_does_not_contain_plaintext_passwords_or_tokens(checks):
    values = checks.owner_fixtures(uuid.uuid4(), "team", 2000)
    assert all(set(row) == {"id", "subject", "team", "native", "name", "display"} for row in values)


@pytest.mark.parametrize(
    "actual", [["one", "one"], ["one", "three"], ["one"], ["one", "two", "three"]]
)
def test_matching_count_cannot_hide_duplicate_missing_or_foreign_member(checks, actual):
    with pytest.raises(AssertionError):
        checks.assert_exact_owners(actual, ["one", "two"])


def test_original_owner_order_does_not_change_membership_meaning(checks):
    checks.assert_exact_owners(["two", "one"], ["one", "two"])
