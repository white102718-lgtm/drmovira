"""只读Worker控制逻辑单测，不把会话替身当作真实数据库或平台绑定证明。"""

from types import SimpleNamespace

import pytest

from orbit_api.account_platform import AccountReadFailure
from orbit_api.account_worker import AccountImportWorker, retry_delay
from orbit_api.errors import OrbitError


@pytest.mark.parametrize("jitter", [0, 10])
def test_three_retry_backoffs_are_after_initial_read_and_bounded(monkeypatch, jitter):
    monkeypatch.setattr("orbit_api.account_worker.secrets.randbelow", lambda maximum: jitter)
    assert [retry_delay(attempt) for attempt in (1, 2, 3)] == [
        30 + jitter,
        60 + jitter,
        120 + jitter,
    ]
    with pytest.raises(ValueError):
        retry_delay(4)


async def test_invalid_batch_limit_fails_before_any_database_access():
    def sessions():
        raise AssertionError("无效批次不能连接数据库")

    worker = AccountImportWorker(sessions, None, {"USD"})
    with pytest.raises(ValueError):
        await worker.run_once(0)
    with pytest.raises(ValueError):
        await worker.recover_interrupted(101)


def test_valid_internal_target_uses_explicit_uuid_field_pointers():
    identifier = "10000000-0000-4000-8000-000000000001"
    worker = AccountImportWorker(None, None, {"USD"}, target=(identifier, identifier))
    assert worker.target == (identifier, identifier)
    with pytest.raises(OrbitError) as error:
        AccountImportWorker(None, None, {"USD"}, target=(identifier, "bad"))
    assert error.value.status == 422 and error.value.pointer == "/batch_id"


async def test_one_source_rate_failure_is_not_retried_inline_for_other_claims():
    prepared, completed = [], []

    class Platform:
        def __init__(self, configuration):
            self.configuration = configuration

        async def prepare(self, identifiers):
            prepared.append(identifiers)
            raise AccountReadFailure("ACCOUNT_PLATFORM_RATE_LIMITED", retryable=True)

        async def fetch_metadata(self, external_id):
            raise AssertionError("范围读取失败不能继续读取账户")

    worker = AccountImportWorker(None, None, {"USD"}, platform_factory=Platform)
    claims = [
        SimpleNamespace(
            batch_id=f"batch-{index}",
            source_id="source",
            source_revision=1,
            configuration=None,
            identifiers=("001",),
            external_id="001",
        )
        for index in range(2)
    ]

    async def claim_one():
        return (claims.pop(0), True) if claims else (None, False)

    async def recover(limit):
        return 0

    async def complete(claim, result=None, failure=None):
        completed.append((result, failure.code, failure.retryable))

    worker.claim_one, worker.recover_interrupted, worker.complete = claim_one, recover, complete
    result = await worker.run_once(3)
    assert result == {"processed": 2, "recovered": 0}
    assert prepared == [("001",)]
    assert completed == [(None, "ACCOUNT_PLATFORM_RATE_LIMITED", True)] * 2


@pytest.mark.parametrize("changed", ["availability", "revision", "owner"])
async def test_existing_binding_still_rechecks_live_vendor_before_skipping_source(
    monkeypatch, changed
):
    """会话替身仅证明本地守卫顺序；实际权限/锁与并发需MySQL联合验收。"""
    import orbit_api.account_worker as module

    current = SimpleNamespace(tenant_id="tenant", subject_id="subject")

    async def access(*args, **kwargs):
        return current

    async def ownership(*args, **kwargs):
        return None

    value = {"availability": "AVAILABLE", "owner_team_id": "team", "data_owner_user_ids": ["owner"]}
    vendor = {"kind": "VENDOR", "revision": 1, "value_json": value}
    if changed == "availability":
        value["availability"] = "DISABLED"
    elif changed == "revision":
        vendor["revision"] = 2
    else:
        value["data_owner_user_ids"] = []

    async def vendors(*args):
        return {"vendor": vendor}

    class Session:
        async def execute(self, *args):
            return SimpleNamespace(scalar_one=lambda: 1)

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "validate_ownership", ownership)
    monkeypatch.setattr(module, "records", vendors)
    batch = {
        "actor_id": "actor",
        "tenant_id": "tenant",
        "actor_subject_id": "subject",
        "scope_version": 1,
        "actor_auth_version": 1,
        "owner_user_id": "owner",
        "owner_team_id": "team",
        "vendor_id": "vendor",
        "vendor_revision": 1,
    }
    with pytest.raises(AccountReadFailure) as error:
        await AccountImportWorker(None, None, {"USD"}).verify(
            Session(), batch, require_source=False
        )
    assert error.value.code == (
        "VENDOR_DISABLED" if changed == "availability" else "ACCOUNT_IMPORT_REFERENCE_CHANGED"
    )
