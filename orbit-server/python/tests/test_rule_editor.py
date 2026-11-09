"""编辑辅助纯合同/当前来源/游标，不计真实MySQL或HTTP验收。"""

import base64
import copy
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
from test_metric_profile_query import CURRENT, NOW, row

import orbit_api.rule_editor_store as core
from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.rule_editor_contract import EditorQuery, parse_editor_query


def uid(n):
    return str(UUID(int=n))


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"action": "EDIT"},
        {"action": "CREATE", "rule_id": uid(1)},
        {"action": "UPDATE"},
        {"action": "CREATE", "previous": {}},
        {"action": "CREATE", "kind": "ACCOUNT"},
        {"action": "CREATE", "kind": "OWNER", "owner_user_id": uid(1)},
        {"action": "CREATE", "kind": "PROFILE"},
        {"action": "CREATE", "kind": "OWNER", "page_size": True},
        {"action": "CREATE", "kind": "OWNER", "page_size": "020"},
        {"action": "CREATE", "kind": "OWNER", "cursor": ""},
        {
            "action": "CREATE",
            "kind": "PROFILE",
            "owner_user_id": uid(1),
            "owner_team_id": uid(2),
            "q": "v1",
        },
    ],
)
def test_strict_no_previous_tenant_or_manual_sql_parameters(values):
    with pytest.raises(OrbitError):
        parse_editor_query(values, options=True)


@pytest.mark.parametrize("size", [20, 50, 100, 200, "20", "50", "100", "200"])
def test_original_four_sizes_and_explicit_actions(size):
    value = parse_editor_query(
        {"action": "CREATE", "kind": "OWNER", "page_size": size}, options=True
    )
    assert value.page_size == int(size)
    assert parse_editor_query({"action": "UPDATE", "rule_id": uid(4)}).rule_id == uid(4)


@pytest.fixture
def tokens():
    return DirectoryTokens(CredentialCipher("pure", {"pure": base64.b64encode(b"e" * 32).decode()}))


def access():
    return SimpleNamespace(
        current=CURRENT, auth_version=1, auth_fingerprint="a" * 64, managed_team_ids=()
    )


class Session:
    def __init__(self, profiles):
        self.profiles, self.sql, self.config_revision = profiles, [], 2
        self.final_mutation = None

    async def execute(self, statement, values):
        sql = " ".join(str(statement).split())
        self.sql.append((sql, values))
        if "UTC_TIMESTAMP" in sql:
            found = [{"revision": 1, "now": NOW.replace(tzinfo=None)}]
        elif "FROM orbit_system_configuration" in sql:
            found = [
                {
                    "id": values["id"],
                    "revision": self.config_revision,
                    "enabled": 1,
                    "section": "META_BM",
                }
            ]
        elif "h.revision AS head_revision" in sql:
            found = copy.deepcopy(self.profiles)
            for item in found:
                item.update(state="ENABLED", head_revision=1)
            if self.final_mutation:
                self.final_mutation(found)
        elif "SELECT h.id,h.current_version" in sql:
            found = [
                {
                    key: item[key]
                    for key in (
                        "id",
                        "current_version",
                        "source",
                        "authority_kind",
                        "source_config_id",
                        "source_config_revision",
                    )
                }
                for item in self.profiles
            ]
        else:
            raise AssertionError("UNEXPECTED_PURE_QUERY")
        keys = tuple(found[0]) if found else ()
        return IteratorResult(
            SimpleResultMetaData(keys), iter(tuple(item[key] for key in keys) for item in found)
        )


@pytest.mark.asyncio
async def test_meta_profile_source_clock_order_and_original_twelve_fields(tokens):
    session = Session([row(1, source="META"), row(2, source="META")])
    result, clock = await core.RuleEditorStore(tokens)._profiles(session, access())
    assert len(result) == 2 and len(result[0]) == 12 and "name" not in result[0]
    sqls = [sql for sql, _ in session.sql]
    assert len(sqls) == 4  # probe/唯一config/clock/集合final，而非逐profileN+1。
    assert "FROM orbit_system_configuration" in sqls[1]
    assert "FROM orbit_metric_profile_clock" in sqls[2]
    assert "FOR SHARE OF h,v" in sqls[3]
    assert clock["revision"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption", ["hash", "proof", "observed_column", "future", "verified", "source_drift"]
)
async def test_bad_row_rejects_whole_page_not_partial_skip(tokens, corruption):
    session = Session([row(1, source="META"), row(2, source="META")])

    def mutate(found):
        bad = found[-1]
        if corruption == "hash":
            bad["payload_hash"] = "0" * 64
        elif corruption == "proof":
            proof = json.loads(bad["source_proof_json"])
            proof["evidence_ref"] = "different"
            bad["source_proof_json"] = json.dumps(proof)
        elif corruption == "observed_column":
            bad["observed_at"] = NOW.replace(tzinfo=None)
        elif corruption == "future":
            from datetime import timedelta

            bad["observed_at"] = (NOW + timedelta(days=1)).replace(tzinfo=None)
        elif corruption == "verified":
            value = json.loads(bad["payload_json"])
            value["verified"] = False
            import hashlib

            from orbit_api.directory_tokens import canonical

            bad["payload_json"] = canonical(value)
            bad["payload_hash"] = hashlib.sha256(canonical(value).encode()).hexdigest()
        else:
            bad["source_config_id"] = uid(555)

    session.final_mutation = mutate
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorStore(tokens)._profiles(session, access())
    assert caught.value.status in {409, 503}


@pytest.mark.asyncio
async def test_source_revision_change_rejected_before_metric_clock(tokens):
    session = Session([row(1, source="META")])
    session.config_revision = 3
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorStore(tokens)._profiles(session, access())
    assert caught.value.status == 409
    assert not any("FROM orbit_metric_profile_clock" in sql for sql, _ in session.sql)


@pytest.mark.asyncio
async def test_fixture_not_available_by_default_and_flag_strict_boolean(tokens):
    with pytest.raises(ValueError):
        core.RuleEditorStore(tokens, isolated_fixture="true")
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorStore(tokens)._profiles(Session([row()]), access())
    assert caught.value.status == 503


def test_cursor_binds_session_owner_rule_action_kind_filter_size_and_watermark(tokens):
    store = core.RuleEditorStore(tokens)
    query = EditorQuery("CREATE", None, kind="OWNER", page_size=20)
    directory = {"revision": 1, "now": NOW.replace(tzinfo=None)}
    result = store._page(
        access(),
        None,
        query,
        directory,
        directory,
        [{"id": uid(n)} for n in range(1, 22)],
        None,
        "Bearer one",
    )
    claims, after = store._cursor(replace(query, cursor=result["next_cursor"]))
    assert after == uid(20)
    for changed_query in (
        replace(query, action="UPDATE", rule_id=uid(55)),
        replace(query, kind="PROFILE"),
        replace(query, q="different"),
        replace(query, page_size=50),
    ):
        with pytest.raises(OrbitError):
            store._page(
                access(), None, changed_query, directory, directory, [], claims, "Bearer one"
            )
    with pytest.raises(OrbitError):
        store._page(access(), None, query, directory, directory, [], claims, "Bearer two")
    with pytest.raises(OrbitError):
        store._page(
            access(), None, query, directory, directory | {"revision": 2}, [], claims, "Bearer one"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,permission", [("CREATE", "rules.create"), ("UPDATE", "rules.edit")]
)
async def test_begin_authorizes_exact_original_action_no_other_menu(
    tokens, monkeypatch, action, permission
):
    session = Session([])
    current = access()
    authorization = AsyncMock(return_value=current)
    monkeypatch.setattr(core, "transaction", lambda selected: None)
    monkeypatch.setattr(core, "authorize_rule", authorization)
    store = core.RuleEditorStore(tokens)
    monkeypatch.setattr(store, "_rule", AsyncMock(return_value={"id": uid(5)}))
    await store._begin(session, 31, EditorQuery(action, uid(5) if action == "UPDATE" else None))
    assert authorization.await_args.args == (session, 31, permission)


@pytest.mark.asyncio
async def test_update_profile_write_previous_only_after_current_rule_finish(tokens, monkeypatch):
    store = core.RuleEditorStore(tokens)
    events = []
    current, session = access(), Session([])
    probe = {"id": uid(4), "revision": 1, "owner_user_id": uid(5), "owner_team_id": uid(6)}
    locked = probe | {"revision": 2}
    directory = {"revision": 1, "now": NOW.replace(tzinfo=None)}
    owner = SimpleNamespace(auth_fingerprint="b" * 64, managed_team_ids=())
    monkeypatch.setattr(store, "_begin", AsyncMock(return_value=(current, probe, directory)))
    monkeypatch.setattr(store, "_profiles", AsyncMock(return_value=([], directory)))

    async def finish(*args):
        events.append("locked-current-rule")
        return locked

    async def scope(*args, **kwargs):
        if kwargs.get("for_write"):
            assert events == ["locked-current-rule"] and kwargs["previous"] is locked
            events.append("write-ownership")
        else:
            assert "previous" not in kwargs
        return owner

    monkeypatch.setattr(store, "_finish", finish)
    monkeypatch.setattr(core, "owner_scope", scope)
    monkeypatch.setattr(core, "revalidate_owner", AsyncMock())
    await store.options(
        session,
        31,
        "auth",
        EditorQuery("UPDATE", uid(4), "PROFILE", CURRENT.subject_id, CURRENT.team_id),
    )
    assert events == ["locked-current-rule", "write-ownership"]


@pytest.mark.asyncio
async def test_forbidden_new_owner_rejected_before_profile_query(tokens, monkeypatch):
    store = core.RuleEditorStore(tokens)
    directory = {"revision": 1, "now": NOW.replace(tzinfo=None)}
    monkeypatch.setattr(store, "_begin", AsyncMock(return_value=(access(), None, directory)))
    profiles = AsyncMock()
    monkeypatch.setattr(store, "_profiles", profiles)
    with pytest.raises(OrbitError) as caught:
        await store.options(
            Session([]),
            31,
            "auth",
            EditorQuery("CREATE", None, "PROFILE", uid(44), CURRENT.team_id),
        )
    assert caught.value.code == "OWNERSHIP_DENIED"
    profiles.assert_not_awaited()


@pytest.mark.asyncio
async def test_fixture_flag_checks_real_boundary_even_empty_context(tokens, monkeypatch):
    monkeypatch.setattr(core, "transaction", lambda session: None)
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(return_value=access()))
    boundary = AsyncMock(side_effect=OrbitError(503, "TEST_DATABASE_ONLY", "pure"))
    monkeypatch.setattr(core, "fixture_boundary", boundary)
    session = Session([])
    with pytest.raises(OrbitError):
        await core.RuleEditorStore(tokens, isolated_fixture=True)._begin(
            session, 31, EditorQuery("CREATE", None)
        )
    boundary.assert_awaited_once_with(session)
    assert session.sql == []


@pytest.mark.asyncio
@pytest.mark.parametrize("microsecond", [123499, 123500, 999999])
async def test_actual_public_validator_preserves_legal_proof_microseconds_and_mysql_round(
    tokens, microsecond
):
    from datetime import datetime

    from orbit_api.metric_profile_query import mysql_millisecond_instant

    data = row(1, source="META")
    proof = json.loads(data["source_proof_json"])
    observed = datetime(2026, 11, 1, 0, 0, 0, microsecond, tzinfo=NOW.tzinfo)
    proof["observed_at"] = observed.isoformat()
    data["source_proof_json"] = json.dumps(proof)
    data["observed_at"] = mysql_millisecond_instant(observed).replace(tzinfo=None)
    values, _ = await core.RuleEditorStore(tokens)._profiles(Session([data]), access())
    assert len(values) == 1 and values[0]["version"] == data["current_version"]


@pytest.mark.asyncio
async def test_clock_after_source_uses_current_locked_config_not_old_rr_join(tokens):
    session = Session([row(1, source="META")])

    def old_snapshot(found):
        found[0]["config_revision"] = 1
        found[0]["config_enabled"] = 0

    session.final_mutation = old_snapshot
    values, _ = await core.RuleEditorStore(tokens)._profiles(session, access())
    assert len(values) == 1
    final_sql = session.sql[-1][0]
    assert "JOIN orbit_system_configuration" not in final_sql


@pytest.mark.asyncio
async def test_inactive_owner_context_does_not_read_or_return_profile(tokens, monkeypatch):
    store = core.RuleEditorStore(tokens)
    previous = {
        "id": uid(4),
        "revision": 1,
        "state": "DRAFT",
        "owner_user_id": CURRENT.subject_id,
        "owner_team_id": CURRENT.team_id,
        "metric_profile_id": uid(10),
        "metric_profile_version": "old-version",
    }
    monkeypatch.setattr(
        store, "_begin", AsyncMock(return_value=(access(), previous, {"revision": 1, "now": NOW}))
    )
    monkeypatch.setattr(store, "_label", AsyncMock(return_value=None))
    monkeypatch.setattr(store, "_finish", AsyncMock(return_value=previous))
    profiles = AsyncMock()
    monkeypatch.setattr(store, "_profiles", profiles)
    value = await store.context(Session([]), 31, "auth", EditorQuery("UPDATE", uid(4)))
    assert value["selected_owner"] == {"item": None, "can_keep": False}
    assert value["selected_profile"] == {
        "id": uid(10),
        "bound_version": "old-version",
        "current": None,
        "status": "UNAVAILABLE",
    }
    profiles.assert_not_awaited()
