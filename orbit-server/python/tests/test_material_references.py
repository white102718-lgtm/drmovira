"""跨模块素材交集和冻结清单单测；真实权限/SQL/回滚须独立集成验收。"""

import asyncio
from decimal import Decimal
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest

from orbit_api import material_references as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError

A, B, OWNER, TEAM, TENANT = [str(UUID(int=i)) for i in range(1, 6)]
CONTEXT = BusinessContext(7, TENANT, "USER", OWNER, TEAM)


@pytest.mark.parametrize("ids", [[], [A] * 201, A, None, ["invalid"], [True]])
def test_selection_invalid_or_unbounded(ids):
    with pytest.raises(OrbitError) as error:
        module.normalize_selection(ids)
    assert error.value.status == 422


def test_selection_deduplicates_sorts_and_requires_complete_frozen_maps():
    assert module.normalize_selection([B, A, A], {A: 1, B: 2}, {A: "a" * 64, B: "b" * 64}) == [A, B]
    with pytest.raises(OrbitError):
        module.normalize_selection([A, B], {A: 1})
    with pytest.raises(OrbitError):
        module.normalize_selection([A], {A: 1, B: 2})


@pytest.mark.parametrize("revision", [True, False, 0, -1, 9007199254740992, 1.0, "1"])
def test_frozen_revision_is_strict_safe_integer(revision):
    with pytest.raises(OrbitError):
        module.normalize_selection([A], {A: revision})


@pytest.mark.parametrize("sha", ["A" * 64, "g" * 64, "a" * 63, None, 0])
def test_frozen_sha_is_exact_lowercase_digest(sha):
    with pytest.raises(OrbitError):
        module.normalize_selection([A], expected_sha256={A: sha})


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class Session:
    def __init__(self, rows, *, active=True, verified=False):
        self.rows = rows
        self.active = active
        self.verified = verified
        self.transaction = object()
        self.info = {}
        self.sql = []
        self.sync_session = SimpleNamespace(get_transaction=lambda: self.transaction)

    def in_transaction(self):
        return self.active

    async def execute(self, statement, params):
        self.sql.append((str(statement), params))
        if "FROM orbit_material_scan_receipt" in str(statement):
            return Rows([{"asset_id": row["id"]} for row in self.rows] if self.verified else [])
        return Rows(self.rows)


def row(identifier=A, **changes):
    return MappingProxyType(
        {
            "id": identifier,
            "revision": 3,
            "name": "素材",
            "owner_user_id": OWNER,
            "owner_team_id": TEAM,
            "kind": "VIDEO",
            "state": "READY",
            "sha256": "a" * 64,
            "mime": "video/mp4",
            "byte_size": 100,
            "width_px": 1920,
            "height_px": 1080,
            "duration_seconds": Decimal("1.250"),
            "physical_cleanup_state": "LIVE",
            **changes,
        }
    )


@pytest.fixture
def authorization(monkeypatch):
    events = []

    async def contexts(*args):
        events.append("authorization")
        return CONTEXT, CONTEXT, (), ()

    async def clock(*args):
        events.append("clock")

    monkeypatch.setattr(module, "_contexts", contexts)
    monkeypatch.setattr(module.MaterialWorker, "lock_clock", clock)
    return events


def read(session, ids=None, **kwargs):
    return asyncio.run(
        module.require_allocation_assets(session, CONTEXT, OWNER, TEAM, ids or [A], **kwargs)
    )


def test_safe_metadata_retains_decimal_contract_and_explicit_unscanned(authorization):
    session = Session([row()])
    result = read(session, expected_revisions={A: 3}, expected_sha256={A: "a" * 64})[A]
    assert authorization == ["authorization", "clock"]
    assert result["duration"] == "1.250"
    assert result["width"] == 1920 and result["height"] == 1080
    assert result["antivirus_status"] == "UNVERIFIED" and result["execution_eligible"] is False
    assert set(result) == {
        "id",
        "revision",
        "name",
        "owner_user_id",
        "owner_team_id",
        "kind",
        "state",
        "sha256",
        "mime",
        "size",
        "width",
        "height",
        "duration",
        "physical_cleanup_state",
        "antivirus_status",
        "execution_eligible",
    }
    assert "ORDER BY id FOR UPDATE" in session.sql[0][0]
    assert session.info["orbit_material_batch_locks"][1] == {A}


@pytest.mark.parametrize("rows", [[], [row(owner_user_id=B)], [row(), row(B, owner_user_id=B)]])
def test_missing_or_either_side_invisible_rejects_entire_batch(authorization, rows):
    session = Session(rows)
    with pytest.raises(OrbitError) as error:
        read(session, [A, B] if len(rows) == 2 else [A])
    assert error.value.status == 404
    assert "orbit_material_batch_locks" not in session.info


@pytest.mark.parametrize(
    "changes,kwargs,code",
    [
        ({"owner_team_id": B}, {}, "REFERENCE_TEAM_MISMATCH"),
        ({"state": "SCANNING"}, {}, "MATERIAL_NOT_READY"),
        ({"physical_cleanup_state": "CLEANING"}, {}, "MATERIAL_NOT_READY"),
        ({"physical_cleanup_state": "PURGED"}, {}, "MATERIAL_NOT_READY"),
        ({}, {"expected_revisions": {A: 4}}, "REVISION_CONFLICT"),
        ({}, {"expected_sha256": {A: "b" * 64}}, "MATERIAL_HASH_CONFLICT"),
    ],
)
def test_state_team_revision_hash_cas(authorization, changes, kwargs, code):
    with pytest.raises(OrbitError) as error:
        read(Session([row(**changes)]), **kwargs)
    assert error.value.code == code


def test_outer_transaction_required_before_any_authorization(authorization):
    with pytest.raises(ValueError):
        read(Session([row()], active=False))
    assert authorization == []


def test_cross_batch_global_lock_order_and_transaction_reset(authorization):
    session = Session([row(B)])
    read(session, [B])
    with pytest.raises(ValueError):
        read(session, [A])
    assert len(session.sql) == 2
    # 同一事务已持有的锁可重入；新事务不能继承旧事务的已授权素材集合。
    read(session, [B])
    session.transaction = object()
    session.rows = [row(A)]
    read(session, [A])
    assert session.info["orbit_material_batch_locks"][1] == {A}


def test_registration_requires_prelocked_assets_and_rejects_historical(authorization):
    session = Session([row()])
    args = (session, CONTEXT, OWNER, TEAM, {A: {"revision": 3, "sha256": "a" * 64}})
    with pytest.raises(ValueError):
        asyncio.run(module.register_active_material_references(*args, "ALLOCATION", B, B))
    with pytest.raises(OrbitError) as error:
        asyncio.run(module.register_active_material_references(*args, "HISTORICAL_EVIDENCE", B, B))
    assert error.value.status == 422
    assert session.sql == []


@pytest.mark.parametrize(
    "role,owner,team,teams,allowed",
    [
        ("USER", OWNER, TEAM, (), True),
        ("USER", A, TEAM, (), False),
        ("TEAM_ADMIN", A, TEAM, (TEAM,), True),
        ("TEAM_ADMIN", A, TEAM, (), False),
        ("TEAM_ADMIN", A, B, (TEAM,), False),
        ("SUPER_ADMIN", A, B, (), True),
    ],
)
def test_explicit_managed_scope_not_same_team_guess(role, owner, team, teams, allowed):
    context = BusinessContext(7, TENANT, role, OWNER, TEAM)
    assert module._readable(row(owner_user_id=owner, owner_team_id=team), context, teams) is allowed


def test_both_contexts_are_live_and_target_does_not_spoof_cookie_actor(monkeypatch):
    calls = []
    target = BusinessContext(8, TENANT, "USER", B, TEAM)

    async def access(session, actor, menu, permission, **kwargs):
        calls.append((actor, menu, permission, kwargs))
        return CONTEXT if actor == 7 else target

    async def owner(*args):
        return {"user_id": 8}

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "one", owner)
    result = asyncio.run(module._contexts(Session([]), CONTEXT, B, TEAM))
    assert result[:2] == (CONTEXT, target)
    assert calls == [
        (7, "assets", "assets.read", {}),
        (8, "assets", "assets.read", {"acting_subject": False}),
    ]


@pytest.mark.parametrize("failure", ["missing", "revoked", "tenant", "subject", "team"])
def test_target_identity_or_scope_change_is_not_partially_accepted(monkeypatch, failure):
    async def access(session, actor, *args, **kwargs):
        if actor == 7:
            return CONTEXT
        if failure == "revoked":
            raise OrbitError(403, "PERMISSION_DENIED", "当前授权失效")
        return BusinessContext(
            8,
            A if failure == "tenant" else TENANT,
            "USER",
            A if failure == "subject" else B,
            A if failure == "team" else TEAM,
        )

    async def owner(*args):
        return None if failure == "missing" else {"user_id": 8}

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "one", owner)
    with pytest.raises(OrbitError) as error:
        asyncio.run(module._contexts(Session([]), CONTEXT, B, TEAM))
    assert error.value.status == 404


def test_existing_active_reference_is_idempotent_without_audit_write(authorization, monkeypatch):
    session = Session([row()], verified=True)
    frozen = read(session)

    async def reference(*args):
        return {"id": B, "active": 1}

    monkeypatch.setattr(module, "one", reference)
    result = asyncio.run(
        module.register_active_material_references(
            session, CONTEXT, OWNER, TEAM, frozen, "ALLOCATION", B, B
        )
    )
    assert result == {A: B}
    assert all(
        "INSERT" not in sql and "UPDATE orbit_material_clock" not in sql for sql, _ in session.sql
    )


def test_new_reference_writes_audit_outbox_and_clock_in_callers_transaction(
    authorization, monkeypatch
):
    session = Session([row()], verified=True)
    frozen = read(session)

    async def missing(*args):
        return None

    monkeypatch.setattr(module, "one", missing)
    result = asyncio.run(
        module.register_active_material_references(
            session, CONTEXT, OWNER, TEAM, frozen, "EXECUTION", B, B
        )
    )
    assert set(result) == {A}
    inserts = [(sql, params) for sql, params in session.sql if "INSERT INTO" in sql]
    assert len(inserts) == 3
    audit = next(params for sql, params in inserts if "orbit_material_audit" in sql)
    assert audit["actor"] == CONTEXT.actor_id and audit["request"] == B
    assert '"before":false' in audit["change"] and '"after":true' in audit["change"]
    assert all("COMMIT" not in sql for sql, _ in session.sql)


def test_legacy_ready_without_scan_proof_cannot_register_active_reference(authorization):
    session = Session([row()])
    frozen = read(session)
    with pytest.raises(OrbitError) as error:
        asyncio.run(
            module.register_active_material_references(
                session, CONTEXT, OWNER, TEAM, frozen, "ALLOCATION", B, B
            )
        )
    assert error.value.code == "ANTIVIRUS_UNVERIFIED"
    assert not any("INSERT INTO" in sql for sql, _ in session.sql)


class ReleaseSession(Session):
    def __init__(self, *, changed=False, missing=False, affected=1):
        super().__init__([])
        self.changed, self.missing, self.affected = changed, missing, affected

    async def execute(self, statement, params):
        sql = str(statement)
        self.sql.append((sql, params))
        if "SELECT id,asset_id FROM orbit_material_reference" in sql:
            return Rows([] if self.changed and "FOR UPDATE" in sql else [{"id": B, "asset_id": A}])
        if "SELECT id,revision FROM orbit_material_asset" in sql:
            return Rows(
                [] if self.missing else [{"id": item, "revision": 3} for item in params["ids"]]
            )
        return SimpleNamespace(rowcount=self.affected)


def ticket(session, **kwargs):
    return asyncio.run(
        module.lock_active_material_reference_set(session, CONTEXT, "ALLOCATION", B, **kwargs)
    )


def release(session, locked, context=CONTEXT):
    return asyncio.run(module.deactivate_locked_material_references(session, context, locked, A))


def test_release_locks_union_then_exact_reference_before_plan_cas(authorization):
    session = ReleaseSession()
    locked = ticket(session, additional_asset_ids=[OWNER, A])
    assert locked.references == ((B, A, 3),)
    assert session.sql[1][1]["ids"] == [A, OWNER]
    assert "FOR UPDATE" not in session.sql[0][0]
    assert "FOR UPDATE" in session.sql[1][0] and "FOR UPDATE" in session.sql[2][0]
    assert session.info["orbit_material_batch_locks"][1] == {A, OWNER}
    assert release(session, locked) == 1
    updates = [(sql, p) for sql, p in session.sql if "UPDATE orbit_material_reference" in sql]
    assert len(updates) == 1
    assert updates[0][1]["reference"] == B and updates[0][1]["asset"] == A
    assert "AND kind=:kind AND resource_id=:resource AND active=1" in updates[0][0]
    assert len([sql for sql, _ in session.sql if "INSERT INTO" in sql]) == 2
    assert all("COMMIT" not in sql for sql, _ in session.sql)
    with pytest.raises(ValueError):
        release(session, locked)


@pytest.mark.parametrize("failure", ["changed", "missing"])
def test_release_preserves_missing_or_changed_reference_evidence(authorization, failure):
    with pytest.raises(OrbitError) as error:
        ticket(ReleaseSession(**{failure: True}))
    assert error.value.code in {"REFERENCE_INTEGRITY", "REFERENCE_SET_CHANGED"}


@pytest.mark.parametrize("failure", ["actor", "tenant", "transaction", "forged"])
def test_release_ticket_not_transferable(authorization, failure):
    from dataclasses import replace

    session = ReleaseSession()
    locked = ticket(session)
    context = CONTEXT
    if failure == "actor":
        context = replace(CONTEXT, actor_id=8)
    elif failure == "tenant":
        context = replace(CONTEXT, tenant_id=B)
    elif failure == "transaction":
        session.transaction = object()
    else:
        locked = replace(locked)
    before = len(session.sql)
    with pytest.raises(ValueError):
        release(session, locked, context)
    assert len(session.sql) == before


def test_release_changed_row_requires_outer_transaction_rollback(authorization):
    session = ReleaseSession(affected=0)
    locked = ticket(session)
    with pytest.raises(OrbitError) as error:
        release(session, locked)
    assert error.value.code == "REFERENCE_SET_CHANGED"
    assert not any("INSERT INTO" in sql for sql, _ in session.sql)


def test_release_history_never_enters_mutation(authorization):
    session = ReleaseSession()
    with pytest.raises(OrbitError):
        asyncio.run(
            module.lock_active_material_reference_set(session, CONTEXT, "HISTORICAL_EVIDENCE", B)
        )
    assert session.sql == []
