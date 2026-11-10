"""授权自动发现的冻结归属、持久页和真实批次汇总回归。"""

import importlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest


def test_import_vendor_is_optional_but_invalid_reference_is_rejected():
    from orbit_api.account_contract import parse_import
    from orbit_api.errors import OrbitError

    value = dict(account_ids_text="123", owner_user_id=str(uuid4()), owner_team_id=str(uuid4()))
    assert parse_import(json.dumps(value).encode()).vendor_id is None
    assert parse_import(json.dumps(value | {"vendor_id": None}).encode()).vendor_id is None
    with pytest.raises(OrbitError):
        parse_import(json.dumps(value | {"vendor_id": ""}).encode())


def test_discovery_summary_cannot_hide_incomplete_enumeration_or_pending_rows():
    m = importlib.import_module("orbit_api.meta_auto_import")
    batches = [
        dict(
            id="batch",
            state="SUCCEEDED",
            total=2,
            success_count=2,
            failed_count=0,
            duplicate_count=0,
        )
    ]
    task = dict(id="task", state="DISCOVERING", error_code=None)
    assert m.public_status(task, batches)["state"] == "DISCOVERING"
    assert (
        m.public_status(task | dict(state="FAILED", error_code="META_PAGE_LIMIT"), batches)["state"]
        == "FAILED"
    )
    assert m.public_status(task | dict(state="IMPORTING"), batches)["state"] == "SUCCEEDED"
    assert m.public_status(task | dict(state="IMPORTING"), [])["state"] == "SUCCEEDED"
    pending = [batches[0] | dict(state="RUNNING", success_count=1)]
    assert m.public_status(task | dict(state="IMPORTING"), pending)["state"] == "IMPORTING"
    failed = [batches[0] | dict(state="PARTIAL_SUCCESS", success_count=1, failed_count=1)]
    assert m.public_status(task | dict(state="IMPORTING"), failed)["state"] == "PARTIAL_SUCCESS"


@pytest.mark.asyncio
async def test_auto_discovered_accounts_read_metadata_without_reenumerating_whole_scope():
    from orbit_api.meta_account_sources import MetaAccountSource, MetaAccountSourceReader
    from orbit_api.meta_read_contract import MetaReadConfiguration

    config = MetaReadConfiguration(str(uuid4()), 1, "v24.0", "ISOLATED")

    class Adapter:
        async def accounts_page(self, **kwargs):
            pytest.fail("已经持久发现的账户不应每行重新枚举全部账户")

        async def account(self, identifier):
            return dict(
                account_id=identifier,
                name="Account",
                currency="USD",
                timezone_name="UTC",
                account_status="1",
            )

    source = MetaAccountSource(config, "LOGIN", None, discovered=True)
    reader = MetaAccountSourceReader(source, adapter_factory=lambda _: Adapter())
    await reader.prepare(("123",))
    assert (await reader.fetch_metadata("123"))["external_id"] == "123"


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

    def all(self):
        return self.value or []


class RecordingSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "auth_version" in sql:
            return Result(4)
        if "orbit_directory_clock" in sql:
            return Result(8)
        return Result()


@pytest.mark.asyncio
async def test_enqueue_freezes_authorizing_actor_and_uses_authorization_as_idempotency_key(
    monkeypatch,
):
    m = importlib.import_module("orbit_api.meta_auto_import")
    current = SimpleNamespace(actor_id=7, tenant_id="tenant", subject_id="subject", team_id="team")

    async def access(*args, **kwargs):
        assert kwargs.get("acting_subject") is False
        return current

    monkeypatch.setattr(m, "require_business_access", access)
    session = RecordingSession()
    authorization = dict(
        id="authorization",
        tenant_id="tenant",
        actor_id=7,
        owner_user_id="subject",
        owner_team_id="team",
    )
    await m.enqueue(session, authorization, "connection", 2, "request")
    inserted = [
        params for sql, params in session.calls if "INSERT INTO orbit_meta_auto_import" in sql
    ]
    assert len(inserted) == 1
    assert inserted[0]["id"] == "authorization"
    assert inserted[0]["actor"] == 7 and inserted[0]["subject"] == "subject"
    assert inserted[0]["team"] == "team" and inserted[0]["tenant"] == "tenant"
    assert inserted[0]["auth"] == 4 and inserted[0]["scope"] == 8


@pytest.mark.asyncio
async def test_enqueue_rejects_actor_tenant_or_team_changed_during_oauth(monkeypatch):
    m = importlib.import_module("orbit_api.meta_auto_import")
    from orbit_api.errors import OrbitError

    for change in ({"tenant_id": "other"}, {"subject_id": "other"}, {"team_id": "other"}):
        current = SimpleNamespace(
            **(dict(actor_id=7, tenant_id="tenant", subject_id="subject", team_id="team") | change)
        )

        async def access(*args, _current=current, **kwargs):
            return _current

        monkeypatch.setattr(m, "require_business_access", access)
        session = RecordingSession()
        with pytest.raises(OrbitError):
            await m.enqueue(
                session,
                dict(
                    id="authorization",
                    tenant_id="tenant",
                    actor_id=7,
                    owner_user_id="subject",
                    owner_team_id="team",
                ),
                "connection",
                2,
                "request",
            )
        assert not any("INSERT INTO orbit_meta_auto_import" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_discovery_resumes_checkpoint_and_publishes_only_after_current_authorization(
    monkeypatch,
):
    m = importlib.import_module("orbit_api.meta_auto_import")
    from orbit_api.meta_account_sources import MetaAccountSource
    from orbit_api.meta_read_contract import MetaReadConfiguration, ReadCheckpoint

    cp = ReadCheckpoint("a" * 64, "b" * 64, "cursor-1", 1, 1, ("cursor-1",), ("123",))
    source = MetaAccountSource(
        MetaReadConfiguration(str(uuid4()), 1, "v24.0", "ISOLATED"), "LOGIN", None
    )
    task = {
        "id": "task",
        "tenant_id": "tenant",
        "claim_id": "lease",
        "checkpoint_json": json.dumps(
            dict(
                source_fingerprint="a" * 64,
                request_fingerprint="b" * 64,
                after="cursor-1",
                page_number=1,
                record_count=1,
                seen_cursors=["cursor-1"],
                seen_keys=["123"],
            )
        ),
    }
    events = []
    page = SimpleNamespace(items=(dict(account_id="456"),), complete=True, checkpoint=None)

    class Adapter:
        async def accounts_page(self, **kwargs):
            assert kwargs["checkpoint"] == cp
            events.append("read")
            return page

    class Worker(m.MetaAutoImportWorker):
        async def claim(self):
            return task

        async def preflight(self, captured):
            events.append("verify")
            return source

        async def publish(self, captured, result):
            assert result is page
            events.append("publish")

    worker = Worker(None, None, "v24.0", adapter_factory=lambda _: Adapter())
    assert await worker.run_once(limit=1) == 1
    assert events == ["verify", "read", "publish"]


@pytest.mark.asyncio
async def test_discovery_denied_before_network_never_publishes_a_batch():
    m = importlib.import_module("orbit_api.meta_auto_import")
    from orbit_api.account_platform import AccountReadFailure

    events = []

    class Worker(m.MetaAutoImportWorker):
        async def claim(self):
            return {"id": "task", "checkpoint_json": None}

        async def preflight(self, task):
            raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")

        async def fail(self, task, error):
            events.append(error.code)

        async def publish(self, *args):
            pytest.fail("撤权后不能创建导入批次")

    worker = Worker(None, None, "v24.0", adapter_factory=lambda _: pytest.fail("撤权后不能读取"))
    await worker.run_once(limit=1)
    assert events == ["ACCOUNT_IMPORT_AUTHORIZATION_CHANGED"]


@pytest.mark.asyncio
async def test_worker_null_vendor_still_checks_live_owner_and_permission(monkeypatch):
    import orbit_api.account_worker as m

    current = SimpleNamespace(tenant_id="tenant", subject_id="subject")

    async def access(*args, **kwargs):
        return current

    async def ownership(*args, **kwargs):
        return None

    async def records(*args):
        pytest.fail("未选择户商不应读取空引用")

    async def source(*args):
        return None

    monkeypatch.setattr(m, "require_business_access", access)
    monkeypatch.setattr(m, "validate_ownership", ownership)
    monkeypatch.setattr(m, "records", records)
    monkeypatch.setattr(m, "import_source", source)
    batch = dict(
        id="batch",
        actor_id=7,
        tenant_id="tenant",
        actor_subject_id="subject",
        scope_version=8,
        actor_auth_version=4,
        owner_user_id="subject",
        owner_team_id="team",
        vendor_id=None,
        vendor_revision=None,
    )
    result = await m.AccountImportWorker(None, None, {"USD"}).verify(
        RecordingSession(), batch, require_source=False
    )
    assert result[0] is current
    from orbit_api.account_platform import AccountReadFailure

    with pytest.raises(AccountReadFailure):
        await m.AccountImportWorker(None, None, {"USD"}).verify(
            RecordingSession(), batch | {"actor_auth_version": 3}, require_source=False
        )


@pytest.mark.asyncio
async def test_standard_import_worker_runs_discovery_before_rows_but_targeted_runs_do_not(
    monkeypatch,
):
    import orbit_api.account_worker as m
    import orbit_api.meta_auto_import as discovery

    events = []

    class Discover:
        def __init__(self, *args, **kwargs):
            pass

        async def run_once(self, limit):
            events.append("discover")

    monkeypatch.setattr(discovery, "MetaAutoImportWorker", Discover)
    for target in (None, (str(uuid4()), str(uuid4()))):
        worker = m.AccountImportWorker(
            None, None, {"USD"}, meta_graph_version="v24.0", target=target
        )

        async def recover(limit):
            events.append("rows")
            return 0

        async def claim():
            return None, False

        worker.recover_interrupted = recover
        worker.claim_one = claim
        await worker.run_once(1)
    assert events == ["discover", "rows", "rows"]
