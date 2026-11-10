"""显式连接来源不回退，旧批次/同步版本不能借新凭据继续。"""

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from orbit_api.account_platform import AccountReadFailure


def module():
    assert importlib.util.find_spec("orbit_api.meta_account_sources") is not None
    return importlib.import_module("orbit_api.meta_account_sources")


class Result:
    def __init__(self, row):
        self.row = row

    def scalar_one(self):
        return self.row

    def mappings(self):
        return self

    def first(self):
        return self.row


class Session:
    def __init__(self, connection, configuration=None):
        self.connection, self.configuration = connection, configuration
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "orbit_system_configuration" in sql:
            return Result(self.configuration)
        if "orbit_meta_connection" in sql:
            return Result(self.connection)
        raise AssertionError(sql)


class Cipher:
    ready = True

    def decrypt_internal(self, envelope, tenant, identifier, field):
        assert field == "meta_token"
        return "ISOLATED_READ_TOKEN"


def connection():
    return dict(
        id=str(uuid4()),
        tenant_id=str(uuid4()),
        revision=2,
        kind="LOGIN",
        status="ACTIVE",
        token_envelope="encrypted",
        scopes_json=["ads_read"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        data_access_expires_at=None,
        configuration_id=None,
        configuration_revision=None,
    )


@pytest.mark.asyncio
async def test_explicit_connection_configuration_preserves_frozen_identity():
    row = connection()
    value = await module().load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )
    assert value.configuration.source_config_id == row["id"]
    assert value.configuration.source_config_revision == 2
    assert value.kind == "LOGIN"
    assert "ISOLATED_READ_TOKEN" not in repr(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"status": "DISCONNECTED"},
        {"revision": 3},
        {"token_envelope": None},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"data_access_expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"scopes_json": []},
    ],
)
async def test_invalid_explicit_connection_fails_instead_of_using_bm(change):
    row = connection()
    session = Session(row | change)
    with pytest.raises(AccountReadFailure):
        await module().load_connection(session, Cipher(), row["tenant_id"], row["id"], 2, "v24.0")
    assert not any("orbit_system_configuration" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_bm_requires_same_original_configuration_revision():
    row = connection() | dict(kind="BM", configuration_id=str(uuid4()), configuration_revision=7)
    with pytest.raises(AccountReadFailure):
        await module().load_connection(
            Session(row, None), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
        )


@pytest.mark.asyncio
async def test_reader_me_scope_and_metadata_never_read_unselected_account():
    m = module()
    row = connection()
    source = await m.load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )
    calls = []

    class Adapter:
        def __init__(self, config):
            pass

        async def accounts_page(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(items=({"account_id": "123"},), complete=True, checkpoint=None)

        async def account(self, identifier):
            calls.append(identifier)
            return {
                "account_id": identifier,
                "name": "Isolated account",
                "currency": "USD",
                "timezone_name": "UTC",
                "account_status": "1",
            }

    reader = m.MetaAccountSourceReader(source, adapter_factory=Adapter)
    await reader.prepare(("123",))
    result = await reader.fetch_metadata("123")
    assert result["external_id"] == "123" and result["account_status"] == "ACTIVE"
    assert calls[0]["edge"] == "me"
    with pytest.raises(AccountReadFailure):
        await reader.fetch_metadata("456")
    assert "456" not in calls


@pytest.mark.asyncio
async def test_reader_missing_scope_and_incomplete_pages_never_authorize():
    m = module()
    row = connection()
    source = await m.load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )

    class Adapter:
        def __init__(self, config):
            pass

        async def accounts_page(self, **kwargs):
            return SimpleNamespace(items=(), complete=True, checkpoint=None)

        async def account(self, identifier):
            raise AssertionError("not authorized")

    reader = m.MetaAccountSourceReader(source, adapter_factory=Adapter)
    await reader.prepare(("123",))
    with pytest.raises(AccountReadFailure):
        await reader.fetch_metadata("123")


@pytest.mark.asyncio
async def test_bm_reader_uses_frozen_business_not_system_user():
    m = module()
    row = connection() | dict(
        kind="BM", principal_id="456", configuration_id=str(uuid4()), configuration_revision=7
    )
    config = dict(
        id=row["configuration_id"],
        revision=7,
        settings_json={"businessId": "789", "graphVersion": "v24.0"},
    )
    source = await m.load_connection(
        Session(row, config), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )
    calls = []

    class Adapter:
        def __init__(self, config):
            pass

        async def accounts_page(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(items=({"account_id": "123"},), complete=True, checkpoint=None)

    reader = m.MetaAccountSourceReader(source, adapter_factory=Adapter)
    await reader.prepare(("123",))
    assert [(c["edge"], c["business_id"]) for c in calls] == [("owned", "789"), ("client", "789")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["missing", "revision", "connection", "frozen_missing", "command_version"]
)
async def test_sync_frozen_source_cannot_switch_or_fall_back(monkeypatch, change):
    m = module()
    selected = dict(connection_id=str(uuid4()), connection_revision=2, revision=1)
    frozen = dict(selected)
    command = dict(
        source_json={"meta_connection_source": frozen},
        source_config_id=selected["connection_id"],
        source_config_revision=2,
    )
    changed = dict(selected)
    if change == "missing":
        changed = None
    elif change == "revision":
        changed["revision"] = 2
    elif change == "connection":
        changed["connection_id"] = str(uuid4())
    elif change == "frozen_missing":
        command["source_json"] = {}
    elif change == "command_version":
        command["source_config_revision"] = 3

    async def source(*args):
        return changed

    async def forbidden(*args):
        raise AssertionError("不能解密或回退失效来源")

    monkeypatch.setattr(m, "account_source", source)
    monkeypatch.setattr(m, "load_connection", forbidden)
    with pytest.raises(AccountReadFailure, match="ACCOUNT_SYNC_SOURCE_CHANGED"):
        await m.load_sync_source(None, None, "tenant", "account", command, "v24.0")


@pytest.mark.asyncio
async def test_sync_only_absence_of_both_explicit_and_frozen_source_allows_legacy(monkeypatch):
    m = module()

    async def absent(*args):
        return None

    monkeypatch.setattr(m, "account_source", absent)
    assert (
        await m.load_sync_source(None, None, "tenant", "account", {"source_json": {}}, "v24.0")
        is None
    )


@pytest.mark.asyncio
async def test_explicit_sync_source_selects_its_connection_without_querying_legacy(monkeypatch):
    import orbit_api.account_actions_store as store_module
    from orbit_api.account_actions_store import AccountActionsStore

    m = module()
    selected = dict(connection_id=str(uuid4()), connection_revision=2, revision=1)
    current = SimpleNamespace(tenant_id=str(uuid4()))
    store = AccountActionsStore(None)

    async def begin(*args):
        return current, None, {"id": str(uuid4())}, "digest", None

    async def source(*args):
        return selected

    async def connection(*args):
        return {"status": "ACTIVE"}

    async def command(*args, **kwargs):
        return kwargs["source"]

    queued = []

    async def enqueue(*args):
        queued.append(args)

    monkeypatch.setattr("orbit_api.meta_sync_runtime.enqueue_metrics", enqueue)
    store.begin, store.command = begin, command
    monkeypatch.setattr(store_module, "account_source", source)
    monkeypatch.setattr(store_module, "connection_row", connection)
    value = await store.sync(None, 1, "account", 1, "key", "auth", "csrf", "reason", str(uuid4()))
    assert value == {
        "id": selected["connection_id"],
        "revision": 2,
        "meta_source": m.source_marker(selected),
    }

    assert len(queued) == 1


@pytest.mark.asyncio
async def test_incomplete_meta_inventory_cannot_authorize_even_seen_account():
    m = module()
    row = connection()
    source = await m.load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )

    class Adapter:
        def __init__(self, config):
            pass

        async def accounts_page(self, **kwargs):
            return SimpleNamespace(
                items=({"account_id": "123"},), complete=False, checkpoint=object()
            )

        async def account(self, identifier):
            raise AssertionError("partial inventory is not authorization")

    reader = m.MetaAccountSourceReader(source, adapter_factory=Adapter)
    with pytest.raises(AccountReadFailure, match="ACCOUNT_PLATFORM_SCOPE_INCOMPLETE"):
        await reader.prepare(("123",))
    with pytest.raises(AccountReadFailure):
        await reader.fetch_metadata("123")


@pytest.mark.asyncio
async def test_reader_rechecks_current_authority_before_every_page_and_metadata():
    m = module()
    row = connection()
    source = await m.load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )

    class Adapter:
        def __init__(self, config):
            pass

        async def accounts_page(self, **kwargs):
            return SimpleNamespace(items=({"account_id": "123"},), complete=True, checkpoint=None)

        async def account(self, identifier):
            raise AssertionError("撤权后不得读Metadata")

    reader = m.MetaAccountSourceReader(source, adapter_factory=Adapter)
    calls = []

    async def guard():
        calls.append(1)
        if len(calls) == 2:
            raise AccountReadFailure("ACCOUNT_SYNC_AUTHORIZATION_CHANGED")

    reader.preflight = guard
    await reader.prepare(("123",))
    with pytest.raises(AccountReadFailure, match="ACCOUNT_SYNC_AUTHORIZATION_CHANGED"):
        await reader.fetch_metadata("123")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_transport_preflight_revocation_is_not_retried_as_network_error(monkeypatch):
    m = module()
    row = connection()
    source = await m.load_connection(
        Session(row), Cipher(), row["tenant_id"], row["id"], 2, "v24.0"
    )
    reader = m.MetaAccountSourceReader(source)
    checks = []

    async def guard():
        checks.append(1)
        if len(checks) > 1:
            raise AccountReadFailure("ACCOUNT_SYNC_AUTHORIZATION_CHANGED")

    async def forbidden_sleep(*args):
        raise AssertionError("授权失效不能当网络错误重试")

    reader.preflight = guard
    reader.adapter.sleep = forbidden_sleep
    with pytest.raises(AccountReadFailure, match="ACCOUNT_SYNC_AUTHORIZATION_CHANGED"):
        await reader.prepare(("123",))
    assert len(checks) == 2
