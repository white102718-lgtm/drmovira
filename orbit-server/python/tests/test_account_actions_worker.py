"""到期分配控制替身测试；真实MySQL原子性/多时区/恢复由主线独立专项验收。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_actions_worker import AccountActionsWorker
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError

TENANT, ACCOUNT, COMMAND, ASSIGNMENT, SOURCE_OWNER, TARGET_OWNER, TEAM, REQUEST = (
    str(UUID(int=index)) for index in range(1, 9)
)
NOW = datetime(2026, 11, 9, 16, tzinfo=UTC)
CURRENT = SimpleNamespace(
    tenant_id=TENANT, actor_id=1, subject_id=SOURCE_OWNER, team_id=TEAM, data_role="SUPER_ADMIN"
)


class Result:
    def __init__(self, rows=(), scalar=None):
        self.rows, self.scalar = rows, scalar

    def scalar_one_or_none(self):
        return self.scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class Session:
    def __init__(self, *, busy=False):
        self.busy, self.calls = busy, []
        source = {"owner_user_id": SOURCE_OWNER, "owner_team_id": TEAM, "vendor_id": None}
        source |= {"timezone_id": "Asia/Shanghai", "currency": "USD"}
        self.account = {"id": ACCOUNT, "revision": 10, "unbound_at": None} | source
        self.command = {
            "id": COMMAND,
            "account_id": ACCOUNT,
            "state": "SCHEDULED",
            "active_kind": "ASSIGNMENT",
            "revision": 1,
            "actor_id": 1,
            "actor_subject_id": SOURCE_OWNER,
            "request_id": REQUEST,
            "assignment_id": ASSIGNMENT,
            "effective_from": (NOW - timedelta(hours=1)).replace(tzinfo=None),
            "source_json": canonical(source),
            "payload_json": canonical(
                {
                    "operator_user_id": TARGET_OWNER,
                    "owner_team_id": TEAM,
                    "vendor_id": None,
                    "effective_from": (NOW - timedelta(hours=1)).isoformat(),
                    "reason": "受控下一日分配",
                }
            ),
        }
        self.future = {
            "owner_user_id": TARGET_OWNER,
            "owner_team_id": TEAM,
            "vendor_id": None,
            "starts_at": self.command["effective_from"],
            "ends_at": None,
            "revision": 1,
        }

    def in_transaction(self):
        return True

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if "FROM orbit_account_clock" in sql:
            return Result(scalar=None if self.busy else 1)
        if sql.startswith("SELECT id,account_id FROM orbit_account_command"):
            allowed = self.command["state"] == "SCHEDULED" or (
                "'BLOCKED'" in sql and self.command["state"] == "BLOCKED"
            )
            due = self.command["effective_from"] <= params["now"]
            return Result([self.command.copy()] if allowed and due else [])
        if sql.startswith("SELECT * FROM orbit_ad_account"):
            return Result([self.account.copy()])
        if sql.startswith("SELECT * FROM orbit_account_command"):
            return Result([self.command.copy()])
        if sql.startswith("SELECT 1 FROM orbit_ad_account"):
            return Result(scalar=1)
        if sql.startswith("SELECT * FROM orbit_account_assignment"):
            return Result([self.future.copy()])
        if sql.startswith("UPDATE orbit_ad_account SET owner_user_id"):
            self.account.update(
                {key: params[key] for key in ("owner_user_id", "owner_team_id", "vendor_id")}
            )
        if "SET state='SUCCEEDED'" in sql:
            self.command.update({"state": "SUCCEEDED", "active_kind": None})
        if "SET state='BLOCKED'" in sql:
            self.command["state"] = "BLOCKED"
        return Result()


def setup(monkeypatch, *, forbidden=False, audit_failure=False):
    events = []

    async def authorization(*args, **kwargs):
        assert kwargs["acting_subject"] is False
        if forbidden:
            raise OrbitError(403, "PERMISSION_DENIED", "已撤销分配权限")
        return CURRENT

    async def managed(*args):
        return set()

    async def vendor(*args, **kwargs):
        assert kwargs["acting_subject"] is False
        return None, {"alias": None, "alias_revision": None, "source": "NO_VENDOR"}

    async def event(*args):
        if audit_failure:
            raise RuntimeError("controlled-audit-failure")
        events.append(args[5])

    monkeypatch.setattr("orbit_api.account_actions_worker.require_business_access", authorization)
    monkeypatch.setattr("orbit_api.account_actions_worker.managed_teams", managed)
    monkeypatch.setattr("orbit_api.account_actions_worker.assignment_vendor", vendor)
    monkeypatch.setattr("orbit_api.account_actions_worker.event", event)
    return events


@pytest.mark.asyncio
async def test_no_early_projection_transfer_and_due_activation_is_idempotent(monkeypatch):
    session, worker = Session(), AccountActionsWorker()
    events = setup(monkeypatch)
    assert await worker.advance_due(session, TENANT, now=NOW - timedelta(hours=2)) == {
        "activated": 0,
        "blocked": 0,
        "busy": False,
    }
    assert session.account["owner_user_id"] == SOURCE_OWNER
    assert (await worker.advance_due(session, TENANT, now=NOW))["activated"] == 1
    assert session.account["owner_user_id"] == TARGET_OWNER
    assert session.command["state"] == "SUCCEEDED"
    assert (await worker.advance_due(session, TENANT, now=NOW))["activated"] == 0
    assert events == ["ACCOUNT_ASSIGNMENT_ACTIVATED"]
    assert all("orbit_account_day_fact" not in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_revoked_actor_blocks_without_projection_update_and_requires_explicit_recovery(
    monkeypatch,
):
    session, worker = Session(), AccountActionsWorker()
    setup(monkeypatch, forbidden=True)
    assert (await worker.advance_due(session, TENANT, now=NOW))["blocked"] == 1
    assert session.command["state"] == "BLOCKED"
    assert session.account["owner_user_id"] == SOURCE_OWNER
    setup(monkeypatch)
    assert (await worker.advance_due(session, TENANT, now=NOW))["activated"] == 0
    assert (await worker.advance_due(session, TENANT, now=NOW, include_blocked=True))[
        "activated"
    ] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["owner", "unbind", "interval"])
async def test_source_or_history_drift_cannot_masquerade_as_completed_assignment(
    monkeypatch, target
):
    session = Session()
    setup(monkeypatch)
    if target == "owner":
        session.account["owner_user_id"] = TARGET_OWNER
    elif target == "unbind":
        session.account["unbound_at"] = NOW
    else:
        session.future["revision"] = 2
    assert (await AccountActionsWorker().advance_due(session, TENANT, now=NOW))["blocked"] == 1
    assert session.command["active_kind"] == "ASSIGNMENT"
    assert not any(
        sql.startswith("UPDATE orbit_ad_account SET owner_user_id") for sql, _ in session.calls
    )


@pytest.mark.asyncio
async def test_audit_failure_propagates_for_outer_database_rollback_not_success(monkeypatch):
    session = Session()
    setup(monkeypatch, audit_failure=True)
    with pytest.raises(RuntimeError, match="controlled-audit-failure"):
        await AccountActionsWorker().advance_due(session, TENANT, now=NOW)


@pytest.mark.asyncio
async def test_busy_tenant_does_not_touch_commands_or_claim_success(monkeypatch):
    setup(monkeypatch)
    session = Session(busy=True)
    assert await AccountActionsWorker().advance_due(session, TENANT, now=NOW) == {
        "activated": 0,
        "blocked": 0,
        "busy": True,
    }
    assert len(session.calls) == 1
