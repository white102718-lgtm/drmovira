"""范围冻结流式控制与计划消费边界；替身不代替MySQL一致性/容量验收。"""

import hashlib
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_scope_contract import ScopeSelection
from orbit_api.account_scope_store import AccountScopeStore
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError

TENANT = str(UUID(int=100001))
OWNER = str(UUID(int=100002))
TEAM = str(UUID(int=100003))
REQUEST = str(UUID(int=100004))
CURRENT = SimpleNamespace(
    actor_id=1, tenant_id=TENANT, subject_id=OWNER, team_id=TEAM, data_role="SUPER_ADMIN"
)


def row(index):
    return {
        "id": str(UUID(int=index)),
        "external_id": "00" + str(index),
        "name": "原始名称" + str(index),
        "name_prefix": "原始名称" + str(index),
        "revision": 1,
        "owner_user_id": OWNER,
        "owner_team_id": TEAM,
        "currency": "USD",
    }


class Result:
    def __init__(self, values):
        self.values = values

    def mappings(self):
        return self

    def one(self):
        return self.values[0]

    def __iter__(self):
        return iter(self.values)


class Session:
    def __init__(self, values):
        self.values, self.calls, self.stored = values, [], None

    def in_transaction(self):
        return True

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params.copy() if isinstance(params, dict) else params))
        if sql.startswith("INSERT INTO orbit_account_scope_snapshot"):
            self.stored = {
                "id": params["id"],
                "request_hash": params["hash"],
                "ready": 0,
                "scope_version": 7,
                "member_count": 0,
                "members_hash": None,
                "created_at": datetime(2026, 11, 8),
            }
        if sql.startswith("SELECT * FROM orbit_account_scope_snapshot"):
            return Result([self.stored])
        if "FROM orbit_ad_account a WHERE" in sql:
            found = [item for item in self.values if item["id"] > params["after"]]
            if "ids" in params:
                assert len(params["ids"]) <= 1000, "不能每块重复发送5万ID"
                chosen = set(params["ids"])
                found = [item for item in found if item["id"] in chosen]
            return Result(found[: params["limit"]])
        return Result([])


async def authorized(session, actor):
    return CURRENT, 7, "real-auth-fingerprint-substitute"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["IDS", "FILTER"])
async def test_1001_members_use_bounded_batches_and_deterministic_streaming_digest(
    monkeypatch, mode
):
    values = [row(index) for index in range(1, 1002)]
    session = Session(values)
    store = AccountScopeStore(None)
    monkeypatch.setattr(store, "authorize", authorized)
    monkeypatch.setattr("orbit_api.account_scope_store.verify_csrf", lambda *args: None)
    selection = ScopeSelection(
        mode,
        tuple(item["id"] for item in values) if mode == "IDS" else (),
        {"q": ""} if mode == "FILTER" else None,
        canonical({"controlled": mode}),
    )
    result = await store.create(session, 1, "", "fixture", "fixture-key-00001", selection, REQUEST)
    frozen = [
        [
            item["id"],
            item["external_id"],
            item["name"],
            item["revision"],
            item["owner_user_id"],
            item["owner_team_id"],
            item["currency"],
        ]
        for item in values
    ]
    assert result["hash"] == hashlib.sha256(canonical(frozen).encode()).hexdigest()
    assert result["count"] == 1001
    assert len(result) == 5
    writes = [
        params for sql, params in session.calls if "INSERT INTO orbit_account_scope_member" in sql
    ]
    assert [len(items) for items in writes] == [1000, 1]
    assert all("UPDATE orbit_account_clock" not in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_invisible_selected_ids_do_not_publish_partial_ready_snapshot(monkeypatch):
    session, store = Session([row(1)]), AccountScopeStore(None)
    monkeypatch.setattr(store, "authorize", authorized)
    monkeypatch.setattr("orbit_api.account_scope_store.verify_csrf", lambda *args: None)
    selection = ScopeSelection("IDS", (row(1)["id"], row(2)["id"]), None, "{}")
    with pytest.raises(OrbitError) as failure:
        await store.create(session, 1, "", "fixture", "fixture-key-00001", selection, REQUEST)
    assert failure.value.status == 404
    assert not any("SET ready=1" in sql for sql, _ in session.calls)
    assert not any("INSERT INTO orbit_account_scope_event" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_filter_limit_detects_50001_without_publishing_truncated_members(monkeypatch):
    session = Session([row(index) for index in range(1, 50002)])
    store = AccountScopeStore(None)
    monkeypatch.setattr(store, "authorize", authorized)
    monkeypatch.setattr("orbit_api.account_scope_store.verify_csrf", lambda *args: None)
    with pytest.raises(OrbitError) as failure:
        await store.create(
            session,
            1,
            "",
            "fixture",
            "fixture-key-00001",
            ScopeSelection("FILTER", (), {"q": ""}, "{}"),
            REQUEST,
        )
    assert failure.value.code == "SCOPE_ACCOUNT_LIMIT"
    assert not any("SET ready=1" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 501, 50000])
async def test_plan_scope_limit_is_not_a_silent_truncation(monkeypatch, count):
    store = AccountScopeStore(None)
    monkeypatch.setattr(store, "authorize", authorized)

    async def snapshot(*args):
        return {"id": REQUEST, "member_count": count}

    monkeypatch.setattr(store, "snapshot", snapshot)
    with pytest.raises(OrbitError) as failure:
        await store.resolve_for_plan(
            None, CURRENT, REQUEST, owner_user_id=OWNER, owner_team_id=TEAM
        )
    assert failure.value.code == "PLAN_ACCOUNT_LIMIT"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["owner", "team", "currency", "mixed", "name-only"])
async def test_plan_consumption_rechecks_frozen_semantics_but_not_ordinary_name_revision(
    monkeypatch, target
):
    store = AccountScopeStore(None)
    monkeypatch.setattr(store, "authorize", authorized)
    item = row(1) | {"frozen_owner": OWNER, "frozen_team": TEAM, "frozen_currency": "USD"}
    if target in {"owner", "team", "currency"}:
        item[
            {"owner": "owner_user_id", "team": "owner_team_id", "currency": "currency"}[target]
        ] = "changed"
    values = [item]
    if target == "mixed":
        values.append(item | {"id": row(2)["id"], "currency": "EUR", "frozen_currency": "EUR"})
    if target == "name-only":
        item.update({"name": "改名不使冻结ID失效", "revision": 200})

    async def snapshot(*args):
        return {"id": REQUEST, "member_count": len(values)}

    class PlanSession:
        async def execute(self, statement, params):
            return Result(values)

    monkeypatch.setattr(store, "snapshot", snapshot)
    if target == "name-only":
        assert await store.resolve_for_plan(
            PlanSession(), CURRENT, REQUEST, owner_user_id=OWNER, owner_team_id=TEAM
        ) == [row(1)["id"]]
    else:
        with pytest.raises(OrbitError) as failure:
            await store.resolve_for_plan(
                PlanSession(), CURRENT, REQUEST, owner_user_id=OWNER, owner_team_id=TEAM
            )
        assert failure.value.code == (
            "PLAN_ACCOUNT_CURRENCY_MISMATCH" if target == "mixed" else "ACCOUNT_OWNERSHIP_CHANGED"
        )
