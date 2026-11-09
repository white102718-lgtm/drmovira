"""命令诊断协议替身测试，不替代真实权限/索引/HTTP专项。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_command_contract import database_time, diagnostic, parse_diagnostic
from orbit_api.account_command_store import AccountCommandStore
from orbit_api.errors import OrbitError

ACCOUNT, REQUEST, COMMAND, SUBJECT, TENANT = (str(UUID(int=i)) for i in range(1, 6))


def row(**changes):
    return {
        "id": COMMAND,
        "account_id": ACCOUNT,
        "request_id": REQUEST,
        "kind": "SYNC",
        "revision": 3,
        "state": "WAITING_RETRY",
        "attempt_count": 1,
        "last_error_code": "ACCOUNT_PLATFORM_RATE_LIMITED",
        "effective_from": None,
        "next_attempt_at": datetime(2026, 11, 8, 1, 2, 3, 123000),
        "created_at": datetime(2026, 11, 8),
        "updated_at": datetime(2026, 11, 8, 1),
        "completed_at": None,
        "source_json": {"token": "不得返回"},
        **changes,
    }


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"kind": "TASK", "request_id": REQUEST},
        {"kind": "SYNC"},
        {"kind": "SYNC", "request_id": "bad"},
        {"kind": "SYNC", "request_id": REQUEST, "actor_id": "1"},
    ],
)
def test_strict_query(query):
    with pytest.raises(OrbitError):
        parse_diagnostic(ACCOUNT, query)


def test_real_command_state_and_no_secrets_or_task_mapping():
    value = diagnostic(row())
    assert len(value) == 13
    assert value["state"] == "WAITING_RETRY"
    assert value["accepted_request_id"] == REQUEST
    assert value["revision"] == 3
    assert value["last_error_code"] == "ACCOUNT_PLATFORM_RATE_LIMITED"
    assert value["next_attempt_at"] == "2026-11-08T01:02:03.123Z"
    assert "source_json" not in value and "task_id" not in value
    assert diagnostic(row(last_error_code="Token secret response"))["last_error_code"] is None


@pytest.mark.parametrize(
    "changes", [{"state": "QUEUED"}, {"attempt_count": 5}, {"revision": True}, {"created_at": None}]
)
def test_invalid_persisted_state_is_not_fabricated(changes):
    with pytest.raises(OrbitError) as error:
        diagnostic(row(**changes))
    assert error.value.status == 503


def test_utc_database_time_never_uses_machine_timezone_or_truncates():
    assert database_time(datetime(2026, 11, 8)) == "2026-11-08T00:00:00.000Z"
    assert database_time(datetime(2026, 11, 8, tzinfo=UTC)) == "2026-11-08T00:00:00.000Z"
    assert database_time(None, optional=True) is None
    with pytest.raises(OrbitError):
        database_time(datetime(2026, 11, 8, microsecond=1))


@pytest.mark.asyncio
@pytest.mark.parametrize("count,expected", [(0, 404), (1, 200), (2, 503)])
async def test_current_scope_before_exact_self_query_and_duplicate_closed(
    monkeypatch, count, expected
):
    import orbit_api.account_command_store as module

    calls = []
    current = SimpleNamespace(tenant_id=TENANT, actor_id=7, subject_id=SUBJECT)

    async def lock(self, session, actor, account, kind, *, write):
        assert actor == 7 and account == ACCOUNT and kind == "SYNC" and write is False
        calls.append("current-action-scope-dueguard")
        return current, [], {"id": ACCOUNT}

    class Result:
        def mappings(self):
            return [row()] * count

    class Session:
        def in_transaction(self):
            return True

        async def execute(self, statement, params):
            assert calls == ["current-action-scope-dueguard"]
            sql = str(statement)
            for clause in [
                "tenant_id=:tenant",
                "actor_id=:actor",
                "actor_subject_id=:subject",
                "account_id=:account",
                "kind=:kind",
                "request_id=:request",
                "LIMIT 2",
            ]:
                assert clause in sql
            assert "source_json" not in sql and "UPDATE" not in sql
            assert params == {
                "tenant": TENANT,
                "actor": 7,
                "subject": SUBJECT,
                "account": ACCOUNT,
                "kind": "SYNC",
                "request": REQUEST,
            }
            return Result()

    monkeypatch.setattr(module.AccountActionsStore, "lock_account", lock)
    if expected == 200:
        assert (
            await AccountCommandStore().get(
                Session(), 7, ACCOUNT, {"kind": "SYNC", "request_id": REQUEST}
            )
        )["command_id"] == COMMAND
    else:
        with pytest.raises(OrbitError) as error:
            await AccountCommandStore().get(
                Session(), 7, ACCOUNT, {"kind": "SYNC", "request_id": REQUEST}
            )
        assert error.value.status == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 503])
async def test_revoked_transferred_and_dueguard_never_read_command(monkeypatch, status):
    import orbit_api.account_command_store as module

    async def denied(*args, **kwargs):
        raise OrbitError(status, "DENIED", "受控拒绝")

    class Session:
        def in_transaction(self):
            return True

        async def execute(self, *args):
            pytest.fail("动作/当前账户范围拒绝后不得查询历史命令")

    monkeypatch.setattr(module.AccountActionsStore, "lock_account", denied)
    with pytest.raises(OrbitError) as error:
        await AccountCommandStore().get(
            Session(), 7, ACCOUNT, {"kind": "SYNC", "request_id": REQUEST}
        )
    assert error.value.status == status
