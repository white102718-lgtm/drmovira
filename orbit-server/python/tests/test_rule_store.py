"""规则定义Store的事务协议纯测试；内存SQL替身不证明MySQL约束或回滚。"""

import copy
from dataclasses import replace
from pathlib import Path

import pytest
from test_rule_access_references import (
    OTHER_USER,
    PROFILE,
    SNAPSHOT,
    TEAM,
    TENANT,
    USER,
    editor_source,
    members,
    metric,
)
from test_rule_access_references import (
    harness as harness,
)
from test_rule_contract import ID, sample_rule

import orbit_api.account_access as account_core
import orbit_api.rule_access as access_core
import orbit_api.rule_scope_references as scope_core
import orbit_api.rule_store as core
from orbit_api.errors import OrbitError
from orbit_api.rule_store import RuleQuery, RuleStore, parse_rule_query


class Result:
    rowcount = 1

    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Tokens:
    def __init__(self):
        self.claims = {}

    def issue(self, purpose, claims):
        token = str(len(self.claims) + 1)
        self.claims[token] = (purpose, copy.deepcopy(claims))
        return token

    def verify(self, purpose, token):
        expected, claims = self.claims[token]
        assert expected == purpose
        return copy.deepcopy(claims)

    @staticmethod
    def session_binding(authorization, actor, tenant):
        return core.digest([authorization, actor, tenant])


@pytest.fixture
async def store_fixture(harness, monkeypatch):
    session, state = harness
    monkeypatch.setattr(account_core, "clock", scope_core.clock)
    base = session.execute
    session.rules = {}
    session.rule_versions = {}
    session.receipts = {}
    session.manifests = {}
    session.rule_members = {}
    session.operations = []
    session.rule_clock = 1
    metric(session)
    # 创建原私有范围的当前fingerprint，不授予任何accounts/monitor/launch动作。
    access = await access_core.authorize_rule(session, 1, "rules.create")
    members(session, access)
    state.permissions.clear()

    def full(head):
        return dict(head) | dict(session.rule_versions[(head["id"], head["revision"])])

    async def execute(statement, values=None):
        sql = str(statement)
        values = values or {}
        if "orbit_rule_" not in sql or "orbit_rule_editor_scope_" in sql:
            return await base(statement, values)
        session.operations.append((sql, copy.deepcopy(values)))
        if "SELECT rule_id FROM orbit_rule_scope_manifest" in sql:
            selected = [
                m
                for m in session.manifests.values()
                if m["source_kind"] == "RULE"
                and m["source_snapshot_id"] == values["id"]
                and (
                    m["rule_id"] != values["rule"]
                    if "rule_id<>:rule" in sql
                    else m["rule_id"] == values["rule"]
                )
            ]
            return Result([{"rule_id": m["rule_id"]} for m in selected[:1]])
        if "SELECT revision,UTC_TIMESTAMP" in sql:
            return Result([{"revision": session.rule_clock, "now": session.now}])
        if "SELECT id FROM orbit_rule_head" in sql:
            return Result(
                [
                    {"id": row["id"]}
                    for row in session.rules.values()
                    if row["id"] != values["id"]
                    and row["name"] == values["name"]
                    and row["state"] != "ARCHIVED"
                ][:1]
            )
        if "SELECT intent_hash,rule_id,response_json" in sql:
            key = (values["actor"], values["op"], values["key"])
            return Result([session.receipts[key]] if key in session.receipts else [])
        if "SELECT h.*" in sql:
            if "id" in values:
                row = session.rules.get(values["id"])
                return Result([full(row)] if row else [])
            rows = sorted(
                session.rules.values(), key=lambda r: (r["created_at"], r["id"]), reverse=True
            )
            if "after_id" in values:
                rows = [
                    r
                    for r in rows
                    if (r["created_at"], r["id"]) < (values["after_time"], values["after_id"])
                ]
            return Result(full(row) for row in rows[: values["limit"]])
        if "SELECT * FROM orbit_rule_scope_manifest" in sql:
            manifest = session.manifests.get(values["id"])
            return Result([manifest] if manifest and manifest["rule_id"] == values["rule"] else [])
        if "SELECT account_id,frozen_owner" in sql:
            return Result(
                [
                    row
                    for row in session.rule_members.get(values["id"], [])
                    if row["account_id"] > values["after"]
                ][:1000]
            )
        if sql.startswith("INSERT INTO orbit_rule_scope_manifest"):
            session.manifests[values["manifest"]] = {
                "id": values["manifest"],
                "rule_id": values["rule"],
                "source_kind": values["source_kind"],
                "source_snapshot_id": values["source"],
                "source_snapshot_hash": values["source_hash"],
                "member_count": values["count"],
                "member_ids_hash": values["hash"],
                "sealed": 0,
            }
        elif sql.startswith("INSERT INTO orbit_rule_scope_member"):
            for row in values:
                session.rule_members.setdefault(row["manifest"], []).append(
                    {
                        "account_id": row["account"],
                        "frozen_owner_user_id": row["owner"],
                        "frozen_owner_team_id": row["team"],
                        "frozen_currency": row["currency"],
                        "frozen_revision": row["revision"],
                    }
                )
        elif sql.startswith("UPDATE orbit_rule_scope_manifest"):
            session.manifests[values["manifest"]]["sealed"] = 1
        elif sql.startswith("INSERT INTO orbit_rule_version"):
            session.rule_versions[(values["id"], values["revision"])] = {
                "payload_json": values["payload"],
                "payload_hash": values["hash"],
                "metric_profile_version": values["profile_version"],
                "metric_profile_hash": values["profile_hash"],
                "profile_proof_hash": values["proof_hash"],
            }
        elif sql.startswith(("INSERT INTO orbit_rule_head", "UPDATE orbit_rule_head")):
            previous = session.rules.get(values["id"])
            if previous and previous["revision"] != values["old_revision"]:
                result = Result()
                result.rowcount = 0
                return result
            session.rules[values["id"]] = {
                "tenant_id": TENANT,
                "id": values["id"],
                "revision": values["revision"],
                "name": values["name"],
                "owner_user_id": values["owner"],
                "owner_team_id": values["team"],
                "target_level": values["target"],
                "metric_profile_id": values["profile"],
                "manifest_id": values["manifest"],
                "state": values["state"],
                "next_run_at": None,
                "created_at": previous["created_at"]
                if previous
                else session.now.replace(tzinfo=None),
            }
        elif sql.startswith("INSERT INTO orbit_rule_idempotency"):
            key = (values["actor"], values["op"], values["key"])
            session.receipts.setdefault(
                key,
                {
                    "intent_hash": values["hash"],
                    "rule_id": values["id"],
                    "response_json": values["body"],
                },
            )
        elif sql.startswith("UPDATE orbit_rule_clock"):
            session.rule_clock += 1
        elif not sql.startswith(("INSERT INTO orbit_rule_event", "INSERT INTO orbit_rule_outbox")):
            raise AssertionError("未覆盖规则SQL协议")
        return Result()

    session.execute = execute
    store = RuleStore(Tokens())
    monkeypatch.setattr(store, "_csrf", lambda *args: None)
    body = sample_rule()
    body.update(
        ownership={"owner_user_id": USER, "owner_team_id": TEAM},
        metric_profile_id=PROFILE,
        scope_snapshot_id=SNAPSHOT,
    )
    return session, state, store, body


async def create(fixture, *, key="RULE_CREATE_KEY_001", body=None):
    session, _state, store, value = fixture
    return await store.save(session, 1, "auth", "csrf", key, body or value, None, None, ID)


async def test_create_complete_original_dto_and_transaction_order(store_fixture):
    session, state, _store, _body = store_fixture
    result = await create(store_fixture)
    assert len(result) == 15 and result["state"] == "DRAFT" and result["revision"] == 1
    assert result["next_run_at"] is None
    assert set(state.permissions) == {"rules.create"}
    sqls = [sql for sql, _ in session.operations]
    positions = [
        next(i for i, sql in enumerate(sqls) if marker in sql)
        for marker in (
            "INSERT INTO orbit_rule_scope_manifest",
            "INSERT INTO orbit_rule_scope_member",
            "UPDATE orbit_rule_scope_manifest",
            "INSERT INTO orbit_rule_event",
            "INSERT INTO orbit_rule_version",
            "INSERT INTO orbit_rule_head",
            "INSERT INTO orbit_rule_outbox",
            "INSERT INTO orbit_rule_idempotency",
        )
    ]
    assert positions == sorted(positions)
    assert len(session.rules) == len(session.rule_versions) == len(session.receipts) == 1


async def test_rule_editor_create_scope_target_generated_once_and_cannot_move(store_fixture):
    session, state, store, body = store_fixture
    await editor_source((session, state))
    original = await create(store_fixture)
    header = session.manifests[session.rules[original["id"]]["manifest_id"]]
    assert header["source_kind"] == "RULE" and header["rule_id"] == original["id"]
    assert len(original) == 15 and "source_kind" not in original
    before = (len(session.rules), len(session.manifests), len(session.rule_versions))
    with pytest.raises(OrbitError) as caught:
        await create(store_fixture, key="RULE_CREATE_OTHER_01", body=body | {"name": "另一个规则"})
    assert caught.value.code == "RULE_SCOPE_ALREADY_BOUND"
    assert (len(session.rules), len(session.manifests), len(session.rule_versions)) == before


async def test_same_rule_public_manifest_collaborative_reuse_does_not_read_private_scope(
    store_fixture,
):
    session, state, store, body = store_fixture
    await editor_source((session, state))
    original = await create(store_fixture)
    manifest = session.rules[original["id"]]["manifest_id"]
    session.rule_snapshot["actor_id"] = 999
    session.rule_snapshot["scope_version"] = 99
    updated = await store.save(
        session,
        1,
        "auth",
        "csrf",
        "RULE_EDITOR_REUSE_01",
        body | {"name": "当前协作编辑"},
        original["id"],
        1,
        ID,
    )
    assert updated["revision"] == 2
    assert session.rules[original["id"]]["manifest_id"] == manifest and len(session.manifests) == 1
    assert set(state.permissions) <= {"rules.create", "rules.edit"}


async def test_same_scope_reuse_cannot_hide_new_dual_source_collision(store_fixture):
    session, state, store, body = store_fixture
    await editor_source((session, state))
    original = await create(store_fixture)
    session.snapshot = dict(session.rule_snapshot)
    before = len(session.rule_versions)
    with pytest.raises(OrbitError) as caught:
        await store.save(
            session,
            1,
            "auth",
            "csrf",
            "RULE_EDITOR_REUSE_02",
            body | {"name": "碰撞"},
            original["id"],
            1,
            ID,
        )
    assert caught.value.code == "RULE_SCOPE_SOURCE_AMBIGUOUS"
    assert len(session.rule_versions) == before


@pytest.mark.parametrize("source_revision,expected_success", [(1, True), (2, False)])
async def test_new_update_scope_first_binding_uses_actual_rule_cas(
    store_fixture, source_revision, expected_success
):
    from uuid import UUID

    session, state, store, body = store_fixture
    original = await create(store_fixture)
    old_snapshot = session.snapshot
    await editor_source(
        (session, state), action="UPDATE", rule_id=original["id"], revision=source_revision
    )
    source_id = str(UUID(int=9010))
    session.rule_snapshot["id"] = source_id
    session.snapshot = old_snapshot
    new_body = body | {"scope_snapshot_id": source_id, "name": "UPDATE新冻结"}
    if expected_success:
        saved = await store.save(
            session, 1, "auth", "csrf", "RULE_EDITOR_UPDATE_01", new_body, original["id"], 1, ID
        )
        assert saved["revision"] == 2
        header = session.manifests[session.rules[saved["id"]]["manifest_id"]]
        assert header["source_kind"] == "RULE" and header["source_snapshot_id"] == source_id
    else:
        with pytest.raises(OrbitError) as caught:
            await store.save(
                session, 1, "auth", "csrf", "RULE_EDITOR_UPDATE_01", new_body, original["id"], 1, ID
            )
        assert caught.value.status == 409 and len(session.rule_versions) == 1


async def test_update_noop_then_changed_body_reuses_manifest_and_original_creation_time(
    store_fixture,
):
    session, _state, store, body = store_fixture
    original = await create(store_fixture)
    manifest = session.rules[original["id"]]["manifest_id"]
    noop = await store.save(
        session, 1, "auth", "csrf", "RULE_UPDATE_KEY_001", body, original["id"], 1, ID
    )
    assert noop == original and len(session.rule_versions) == 1
    updated = await store.save(
        session,
        1,
        "auth",
        "csrf",
        "RULE_UPDATE_KEY_002",
        body | {"name": "第二版"},
        original["id"],
        1,
        ID,
    )
    assert updated["revision"] == 2 and updated["name"] == "第二版"
    assert session.rules[original["id"]]["manifest_id"] == manifest
    assert len(session.manifests) == 1 and len(session.rule_versions) == 2


async def test_old_success_replay_current_original_action_before_old_cas_and_disabled_source(
    store_fixture,
):
    session, state, store, body = store_fixture
    original = await create(store_fixture)
    await store.save(
        session,
        1,
        "auth",
        "csrf",
        "RULE_UPDATE_KEY_002",
        body | {"name": "新名称"},
        original["id"],
        1,
        ID,
    )
    session.source["enabled"] = False
    before = len(session.operations)
    state.permissions.clear()
    replayed = await create(store_fixture)
    assert replayed == original
    assert set(state.permissions) == {"rules.create"}
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in session.operations[before:])


async def test_same_key_changed_intent_conflict_and_current_scope_not_history_exception(
    store_fixture,
):
    session, state, _store, body = store_fixture
    original = await create(store_fixture)
    with pytest.raises(OrbitError) as caught:
        await create(store_fixture, body=body | {"name": "冲突"})
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"
    state.current = replace(state.current, data_role="USER")
    session.rules[original["id"]]["owner_user_id"] = OTHER_USER
    with pytest.raises(OrbitError) as caught:
        await create(store_fixture, body=body | {"name": "冲突"})
    assert caught.value.status == 404


async def test_original_action_revoke_cannot_be_replaced_by_read_for_replay(
    store_fixture, monkeypatch
):
    session, state, _store, _body = store_fixture
    await create(store_fixture)

    async def only_read(_s, _actor, menu, permission):
        assert menu == "rules"
        if permission != "rules.read":
            raise OrbitError(403, "PERMISSION_DENIED", "撤回原动作")
        return state.current

    monkeypatch.setattr(access_core, "require_business_access", only_read)
    with pytest.raises(OrbitError) as caught:
        await create(store_fixture)
    assert caught.value.status == 403
    assert len(session.rules) == 1


async def test_final_concurrent_fallback_preempts_changed_source_error(store_fixture, monkeypatch):
    session, _state, store, _body = store_fixture
    original = await create(store_fixture)
    session.source["enabled"] = False
    real = store._receipt
    count = 0

    async def missed_first(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return None
        return await real(*args, **kwargs)

    monkeypatch.setattr(store, "_receipt", missed_first)
    assert await create(store_fixture) == original
    assert count == 2 and len(session.rules) == 1


async def test_archive_and_pause_do_not_call_source_or_owner_readiness(store_fixture):
    session, state, store, body = store_fixture
    original = await create(store_fixture)
    session.source["enabled"] = False
    session.owner = None
    session.events.clear()
    archived = await store.stop(
        session,
        1,
        "auth",
        "csrf",
        "RULE_ARCHIVE_KEY01",
        original["id"],
        1,
        "停用来源后仍可归档",
        ID,
        archive=True,
    )
    assert archived["state"] == "ARCHIVED" and archived["revision"] == 2
    assert not any(
        "orbit_metric_profile" in sql or "orbit_business_user" in sql for sql, _ in session.events
    )
    # ENABLED仅在协议替身中构造，绝不称真实enable通过。
    session.rules[original["id"]]["state"] = "ENABLED"
    state.permissions.clear()
    paused = await store.stop(
        session, 1, "auth", "csrf", "RULE_PAUSE_KEY_001", original["id"], 2, "暂停", ID
    )
    assert paused["state"] == "PAUSED" and paused["revision"] == 3
    assert set(state.permissions) == {"rules.pause"}
    assert paused["metric_profile_id"] == body["metric_profile_id"]


async def test_cas_failure_and_enabled_edit_have_zero_version_writes(store_fixture):
    session, _state, store, body = store_fixture
    original = await create(store_fixture)
    with pytest.raises(OrbitError) as caught:
        await store.save(
            session, 1, "auth", "csrf", "RULE_UPDATE_KEY_001", body, original["id"], 2, ID
        )
    assert caught.value.code == "REVISION_CONFLICT"
    session.rules[original["id"]]["state"] = "ENABLED"
    with pytest.raises(OrbitError) as caught:
        await store.save(
            session, 1, "auth", "csrf", "RULE_UPDATE_KEY_002", body, original["id"], 1, ID
        )
    assert caught.value.code == "RULE_STATE_CONFLICT" and len(session.rule_versions) == 1


async def test_no_provider_enable_simulate_runs_explicit_unavailable_no_success(store_fixture):
    session, _state, store, _body = store_fixture
    original = await create(store_fixture)
    before = len(session.operations)
    for invocation, expected in [
        (
            store.enable(
                session, 1, "auth", "csrf", "RULE_ENABLE_KEY01", original["id"], 1, ID, ID
            ),
            "RULE_SIMULATION_SOURCE_UNAVAILABLE",
        ),
        (
            store.simulate(session, 1, "auth", "csrf", "RULE_SIMULATE_KEY1", original["id"], 1, ID),
            "RULE_SIMULATION_SOURCE_UNAVAILABLE",
        ),
        (store.runs(session, 1, original["id"]), "RULE_RUN_STORE_UNAVAILABLE"),
    ]:
        with pytest.raises(OrbitError) as caught:
            await invocation
        assert caught.value.status == 503 and caught.value.code == expected
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in session.operations[before:])


@pytest.mark.parametrize(
    "values,pointer",
    [
        ({"status": "RUNNING"}, "/status"),
        ({"entity_type": "ACCOUNT"}, "/entity_type"),
        ({"page_size": 500}, "/page_size"),
        ({"date_from": "2026-02-30"}, "/date_from"),
        ({"channel_id": "invalid"}, "/channel_id"),
        ({"operator_user_id": "native-1"}, "/operator_user_id"),
    ],
)
def test_query_boundary_and_unimplemented_semantics_explicit(values, pointer):
    with pytest.raises(OrbitError) as caught:
        parse_rule_query(values)
    assert caught.value.code == "FIELD_VALIDATION_FAILED" and caught.value.pointer == pointer


async def test_literal_contains_query_escapes_and_no_prefix_substitution(store_fixture):
    session, _state, store, _body = store_fixture
    await create(store_fixture)
    await store.list(session, 1, parse_rule_query({"q": "a%_!b"}))
    sql, values = next(
        (sql, values) for sql, values in reversed(session.operations) if "SELECT h.*" in sql
    )
    assert "h.name LIKE :search ESCAPE '!'" in sql
    assert values["search"] == "%a!%!_!!b%"


@pytest.mark.parametrize("unit", ["a", "中", "😀"])
def test_rule_search_original_one_hundred_character_limit(unit):
    assert parse_rule_query({"q": unit * 100}).q == unit * 100
    with pytest.raises(OrbitError) as caught:
        parse_rule_query({"q": unit * 101})
    assert caught.value.status == 422
    assert caught.value.pointer == "/q"


async def test_cursor_keyset_scope_binding_and_current_watermark(store_fixture):
    session, _state, store, body = store_fixture
    for n in range(21):
        await create(
            store_fixture, key=f"RULE_CREATE_KEY_{n:03d}", body=body | {"name": f"规则{n}"}
        )
    page = await store.list(session, 1, RuleQuery(page_size=20))
    assert len(page["items"]) == 20 and page["next_cursor"]
    second = await store.list(session, 1, RuleQuery(page_size=20, cursor=page["next_cursor"]))
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert not set(r["id"] for r in page["items"]) & set(r["id"] for r in second["items"])
    assert page["data_as_of"] == second["data_as_of"]
    session.rule_clock += 1
    with pytest.raises(OrbitError) as caught:
        await store.list(session, 1, RuleQuery(page_size=20, cursor=page["next_cursor"]))
    assert caught.value.code == "RULE_CURSOR_STALE"


def test_csrf_token_error_is403_not_generic400():
    store = RuleStore(Tokens())

    class BadTokens:
        def verify(self, *_args):
            raise OrbitError(400, "TOKEN_INVALID", "坏令牌")

    store.tokens = BadTokens()
    with pytest.raises(OrbitError) as caught:
        store._csrf(type("Access", (), {"current": None})(), "auth", "bad")
    assert caught.value.status == 403 and caught.value.code == "CSRF_INVALID"


def test_candidate_only_original_name_evidence_and_immutable_fk_chain():
    sql = (
        Path(__file__).parents[2] / "docs/orbit/sql-drafts/057_rules_definitions_candidate.sql"
    ).read_text(encoding="utf8")
    assert sql.count("CREATE TABLE ") == 8 and sql.count("CREATE TRIGGER ") == 18
    assert "FIELDS.md:572" in sql and "uq_rule_active_name(tenant_id,active_name)" in sql
    assert "FOREIGN KEY(tenant_id,rule_id,manifest_id)" in sql
    assert "RULE_MANIFEST_COUNT_MISMATCH" in sql and "RULE_HEAD_VERSION_MISMATCH" in sql
    assert "DELIMITER" not in sql


def test_query_unknown_pointer_and_extreme_numeric_input_fail_safely():
    with pytest.raises(OrbitError) as caught:
        parse_rule_query({"bad~/key": "private"})
    assert caught.value.status == 400 and caught.value.pointer == "/bad~0~1key"
    with pytest.raises(OrbitError) as caught:
        parse_rule_query({"page_size": "9" * 10000})
    assert caught.value.status == 422
    with pytest.raises(OrbitError) as caught:
        parse_rule_query([])
    assert caught.value.status == 400


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", True),
        ("after_time", None),
        ("as_of", "2026-01-01"),
        ("after_id", "not-uuid"),
        ("after_time", "2026-01-01T00:00:00+08:00"),
    ],
)
async def test_signed_but_malformed_cursor_claims_failclosed(store_fixture, field, value):
    session, _state, store, body = store_fixture
    for n in range(21):
        await create(
            store_fixture, key=f"RULE_CURSOR_KEY_{n:03d}", body=body | {"name": f"规则{n}"}
        )
    first = await store.list(session, 1, RuleQuery(page_size=20))
    token = first["next_cursor"]
    purpose, claims = store.tokens.claims[token]
    claims[field] = value
    store.tokens.claims[token] = purpose, claims
    with pytest.raises(OrbitError) as caught:
        await store.list(session, 1, RuleQuery(page_size=20, cursor=token))
    assert caught.value.status == 400 and caught.value.code == "TOKEN_INVALID"


@pytest.mark.parametrize(
    "action,permission", list(core.PERMISSIONS.items()) + [("SIMULATE", "rules.read")]
)
async def test_capabilities_exact_original_action_no_other_menu(store_fixture, action, permission):
    _session, state, store, _body = store_fixture
    session = store_fixture[0]
    result = await store.capabilities(session, 1, "auth", action)
    assert set(result) == {"csrf_token"}
    purpose, claims = store.tokens.claims[result["csrf_token"]]
    assert purpose == "DIRECTORY_CSRF_V1"
    assert claims["binding"] == store.tokens.session_binding("auth", 1, TENANT)
    assert state.permissions[-1] == permission


async def test_source_error_deferred_until_actual_current_object_scope(store_fixture, monkeypatch):
    session, state, store, body = store_fixture
    original = await create(store_fixture)
    state.current = replace(state.current, data_role="USER")

    async def failed_source(*_args, **_kwargs):
        session.rules[original["id"]]["owner_user_id"] = OTHER_USER
        raise OrbitError(503, "RULE_METRIC_PROFILE_UNAVAILABLE", "来源不可用")

    monkeypatch.setattr(core, "lock_rule_profile", failed_source)
    with pytest.raises(OrbitError) as caught:
        await store.save(
            session, 1, "auth", "csrf", "RULE_DEFER_SCOPE01", body, original["id"], 1, ID
        )
    assert caught.value.status == 404
    assert len(session.rule_versions) == 1


async def test_name_conflict_before_any_manifest_event_and_archive_releases_name(store_fixture):
    session, _state, store, body = store_fixture
    original = await create(store_fixture)
    counts = (
        len(session.rules),
        len(session.manifests),
        len(session.rule_versions),
        len(session.receipts),
    )
    before = len(session.operations)
    with pytest.raises(OrbitError) as caught:
        await create(store_fixture, key="RULE_DUPLICATE_KEY1")
    assert caught.value.code == "RULE_NAME_CONFLICT" and caught.value.pointer == "/name"
    assert counts == (
        len(session.rules),
        len(session.manifests),
        len(session.rule_versions),
        len(session.receipts),
    )
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in session.operations[before:])
    await store.stop(
        session,
        1,
        "auth",
        "csrf",
        "RULE_ARCHIVE_KEY01",
        original["id"],
        1,
        "归档释放名称",
        ID,
        archive=True,
    )
    replacement = await create(store_fixture, key="RULE_DUPLICATE_KEY2")
    assert replacement["name"] == body["name"] and replacement["id"] != original["id"]
