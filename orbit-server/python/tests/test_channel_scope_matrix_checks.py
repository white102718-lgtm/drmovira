"""仅验证专项夹具防污染/拒绝对照能力，不代替真实HTTP/MySQL矩阵。"""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def checks(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("channel_scope_matrix_checks")


class Database:
    def __init__(self, name="orbit_py_it_" + "a" * 32):
        self.name = name
        self.rows = {}
        self.queries = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql):
        self.queries.append(sql)

    def fetchone(self):
        return (self.name,)

    def fetchall(self):
        return self.rows.get(self.queries[-1].removeprefix("SELECT * FROM "), [])


@pytest.mark.parametrize(
    "database", ["orbit", "orbit_py_it_abc", "mysql", "orbit_py_it_" + "g" * 32]
)
def test_snapshot_refuses_nonisolated_database_before_reading_tables(checks, database):
    connection = Database(database)
    with pytest.raises(AssertionError):
        checks.snapshot(connection)
    assert connection.queries == ["SELECT DATABASE()"]


@pytest.mark.parametrize(
    "table",
    [
        "orbit_channel",
        "orbit_channel_owner",
        "orbit_reference_clock",
        "orbit_reference_record",
        "orbit_reference_owner",
        "orbit_reference_product_agent",
        "orbit_reference_import",
        "orbit_reference_event",
        "orbit_reference_idempotency",
    ],
)
def test_rejection_snapshot_detects_changed_value_with_same_row_count(checks, table):
    connection = Database()
    connection.rows[table] = [("id", "original-json", 1)]
    before = checks.snapshot(connection)
    connection.rows[table] = [("id", "modified-json", 1)]
    assert checks.snapshot(connection) != before


def test_snapshot_is_stable_without_database_order_assumptions(checks):
    connection = Database()
    connection.rows["orbit_channel"] = [("b",), ("a",)]
    before = checks.snapshot(connection)
    connection.rows["orbit_channel"] = [("a",), ("b",)]
    assert checks.snapshot(connection) == before


def test_owner_intent_copies_explicit_empty_and_shared_collections(checks):
    actor = {"id": "user", "team": "team"}
    owners = ["user", "peer"]
    intent = checks.own(actor, owners)
    owners.append("foreign")
    assert intent["data_owner_user_ids"] == ["user", "peer"]
    assert checks.own(actor, [])["data_owner_user_ids"] == []


def test_later_dialog_changes_do_not_mutate_original_channel_intent(checks):
    actor = {"id": "user", "team": "team"}
    supplied = {"ownership": checks.own(actor)}
    body = checks.write_body(actor, "product", "agent", **supplied)
    supplied["ownership"]["data_owner_user_ids"].append("peer")
    assert body["ownership"]["data_owner_user_ids"] == ["user"]
    assert body["url"].endswith("#retained")


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/channels", None),
        ("PUT", "/api/v1/channels/object", 3),
        ("PUT", "/api/v1/channels/object/owners", 3),
        ("POST", "/api/v1/channels/object/archive", 3),
    ],
)
def test_request_revision_matches_create_and_existing_object_contract(
    checks, method, path, expected
):
    assert checks.request_revision(method, path, 3) == expected


def test_failed_denial_emits_only_fixed_method_and_status_numbers(checks, capsys):
    with pytest.raises(AssertionError):
        checks.assert_denial_status("POST", 403, 400)
    assert capsys.readouterr().out == (
        "CHANNEL_SCOPE_DENIAL method=POST expected_status=403 actual_status=400\n"
    )


def test_successful_denial_is_quiet(checks, capsys):
    checks.assert_denial_status("PUT", 404, 404)
    assert capsys.readouterr().out == ""
