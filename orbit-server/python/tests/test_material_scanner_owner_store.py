"""037协议纯测；真实原子提交/并发/外键另由本机UUID数据库专项验收。"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_scanner_owner_store import (
    SOURCE_FIELDS,
    StoredOwnerEvent,
    append_owner_event,
    create_owner_audit_sink,
    read_owner_events,
    validate_owner_event,
)


@pytest.fixture
def event():
    return {
        "event_id": str(uuid4()),
        "profile_id": "explicit-owner",
        "definition_revision": 1,
        "instance_id": str(uuid4()),
        "action": "STARTING",
        "occurred_at": datetime.now(UTC).isoformat(),
        **{field: "a" * 64 for field in SOURCE_FIELDS},
    }


def test_exact_safe_fields_preserve_microseconds_and_timezone_normalization(event):
    values = validate_owner_event(event)
    assert values["occurred_at"].tzinfo is None and values["sequence_no"] == 1
    assert len(values["payload_sha256"]) == 64
    assert (
        validate_owner_event({**event, "occurred_at": event["occurred_at"].replace("+00:00", "Z")})
        == values
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_id", "not-uuid"),
        ("instance_id", "ABC"),
        ("profile_id", "../path"),
        ("profile_id", "x" * 41),
        ("definition_revision", True),
        ("definition_revision", 0),
        ("definition_revision", 9_007_199_254_740_992),
        ("action", "FAILED"),
        ("action", ["STARTING"]),
        ("occurred_at", "2026-11-08T01:00:00"),
        ("occurred_at", "2026-11-08T01:00:00+08:00"),
        ("source_sha256", "A" * 64),
        ("source_sha256", None),
        ("config_sha256", "a" * 63),
        ("release_receipt_sha256", "/private/file"),
    ],
)
def test_invalid_or_secret_shaped_values_rejected_without_echo(event, field, value):
    with pytest.raises(OrbitError) as error:
        validate_owner_event({**event, field: value})
    assert error.value.code == "SCANNER_OWNER_AUDIT_INVALID"
    assert str(value) not in error.value.message


@pytest.mark.parametrize("field", ["pid", "port", "password", "config_file", "tenant_id"])
def test_extra_infrastructure_or_user_claims_never_persist(event, field):
    with pytest.raises(OrbitError):
        validate_owner_event({**event, field: "sensitive"})


class Session:
    def __init__(self, rows=(), transaction=True):
        self.rows, self.calls, self.transaction = list(rows), [], transaction

    def in_transaction(self):
        return self.transaction

    async def execute(self, sql, values=None):
        self.calls.append((str(sql), values))
        if "SELECT UTC_TIMESTAMP" in str(sql):
            return SimpleNamespace(scalar_one=lambda: datetime.now(UTC).replace(tzinfo=None))
        if str(sql).lstrip().startswith("SELECT"):
            row = self.rows.pop(0)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: row))
        return None


def head(event, *, state="STARTING", sequence=1):
    values = validate_owner_event(event)
    return {
        **values,
        "state": state,
        "sequence_no": sequence,
        "last_occurred_at": values["occurred_at"],
    }


async def test_append_requires_outer_transaction_and_never_commits(event):
    session = Session(transaction=False)
    with pytest.raises(RuntimeError):
        await append_owner_event(session, event)
    assert session.calls == []


async def test_append_sql_uses_head_lock_and_all_three_tables_without_process_io(event):
    session = Session([head(event), None, None])
    result = await append_owner_event(session, event)
    assert result == StoredOwnerEvent(event["event_id"], 1, False)
    sqls = [sql for sql, _ in session.calls]
    assert "FOR UPDATE" in sqls[2]
    assert any("INSERT INTO orbit_scanner_owner_audit" in sql for sql in sqls)
    assert any("INSERT INTO orbit_scanner_owner_outbox" in sql for sql in sqls)
    assert "UPDATE orbit_scanner_owner_instance" in sqls[-1]


async def test_exact_replay_has_no_audit_outbox_or_head_update(event):
    values = validate_owner_event(event)
    session = Session([head(event, state="STOPPED", sequence=3), values])
    assert (await append_owner_event(session, event)).replayed
    assert not any(
        "INSERT INTO orbit_scanner_owner_audit" in sql
        or "INSERT INTO orbit_scanner_owner_outbox" in sql
        or sql.lstrip().startswith("UPDATE")
        for sql, _ in session.calls
    )


@pytest.mark.parametrize(
    "rows,code",
    [
        ([None], "SCANNER_OWNER_AUDIT_SOURCE_CHANGED"),
        (["source"], "SCANNER_OWNER_AUDIT_SOURCE_CHANGED"),
        (["conflict"], "SCANNER_OWNER_AUDIT_CONFLICT"),
        (["duplicate"], "SCANNER_OWNER_AUDIT_CONFLICT"),
        (["sequence"], "SCANNER_OWNER_AUDIT_SEQUENCE_INVALID"),
    ],
)
async def test_sql_conflicts_fail_before_any_event_insert(event, rows, code):
    marker = rows[0]
    if marker == "source":
        rows = [{**head(event), "source_sha256": "b" * 64}]
    elif marker == "conflict":
        rows = [head(event), {"payload_sha256": "b" * 64, "sequence_no": 1}]
    elif marker == "duplicate":
        rows = [head(event), None, {"event_id": str(uuid4())}]
    elif marker == "sequence":
        rows = [head(event, state="STOPPED", sequence=3), None, None]
    session = Session(rows)
    with pytest.raises(OrbitError) as error:
        await append_owner_event(session, event)
    assert error.value.code == code
    assert not any("INSERT INTO orbit_scanner_owner_audit" in sql for sql, _ in session.calls)


async def test_sink_returns_only_after_commit_and_does_not_echo_database_failure(
    monkeypatch, event
):
    import orbit_api.material_scanner_owner_store as module

    calls = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("session-close")

        @asynccontextmanager
        async def begin(self):
            calls.append("begin")
            try:
                yield
            except Exception:
                calls.append("rollback")
                raise
            calls.append("commit")

    async def append(session, payload):
        calls.append("append")
        return StoredOwnerEvent(payload["event_id"], 1, False)

    monkeypatch.setattr(module, "append_owner_event", append)
    sink = create_owner_audit_sink(Connection)
    assert (await sink(event)).event_id == event["event_id"]
    assert calls == ["begin", "append", "commit", "session-close"]

    async def fail(*args):
        raise RuntimeError("private-password-and-path")

    monkeypatch.setattr(module, "append_owner_event", fail)
    with pytest.raises(OrbitError) as error:
        await sink(event)
    assert calls[-2:] == ["rollback", "session-close"]
    assert error.value.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"
    assert "private" not in error.value.message


@pytest.mark.parametrize(
    "watermark,limit", [(-1, 100), (True, 1), (4, 1), (0, 0), (0, 201), (0, True)]
)
async def test_internal_reads_are_bounded_and_reject_bad_watermarks(event, watermark, limit):
    session = Session()
    with pytest.raises(ValueError):
        await read_owner_events(
            session,
            event["profile_id"],
            1,
            event["instance_id"],
            after_sequence=watermark,
            limit=limit,
        )
    assert not session.calls


async def test_sink_commit_failure_never_returns_stored_result(monkeypatch, event):
    import orbit_api.material_scanner_owner_store as module

    calls = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("closed")

        @asynccontextmanager
        async def begin(self):
            yield
            calls.append("commit-failed")
            raise RuntimeError("private-database-detail")

    async def append(session, payload):
        return StoredOwnerEvent(payload["event_id"], 1, False)

    monkeypatch.setattr(module, "append_owner_event", append)
    with pytest.raises(OrbitError) as error:
        await create_owner_audit_sink(Connection)(event)
    assert calls == ["commit-failed", "closed"]
    assert error.value.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("remote.example", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "production"),
        ("127.0.0.1", 13306, "orbit_py_it_bad"),
    ],
)
def test_real_sql_tool_rejects_shared_or_non_uuid_targets(host, port, database):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "tools/material_scanner_owner_store_checks.py"
    spec = importlib.util.spec_from_file_location("owner_store_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.validate_owner_store_target(SimpleNamespace(host=host, port=port), database)


def test_migration_declares_atomic_outbox_constraints_and_chinese_field_comments():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1]
        / "orbit_api/migrations/037_material_scanner_owner_audit.sql"
    ).read_text("utf-8")
    assert "fk_scanner_owner_outbox_audit" in sql and "FOREIGN KEY(event_id)" in sql
    assert "uq_scanner_owner_instance_uuid" in sql and "uq_scanner_owner_sequence" in sql
    assert "idx_scanner_owner_outbox_pending(processed_at,created_at,event_id)" in sql
    assert "DEFAULT (UTC_TIMESTAMP(6))" in sql
