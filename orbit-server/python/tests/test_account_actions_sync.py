"""同步执行器控制协议；会话/平台替身不等于真实MySQL事务或Meta授权验收。"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_actions_sync import AccountSyncWorker, SyncClaim, claim_matches, retry_at
from orbit_api.account_platform import AccountReadFailure, MetaReadConfiguration
from orbit_api.errors import OrbitError

TENANT, ACCOUNT, COMMAND, CLAIM_ID, OWNER, TEAM, REQUEST, SOURCE = (
    str(UUID(int=index)) for index in range(1, 9)
)
NOW = datetime(2026, 11, 9, 8, 0, 0, 123456, tzinfo=UTC)
CONFIG = MetaReadConfiguration("42", "v25.0", "CONTROLLED_TEST_TOKEN")
CLAIM = SyncClaim(TENANT, COMMAND, ACCOUNT, CLAIM_ID, 4, "00123", CONFIG)


@pytest.mark.parametrize("attempt,seconds", [(1, 30), (2, 60), (3, 120), (4, None)])
def test_retry_budget(attempt, seconds):
    due = retry_at(attempt, NOW)
    assert due == (NOW + timedelta(seconds=seconds) if seconds else None)


@pytest.mark.parametrize("attempt", [True, 0, 5, -1, "1"])
def test_invalid_attempt(attempt):
    with pytest.raises(ValueError):
        retry_at(attempt, NOW)


def test_naive_and_offset_time():
    with pytest.raises(ValueError):
        retry_at(1, NOW.replace(tzinfo=None))
    from datetime import timezone

    assert retry_at(1, NOW.astimezone(timezone(timedelta(hours=8)))) == NOW + timedelta(seconds=30)


def test_claim_fence_terminal_and_stale():
    command = {
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "state": "RUNNING",
        "active_kind": "SYNC",
        "claim_id": CLAIM_ID,
        "revision": 4,
    }
    assert claim_matches(command, CLAIM)
    for mutation in (
        {"state": "SUCCEEDED"},
        {"active_kind": None},
        {"claim_id": SOURCE},
        {"revision": 5},
        {"tenant_id": SOURCE},
        {"account_id": SOURCE},
    ):
        assert not claim_matches(command | mutation, CLAIM)
    assert not claim_matches(None, CLAIM)
    assert "CONTROLLED_TEST_TOKEN" not in repr(CLAIM)


class Result:
    def scalar_one(self):
        return NOW.replace(tzinfo=None)


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

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return Result()


@pytest.fixture
def harness(monkeypatch):
    import orbit_api.account_actions_sync as module

    session = Session()
    worker = AccountSyncWorker(lambda: session, object(), {"USD"}, TENANT)
    account = {
        "id": ACCOUNT,
        "revision": 10,
        "currency": "USD",
        "timezone_id": "Asia/Shanghai",
        "synced_at": (NOW - timedelta(days=1)).replace(tzinfo=None),
        "details_json": {"kept": True},
    }
    command = {
        "id": COMMAND,
        "state": "RUNNING",
        "active_kind": "SYNC",
        "claim_id": CLAIM_ID,
        "revision": 4,
        "claimed_at": (NOW - timedelta(seconds=1)).replace(tzinfo=None),
        "attempt_count": 1,
        "request_id": REQUEST,
        "actor_id": 1,
        "actor_subject_id": OWNER,
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "source_config_id": SOURCE,
        "source_config_revision": 7,
    }
    transitions, events = [], []

    async def lock(*args, **kwargs):
        return account, command

    async def verify(*args, **kwargs):
        return SimpleNamespace(actor_id=1, tenant_id=TENANT, subject_id=OWNER), 9, CONFIG

    async def transition(_session, _command, state, **kwargs):
        transitions.append((state, kwargs))

    async def event(*args):
        events.append(args)

    monkeypatch.setattr(worker, "lock", lock)
    monkeypatch.setattr(worker, "verify", verify)
    monkeypatch.setattr(worker, "transition", transition)
    monkeypatch.setattr(module, "event", event)
    value = {
        "external_id": "00123",
        "name": "真实读取名",
        "currency": "USD",
        "timezone_id": "Asia/Shanghai",
        "account_status": "ACTIVE",
        "auth_status": "AUTHORIZED",
        "observed_at": NOW - timedelta(microseconds=1),
    }
    return worker, session, account, command, value, transitions, events


@pytest.mark.asyncio
async def test_complete_preserves_money_and_history(harness):
    worker, session, account, command, value, transitions, events = harness
    assert await worker.complete(CLAIM, result=value)
    updates = [(sql, params) for sql, params in session.calls if sql.startswith("UPDATE")]
    assert len(updates) == 1
    sql, params = updates[0]
    assert params["expected"] == account["revision"]
    assert params["observed"] == value["observed_at"].replace(tzinfo=None)
    assert params["name"] == "真实读取名"
    assert all(field not in sql for field in ("value_json", "owner_user_id", "balance", "spend"))
    assert transitions == [("SUCCEEDED", {})]
    assert events[0][5] == "ACCOUNT_METADATA_SYNCHRONIZED"
    assert all("assignment" not in sql.lower() for sql, _ in session.calls)


@pytest.mark.parametrize("change", [{"currency": "EUR"}, {"timezone_id": "UTC"}])
@pytest.mark.asyncio
async def test_metadata_reconciliation_not_silent(harness, change):
    worker, session, _account, _command, value, transitions, events = harness
    worker.currencies = frozenset({"USD", "EUR"})
    assert await worker.complete(CLAIM, result=value | change)
    assert transitions == [("FAILED", {"code": "ACCOUNT_METADATA_RECONCILIATION_REQUIRED"})]
    assert not events
    assert not any(sql.startswith("UPDATE") for sql, _ in session.calls)


@pytest.mark.parametrize("change", ["claim", "terminal", "expired"])
@pytest.mark.asyncio
async def test_late_result_cannot_revive(harness, change):
    worker, session, _account, command, value, transitions, events = harness
    if change == "claim":
        command["claim_id"] = SOURCE
    elif change == "terminal":
        command.update(state="FAILED", active_kind=None)
    else:
        command["claimed_at"] = (NOW - timedelta(seconds=120)).replace(tzinfo=None)
    assert not await worker.complete(CLAIM, result=value)
    assert not transitions and not events
    assert not any(sql.startswith("UPDATE") for sql, _ in session.calls)


@pytest.mark.parametrize(
    "attempt,expected", [(1, "WAITING_RETRY"), (3, "WAITING_RETRY"), (4, "FAILED")]
)
@pytest.mark.asyncio
async def test_transient_failure_only_bounded_read(harness, attempt, expected):
    worker, _session, _account, command, _value, transitions, events = harness
    command["attempt_count"] = attempt
    assert await worker.complete(
        CLAIM, failure=AccountReadFailure("ACCOUNT_PLATFORM_READ_UNCERTAIN", retryable=True)
    )
    assert transitions[0][0] == expected
    assert transitions[0][1]["next_at"] == retry_at(attempt, NOW)
    assert not events


@pytest.mark.asyncio
async def test_permission_loss_overrides_retryable_platform_failure(harness, monkeypatch):
    worker, _session, _account, _command, _value, transitions, _events = harness

    async def revoked(*args, **kwargs):
        raise AccountReadFailure("ACCOUNT_SYNC_AUTHORIZATION_CHANGED")

    monkeypatch.setattr(worker, "verify", revoked)
    assert await worker.complete(CLAIM, failure=AccountReadFailure("NETWORK", retryable=True))
    assert transitions == [
        ("FAILED", {"code": "ACCOUNT_SYNC_AUTHORIZATION_CHANGED", "next_at": None})
    ]


@pytest.mark.parametrize("observed", [NOW + timedelta(microseconds=1), NOW - timedelta(days=1)])
@pytest.mark.asyncio
async def test_future_or_stale_observation_rejected(harness, observed):
    worker, session, _account, _command, value, transitions, _events = harness
    await worker.complete(CLAIM, result=value | {"observed_at": observed})
    assert transitions == [("FAILED", {"code": "ACCOUNT_SYNC_OBSERVATION_STALE"})]
    assert not any(sql.startswith("UPDATE") for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_cancelled_network_does_not_complete_or_resend(harness, monkeypatch):
    import asyncio

    worker, _session, _account, _command, _value, transitions, _events = harness
    claims, reads = [], []

    async def claim():
        claims.append(True)
        return CLAIM, True

    class Reader:
        def __init__(self, configuration):
            assert configuration is CONFIG

        async def prepare(self, ids):
            reads.append(ids)
            raise asyncio.CancelledError

    monkeypatch.setattr(worker, "claim", claim)
    worker.platform_factory = Reader
    with pytest.raises(asyncio.CancelledError):
        await worker.run_once(limit=3)
    assert claims == [True] and reads == [("00123",)] and not transitions


@pytest.mark.asyncio
async def test_batch_invalid_without_claim(harness, monkeypatch):
    worker, *_ = harness

    async def forbidden():
        raise AssertionError("非法批量不能认领")

    monkeypatch.setattr(worker, "claim", forbidden)
    for limit in (0, 101, True, "10"):
        with pytest.raises(OrbitError) as error:
            await worker.run_once(limit=limit)
        assert error.value.status == 422


@pytest.mark.parametrize(
    "change,code",
    [
        ("none", None),
        ("auth", "ACCOUNT_SYNC_AUTHORIZATION_CHANGED"),
        ("subject", "ACCOUNT_SYNC_AUTHORIZATION_CHANGED"),
        ("scope", "ACCOUNT_SYNC_SCOPE_CHANGED"),
        ("unbound", "ACCOUNT_LOCALLY_UNBOUND"),
        ("owner", "ACCOUNT_SYNC_OWNERSHIP_CHANGED"),
        ("revision", "ACCOUNT_SYNC_ACCOUNT_CHANGED"),
        ("source", "ACCOUNT_SYNC_SOURCE_CHANGED"),
        ("token", "ACCOUNT_SYNC_SOURCE_UNAVAILABLE"),
        ("settings", "ACCOUNT_SYNC_SOURCE_UNAVAILABLE"),
        ("decrypt", "ACCOUNT_SYNC_SOURCE_UNAVAILABLE"),
        ("due", "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"),
    ],
)
@pytest.mark.asyncio
async def test_live_verify_current_scope_source_and_versions(monkeypatch, change, code):
    import orbit_api.account_actions_sync as module

    class LiveResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalar_one(self):
            return self.value

        def mappings(self):
            return self

        def first(self):
            return self.value

    source = {
        "id": SOURCE,
        "revision": 7,
        "settings_json": {"businessId": "42", "graphVersion": "v25.0"},
        "secrets_json": {"accessToken": "CONTROLLED_CIPHERTEXT"},
    }
    if change == "token":
        source["secrets_json"] = {}
    if change == "settings":
        source["settings_json"] = None

    class LiveSession:
        async def execute(self, statement, params=None):
            sql = str(statement)
            if "information_schema.TABLES" in sql:
                assert params == {"table": "orbit_meta_account_source"}
                return LiveResult(0)  # 此旧来源场景明确未安装Meta来源扩展。
            if "sys_identity_subject" in sql:
                return LiveResult(10 if change == "auth" else 9)
            if "SELECT 1 FROM orbit_ad_account" in sql:
                return LiveResult(None if change == "scope" else 1)
            if "orbit_system_configuration" in sql:
                assert params["id"] == SOURCE and params["revision"] == 7
                return LiveResult(None if change == "source" else source)
            raise AssertionError(sql)

    class Cipher:
        ready = True

        def decrypt_internal(self, encrypted, tenant, identifier, field):
            assert (encrypted, tenant, identifier, field) == (
                "CONTROLLED_CIPHERTEXT",
                TENANT,
                SOURCE,
                "accessToken",
            )
            if change == "decrypt":
                raise OrbitError(503, "CREDENTIAL_KEY_UNAVAILABLE", "受控解密密钥不可用")
            return "CONTROLLED_TEST_TOKEN"

    current = SimpleNamespace(
        tenant_id=TENANT,
        actor_id=1,
        subject_id=SOURCE if change == "subject" else OWNER,
        data_role="SUPER_ADMIN",
    )

    async def access(_session, actor, menu, permission, *, acting_subject):
        assert (actor, menu, permission, acting_subject) == (1, "accounts", "accounts.sync", False)
        return current

    async def projection(*args):
        if change == "due":
            raise OrbitError(503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "测试明确到期阻断")

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "require_projection_current", projection)
    account = {
        "id": ACCOUNT,
        "revision": 10,
        "unbound_at": NOW if change == "unbound" else None,
        "owner_user_id": SOURCE if change == "owner" else OWNER,
        "owner_team_id": TEAM,
        "vendor_id": None,
    }
    command = {
        "actor_id": 1,
        "actor_subject_id": OWNER,
        "claimed_auth_version": 9,
        "claimed_account_revision": 11 if change == "revision" else 10,
        "source_config_id": SOURCE,
        "source_config_revision": 7,
        "source_json": {"owner_user_id": OWNER, "owner_team_id": TEAM, "vendor_id": None},
    }
    worker = AccountSyncWorker(None, Cipher(), {"USD"}, TENANT)
    if code:
        with pytest.raises(AccountReadFailure) as error:
            await worker.verify(LiveSession(), account, command)
        assert error.value.code == code and not error.value.retryable
    else:
        result, version, configuration = await worker.verify(LiveSession(), account, command)
        assert result is current and version == 9 and configuration.business_id == "42"
