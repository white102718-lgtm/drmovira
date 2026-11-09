"""账户命令控制单测；会话/来源替身不代替真实权限或MySQL原子验收。"""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_actions_contract import Assignment, next_business_midnight
from orbit_api.account_actions_store import (
    AccountActionsStore,
    projection_instant,
    require_projection_current,
)
from orbit_api.errors import OrbitError

TENANT, ACCOUNT, SOURCE_OWNER, TARGET_OWNER, TEAM, REQUEST, INTERVAL = (
    str(UUID(int=index)) for index in range(1, 8)
)
CURRENT = SimpleNamespace(
    tenant_id=TENANT, actor_id=1, subject_id=SOURCE_OWNER, team_id=TEAM, data_role="SUPER_ADMIN"
)


class Result:
    def __init__(self, rows=(), scalar=None):
        self.rows, self.scalar = rows, scalar

    def mappings(self):
        return self

    def scalar_one_or_none(self):
        return self.scalar

    def __iter__(self):
        return iter(self.rows)


def account():
    return {
        "id": ACCOUNT,
        "revision": 4,
        "owner_user_id": SOURCE_OWNER,
        "owner_team_id": TEAM,
        "vendor_id": None,
        "timezone_id": "Asia/Shanghai",
        "currency": "USD",
    }


class Session:
    def __init__(self):
        self.calls = []
        self.sources = [
            {
                "id": REQUEST,
                "revision": 1,
                "secrets_json": '{"accessToken":"fixture"}',
                "settings_json": '{"businessId":"42","graphVersion":"v25.0"}',
            }
        ]

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if "FROM orbit_account_assignment" in sql and sql.startswith("SELECT"):
            return Result(
                [
                    account()
                    | {
                        "id": INTERVAL,
                        "starts_at": (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None),
                        "ends_at": None,
                    }
                ]
            )
        if "FROM orbit_system_configuration" in sql:
            return Result(self.sources)
        return Result()


def setup(monkeypatch, *, replay=None):
    store = AccountActionsStore(None)
    events = []

    async def begin(*args):
        return CURRENT, set(), account(), "fixture-hash", replay

    async def vendor(*args):
        return None, {"alias": None, "alias_revision": None, "source": "NO_VENDOR"}

    async def event(*args):
        events.append(args)

    monkeypatch.setattr(store, "begin", begin)
    monkeypatch.setattr("orbit_api.account_actions_store.assignment_vendor", vendor)
    monkeypatch.setattr("orbit_api.account_actions_store.event", event)
    return store, events


@pytest.mark.asyncio
async def test_assignment_accepts_future_history_without_early_projection_or_metric_success(
    monkeypatch,
):
    store, events = setup(monkeypatch)
    session = Session()
    effective = next_business_midnight("Asia/Shanghai", datetime.now(UTC))
    value = Assignment(TARGET_OWNER, TEAM, None, effective.isoformat(), "受控分配原因")
    ack = await store.assign(session, 1, ACCOUNT, 4, "fixture-key", "", "", value, REQUEST)
    assert ack == {"id": ACCOUNT, "revision": 5, "state": "SCHEDULED", "request_id": REQUEST}
    closes = [params for sql, params in session.calls if "SET ends_at=:effective" in sql]
    assert len(closes) == 1 and closes[0]["effective"] == effective.replace(tzinfo=None)
    assert any("INSERT INTO orbit_account_assignment" in sql for sql, _ in session.calls)
    assert not any("UPDATE orbit_ad_account SET owner_user_id" in sql for sql, _ in session.calls)
    assert not any(
        "synced_at" in sql or "orbit_account_day_fact" in sql for sql, _ in session.calls
    )
    assert events[0][5] == "ACCOUNT_ASSIGNMENT_SCHEDULED"


@pytest.mark.asyncio
async def test_persistent_sync_waiting_executor_never_marks_synced_or_zero_spend(monkeypatch):
    store, _ = setup(monkeypatch)
    session = Session()
    ack = await store.sync(session, 1, ACCOUNT, 4, "fixture-key", "", "", "受控同步", REQUEST)
    assert ack["state"] == "WAITING_EXECUTOR"
    inserted = [
        params for sql, params in session.calls if "INSERT INTO orbit_account_command" in sql
    ]
    assert inserted[0]["error"] == "ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED"
    assert inserted[0]["config"] == REQUEST
    assert not any("synced_at" in sql or "spend" in sql.lower() for sql, _ in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2])
async def test_missing_or_ambiguous_source_never_guesses_token_or_fake_queues(monkeypatch, count):
    store, _ = setup(monkeypatch)
    session = Session()
    session.sources = session.sources * count
    with pytest.raises(OrbitError) as failure:
        await store.sync(session, 1, ACCOUNT, 4, "fixture-key", "", "", "受控同步", REQUEST)
    assert failure.value.code == "ACCOUNT_SYNC_SOURCE_UNAVAILABLE"
    assert not any("INSERT INTO orbit_account_command" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_unbind_is_local_preserves_history_and_ends_unexecuted_read_job(monkeypatch):
    store, events = setup(monkeypatch)
    session = Session()
    ack = await store.unbind(session, 1, ACCOUNT, 4, "fixture-key", "", "", "受控本地解绑", REQUEST)
    assert ack["state"] == "SUCCEEDED"
    assert any("SET unbound_at=:now" in sql for sql, _ in session.calls)
    assert any("ACCOUNT_LOCALLY_UNBOUND" in sql for sql, _ in session.calls)
    assert not any("DELETE " in sql or "auth_status=" in sql for sql, _ in session.calls)
    assert events[0][5] == "ACCOUNT_UNBIND_SUCCEEDED"


@pytest.mark.asyncio
async def test_idempotent_replay_returns_original_ack_without_reclosing_history(monkeypatch):
    original = {"id": ACCOUNT, "revision": 2, "state": "SCHEDULED", "request_id": REQUEST}
    store, events = setup(monkeypatch, replay=original)
    session = Session()
    value = Assignment(TARGET_OWNER, TEAM, None, "2020-01-01T00:00:00Z", "原意图")
    assert (
        await store.assign(session, 1, ACCOUNT, 1, "fixture-key", "", "", value, REQUEST)
        == original
    )
    assert session.calls == [] and events == []


@pytest.mark.asyncio
async def test_lagging_due_projection_is_dependency_failure_never_old_owner_success():
    class LagSession:
        async def execute(self, statement, params):
            return Result(scalar=1)

    with pytest.raises(OrbitError) as failure:
        await require_projection_current(LagSession(), TENANT, ACCOUNT, datetime.now(UTC))
    assert failure.value.status == 503
    assert failure.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"


def test_projection_guard_never_drops_non_utc_offset_or_accepts_implicit_local_clock():
    local = datetime(2026, 11, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    assert projection_instant(local) == datetime(2026, 11, 8, 16)
    with pytest.raises(ValueError):
        projection_instant(local.replace(tzinfo=None))
