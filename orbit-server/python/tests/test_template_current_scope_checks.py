"""RR专项安全边界与配置source/head回归纯测；不代替真实数据库竞态。"""

import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tools.template_current_scope_checks import (
    TEMPLATE_CURRENT_SCOPE_CASES,
    assert_current_scope_denied,
    guard_template_scope_target,
    run_template_current_scope_checks,
)

from orbit_api.errors import OrbitError


class Admin:
    host, port = "127.0.0.1", 13306

    def __init__(self, database):
        self.database, self.calls = database, []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, statement):
        self.calls.append(statement)

    def fetchone(self):
        return (self.database,)

    def commit(self):
        self.calls.append("commit")


@pytest.mark.parametrize("field,value", [("host", "production.example"), ("port", 3306)])
def test_guard_rejects_nonisolated_target_before_any_sql(field, value):
    database = "orbit_py_it_" + uuid4().hex
    admin = Admin(database)
    setattr(admin, field, value)
    with pytest.raises(ValueError):
        guard_template_scope_target(admin, database)
    assert admin.calls == []


@pytest.mark.parametrize("database", ["orbit", "orbit_py_it_123", None])
def test_guard_rejects_unbounded_or_unknown_database(database):
    admin = Admin(database)
    with pytest.raises(ValueError):
        guard_template_scope_target(admin, database)
    assert admin.calls == []


def test_guard_checks_actual_current_database_not_only_requested_name():
    admin = Admin("another_database")
    with pytest.raises(ValueError):
        guard_template_scope_target(admin, "orbit_py_it_" + uuid4().hex)
    assert admin.calls == ["SELECT DATABASE()"]


def test_successful_guard_ends_administrative_read_transaction():
    database = "orbit_py_it_" + uuid4().hex
    admin = Admin(database)
    guard_template_scope_target(admin, database)
    assert admin.calls == ["SELECT DATABASE()", "commit"]


@pytest.mark.parametrize(
    "status,code", [(403, "PERMISSION_DENIED"), (503, "STATE_UNAVAILABLE"), (404, "OTHER_CODE")]
)
def test_scope_denial_cannot_be_substituted_by_unrelated_failure(status, code):
    with pytest.raises(AssertionError):
        assert_current_scope_denied(OrbitError(status, code, "受控拒绝"))


def test_three_cases_and_seven_argument_entrypoint_are_exact():
    assert len(TEMPLATE_CURRENT_SCOPE_CASES) == len(set(TEMPLATE_CURRENT_SCOPE_CASES)) == 3
    assert list(inspect.signature(run_template_current_scope_checks).parameters) == [
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
    ]
    assert_current_scope_denied(OrbitError(404, "NOT_FOUND", "当前范围拒绝"))


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_validated_edit_uses_configuration_source_one_not_state_head_two(
    monkeypatch, changed
):
    import orbit_api.launch_plan_source as source_module
    import orbit_api.launch_store as module
    from orbit_api.authorization import BusinessContext

    tenant, subject, team, plan_id = (str(uuid4()) for _ in range(4))
    current = BusinessContext(1, tenant, "USER", subject, team)
    value = {"name": "原配置"}
    previous = dict(
        id=plan_id,
        revision=2,
        state="VALIDATED",
        payload_json=value,
        created_at=datetime(2026, 11, 8),
        updated_at=datetime(2026, 11, 8),
    )
    requested = value | {"name": "修改配置"} if changed else dict(value)
    monkeypatch.setattr(module.access, "successful_replay", AsyncMock(return_value=None))
    monkeypatch.setattr(module.access, "context", AsyncMock(return_value=current))
    monkeypatch.setattr(module.access, "clock", AsyncMock())
    monkeypatch.setattr(module.access, "replay", AsyncMock(return_value=None))
    remember = AsyncMock()
    monkeypatch.setattr(module.access, "remember", remember)
    monkeypatch.setattr(module, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(module, "expanded_counts", lambda *args: None)
    monkeypatch.setattr(module, "validate_sources", AsyncMock(return_value={"metric_profiles": {}}))
    anchor = AsyncMock(return_value=SimpleNamespace(source_revision=1, head_revision=2))
    monkeypatch.setattr(source_module, "capture_plan_source", anchor)
    calls = []

    async def execute(statement, parameters):
        calls.append((str(statement), parameters))
        assert parameters["revision"] == 1
        return SimpleNamespace(scalar_one=lambda: {"metric_profiles": {}})

    session = SimpleNamespace(execute=execute)
    store = module.LaunchStore(None)
    monkeypatch.setattr(store, "row", AsyncMock(return_value=previous))
    persist = AsyncMock(return_value={"state": "DRAFT", "revision": 3})
    monkeypatch.setattr(store, "persist", persist)
    result = await store.save(
        session, 1, "auth", "csrf", "new-key", requested, plan_id, 2, str(uuid4())
    )
    anchor.assert_awaited_once_with(session, current, previous)
    assert len(calls) == 1 and "orbit_launch_plan_version" in calls[0][0]
    if changed:
        assert result == {"state": "DRAFT", "revision": 3}
        persist.assert_awaited_once()
        assert persist.await_args.args[2] == requested
        assert persist.await_args.args[5] == previous
        remember.assert_not_awaited()
    else:
        assert result["state"] == "VALIDATED" and result["revision"] == 2
        persist.assert_not_awaited()
        remember.assert_awaited_once()
