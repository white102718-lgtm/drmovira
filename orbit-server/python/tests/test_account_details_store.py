"""账户详情读模型控制专项；会话替身不代表MySQL、锁与HTTP业务验收。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from orbit_api.account_details_contract import filters
from orbit_api.account_details_store import AccountDetailsStore
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"


class Tokens:
    def __init__(self):
        self.claims = None

    def issue(self, purpose, claims):
        assert purpose == "ACCOUNT_DETAILS_CURSOR_V1"
        self.claims = claims
        return "controlled-token"

    def verify(self, purpose, token):
        assert purpose == "ACCOUNT_DETAILS_CURSOR_V1" and token == "controlled-token"
        return self.claims


async def test_new_catalog_revision_invalidates_cursor_before_account_rows_are_queried(monkeypatch):
    import orbit_api.account_details_store as module

    current = SimpleNamespace(tenant_id=ID, subject_id=ID, data_role="USER", team_id=ID, actor_id=1)

    async def access(*args):
        return current, []

    async def one(*args):
        return 1

    monkeypatch.setattr(module, "context", access)
    monkeypatch.setattr(module, "clock", one)
    monkeypatch.setattr(module, "scope_version", one)
    tokens = Tokens()
    store = AccountDetailsStore(tokens)

    async def watermark(*args):
        return {"revision": 0, "snapshot_id": None}

    async def enriched(*args):
        return []

    store.watermark, store.enrich = watermark, enriched

    class Session:
        version = 1
        reads = 0

        async def execute(self, statement, params=None):
            query = str(statement)
            if "orbit_reference_clock" in query:
                return SimpleNamespace(scalar_one=lambda: self.version)
            if "UTC_TIMESTAMP" in query:
                return SimpleNamespace(scalar_one=lambda: datetime(2026, 11, 8))
            self.reads += 1
            return SimpleNamespace(mappings=lambda: [{"id": ID}] * 21)

    session = Session()
    page = await store.list(session, 1, filters({"page_size": "20"}))
    assert page["next_cursor"] == "controlled-token" and session.reads == 1
    session.version = 2
    with pytest.raises(OrbitError) as error:
        await store.list(session, 1, filters({"page_size": "20"}), page["next_cursor"])
    assert error.value.status == 409 and session.reads == 1


@pytest.mark.parametrize("facts,revision", [([], 0), ([{}] * 1001, 0), ([{}], True), ([None], 0)])
async def test_invalid_publication_limits_fail_before_database_access(facts, revision):
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError("非法结构不能访问数据库")

    with pytest.raises(OrbitError):
        await AccountDetailsStore(None).publish(NoDatabase(), 1, revision, facts=facts)


async def test_publication_requires_explicit_outer_transaction():
    with pytest.raises(ValueError, match="显式事务"):
        await AccountDetailsStore(None).publish(
            SimpleNamespace(in_transaction=lambda: False), 1, 0, facts=[{"account_id": ID}]
        )


async def test_summary_prelocks_source_before_clock_and_only_enriches_final_page(monkeypatch):
    """候选仅用于预锁来源；真实行必须在clock之后重新选择，DTO形状保持不变。"""
    import orbit_api.account_details_store as module

    events = []
    current = SimpleNamespace(tenant_id=ID, subject_id=ID, data_role="USER", team_id=ID, actor_id=1)

    async def access(*args):
        events.append("auth")
        return current, []

    async def clock(*args):
        events.append("clock")
        return 1

    async def scope(*args):
        return 1

    monkeypatch.setattr(module, "context", access)
    monkeypatch.setattr(module, "clock", clock)
    monkeypatch.setattr(module, "scope_version", scope)

    class Summary:
        async def authorize_list(self, session, actor):
            value, managed = await access(session, actor, "accounts.read")
            return value, managed, self

        async def prepare_for_list(self, session, actor, ids, authorization):
            assert authorization is self
            events.append("source")
            assert ids == [ID] and actor == 1
            return self

        async def resolve(self, session, actor, page, ticket):
            events.append("resolve")
            assert ticket is self and page == [{"id": ID}]
            return {ID: {"identity_status": "SYNCED", "identity_count": 0}}

    store = AccountDetailsStore(Tokens(), identity_summary=Summary())

    async def page(*args):
        events.append(f"page-{args[-1]}")
        return [{"id": ID}]

    async def watermark(*args):
        return {"revision": 0, "snapshot_id": None}

    async def enrich(*args):
        return [{"account": {"id": ID}, "details": {"identity_status": "UNSYNCED", "note": None}}]

    class Session:
        async def execute(self, statement, params=None):
            return SimpleNamespace(
                scalar_one=lambda: (
                    1 if "orbit_reference_clock" in str(statement) else datetime(2026, 11, 9)
                )
            )

    store._page, store.watermark, store.enrich = page, watermark, enrich
    result = await store.list(Session(), 1, filters({"page_size": "20"}))
    assert events == ["auth", "page-20", "source", "clock", "page-21", "resolve"]
    assert result["items"] == [
        {
            "account": {"id": ID},
            "details": {"identity_status": "SYNCED", "identity_count": 0, "note": None},
        }
    ]


async def test_summary_invalid_cursor_never_probes_account_or_source(monkeypatch):
    import orbit_api.account_details_store as module

    async def access(*args):
        return SimpleNamespace(), []

    monkeypatch.setattr(module, "context", access)

    class RejectTokens:
        def verify(self, *args):
            raise OrbitError(400, "TOKEN_INVALID", "无效游标")

    class NoProbe:
        async def authorize_list(self, session, actor):
            value, managed = await access(session, actor, "accounts.read")
            return value, managed, self

        def __getattr__(self, name):
            pytest.fail("无效游标不得触发账户预读或来源锁")

    with pytest.raises(OrbitError) as error:
        await AccountDetailsStore(RejectTokens(), identity_summary=NoProbe()).list(
            NoProbe(), 1, filters({}), "bad-cursor"
        )
    assert error.value.code == "TOKEN_INVALID"
