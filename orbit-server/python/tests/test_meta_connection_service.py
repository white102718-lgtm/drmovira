"""一次性授权状态及连接版本拒绝路径的行为回归。"""

from datetime import datetime, timedelta

import pytest


def test_state_binding_expires_and_cannot_be_reused():
    from orbit_api.meta_connection_service import validate_state_row

    now = datetime(2026, 11, 10)
    row = dict(
        status="PENDING",
        expires_at=now + timedelta(minutes=10),
        tenant_id="tenant",
        actor_id=7,
        browser_session_id="session",
        app_id="123",
    )
    validate_state_row(row, tenant="tenant", actor=7, browser="session", app_id="123", now=now)
    for change in (
        {"status": "EXCHANGING"},
        {"expires_at": now},
        {"tenant_id": "other"},
        {"actor_id": 8},
        {"browser_session_id": "other"},
        {"app_id": "9"},
    ):
        with pytest.raises(Exception) as exc:
            validate_state_row(
                row | change, tenant="tenant", actor=7, browser="session", app_id="123", now=now
            )
        assert getattr(exc.value, "code", None) == "META_STATE_INVALID"


def test_revocation_during_validation_cannot_publish_connection():
    import orbit_api.meta_connection_service as service

    assert hasattr(service, "require_publication_epoch"), "缺少撤销后迟到发布保护"
    started = datetime(2026, 11, 10, 1)
    service.require_publication_epoch(None, started)
    service.require_publication_epoch(started - timedelta(seconds=1), started)
    with pytest.raises(Exception) as error:
        service.require_publication_epoch(started, started)
    assert error.value.code == "META_AUTHORIZATION_REVOKED"


def test_exchange_result_requires_still_consumed_original_state():
    import orbit_api.meta_connection_service as service

    assert hasattr(service, "validate_exchange_row"), "交换完成前未重读一次性状态"
    now = datetime(2026, 11, 10)
    row = dict(
        status="EXCHANGING",
        expires_at=now + timedelta(minutes=10),
        tenant_id="tenant",
        actor_id=7,
        browser_session_id="session",
        app_id="123",
    )
    service.validate_exchange_row(
        row, tenant="tenant", actor=7, browser="session", app_id="123", now=now
    )
    from orbit_api.errors import OrbitError

    for status in ("COMPLETED", "FAILED", "CANCELLED", "PENDING"):
        with pytest.raises(OrbitError):
            service.validate_exchange_row(
                row | {"status": status},
                tenant="tenant",
                actor=7,
                browser="session",
                app_id="123",
                now=now,
            )


@pytest.mark.asyncio
async def test_start_serializes_on_account_clock_without_browser_lock_upgrade(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    import orbit_api.meta_connection_service as m
    from orbit_api.meta_connection_contract import MetaApplication

    calls = []

    class Result:
        def __init__(self, value=None):
            self.value = value

        def scalar_one(self):
            return self.value

        def scalar_one_or_none(self):
            return self.value

        def mappings(self):
            return self

        def first(self):
            return self.value

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def begin(self):
            yield self

        async def execute(self, sql, params=None):
            sql = str(sql)
            calls.append(sql)
            assert not ("orbit_browser_session" in sql and "FOR UPDATE" in sql)
            if "FROM orbit_account_clock" in sql:
                return Result(1)
            if "UTC_TIMESTAMP" in sql and sql.startswith("SELECT"):
                return Result(datetime(2026, 11, 10))
            if "orbit_meta_authorization_session" in sql:
                assert any("FROM orbit_account_clock" in prior for prior in calls[:-1])
            return Result()

    current = SimpleNamespace(
        tenant_id=str(uuid4()),
        actor_id=7,
        subject_id=str(uuid4()),
        team_id=str(uuid4()),
        data_role="SUPER_ADMIN",
    )

    async def access(*args):
        return current

    async def event(*args):
        calls.append("AUDIT")

    monkeypatch.setattr(m, "access", access)
    monkeypatch.setattr(m, "authorizing_owner", access)
    monkeypatch.setattr(m, "event", event)
    monkeypatch.setattr(
        m, "browser_identity", lambda actor: SimpleNamespace(session_id=str(uuid4()))
    )
    cipher = SimpleNamespace(encrypt=lambda *args: "encrypted")
    result = await m.MetaConnectionService(
        Session, cipher, MetaApplication("123", "secret", "v24.0", "456"), None
    ).start(7, "/orbit/accounts", "key", str(uuid4()))
    assert "authorize_url" in result and calls[-1] == "AUDIT"


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_exchange_failure_persists_failed_state_with_sanitized_audit(monkeypatch, duplicate):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    import orbit_api.meta_connection_service as m
    from orbit_api.errors import OrbitError
    from orbit_api.meta_connection_contract import MetaApplication

    now = datetime(2026, 11, 10)
    tenant, browser, identifier = str(uuid4()), str(uuid4()), str(uuid4())
    row = dict(
        id=identifier,
        tenant_id=tenant,
        actor_id=7,
        browser_session_id=browser,
        status="PENDING",
        app_id="123",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
        return_to="/orbit/accounts",
        connection_id=None,
    )
    calls, audits = [], []

    class Result:
        rowcount = 1

        def __init__(self, value=None):
            self.value = value

        def scalar_one(self):
            return self.value

        def scalar_one_or_none(self):
            return self.value

        def mappings(self):
            return self

        def first(self):
            return self.value

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def begin(self):
            yield self

        async def execute(self, sql, params=None):
            sql = str(sql)
            calls.append(sql)
            if "FROM orbit_account_clock" in sql:
                return Result(1)
            if sql.startswith("SELECT UTC_TIMESTAMP"):
                return Result(now)
            if sql.startswith("SELECT * FROM orbit_meta_authorization_session"):
                return Result(row)
            return Result()

    current = SimpleNamespace(
        tenant_id=tenant, actor_id=7, subject_id=str(uuid4()), data_role="SUPER_ADMIN"
    )

    async def access(*args):
        return current

    async def event(*args):
        audits.append(args[5])

    async def exchange(code):
        if duplicate:
            raise OrbitError(409, "META_ALREADY_CONNECTED", "private-token-do-not-echo")
        raise ValueError("private-token-do-not-echo")

    monkeypatch.setattr(m, "access", access)
    monkeypatch.setattr(m, "event", event)
    monkeypatch.setattr(m, "browser_identity", lambda actor: SimpleNamespace(session_id=browser))
    service = m.MetaConnectionService(
        Session,
        None,
        MetaApplication("123", "secret", "v24.0", "456"),
        SimpleNamespace(exchange=exchange),
    )
    with pytest.raises(OrbitError) as error:
        await service.callback(7, "s" * 32, "code", str(uuid4()))
    assert error.value.code == (
        "META_ALREADY_CONNECTED" if duplicate else "META_AUTHORIZATION_FAILED"
    )
    assert "private-token" not in str(error.value)
    assert audits == ["META_AUTHORIZATION_CONSUMED", "META_AUTHORIZATION_FAILED"]
    assert any("status='FAILED',state_envelope=''" in sql for sql in calls)
