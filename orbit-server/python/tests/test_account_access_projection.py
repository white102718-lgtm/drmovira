"""共享时钟必须先锁再核到期投影；替身控制分支，不冒充实际SQL并发。"""

from types import SimpleNamespace

import pytest

from orbit_api.account_access import clock
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.errors import OrbitError


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, values):
        self.values, self.calls = iter(values), []

    async def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return Result(next(self.values))


CURRENT = SimpleNamespace(tenant_id="tenant", actor_id=1, subject_id="subject")


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
async def test_current_projection_preserves_read_concurrency_and_write_lock_order(write):
    session = Session([17, None])
    assert await clock(session, CURRENT, write=write) == 17
    assert len(session.calls) == 2
    assert "orbit_account_clock" in session.calls[0][0]
    assert ("FOR UPDATE" if write else "FOR SHARE") in session.calls[0][0]
    assert "orbit_account_command" in session.calls[1][0]
    assert "active_kind='ASSIGNMENT'" in session.calls[1][0]
    assert session.calls[1][1]["tenant"] == CURRENT.tenant_id
    assert session.calls[1][1]["now"].tzinfo is None  # SQL按明确UTC无时区存储。


@pytest.mark.asyncio
async def test_due_projection_never_returns_old_read_watermark():
    session = Session([17, 1])
    with pytest.raises(OrbitError) as failure:
        await clock(session, CURRENT)
    assert failure.value.status == 503
    assert failure.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revision,code",
    [(None, "ACCOUNT_INITIALIZATION_REQUIRED"), (MAX_REVISION, "REVISION_EXHAUSTED")],
)
async def test_invalid_clock_cannot_be_used_to_bypass_projection_guard(revision, code):
    session = Session([revision])
    with pytest.raises(OrbitError) as failure:
        await clock(session, CURRENT)
    assert failure.value.code == code
    assert len(session.calls) == 1
