"""规则三桥SQL/授权协议纯测试；替身不是MySQL或真实指标来源证据。"""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

import orbit_api.rule_access as access_core
import orbit_api.rule_profile_references as profile_core
import orbit_api.rule_scope_references as scope_core
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_access import (
    RULE_ACTIONS,
    authorize_rule,
    owner_scope,
    require_rule_visible,
)
from orbit_api.rule_profile_references import lock_rule_profile
from orbit_api.rule_scope_references import capture_rule_scope, revalidate_rule_members

TENANT = str(UUID(int=1))
USER = str(UUID(int=2))
TEAM = str(UUID(int=3))
PROFILE = str(UUID(int=4))
SOURCE = str(UUID(int=5))
SNAPSHOT = str(UUID(int=6))
OTHER_USER = str(UUID(int=7))
OTHER_TEAM = str(UUID(int=8))


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Session:
    def __init__(self):
        self.sync_session = self
        self.tx = object()
        self.events = []
        self.version = 1
        self.owner = {
            "actor_id": 2,
            "tenant_id": TENANT,
            "subject_id": USER,
            "team_id": TEAM,
            "data_role": "USER",
            "auth_version": 1,
        }
        self.rows = []
        self.snapshot = None
        self.rule_snapshot = None
        self.bound_rule_ids = []
        self.probe = None
        self.profile = None
        self.source = {"id": SOURCE, "revision": 1, "enabled": True, "section": "META_BM"}
        self.now = datetime(2026, 11, 9, 1, tzinfo=UTC)

    def in_transaction(self):
        return self.tx is not None

    def get_transaction(self):
        return self.tx

    async def execute(self, statement, values=None):
        sql = str(statement)
        values = values or {}
        self.events.append((sql, values))
        assert sql.lstrip().upper().startswith("SELECT"), "三桥不能写持久表"
        if "SELECT auth_version FROM sys_identity_subject" in sql:
            return Result([self.version])
        if "FROM orbit_business_user b" in sql:
            return Result([self.owner] if self.owner else [])
        if "FROM orbit_account_scope_snapshot" in sql:
            return Result(
                [self.snapshot] if self.snapshot and self.snapshot["id"] == values["id"] else []
            )
        if "FROM orbit_rule_editor_scope_snapshot" in sql:
            return Result(
                [self.rule_snapshot]
                if self.rule_snapshot and self.rule_snapshot["id"] == values["id"]
                else []
            )
        if "SELECT rule_id FROM orbit_rule_scope_manifest" in sql:
            selected = [
                r
                for r in self.bound_rule_ids
                if (r != values["rule"] if "rule_id<>:rule" in sql else r == values["rule"])
            ]
            return Result([{"rule_id": r} for r in selected[:1]])
        if "FROM orbit_account_scope_member" in sql or "FROM orbit_rule_editor_scope_member" in sql:
            rows = [r for r in self.rows if r["account_id"] > values["after"]][:1000]
            return Result(rows)
        if "FROM orbit_ad_account" in sql:
            return Result([r for r in self.rows if r["id"] in values["ids"]])
        if "FROM orbit_system_configuration" in sql:
            return Result([self.source] if self.source else [])
        if "FROM orbit_metric_profile_clock" in sql:
            return Result([{"revision": 2, "now": self.now}])
        if "AS head_revision" in sql:
            return Result([self.profile] if self.profile else [])
        if "FROM orbit_metric_profile_head" in sql:
            return Result([self.probe] if self.probe else [])
        raise AssertionError("未覆盖SQL协议")


@pytest.fixture
def harness(monkeypatch):
    session = Session()
    state = SimpleNamespace(
        current=BusinessContext(1, TENANT, "SUPER_ADMIN", USER, TEAM),
        managed={},
        denied=False,
        permissions=[],
        writes=[],
    )

    async def authorized(s, actor, menu, permission):
        assert s is session and actor == 1 and menu == "rules"
        state.permissions.append(permission)
        if state.denied:
            raise OrbitError(403, "PERMISSION_DENIED", "撤权")
        return state.current

    async def managed(s, current):
        s.events.append(("MANAGED FOR SHARE", {"actor": current.actor_id}))
        return state.managed.get(current.actor_id, [])

    async def ownership(s, current, value, *, previous):
        state.writes.append((value, previous))
        if current.data_role == "USER" and value["data_owner_user_ids"] != [current.subject_id]:
            raise OrbitError(403, "OWNERSHIP_DENIED", "不能指派他人")

    async def clock(s, current):
        s.events.append(("ACCOUNT CLOCK FOR SHARE", {"tenant": current.tenant_id}))
        return 3

    monkeypatch.setattr(access_core, "require_business_access", authorized)
    monkeypatch.setattr(access_core, "managed_teams", managed)
    monkeypatch.setattr(access_core, "validate_ownership", ownership)
    monkeypatch.setattr(scope_core, "clock", clock)
    return session, state


async def contexts(harness, permission="rules.create"):
    session, _state = harness
    access = await authorize_rule(session, 1, permission)
    owner = await owner_scope(session, access, {"owner_user_id": USER, "owner_team_id": TEAM})
    return access, owner


def members(session, access, count=2):
    session.rows = [
        {
            "account_id": str(UUID(int=100 + i)),
            "external_id": f"000{i}",
            "name": f"账户{i}",
            "account_revision": 1,
            "frozen_owner": USER,
            "frozen_team": TEAM,
            "frozen_currency": "USD",
            "id": str(UUID(int=100 + i)),
            "owner_user_id": USER,
            "owner_team_id": TEAM,
            "currency": "USD" if i % 2 else "EUR",
            "revision": 2,
        }
        for i in range(count)
    ]
    source = [
        [
            r["account_id"],
            r["external_id"],
            r["name"],
            r["account_revision"],
            r["frozen_owner"],
            r["frozen_team"],
            r["frozen_currency"],
        ]
        for r in session.rows
    ]
    session.snapshot = {
        "id": SNAPSHOT,
        "ready": 1,
        "cleanup_requested": 0,
        "actor_id": 1,
        "scope_version": access.auth_version,
        "auth_fingerprint": access.auth_fingerprint,
        "member_count": count,
        "members_hash": hashlib.sha256(canonical(source).encode()).hexdigest(),
    }


def metric(session, source="META"):
    profile = {
        "id": PROFILE,
        "version": "v1.00",
        "source": source,
        "register_action_type": "complete_registration",
        "purchase_action_type": "purchase",
        "value_action_type": "purchase",
        "attribution_windows": ["7d_click"],
        "action_report_time": "conversion",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 7,
        "verified": True,
    }
    config, rev = (SOURCE, 1) if source == "META" else (None, None)
    proof = {
        "source_sha256": "a" * 64,
        "observed_at": "2026-11-09T00:00:00.123499+00:00",
        "evidence_ref": "RULE_ISOLATED_PROTOCOL",
        "source_config_id": config,
        "source_config_revision": rev,
    }
    session.probe = {
        "current_version": "v1.00",
        "source": source,
        "authority_kind": "TRUSTED" if source == "META" else "ISOLATED_TEST",
        "source_config_id": config,
        "source_config_revision": rev,
    }
    session.profile = session.probe | {
        "head_revision": 2,
        "state": "ENABLED",
        "payload_json": profile,
        "payload_hash": hashlib.sha256(canonical(profile).encode()).hexdigest(),
        "source_proof_json": proof,
        "observed_at": datetime(2026, 11, 9, 0, 0, 0, 123000),
        "source_sha256": "a" * 64,
        "evidence_ref": proof["evidence_ref"],
    }


@pytest.mark.parametrize("permission", sorted(RULE_ACTIONS))
async def test_each_exact_original_action_never_demands_other_menu(harness, permission):
    session, state = harness
    access = await authorize_rule(session, 1, permission)
    assert access.permission == permission
    assert state.permissions == [permission]


async def test_no_extra_actions_and_current_revoke(harness):
    session, state = harness
    with pytest.raises(ValueError):
        await authorize_rule(session, 1, "monitor.read")
    access, owner = await contexts(harness)
    state.denied = True
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.status == 403


async def test_cross_transaction_and_forged_ticket_rejected(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    with pytest.raises(ValueError):
        await capture_rule_scope(session, replace(access, _issuer=object()), SNAPSHOT, owner)
    session.tx = object()
    with pytest.raises(ValueError):
        await capture_rule_scope(session, access, SNAPSHOT, owner)


@pytest.mark.parametrize(
    "role,own,managed,allowed",
    [
        ("USER", True, False, True),
        ("USER", False, True, False),
        ("TEAM_ADMIN", True, False, True),
        ("TEAM_ADMIN", False, True, True),
        ("TEAM_ADMIN", False, False, False),
        ("SUPER_ADMIN", False, False, True),
    ],
)
async def test_rule_object_read_self_or_explicit_managed_only(harness, role, own, managed, allowed):
    session, state = harness
    state.current = replace(state.current, data_role=role)
    state.managed[1] = [OTHER_TEAM] if managed else []
    access = await authorize_rule(session, 1, "rules.read")
    row = {
        "tenant_id": TENANT,
        "owner_user_id": USER if own else OTHER_USER,
        "owner_team_id": OTHER_TEAM,
    }
    if allowed:
        require_rule_visible(access, row)
    else:
        with pytest.raises(OrbitError) as caught:
            require_rule_visible(access, row)
        assert caught.value.status == 404


async def test_owner_write_explicit_validation_and_no_owner_extra_menu(harness):
    session, state = harness
    access = await authorize_rule(session, 1, "rules.edit")
    await owner_scope(
        session, access, {"owner_user_id": USER, "owner_team_id": TEAM}, for_write=True
    )
    assert state.writes == [({"owner_team_id": TEAM, "data_owner_user_ids": [USER]}, None)]
    assert state.permissions == ["rules.edit"]
    state.current = replace(state.current, data_role="USER")
    access = await authorize_rule(session, 1, "rules.edit")
    with pytest.raises(OrbitError):
        await owner_scope(
            session, access, {"owner_user_id": OTHER_USER, "owner_team_id": TEAM}, for_write=True
        )


async def test_snapshot_hash_full_metadata_but_rule_identity_ids_only(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access, 501)
    scope = await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert len(scope.members) == 501  # 不沿Plan500，也不强制所有账户同币种。
    before = scope.member_hash
    for row in session.rows:
        row["revision"] = 3
    latest = await revalidate_rule_members(session, access, owner, scope.members)
    assert all(row.revision == 3 for row in latest)
    assert scope.member_hash == before


@pytest.mark.parametrize(
    "mutation", ["owner", "caller", "member_hash", "count", "private", "generation"]
)
async def test_scope_complete_intersection_privacy_root_and_generation(harness, mutation):
    session, state = harness
    access, owner = await contexts(harness)
    members(session, access)
    if mutation == "owner":
        session.rows[-1]["owner_user_id"] = OTHER_USER
    elif mutation == "caller":
        state.current = replace(state.current, data_role="USER")
    elif mutation == "member_hash":
        session.rows[-1]["name"] = "篡改历史"
    elif mutation == "count":
        session.snapshot["member_count"] += 1
    elif mutation == "private":
        session.snapshot["actor_id"] = 2
    else:
        session.snapshot["scope_version"] += 1
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.status in ({404} if mutation == "private" else {403, 409})


async def test_scope_50001_rejected_before_any_partial_member_scan(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access)
    session.snapshot["member_count"] = 50001
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.code == "RULE_ACCOUNT_LIMIT"
    assert not any("FROM orbit_account_scope_member" in sql for sql, _ in session.events)


async def editor_source(harness, *, action="CREATE", rule_id=None, revision=None):
    """明确内存SQL协议样本；不冒充实际061/并发或生产authority。"""
    session, _state = harness
    access, owner = await contexts(harness, "rules.create" if action == "CREATE" else "rules.edit")
    members(session, access)
    intent = {
        "action": action,
        "rule_id": rule_id,
        "rule_revision": revision,
        "ownership": {"owner_user_id": USER, "owner_team_id": TEAM},
        "selection": {
            "mode": "IDS",
            "account_ids": [r["account_id"] for r in session.rows],
            "filter": None,
        },
    }
    session.rule_snapshot = dict(session.snapshot) | {
        "action": action,
        "rule_id": rule_id,
        "rule_revision": revision,
        "owner_user_id": USER,
        "owner_team_id": TEAM,
        "owner_auth_fingerprint": owner.auth_fingerprint,
        "request_json": canonical(intent),
        "request_hash": hashlib.sha256(canonical(intent).encode()).hexdigest(),
    }
    session.snapshot = None
    return access, owner


async def test_editor_create_exact_target_and_internal_kind_without_public_dto_change(harness):
    session, _state = harness
    access, owner = await editor_source(harness)
    target = str(UUID(int=9000))
    scope = await capture_rule_scope(session, access, SNAPSHOT, owner, target_rule_id=target)
    assert scope.source_kind == "RULE" and scope._target_rule_id == target
    assert len(scope.members) == 2
    sqls = [sql for sql, _ in session.events]
    source_sql = next(sql for sql in sqls if "FROM orbit_rule_editor_scope_snapshot" in sql)
    assert "FOR UPDATE" in source_sql
    assert sqls.index(
        next(sql for sql in sqls if "FROM orbit_account_scope_snapshot" in sql)
    ) < sqls.index(source_sql)
    assert all(
        "LIMIT 1 FOR SHARE" in sql
        for sql in sqls
        if "SELECT rule_id FROM orbit_rule_scope_manifest" in sql
    )


async def test_source_uuid_collision_rejected_even_for_creator_before_member_scan(harness):
    session, _state = harness
    access, owner = await editor_source(harness)
    session.snapshot = dict(session.rule_snapshot)
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(
            session, access, SNAPSHOT, owner, target_rule_id=str(UUID(int=9000))
        )
    assert caught.value.code == "RULE_SCOPE_SOURCE_AMBIGUOUS"
    assert not any("FROM orbit_rule_editor_scope_member" in sql for sql, _ in session.events)


@pytest.mark.parametrize(
    "change",
    [
        "creator",
        "scope_generation",
        "owner_generation",
        "owner",
        "team",
        "intent_hash",
        "intent_column",
        "count",
        "member_hash",
    ],
)
async def test_editor_new_source_strict_context_and_full_members(harness, change):
    session, _state = harness
    access, owner = await editor_source(harness)
    row = session.rule_snapshot
    if change == "creator":
        row["actor_id"] = 2
    elif change == "scope_generation":
        row["scope_version"] += 1
    elif change == "owner_generation":
        row["owner_auth_fingerprint"] = "f" * 64
    elif change == "owner":
        row["owner_user_id"] = OTHER_USER
    elif change == "team":
        row["owner_team_id"] = OTHER_TEAM
    elif change == "intent_hash":
        row["request_hash"] = "0" * 64
    elif change == "intent_column":
        row["action"] = "UPDATE"
    elif change == "count":
        row["member_count"] += 1
    else:
        session.rows[-1]["name"] = "篡改历史"
    with pytest.raises(OrbitError):
        await capture_rule_scope(
            session, access, SNAPSHOT, owner, target_rule_id=str(UUID(int=9000))
        )


@pytest.mark.parametrize("bound", [True, False])
async def test_create_scope_cannot_move_to_other_rule_or_update_unbound_scope(harness, bound):
    session, _state = harness
    access, owner = await editor_source(harness)
    if bound:
        session.bound_rule_ids = [str(UUID(int=8000))]
    else:
        access, owner = await contexts(harness, "rules.edit")
    with pytest.raises(OrbitError):
        await capture_rule_scope(
            session, access, SNAPSHOT, owner, target_rule_id=str(UUID(int=9000))
        )


@pytest.mark.parametrize("wrong", ["target", "revision", "bool_revision", "missing_revision"])
async def test_update_scope_first_binding_exact_rule_and_revision(harness, wrong):
    session, _state = harness
    target = str(UUID(int=9000))
    access, owner = await editor_source(harness, action="UPDATE", rule_id=target, revision=1)
    actual_target = str(UUID(int=9001)) if wrong == "target" else target
    expected = {"target": 1, "revision": 2, "bool_revision": True, "missing_revision": None}[wrong]
    with pytest.raises(OrbitError):
        await capture_rule_scope(
            session, access, SNAPSHOT, owner, target_rule_id=actual_target, expected=expected
        )


async def test_update_first_binding_and_same_rule_historical_revision_reuse(harness):
    session, _state = harness
    target = str(UUID(int=9000))
    access, owner = await editor_source(harness, action="UPDATE", rule_id=target, revision=1)
    first = await capture_rule_scope(
        session, access, SNAPSHOT, owner, target_rule_id=target, expected=1
    )
    assert first.source_kind == "RULE"
    session.bound_rule_ids = [target]
    later = await capture_rule_scope(
        session, access, SNAPSHOT, owner, target_rule_id=target, expected=5
    )
    assert later.member_hash == first.member_hash and session.rule_snapshot["rule_revision"] == 1


async def test_reused_published_rule_allows_current_collaborator_not_private_creator(harness):
    session, _state = harness
    target = str(UUID(int=9000))
    access, _owner = await editor_source(harness)
    session.rule_snapshot["actor_id"] = 999
    session.rule_snapshot["scope_version"] = 99  # 历史creator版本不授当前权，也不阻止合法Rule协作。
    session.bound_rule_ids = [target]
    header = {
        "source_kind": "RULE",
        "rule_id": target,
        "member_count": 2,
        "source_snapshot_hash": session.rule_snapshot["members_hash"],
    }
    assert (
        await scope_core.verify_reused_scope_source(session, access, SNAPSHOT, header, target)
        == "RULE"
    )


@pytest.mark.parametrize(
    "field", ["source_kind", "rule_id", "member_count", "source_snapshot_hash"]
)
async def test_reused_rule_source_kind_binding_and_original_hash_cannot_drift(harness, field):
    session, _state = harness
    target = str(UUID(int=9000))
    access, _owner = await editor_source(harness)
    session.bound_rule_ids = [target]
    header = {
        "source_kind": "RULE",
        "rule_id": target,
        "member_count": 2,
        "source_snapshot_hash": session.rule_snapshot["members_hash"],
    }
    header[field] = 3 if field == "member_count" else "invalid"
    with pytest.raises(OrbitError):
        await scope_core.verify_reused_scope_source(session, access, SNAPSHOT, header, target)


async def test_scope_chunk_boundaries_and_current_locking_not_old_rr(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access, 2001)
    scope = await capture_rule_scope(session, access, SNAPSHOT, owner)
    reads = [sql for sql, _ in session.events if "FROM orbit_account_scope_member" in sql]
    assert len(reads) == 4  # 1000+1000+1+终止，非2001次逐户读取。
    assert all("LIMIT 1000 FOR SHARE OF m,a" in sql for sql in reads)
    assert len(scope.members) == 2001


async def test_profile_source_then_metric_clock_then_head_before_account(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access)
    metric(session)
    bound = await lock_rule_profile(session, access, owner, PROFILE)
    await capture_rule_scope(session, access, SNAPSHOT, owner)
    sqls = [sql for sql, _ in session.events]
    order = [
        next(i for i, sql in enumerate(sqls) if marker in sql)
        for marker in (
            "FROM orbit_system_configuration",
            "FROM orbit_metric_profile_clock",
            "AS head_revision",
            "ACCOUNT CLOCK",
            "FROM orbit_account_scope_member",
        )
    ]
    assert order == sorted(order)
    assert bound.version == "v1.00"
    assert b"123499" in bound.source_proof_json  # 不把原proof微秒舍入成DATETIME3。
    assert not any("adapter" in sql.lower() for sql in sqls)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("disabled_source", "METRIC_PROFILE_SOURCE_CHANGED"),
        ("changed_source", "METRIC_PROFILE_SOURCE_CHANGED"),
        ("changed_version", "METRIC_PROFILE_SOURCE_CHANGED"),
        ("disabled_head", "METRIC_PROFILE_UNAVAILABLE"),
        ("bad_hash", "RULE_METRIC_PROFILE_UNAVAILABLE"),
        ("bad_proof", "RULE_METRIC_PROFILE_UNAVAILABLE"),
        ("verified_false", "RULE_METRIC_PROFILE_UNAVAILABLE"),
    ],
)
async def test_profile_current_generation_corruption_failclosed_no_late_source_lock(
    harness, mutation, code
):
    session, _state = harness
    access, owner = await contexts(harness)
    metric(session)
    if mutation == "disabled_source":
        session.source["enabled"] = False
    elif mutation == "changed_source":
        session.profile["source_config_id"] = str(UUID(int=900))
    elif mutation == "changed_version":
        session.profile["current_version"] = "v2"
    elif mutation == "disabled_head":
        session.profile["state"] = "DISABLED"
    elif mutation == "bad_hash":
        session.profile["payload_hash"] = "b" * 64
    elif mutation == "bad_proof":
        session.profile["source_proof_json"]["source_sha256"] = "b" * 64
    else:
        session.profile["payload_json"]["verified"] = False
    with pytest.raises(OrbitError) as caught:
        await lock_rule_profile(session, access, owner, PROFILE)
    assert caught.value.code == code
    assert len([sql for sql, _ in session.events if "FROM orbit_system_configuration" in sql]) == 1


@pytest.mark.parametrize("source", ["META", "FIXTURE"])
async def test_profile_expected_exact_version_no_latest_rebind(harness, monkeypatch, source):
    session, _state = harness
    access, owner = await contexts(harness)
    metric(session, source=source)

    async def no_fixture_lock(_session):
        raise AssertionError("原精确版本不符时不应进入新来源分支")

    monkeypatch.setattr(profile_core, "fixture_boundary", no_fixture_lock)
    with pytest.raises(OrbitError) as caught:
        await lock_rule_profile(session, access, owner, PROFILE, expected_version="v0")
    assert caught.value.code == "METRIC_PROFILE_VERSION_CHANGED"
    assert not any(
        "FROM orbit_system_configuration" in sql or "FROM orbit_metric_profile_clock" in sql
        for sql, _ in session.events
    )


async def test_profile_fixture_requires_actual_uuid_db_boundary(harness, monkeypatch):
    session, _state = harness
    access, owner = await contexts(harness)
    metric(session, "FIXTURE")
    with pytest.raises(OrbitError):
        await lock_rule_profile(session, access, owner, PROFILE)
    called = []

    async def strict_boundary(s):
        called.append(s)

    monkeypatch.setattr(profile_core, "fixture_boundary", strict_boundary)
    binding = await lock_rule_profile(session, access, owner, PROFILE)
    assert binding.source == "FIXTURE" and called == [session]
    returned = binding.profile()
    returned["verified"] = False
    assert binding.profile()["verified"] is True


@pytest.mark.parametrize("mutation", ["auth_version", "managed", "disabled", "tenant", "team"])
async def test_owner_live_scope_revocation_checked_again_before_reference(harness, mutation):
    session, state = harness
    session.owner["data_role"] = "TEAM_ADMIN"
    state.managed[2] = [OTHER_TEAM]
    access, owner = await contexts(harness)
    members(session, access)
    if mutation == "auth_version":
        session.owner["auth_version"] = 2
    elif mutation == "managed":
        state.managed[2] = []
    elif mutation == "disabled":
        session.owner = None
    elif mutation == "tenant":
        session.owner["tenant_id"] = str(UUID(int=90))
    else:
        session.owner["team_id"] = OTHER_TEAM
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.code == "RULE_OWNER_SCOPE_CHANGED"
    assert not any("FROM orbit_account_scope_member" in sql for sql, _ in session.events)


async def test_owner_managed_read_and_caller_read_both_required(harness):
    session, state = harness
    session.owner["data_role"] = "TEAM_ADMIN"
    state.managed[2] = [OTHER_TEAM]
    access, owner = await contexts(harness)
    members(session, access)
    session.rows[-1].update(owner_user_id=OTHER_USER, owner_team_id=OTHER_TEAM)
    assert len((await capture_rule_scope(session, access, SNAPSHOT, owner)).members) == 2
    state.managed[2] = []
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.code == "RULE_OWNER_SCOPE_CHANGED"


async def test_50000_protocol_limit_never_truncates_or_demands_single_currency(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access, 50000)
    selected = await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert len(selected.members) == 50000
    assert selected.members[0].account_id == str(UUID(int=100))
    assert selected.members[-1].account_id == str(UUID(int=50099))
    assert {m.currency for m in selected.members} == {"USD", "EUR"}
    queries = [sql for sql, _ in session.events if "FROM orbit_account_scope_member" in sql]
    assert len(queries) == 51


async def test_runtime_manifest_not_original_creator_and_missing_current_account_rejects(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access)
    selected = await capture_rule_scope(session, access, SNAPSHOT, owner)
    session.events.clear()
    session.snapshot = None  # Rule后续消费专属manifest不再冒原creator读取snapshot。
    assert len(await revalidate_rule_members(session, access, owner, selected.members)) == 2
    assert not any("scope_snapshot" in sql for sql, _ in session.events)
    session.rows.pop()
    with pytest.raises(OrbitError) as caught:
        await revalidate_rule_members(session, access, owner, selected.members)
    assert caught.value.code == "RULE_ACCOUNT_SCOPE_CHANGED"


async def test_empty_scope_and_no_partial_outputs(harness):
    session, _state = harness
    access, owner = await contexts(harness)
    members(session, access, 0)
    with pytest.raises(OrbitError) as caught:
        await capture_rule_scope(session, access, SNAPSHOT, owner)
    assert caught.value.code == "RULE_ACCOUNT_LIMIT"


@pytest.mark.parametrize(
    "micros,projected",
    [
        (123499, datetime(2026, 11, 9, 0, 0, 0, 123000)),
        (123500, datetime(2026, 11, 9, 0, 0, 0, 124000)),
        (999999, datetime(2026, 11, 9, 0, 0, 1)),
    ],
)
async def test_metric_040_round_millisecond_not_055_floor(harness, micros, projected):
    session, _state = harness
    access, owner = await contexts(harness)
    metric(session)
    original = datetime(2026, 11, 9, 0, 0, 0, micros, tzinfo=UTC).isoformat()
    session.profile["source_proof_json"]["observed_at"] = original
    session.profile["observed_at"] = projected
    result = await lock_rule_profile(session, access, owner, PROFILE)
    assert original.encode() in result.source_proof_json
    clock_sql = next(sql for sql, _ in session.events if "FROM orbit_metric_profile_clock" in sql)
    assert "UTC_TIMESTAMP(3) AS now" in clock_sql


@pytest.mark.parametrize("mutation", ["future", "wrong_column", "raw_micros", "offset"])
async def test_metric_observed_independent_column_and_sql_future_reject(harness, mutation):
    session, _state = harness
    access, owner = await contexts(harness)
    metric(session)
    if mutation == "future":
        later = session.now + timedelta(seconds=1)
        session.profile["source_proof_json"]["observed_at"] = later.isoformat()
        session.profile["observed_at"] = later.replace(tzinfo=None)
    elif mutation == "wrong_column":
        session.profile["observed_at"] += timedelta(milliseconds=1)
    elif mutation == "raw_micros":
        session.profile["observed_at"] = datetime(2026, 11, 9, 0, 0, 0, 123499)
    else:
        session.profile["source_proof_json"]["observed_at"] = "2026-11-09T00:00:00.123499+08:00"
    with pytest.raises(OrbitError) as caught:
        await lock_rule_profile(session, access, owner, PROFILE)
    assert caught.value.code == "RULE_METRIC_PROFILE_UNAVAILABLE"
