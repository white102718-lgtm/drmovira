"""追加工具会话时钟归属纯测；不证明驱动或MySQL真实时钟支持。"""

from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import tools.launch_execution_lease_store_checks as module
from test_launch_execution_lease_contract import NOW


class Connection:
    def __init__(self):
        self.timestamp = Decimal(0)
        self.current = NOW + timedelta(seconds=2)
        self.active = False
        self.invalidated = False
        self.returned_to_pool = False
        self.reject_reset = False
        self.drift = False
        self.ids_read = 0
        self.trace = []

    async def __aenter__(self):
        self.trace.append("owned_connection")
        return self

    async def __aexit__(self, *_args):
        self.returned_to_pool = not self.invalidated
        self.trace.append("close")

    def in_transaction(self):
        return self.active

    async def execute(self, statement, values=None):
        self.active = True
        sql = str(statement)
        self.trace.append(sql)
        if sql == "SELECT CONNECTION_ID()":
            self.ids_read += 1
            result = 8 if self.drift and self.ids_read > 1 else 7
        elif sql == "SET SESSION timestamp=:value":
            self.timestamp = values["value"]
            result = None
        elif sql == "SELECT UTC_TIMESTAMP(6)":
            assert self.timestamp != 0
            result = self.current.replace(tzinfo=None)
        elif sql == "SET SESSION timestamp=0":
            if self.reject_reset:
                raise RuntimeError("reset rejected")
            self.timestamp = Decimal(0)
            result = None
        else:
            raise AssertionError("未知SQL")
        return SimpleNamespace(scalar_one=lambda: result)

    async def commit(self):
        self.active = False
        self.trace.append("commit")

    async def rollback(self):
        self.active = False
        self.trace.append("rollback")

    async def invalidate(self):
        self.invalidated = True
        self.active = False
        self.trace.append("invalidate")


class Session:
    def __init__(self, bind, **_kwargs):
        self.bind = bind

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    @asynccontextmanager
    async def begin(self):
        self.bind.trace.append("session_begin")
        try:
            yield
        except BaseException:
            await self.bind.rollback()
            raise
        else:
            await self.bind.commit()

    async def execute(self, *args, **kwargs):
        return await self.bind.execute(*args, **kwargs)


@pytest.mark.asyncio
async def test_set_commit_business_and_reset_keep_exact_owned_connection(monkeypatch):
    connection = Connection()
    receipt = object()

    async def appended(session, *_args):
        assert session.bind is connection
        assert connection.timestamp != 0
        connection.trace.append("append")
        return receipt

    monkeypatch.setattr(module, "AsyncSession", Session)
    result = await module.append_with_owned_connection(
        SimpleNamespace(connect=lambda: connection),
        SimpleNamespace(append_verified_fact=appended),
        object(),
        replay_clock=connection.current,
    )
    assert result is receipt
    assert connection.ids_read == 3  # SET前、业务事务内、finally原连接归零前。
    assert connection.timestamp == 0 and connection.returned_to_pool
    assert not connection.invalidated
    assert connection.trace.index("SET SESSION timestamp=0") > connection.trace.index("append")


@pytest.mark.asyncio
async def test_business_error_still_resets_exact_owned_connection(monkeypatch):
    connection = Connection()

    async def appended(*_args):
        raise RuntimeError("business rejected")

    monkeypatch.setattr(module, "AsyncSession", Session)
    with pytest.raises(RuntimeError, match="business rejected"):
        await module.append_with_owned_connection(
            SimpleNamespace(connect=lambda: connection),
            SimpleNamespace(append_verified_fact=appended),
            object(),
            replay_clock=connection.current,
        )
    assert connection.timestamp == 0 and connection.returned_to_pool


@pytest.mark.asyncio
async def test_reset_uncertainty_discards_owned_connection_instead_of_returning_to_pool(
    monkeypatch,
):
    connection = Connection()
    connection.reject_reset = True

    async def appended(*_args):
        return object()

    monkeypatch.setattr(module, "AsyncSession", Session)
    with pytest.raises(RuntimeError, match="reset rejected"):
        await module.append_with_owned_connection(
            SimpleNamespace(connect=lambda: connection),
            SimpleNamespace(append_verified_fact=appended),
            object(),
            replay_clock=connection.current,
        )
    assert connection.invalidated and not connection.returned_to_pool


@pytest.mark.asyncio
async def test_connection_identity_drift_rejects_before_append_and_invalidates(monkeypatch, capsys):
    connection = Connection()
    connection.drift = True
    called = []

    async def appended(*_args):
        called.append(True)

    monkeypatch.setattr(module, "AsyncSession", Session)
    with pytest.raises(AssertionError):
        await module.append_with_owned_connection(
            SimpleNamespace(connect=lambda: connection),
            SimpleNamespace(append_verified_fact=appended),
            object(),
            replay_clock=connection.current,
        )
    assert not called and connection.invalidated and not connection.returned_to_pool
    diagnostic = capsys.readouterr().out
    assert '"connection_before": 7' in diagnostic and '"connection_after": 8' in diagnostic
