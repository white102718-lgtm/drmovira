"""独立scope合同/真实RowMapping纯适配测试；不替代SQL/HTTP或50k容量。"""

import copy
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData

import orbit_api.rule_editor_scope_store as core
from orbit_api.account_scope_contract import MAX_BODY
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_editor_scope_contract import (
    ScopeContext,
    parse_scope_query,
    parse_scope_write,
)
from orbit_api.scope_selection_engine import FrozenMemberRoot


def uid(n):
    return str(UUID(int=n))


def body(**changes):
    result = {
        "action": "CREATE",
        "rule_id": None,
        "ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)},
        "selection": {"mode": "IDS", "account_ids": [uid(10)], "filter": None},
    }
    return result | changes


@pytest.mark.parametrize(
    "change",
    [
        {"previous": {}},
        {"action": "EDIT"},
        {"action": "UPDATE"},
        {"rule_id": uid(4)},
        {"ownership": {"owner_user_id": uid(2)}},
        {"selection": {"mode": "IDS", "account_ids": [uid(10), uid(10)], "filter": None}},
        {"selection": {"mode": "IDS", "account_ids": [], "filter": None}},
        {"selection": {"mode": "IDS", "account_ids": [uid(10)], "filter": {}}},
        {"selection": {"mode": "FILTER", "account_ids": [], "filter": {"q": "x"}}},
    ],
)
def test_strict_write_no_previous_or_partial_filter(change):
    with pytest.raises(OrbitError):
        parse_scope_write(canonical(body(**change)).encode())


def test_write_duplicate_key_and_bounded_raw_and_full_normalized_intent():
    with pytest.raises(OrbitError):
        parse_scope_write(b'{"action":"CREATE","action":"UPDATE"}')
    with pytest.raises(OrbitError) as caught:
        parse_scope_write(b" " * (MAX_BODY + 1))
    assert caught.value.status == 413
    request = body(selection={"mode": "IDS", "account_ids": [uid(11), uid(10)], "filter": None})
    parsed = parse_scope_write(canonical(request).encode())
    assert parsed.selection.account_ids == (uid(10), uid(11))
    assert json.loads(parsed.canonical)["selection"]["account_ids"] == [uid(10), uid(11)]
    assert parsed.context.ownership == request["ownership"]


@pytest.mark.parametrize("size", [20, 50, 100, 200, "20", "50", "100", "200"])
def test_candidate_four_sizes_and_no_borrowed_metrics_filter(size):
    q = parse_scope_query(
        {"action": "CREATE", "owner_user_id": uid(2), "owner_team_id": uid(3), "page_size": size}
    )
    assert q.page_size == int(size)
    assert parse_scope_query({"page_size": size}, members=True).context is None


@pytest.mark.parametrize(
    "values",
    [
        {"page_size": True},
        {"page_size": 500},
        {"page_size": "020"},
        {"cursor": ""},
        {"cursor": "x" * 2049},
        {"date_from": "2026-01-01"},
        {"scope": "all"},
        {"previous": {}},
    ],
)
def test_member_query_strict(values):
    with pytest.raises(OrbitError):
        parse_scope_query(values, members=True)


def member(n, *, currency="USD"):
    return {
        "account_id": uid(n),
        "external_id": "00" + str(n),
        "name": "完整😀账户" + str(n),
        "name_prefix": "完整😀账户",
        "account_revision": 1,
        "owner_user_id": uid(2),
        "owner_team_id": uid(3),
        "currency": currency,
    }


def test_seven_field_root_preserves_unicode_leading_zero_null_and_chunk_order():
    root = FrozenMemberRoot()
    items = [member(10), member(11, currency=None)]
    for row in items:
        root.add(row)
    expected = [
        [
            r[k]
            for k in (
                "account_id",
                "external_id",
                "name",
                "account_revision",
                "owner_user_id",
                "owner_team_id",
                "currency",
            )
        ]
        for r in items
    ]
    assert root.hexdigest() == hashlib.sha256(canonical(expected).encode()).hexdigest()
    assert root.count == 2 and root.after == uid(11)
    assert root.hexdigest() == root.hexdigest()  # 读取摘要不封死/破坏内部hash。


@pytest.mark.parametrize(
    "change",
    [
        {"account_revision": True},
        {"account_revision": 0},
        {"currency": "usd"},
        {"currency": 123},
        {"external_id": "act_10"},
        {"external_id": "１２"},
        {"owner_user_id": "bad"},
        {"name": None},
    ],
)
def test_hash_rejects_corrupt_frozen_values(change):
    with pytest.raises(OrbitError):
        FrozenMemberRoot().add(member(10) | change)


def test_hash_rejects_order_duplicate_and_50001_without_truncation():
    root = FrozenMemberRoot()
    root.add(member(10))
    with pytest.raises(OrbitError):
        root.add(member(10))
    root.count = 50000
    with pytest.raises(OrbitError) as caught:
        root.add(member(11))
    assert caught.value.status == 422


def result(found):
    keys = tuple(found[0]) if found else ()
    return IteratorResult(
        SimpleResultMetaData(keys), iter(tuple(r[k] for k in keys) for r in found)
    )


class Tokens:
    def session_binding(self, auth, actor, tenant):
        return [auth, actor, tenant]

    def issue(self, purpose, value):
        return canonical({"purpose": purpose, "value": value})

    def verify(self, purpose, token):
        value = json.loads(token)
        assert value["purpose"] == purpose
        return value["value"]


@pytest.fixture
def setup(monkeypatch):
    access = SimpleNamespace(
        current=SimpleNamespace(
            actor_id=1, tenant_id=uid(1), subject_id=uid(2), team_id=uid(3), data_role="USER"
        ),
        auth_version=1,
        auth_fingerprint="a" * 64,
        managed_team_ids=(),
    )
    owner = SimpleNamespace(
        current=access.current, auth_version=1, auth_fingerprint="b" * 64, managed_team_ids=()
    )
    store = core.RuleEditorScopeStore(Tokens())
    store._begin = AsyncMock(return_value=(access, owner, None))
    store._finish = AsyncMock()
    store._watermark = AsyncMock(return_value=(1, "2026-11-09T00:00:00.000Z"))
    monkeypatch.setattr(core, "verify_csrf", lambda *a: None)
    monkeypatch.setattr(core, "transaction", lambda session: object())
    return store, access, owner


class Session:
    def __init__(self, members):
        self.members, self.snapshot, self.sql = members, None, []
        self.fail_outbox = False

    async def execute(self, statement, values):
        sql = " ".join(str(statement).split())
        self.sql.append((sql, values))
        if sql.startswith("SELECT * FROM orbit_rule_editor_scope_snapshot"):
            return result([copy.deepcopy(self.snapshot)] if self.snapshot else [])
        if sql.startswith("INSERT INTO orbit_rule_editor_scope_snapshot"):
            p = values
            self.snapshot = {
                "tenant_id": p["tenant"],
                "id": p["id"],
                "actor_id": p["actor"],
                "action": p["action"],
                "rule_id": p["rule"],
                "rule_revision": p["rule_revision"],
                "owner_user_id": p["owner"],
                "owner_team_id": p["team"],
                "scope_version": p["scope"],
                "auth_fingerprint": p["auth"],
                "owner_auth_fingerprint": p["owner_auth"],
                "request_json": p["body"],
                "request_hash": p["hash"],
                "member_count": 0,
                "ready": 0,
                "members_hash": None,
                "created_at": datetime(2026, 11, 9),
            }
        elif sql.startswith("SELECT a.id AS account_id"):
            data = [r for r in self.members if r["account_id"] > values.get("after", "")]
            if "ids" in values:
                data = [r for r in data if r["account_id"] in values["ids"]]
            return result(data[: values["limit"]])
        elif sql.startswith("SELECT m.*"):
            data = [
                r
                | {
                    "current_id": r["account_id"],
                    "current_owner": r["owner_user_id"],
                    "current_team": r["owner_team_id"],
                }
                for r in self.members
                if r["account_id"] > values["after"]
            ]
            return result(data[:1000])
        elif sql.startswith("UPDATE orbit_rule_editor_scope_snapshot"):
            self.snapshot.update(ready=1, member_count=values["count"], members_hash=values["root"])
        elif sql.startswith("INSERT INTO orbit_rule_editor_scope_outbox") and self.fail_outbox:
            raise RuntimeError("PURE_OUTBOX_FAILURE")
        return result([])


@pytest.mark.asyncio
async def test_scope_create_batches_real_mapping_and_original_five_fields(setup):
    store, access, _owner = setup
    data = [member(n) for n in range(10, 1011)]
    session = Session(data)
    value = parse_scope_write(
        canonical(
            body(
                selection={
                    "mode": "IDS",
                    "account_ids": [r["account_id"] for r in data],
                    "filter": None,
                }
            )
        ).encode()
    )
    response = await store.create(session, 1, "session", "csrf", "key", value, None, uid(10000))
    assert set(response) == {"id", "count", "scope_version", "hash", "created_at"}
    assert response["count"] == 1001 and response["scope_version"] == access.auth_version
    batches = [
        p for sql, p in session.sql if sql.startswith("INSERT INTO orbit_rule_editor_scope_member")
    ]
    assert [len(p) for p in batches] == [1000, 1]
    reads = [p for sql, p in session.sql if sql.startswith("SELECT a.id")]
    assert [len(p["ids"]) for p in reads] == [1000, 1]
    names = [sql.split()[2] for sql, _ in session.sql if sql.startswith("INSERT")]
    assert names[-2:] == [
        "orbit_rule_editor_scope_event(tenant_id,id,snapshot_id,actor_id,request_id,member_count,members_hash)",
        "orbit_rule_editor_scope_outbox(tenant_id,event_id,snapshot_id)",
    ]
    frozen = json.loads(session.snapshot["request_json"])
    assert frozen["rule_revision"] is None
    assert set(frozen) == {"action", "rule_id", "rule_revision", "ownership", "selection"}


@pytest.mark.asyncio
async def test_same_key_reads_original_receipt_no_dml_and_different_body_conflicts(setup):
    store, _access, _owner = setup
    session = Session([member(10)])
    value = parse_scope_write(canonical(body()).encode())
    original = await store.create(session, 1, "session", "csrf", "key", value, None, uid(10000))
    session.sql.clear()
    assert (
        await store.create(session, 1, "session", "csrf", "key", value, None, uid(10001))
        == original
    )
    assert all(sql.startswith("SELECT") for sql, _ in session.sql)
    other = parse_scope_write(
        canonical(
            body(selection={"mode": "IDS", "account_ids": [uid(11)], "filter": None})
        ).encode()
    )
    with pytest.raises(OrbitError) as caught:
        await store.create(session, 1, "session", "csrf", "key", other, None, uid(10002))
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_missing_ids_not_partial_and_outbox_failure_propagates(setup):
    store, _access, _owner = setup
    with pytest.raises(OrbitError) as caught:
        await store.create(
            Session([]),
            1,
            "s",
            "c",
            "k",
            parse_scope_write(canonical(body()).encode()),
            None,
            uid(10000),
        )
    assert caught.value.status == 404
    session = Session([member(10)])
    session.fail_outbox = True
    with pytest.raises(RuntimeError, match="^PURE_OUTBOX_FAILURE$"):
        await store.create(
            session,
            1,
            "s",
            "c",
            "k",
            parse_scope_write(canonical(body()).encode()),
            None,
            uid(10000),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "ready",
        "scope_version",
        "auth_fingerprint",
        "owner_auth_fingerprint",
        "members_hash",
        "member_count",
        "actor_id",
    ],
)
async def test_whole_snapshot_replay_revalidates_both_scope_and_full_root(setup, field):
    store, _access, _owner = setup
    session = Session([member(10)])
    value = parse_scope_write(canonical(body()).encode())
    await store.create(session, 1, "s", "c", "k", value, None, uid(10000))
    session.snapshot[field] = 0 if isinstance(session.snapshot[field], int) else "f" * 64
    with pytest.raises(OrbitError):
        await store.create(session, 1, "s", "c", "k", value, None, uid(10000))


def test_visibility_predicates_never_override_each_others_identity():
    current = SimpleNamespace(subject_id=uid(1), data_role="TEAM_ADMIN")
    left, lparams = core.visibility(current, (uid(2),), "caller")
    right, rparams = core.visibility(current, (uid(3),), "owner")
    assert not set(lparams) & set(rparams)
    assert "caller_team_0" in left and "owner_team_0" in right
    with pytest.raises(ValueError):
        core.visibility(current, (), "a;DROP")


def test_scope_cursor_domain_filter_session_and_size_binding(setup):
    store, access, owner = setup
    query = parse_scope_query(
        {"action": "CREATE", "owner_user_id": uid(2), "owner_team_id": uid(3)}
    )
    binding = store._binding("session", access, owner, None, query, 1, None)
    for auth, version in [("other", 1), ("session", 2)]:
        assert store._binding(auth, access, owner, None, query, version, None) != binding
    payload = {
        "domain": "RULE_EDITOR_ACCOUNTS_V1",
        "binding": binding,
        "after": uid(10),
        "as_of": "2026-11-09T00:00:00.000Z",
    }
    from dataclasses import replace

    cursor = replace(query, cursor=store.tokens.issue(core.PURPOSE, payload))
    assert store._cursor(cursor, binding, domain="RULE_EDITOR_ACCOUNTS_V1")[0] == uid(10)
    with pytest.raises(OrbitError):
        store._cursor(cursor, binding, domain="RULE_EDITOR_SCOPE_MEMBERS_V1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,permission", [("CREATE", "rules.create"), ("UPDATE", "rules.edit")]
)
async def test_real_begin_selects_only_original_action_and_server_previous(
    setup, monkeypatch, action, permission
):
    store, access, owner = setup
    current = {"id": uid(100), "state": "DRAFT", "revision": 2}
    authorize = AsyncMock(return_value=access)
    ownership = AsyncMock(return_value=owner)
    monkeypatch.setattr(core, "authorize_rule", authorize)
    monkeypatch.setattr(core, "owner_scope", ownership)
    store._rule = AsyncMock(return_value=current)
    context = ScopeContext(action, uid(100) if action == "UPDATE" else None, uid(2), uid(3))
    session = object()
    actual = await core.RuleEditorScopeStore._begin(store, session, 1, context)
    assert actual == (access, owner, current if action == "UPDATE" else None)
    authorize.assert_awaited_once_with(session, 1, permission)
    ownership.assert_awaited_once_with(
        session,
        access,
        context.ownership,
        for_write=True,
        previous=current if action == "UPDATE" else None,
    )


@pytest.mark.asyncio
async def test_historical_members_context_survives_rule_revision_and_state_but_not_new_freeze(
    setup, monkeypatch
):
    store, access, owner = setup
    current = {"id": uid(100), "state": "ENABLED", "revision": 3}
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(return_value=access))
    monkeypatch.setattr(core, "owner_scope", AsyncMock(return_value=owner))
    store._rule = AsyncMock(return_value=current)
    context = ScopeContext("UPDATE", uid(100), uid(2), uid(3))
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorScopeStore._begin(store, object(), 1, context)
    assert caught.value.code == "RULE_STATE_CONFLICT"
    assert (await core.RuleEditorScopeStore._begin(store, object(), 1, context, editing=False))[
        2
    ] is current


@pytest.mark.asyncio
async def test_candidate_page_preserves_original_member3_and_checks_both_ranges(setup):
    store, _access, _owner = setup
    query = parse_scope_query(
        {"action": "CREATE", "owner_user_id": uid(2), "owner_team_id": uid(3), "page_size": "20"}
    )
    session = Session([member(n) for n in range(10, 31)])
    response = await store.accounts(session, 1, "s", query)
    assert len(response["items"]) == 20 and response["next_cursor"]
    assert set(response) == {"items", "next_cursor", "data_as_of", "scope_version"}
    assert all(set(item) == {"account_id", "external_id", "name"} for item in response["items"])
    sql, params = session.sql[0]
    assert "a.owner_user_id=:caller_subject" in sql
    assert "a.owner_user_id=:owner_subject" in sql
    assert params["limit"] == 21 and "FOR SHARE OF a" in sql
    store._finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_later_page_member_revocation_rejects_whole_snapshot(setup):
    store, access, owner = setup
    data = [member(n) for n in range(10, 1011)]
    session = Session(data)
    root = FrozenMemberRoot()
    for item in data:
        root.add(item)
    snapshot = {
        "tenant_id": access.current.tenant_id,
        "actor_id": 1,
        "id": uid(10000),
        "ready": 1,
        "scope_version": 1,
        "auth_fingerprint": access.auth_fingerprint,
        "owner_auth_fingerprint": owner.auth_fingerprint,
        "member_count": 1001,
        "members_hash": root.hexdigest(),
    }
    original = session.execute

    async def revoked(statement, values):
        response = await original(statement, values)
        if str(statement).startswith("SELECT m.*") and values["after"]:
            return result(
                [
                    data[-1]
                    | {
                        "current_id": data[-1]["account_id"],
                        "current_owner": uid(5000),
                        "current_team": uid(5001),
                    }
                ]
            )
        return response

    session.execute = revoked
    with pytest.raises(OrbitError) as caught:
        await store._verify_snapshot(session, access, owner, snapshot)
    assert caught.value.code == "RULE_EDITOR_SCOPE_CHANGED"
    assert len(session.sql) == 2  # 确实读取第二批，不能只按当前页放行。


@pytest.mark.asyncio
async def test_unknown_db_failure_propagates_no_publication(setup):
    store, _access, _owner = setup
    session = Session([member(10)])
    original = session.execute

    async def fail(statement, values):
        if str(statement).startswith("SELECT a.id"):
            raise RuntimeError("PURE_DB_FAILURE")
        return await original(statement, values)

    session.execute = fail
    with pytest.raises(RuntimeError, match="^PURE_DB_FAILURE$"):
        await store.create(
            session,
            1,
            "s",
            "c",
            "k",
            parse_scope_write(canonical(body()).encode()),
            None,
            uid(10000),
        )
    assert not any("scope_event" in sql or "scope_outbox" in sql for sql, _ in session.sql)


@pytest.mark.asyncio
async def test_outer_transaction_and_original_action_denial_before_business_sql(monkeypatch):
    session = SimpleNamespace(in_transaction=lambda: False, execute=AsyncMock())
    store = core.RuleEditorScopeStore(Tokens())
    query = parse_scope_query(
        {"action": "CREATE", "owner_user_id": uid(2), "owner_team_id": uid(3)}
    )
    with pytest.raises(ValueError):
        await store.accounts(session, 1, "s", query)
    session.execute.assert_not_awaited()
    monkeypatch.setattr(core, "transaction", lambda session: object())
    denied = AsyncMock(side_effect=OrbitError(403, "PERMISSION_DENIED", "拒绝"))
    monkeypatch.setattr(core, "authorize_rule", denied)
    with pytest.raises(OrbitError) as caught:
        await store.accounts(session, 1, "s", query)
    assert caught.value.status == 403
    denied.assert_awaited_once_with(session, 1, "rules.create")
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_key_race_uses_current_receipt_without_mutating_published_row(setup):
    from sqlalchemy.exc import DBAPIError

    store, _access, _owner = setup
    session = Session([member(10)])
    value = parse_scope_write(canonical(body()).encode())
    original = await store.create(session, 1, "s", "c", "k", value, None, uid(10000))
    execute = session.execute
    first = True

    async def old_read_then_conflict(statement, values):
        nonlocal first
        sql = str(statement)
        if sql.startswith("SELECT * FROM orbit_rule_editor_scope_snapshot") and first:
            first = False
            return result([])  # 已有RR快照尚未看到另一提交；INSERT唯一键仍检测当前冲突。
        if sql.startswith("INSERT INTO orbit_rule_editor_scope_snapshot"):
            raise DBAPIError("SAFE_PURE", None, Exception(1062, "ignored"))
        return await execute(statement, values)

    session.execute = old_read_then_conflict
    session.sql.clear()
    assert await store.create(session, 1, "s", "c", "k", value, None, uid(10001)) == original
    assert all(sql.startswith("SELECT") for sql, _ in session.sql)
    assert any("request_key=:key FOR SHARE" in sql for sql, _ in session.sql)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["action", "rule_id", "owner_user_id", "owner_team_id", "request_hash"]
)
async def test_replay_independent_projection_must_match_frozen_intent(setup, field):
    store, _access, _owner = setup
    session = Session([member(10)])
    value = parse_scope_write(canonical(body()).encode())
    await store.create(session, 1, "s", "c", "k", value, None, uid(10000))
    session.snapshot[field] = "f" * 64
    with pytest.raises(OrbitError) as caught:
        await store.create(session, 1, "s", "c", "k", value, None, uid(10000))
    assert caught.value.status == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("different_expected", [2, 99])
async def test_update_receipt_binds_original_if_match_not_only_body(setup, different_expected):
    store, access, owner = setup
    previous = {"id": uid(100), "revision": 1, "state": "DRAFT"}
    store._begin.return_value = (access, owner, previous)
    value = parse_scope_write(canonical(body(action="UPDATE", rule_id=uid(100))).encode())
    session = Session([member(10)])
    original = await store.create(session, 1, "s", "c", "k", value, 1, uid(10000))
    session.sql.clear()
    with pytest.raises(OrbitError) as caught:
        await store.create(session, 1, "s", "c", "k", value, different_expected, uid(10001))
    assert caught.value.status == 409 and caught.value.code == "IDEMPOTENCY_CONFLICT"
    assert all(sql.startswith("SELECT") for sql, _ in session.sql)
    # 原If-Match在当前head改版后仍返回同一已提交receipt，不重新冻结或改历史。
    store._begin.return_value = (access, owner, previous | {"revision": 2, "state": "ENABLED"})
    assert await store.create(session, 1, "s", "c", "k", value, 1, uid(10002)) == original
    assert all(sql.startswith("SELECT") for sql, _ in session.sql)


@pytest.mark.asyncio
async def test_update_duplicate_insert_race_checks_expected_in_current_receipt(setup):
    from sqlalchemy.exc import DBAPIError

    store, access, owner = setup
    store._begin.return_value = (access, owner, {"id": uid(100), "revision": 1, "state": "DRAFT"})
    value = parse_scope_write(canonical(body(action="UPDATE", rule_id=uid(100))).encode())
    session = Session([member(10)])
    await store.create(session, 1, "s", "c", "k", value, 1, uid(10000))
    store._begin.return_value = (access, owner, {"id": uid(100), "revision": 2, "state": "DRAFT"})
    execute, first = session.execute, True

    async def race(statement, values):
        nonlocal first
        sql = str(statement)
        if sql.startswith("SELECT * FROM orbit_rule_editor_scope_snapshot") and first:
            first = False
            return result([])
        if sql.startswith("INSERT INTO orbit_rule_editor_scope_snapshot"):
            raise DBAPIError("SAFE_PURE", None, Exception(1062, "ignored"))
        return await execute(statement, values)

    session.execute = race
    with pytest.raises(OrbitError) as caught:
        await store.create(session, 1, "s", "c", "k", value, 2, uid(10001))
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_corrupt_persisted_member_uuid_is_integrity_503_not_client_422(setup):
    store, access, owner = setup
    session = Session([member(10)])
    value = parse_scope_write(canonical(body()).encode())
    await store.create(session, 1, "s", "c", "k", value, None, uid(10000))
    session.members[0]["account_id"] = "invalid-persisted-uuid"
    with pytest.raises(OrbitError) as caught:
        await store._verify_snapshot(session, access, owner, session.snapshot)
    assert caught.value.status == 503 and caught.value.code == "RULE_EDITOR_SCOPE_UNAVAILABLE"


def test_invalid_user_selection_uuid_remains_original_field_422():
    value = body(selection={"mode": "IDS", "account_ids": ["invalid-user-uuid"], "filter": None})
    with pytest.raises(OrbitError) as caught:
        parse_scope_write(canonical(value).encode())
    assert caught.value.status == 422 and caught.value.code == "FIELD_INVALID"


@pytest.mark.asyncio
async def test_creation_member_limit_422_is_not_reclassified_as_persistent_corruption(
    setup, monkeypatch
):
    store, _access, _owner = setup
    root = FrozenMemberRoot()
    root.count = 50000
    monkeypatch.setattr(core, "FrozenMemberRoot", lambda: root)
    with pytest.raises(OrbitError) as caught:
        await store.create(
            Session([member(10)]),
            1,
            "s",
            "c",
            "k",
            parse_scope_write(canonical(body()).encode()),
            None,
            uid(10000),
        )
    assert caught.value.status == 422 and caught.value.code == "SCOPE_ACCOUNT_LIMIT"
