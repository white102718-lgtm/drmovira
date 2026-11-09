"""旧导入Worker补保护的锁序控制；真实锁/HTTP验收由主线隔离专项执行。"""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from orbit_api.account_worker import AccountImportWorker
from orbit_api.errors import OrbitError


class Session:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    @asynccontextmanager
    async def begin(self):
        yield self

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        assert "orbit_account_clock" in str(statement), "到期保护前不能先取batch/row锁"
        return SimpleNamespace(scalar_one_or_none=lambda: 1)


@pytest.mark.parametrize("phase", ["claim_or_write", "before_http"])
@pytest.mark.asyncio
async def test_due_guard_precedes_batch_and_row_locks(monkeypatch, phase):
    import orbit_api.account_actions_store as module

    session, guards = Session(), []

    async def blocked(_session, tenant, now):
        guards.append((tenant, now))
        assert isinstance(now, datetime) and now.tzinfo is not None
        assert len(session.calls) == 1
        raise OrbitError(503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "到期归属等待追平")

    monkeypatch.setattr(module, "require_tenant_projections_current", blocked)
    worker = AccountImportWorker(lambda: session, None, {"USD"})
    with pytest.raises(OrbitError) as error:
        if phase == "claim_or_write":
            await worker.lock_batch(session, "tenant", "batch")
        else:
            await worker.preflight(SimpleNamespace(tenant="tenant", batch_id="batch", row_id="row"))
    assert error.value.status == 503 and error.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
    assert len(guards) == 1 and guards[0][0] == "tenant"
    assert len(session.calls) == 1
    expected = "FOR UPDATE SKIP LOCKED" if phase == "claim_or_write" else "FOR SHARE"
    assert expected in session.calls[0][0]
