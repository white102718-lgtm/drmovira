"""READ真实工具的纯护栏；不连接SQL，不将内存Provider当真实来源证据。"""

import asyncio
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_store import (
    PublicationValidationReceipt,
    publication_validation_binding,
)

PATH = Path(__file__).resolve().parents[2] / "tools/metrics_query_read_checks.py"
spec = importlib.util.spec_from_file_location("metrics_read_tool_guard", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 32 + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_entry_rejects_target_before_sql_http_or_imported_fixture(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        module.run_metrics_query_read_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.assert_not_called()


def test_actual_database_mismatch_stops_after_readonly_database_probe():
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = ("wrong_database",)
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: cursor, commit=Mock())
    with pytest.raises(ValueError):
        module.guard_target(admin, "orbit_py_it_" + "a" * 32)
    cursor.execute.assert_called_once_with("SELECT DATABASE()")
    admin.commit.assert_not_called()


@pytest.mark.parametrize(
    "identifier",
    [
        "orbit_metric_publication",
        "it_metric_read_" + "a" * 15,
        "it_metric_read_" + "A" * 16,
        "it_metric_read_" + "a" * 16 + ";DROP TABLE x",
        None,
    ],
)
def test_evidence_identifier_never_accepts_other_table_or_request_input(identifier):
    with pytest.raises(ValueError):
        module.RegisteredSqlReadSource(identifier)


def head():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "tenant_id": str(uuid4()),
        "id": str(uuid4()),
        "generation": 1,
        "profile_id": str(uuid4()),
        "profile_version": "observed-v001",
        "profile_hash": "a" * 64,
        "authority_kind": "ISOLATED_TEST",
        "source_config_id": str(uuid4()),
        "source_config_revision": 1,
        "source_proof_json": '{"kind":"SQL_ONLY_NOT_PLATFORM"}',
        "state": "PUBLISHED",
        "expected_cell_count": 1,
        "expected_cells_hash": "b" * 64,
        "captured_cells_hash": "b" * 64,
        "cell_count": 1,
        "fact_count": 1,
        "capture_sequence_max": 120,
        "manifest_hash": "c" * 64,
        "publisher_actor_id": 1,
        "request_id": str(uuid4()),
        "oldest_observed_at": now,
        "created_at": now,
        "published_at": now,
    }


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class Session:
    def __init__(self, header):
        value = list(publication_validation_binding(header))
        self.registration = [
            {
                "publication_id": header["id"],
                "binding_json": json.dumps(value),
                "binding_hash": hashlib.sha256(canonical(value).encode()).hexdigest(),
                "revoked": 0,
            }
        ]
        self.configuration = [
            {"section": "METRICS", "enabled": 1, "revision": 1, "verification_status": "UNTESTED"}
        ]
        self.calls = []

    async def execute(self, statement, values):
        sql = str(statement)
        self.calls.append((sql, values))
        if "binding_json" in sql:
            return Result(self.registration)
        if "FROM orbit_system_configuration" in sql:
            return Result(self.configuration)
        raise AssertionError("未登记的纯SQL替身")


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.syspath_prepend(str(PATH.parent))
    value = head()
    source = module.RegisteredSqlReadSource("it_metric_read_" + "a" * 16)
    session = Session(value)
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=value["tenant_id"]))
    return value, source, session, scope


def verify(scenario):
    value, source, session, scope = scenario
    return asyncio.run(source.verify_publications(session, scope, {}, (value,)))


def test_receipt_is_exact_pre_registered_tuple_and_current_unverified_technical_configuration(
    scenario,
):
    value, source, session, _ = scenario
    receipts = verify(scenario)
    assert type(receipts) is tuple and len(receipts) == 1
    assert type(receipts[0]) is PublicationValidationReceipt
    assert receipts[0].binding == tuple(json.loads(session.registration[0]["binding_json"]))
    assert "FOR SHARE" in session.calls[0][0] and "FOR SHARE" in session.calls[1][0]
    assert session.calls[1][1]["id"] == value["source_config_id"]
    assert source.batches == [(value["id"],)]
    assert source.kind == "ISOLATED_TEST"


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "revoked",
        "bad-json",
        "wrong-hash",
        "wrong-body",
        "bool-as-int",
        "incoming-changed",
    ],
)
def test_registered_source_cannot_echo_changed_head_or_return_corrupt_evidence(scenario, failure):
    value, _, session, _ = scenario
    row = session.registration[0]
    if failure == "missing":
        session.registration = []
    elif failure == "revoked":
        row["revoked"] = 1
    elif failure == "bad-json":
        row["binding_json"] = "invalid"
    elif failure == "wrong-hash":
        row["binding_hash"] = "f" * 64
    elif failure == "incoming-changed":
        value["fact_count"] = 2
    else:
        binding = json.loads(row["binding_json"])
        binding[2 if failure == "bool-as-int" else 17] = (
            True if failure == "bool-as-int" else "d" * 64
        )
        row["binding_json"] = json.dumps(binding)
        row["binding_hash"] = hashlib.sha256(canonical(binding).encode()).hexdigest()
    with pytest.raises(OrbitError) as result:
        verify(scenario)
    assert result.value.status == 503 and result.value.code == "METRICS_DATA_UNVERIFIED"
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": 0},
        {"revision": 2},
        {"section": "META_BM"},
        {"verification_status": "READ_VERIFIED"},
        None,
    ],
)
def test_technical_config_is_current_exact_revision_and_never_claims_meta_verification(
    scenario, changes
):
    _, _, session, _ = scenario
    if changes is None:
        session.configuration = []
    else:
        session.configuration[0] |= changes
    with pytest.raises(OrbitError) as result:
        verify(scenario)
    assert result.value.status == 503 and len(session.calls) == 2


@pytest.mark.parametrize("count", [0, 201])
def test_provider_batch_guard_precedes_database_reads(scenario, count):
    value, source, session, scope = scenario
    with pytest.raises(AssertionError, match="metric_read_receipt_batch_bound"):
        asyncio.run(source.verify_publications(session, scope, {}, (value,) * count))
    assert session.calls == []


def test_exact_ten_scenarios_and_cleanup_does_not_touch_other_tables_or_tokens():
    assert len(module.METRIC_QUERY_READ_CASES) == len(set(module.METRIC_QUERY_READ_CASES)) == 10
    source = PATH.read_text(encoding="utf-8")
    assert 'cleanup.callback(sql, "DROP TABLE " + table)' in source
    assert 'cleanup.callback(sql, "INSERT INTO sys_role_menu' in source
    assert "TRUNCATE" not in source and "DELETE FROM orbit_metric_" not in source
    assert "SQL_ONLY_NOT_PLATFORM" in source and '"UNTESTED"' in source
    assert "print(" not in source and ".write_text(" not in source
    assert "METRICS_DATA_UNVERIFIED" in source
