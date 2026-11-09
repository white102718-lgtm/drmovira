"""监测范围消费的有限授权纯测；真实范围容量及当前SQL另行验证。"""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

import orbit_api.metrics_scope_access as module
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError


class Session:
    def __init__(self, version=7, transaction=True):
        self.version, self.transaction, self.statements = version, transaction, []

    def in_transaction(self):
        return self.transaction

    async def execute(self, statement, params):
        self.statements.append((str(statement), params))
        return SimpleNamespace(scalar_one_or_none=lambda: self.version)


@pytest.fixture
def environment(monkeypatch):
    current = BusinessContext(23, str(uuid4()), "TEAM_ADMIN", str(uuid4()), str(uuid4()))
    teams = [str(uuid4()), str(uuid4())]
    grants, checked = [], []

    async def authorize(session, actor, menu, action):
        grants.append((actor, menu, action))
        return current

    async def managed(session, context):
        assert context is current
        return teams

    async def snapshot(session, context, version, fingerprint, identifier):
        checked.append((context, version, fingerprint, identifier))
        return {"id": identifier, "members_hash": "a" * 64, "member_count": 50000}

    monkeypatch.setattr(module, "require_business_access", authorize)
    monkeypatch.setattr(module, "managed_teams", managed)
    monkeypatch.setattr(module, "verified_snapshot", snapshot)
    return current, teams, grants, checked


@pytest.mark.asyncio
async def test_nonempty_scope_uses_only_monitor_and_preserves_all_fifty_thousand(environment):
    current, teams, grants, checked = environment
    identifier, session = str(uuid4()), Session()
    result = await module.authorize_metric_scope(session, 23, identifier)
    expected = hashlib.sha256(
        canonical(
            [
                23,
                current.tenant_id,
                current.subject_id,
                current.data_role,
                current.team_id,
                sorted(teams),
                7,
            ]
        ).encode()
    ).hexdigest()
    assert grants == [(23, "monitor", "monitor.read")]
    assert checked == [(current, 7, expected, identifier)]
    assert result.member_count == 50000 and result.snapshot_id == identifier
    assert result.snapshot_hash == "a" * 64 and result.auth_fingerprint == expected
    assert "FOR SHARE" in session.statements[0][0]


@pytest.mark.asyncio
async def test_null_scope_does_not_require_an_account_snapshot(environment):
    _, _, grants, checked = environment
    result = await module.authorize_metric_scope(Session(), 23, None)
    assert grants == [(23, "monitor", "monitor.read")] and checked == []
    assert (result.snapshot_id, result.snapshot_hash, result.member_count) == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code", [(403, "PERMISSION_DENIED"), (404, "NOT_FOUND"), (409, "SCOPE_CHANGED")]
)
async def test_current_scope_failure_cannot_become_empty_or_partial(
    environment, monkeypatch, status, code
):
    async def denied(*args):
        raise OrbitError(status, code, "当前范围已失效")

    monkeypatch.setattr(module, "verified_snapshot", denied)
    with pytest.raises(OrbitError) as caught:
        await module.authorize_metric_scope(Session(), 23, str(uuid4()))
    assert (caught.value.status, caught.value.code) == (status, code)


@pytest.mark.asyncio
async def test_action_revocation_stops_before_scope_or_version_read(environment, monkeypatch):
    async def denied(*args):
        raise OrbitError(403, "PERMISSION_DENIED", "当前监测权限已撤销")

    monkeypatch.setattr(module, "require_business_access", denied)
    session = Session()
    with pytest.raises(OrbitError):
        await module.authorize_metric_scope(session, 23, str(uuid4()))
    assert session.statements == [] and environment[3] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, True, 0, -1, 9007199254740992])
async def test_invalid_authorization_version_never_consumes_scope(environment, version):
    with pytest.raises(OrbitError) as caught:
        await module.authorize_metric_scope(Session(version), 23, str(uuid4()))
    assert (caught.value.status, caught.value.code) == (409, "SCOPE_VERSION_INVALID")
    assert environment[3] == []


@pytest.mark.asyncio
async def test_empty_frozen_selection_remains_distinct_from_no_scope(environment, monkeypatch):
    identifier = str(uuid4())

    async def empty(*args):
        return {"id": identifier, "members_hash": "b" * 64, "member_count": 0}

    monkeypatch.setattr(module, "verified_snapshot", empty)
    result = await module.authorize_metric_scope(Session(), 23, identifier)
    assert result.member_count == 0 and result.snapshot_id == identifier


@pytest.mark.asyncio
async def test_without_outer_transaction_fails_before_authorization(environment):
    session = Session(transaction=False)
    with pytest.raises(ValueError):
        await module.authorize_metric_scope(session, 23, None)
    assert session.statements == [] and environment[2:] == ([], [])
