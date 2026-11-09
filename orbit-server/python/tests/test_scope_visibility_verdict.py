"""仅事务替身的范围证明边界；不冒充MySQL触发器或真实容量验收。"""

import hashlib
from pathlib import Path

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.scope_visibility_verdict import (
    PREDICATE_VERSION,
    proof_matches,
    verified_snapshot,
)

TENANT = "00000000-0000-4000-8000-000000000001"
SUBJECT = "00000000-0000-4000-8000-000000000002"
TEAM = "00000000-0000-4000-8000-000000000003"
SNAPSHOT = "00000000-0000-4000-8000-000000000004"
CURRENT = BusinessContext(17, TENANT, "USER", SUBJECT, TEAM)
DIGEST = "a" * 64
MEMBERS_HASH = "b" * 64


def snapshot(**changes):
    return {
        "id": SNAPSHOT,
        "tenant_id": TENANT,
        "actor_id": 17,
        "scope_version": 7,
        "auth_fingerprint": DIGEST,
        "member_count": 50_000,
        "members_hash": MEMBERS_HASH,
        "ready": 1,
        "cleanup_requested": 0,
    } | changes


def proof(**changes):
    return {
        "actor_id": 17,
        "auth_version": 7,
        "auth_digest": DIGEST,
        "account_version": 23,
        "members_hash": MEMBERS_HASH,
        "member_count": 50_000,
        "predicate_version": PREDICATE_VERSION,
    } | changes


class Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, row=None, *, verdict=None, invisible=None, write_error=False):
        self.row = snapshot() if row is None else row
        self.verdict = verdict
        self.invisible = invisible
        self.write_error = write_error
        self.calls = []

    def in_transaction(self):
        return True

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if sql.startswith("SELECT * FROM orbit_account_scope_snapshot"):
            return Result(self.row if self.row is not False else None)
        if sql.startswith("SELECT actor_id,"):
            return Result(self.verdict)
        if sql.startswith("SELECT 1 FROM orbit_account_scope_member"):
            return Result(self.invisible)
        if sql.startswith("INSERT INTO orbit_scope_access_verdict"):
            if self.write_error:
                raise RuntimeError("isolated write failure")
            return Result(None)
        raise AssertionError("意外SQL种类")


@pytest.fixture(autouse=True)
def trusted_clock(monkeypatch):
    async def clock(session, current):
        assert isinstance(current, BusinessContext) and current.actor_id == 17
        session.calls.append(("CLOCK_SHARE_WITH_DUE_GUARD", {}))
        return 23

    monkeypatch.setattr("orbit_api.scope_visibility_verdict.clock", clock)


@pytest.mark.asyncio
async def test_exact_positive_hit_still_checks_clock_and_parent_without_member_scan_or_write():
    session = Session(verdict=proof())
    result = await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert result == snapshot()
    assert session.calls[0][0] == "CLOCK_SHARE_WITH_DUE_GUARD"
    assert "cleanup_requested=0 FOR SHARE" in session.calls[1][0]
    assert session.calls[1][1] == {
        "tenant": TENANT,
        "actor": 17,
        "subject": SUBJECT,
        "id": SNAPSHOT,
    }
    assert len(session.calls) == 3
    assert "FOR SHARE" not in session.calls[2][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("actor_id", 18),
        ("auth_version", 8),
        ("auth_digest", "c" * 64),
        ("account_version", 24),
        ("members_hash", "c" * 64),
        ("member_count", 49_999),
        ("predicate_version", PREDICATE_VERSION + 1),
    ],
)
async def test_any_dependency_mismatch_rechecks_all_members_before_replacing_proof(key, value):
    session = Session(verdict=proof(**{key: value}))
    await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert len(session.calls) == 5
    sql, params = session.calls[3]
    assert "LEFT JOIN orbit_ad_account" in sql and "a.id IS NULL OR NOT" in sql
    assert "a.owner_user_id=:subject" in sql
    assert sql.endswith("LIMIT 1 FOR SHARE OF a")
    assert "LIMIT 500" not in sql and "LIMIT 200" not in sql
    assert params["id"] == SNAPSHOT
    write, values = session.calls[4]
    assert "ON DUPLICATE KEY UPDATE" in write
    assert {field: values[field] for field in proof()} == proof()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 500, 50_000])
async def test_unseen_proof_checks_complete_scope_without_imposing_plan_limit(count):
    session = Session(snapshot(member_count=count))
    assert (await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT))["member_count"] == count
    assert session.calls[-1][1]["member_count"] == count


@pytest.mark.asyncio
async def test_missing_or_now_invisible_member_never_publishes_positive_proof():
    session = Session(verdict=proof(account_version=22), invisible=1)
    with pytest.raises(OrbitError) as failure:
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert (failure.value.status, failure.value.code) == (409, "SCOPE_CHANGED")
    assert not any(sql.startswith("INSERT") for sql, _ in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [False, snapshot(cleanup_requested=1)])
async def test_missing_or_cleanup_parent_is_404_before_reading_proof(row):
    session = Session(row)
    with pytest.raises(OrbitError) as failure:
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert failure.value.status == 404
    assert len(session.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"scope_version": 6},
        {"auth_fingerprint": "c" * 64},
        {"member_count": -1},
        {"member_count": 50_001},
        {"member_count": True},
        {"members_hash": None},
        {"members_hash": "B" * 64},
    ],
)
async def test_original_snapshot_authorization_and_integrity_checks_precede_cache(change):
    session = Session(snapshot(**change), verdict=proof())
    with pytest.raises(OrbitError) as failure:
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert failure.value.status == 409
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_projection_lag_stops_before_parent_or_cache(monkeypatch):
    async def blocked(session, current):
        raise OrbitError(503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "isolated")

    monkeypatch.setattr("orbit_api.scope_visibility_verdict.clock", blocked)
    session = Session(verdict=proof())
    with pytest.raises(OrbitError) as failure:
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    assert failure.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
    assert not session.calls


@pytest.mark.asyncio
async def test_sql_failure_is_not_hidden_as_success():
    session = Session(write_error=True)
    with pytest.raises(RuntimeError, match="isolated write failure"):
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)


@pytest.mark.asyncio
@pytest.mark.parametrize("version,digest", [(True, DIGEST), (0, DIGEST), (7, "A" * 64)])
async def test_invalid_internal_authorization_arguments_do_not_touch_database(version, digest):
    session = Session()
    with pytest.raises(ValueError):
        await verified_snapshot(session, CURRENT, version, digest, SNAPSHOT)
    assert not session.calls


@pytest.mark.asyncio
async def test_no_outer_transaction_or_untrusted_context_is_rejected():
    session = Session()
    session.in_transaction = lambda: False
    with pytest.raises(ValueError):
        await verified_snapshot(session, CURRENT, 7, DIGEST, SNAPSHOT)
    session.in_transaction = lambda: True
    with pytest.raises(ValueError):
        await verified_snapshot(session, object(), 7, DIGEST, SNAPSHOT)
    assert not session.calls


def test_partial_proof_is_not_a_positive_hit():
    assert not proof_matches(None, proof())
    assert not proof_matches({}, proof())
    assert proof_matches(proof(), proof())


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [[], [TEAM], [TEAM, SUBJECT]])
async def test_team_miss_compiles_only_current_explicit_managed_set(monkeypatch, managed):
    current = BusinessContext(17, TENANT, "TEAM_ADMIN", SUBJECT, TEAM)
    digest = hashlib.sha256(
        canonical([17, TENANT, SUBJECT, "TEAM_ADMIN", TEAM, sorted(managed), 7]).encode()
    ).hexdigest()

    async def current_managers(session, context):
        assert context is current
        session.calls.append(("MANAGED_CURRENT_SHARE", {}))
        return managed

    monkeypatch.setattr("orbit_api.scope_visibility_verdict.managed_teams", current_managers)
    session = Session(snapshot(auth_fingerprint=digest))
    await verified_snapshot(session, current, 7, digest, SNAPSHOT)
    assert session.calls[3][0] == "MANAGED_CURRENT_SHARE"
    sql, params = session.calls[4]
    assert "EXISTS" not in sql
    assert "a.owner_user_id=:subject" in sql
    if managed:
        assert "a.owner_team_id IN (__[POSTCOMPILE_managed])" in sql
        assert params["managed"] == sorted(managed)
    else:
        assert "owner_team_id" not in sql


@pytest.mark.asyncio
async def test_team_current_managers_no_longer_match_original_authorized_digest(monkeypatch):
    current = BusinessContext(17, TENANT, "TEAM_ADMIN", SUBJECT, TEAM)

    async def managers(session, context):
        return []

    monkeypatch.setattr("orbit_api.scope_visibility_verdict.managed_teams", managers)
    session = Session()
    with pytest.raises(OrbitError) as failure:
        await verified_snapshot(session, current, 7, DIGEST, SNAPSHOT)
    assert failure.value.code == "SCOPE_CHANGED"
    assert not any(sql.startswith("INSERT") for sql, _ in session.calls)
    assert not any("LEFT JOIN orbit_ad_account" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_super_admin_predicate_does_not_add_target_owner_or_unbound_constraints():
    current = BusinessContext(17, TENANT, "SUPER_ADMIN", SUBJECT, TEAM)
    session = Session()
    await verified_snapshot(session, current, 7, DIGEST, SNAPSHOT)
    sql = session.calls[3][0]
    assert "a.id IS NULL OR NOT (1=1)" in sql
    assert "unbound_at" not in sql and "owner_user_id=" not in sql


def test_candidate_migration_has_guards_for_ready_parent_and_all_member_mutations():
    sql = (
        Path(__file__).parents[1] / "orbit_api/migrations/043_scope_access_verdict.sql"
    ).read_text(encoding="utf-8")
    assert sql.count("CREATE TRIGGER") == 6
    for kind in ("INSERT", "UPDATE", "DELETE"):
        assert f"BEFORE {kind} ON orbit_account_scope_snapshot" in sql
        assert f"BEFORE {kind} ON orbit_account_scope_member" in sql
    assert "FOREIGN KEY(tenant_id,snapshot_id)" in sql
    assert "cleanup_requested=1 AND NEW.cleanup_requested<>1" in sql
    assert "member_count BETWEEN 0 AND 50000" in sql
    assert "NOT (NEW.request_json <=> OLD.request_json)" in sql
    assert "TTL" in sql
