"""规则只读列表候选纯协议；不替代真实RC/权限/键集SQL专项。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

import orbit_api.rule_list_filter_store as core
from orbit_api.errors import OrbitError
from orbit_api.rule_list_filter_contract import (
    DOMAIN,
    PURPOSE,
    RuleListFilterQuery,
    parse_list_filter_query,
    response_page,
)


def uid(value):
    return str(UUID(int=value))


@pytest.mark.parametrize("size", [20, 50, 100, 200, "20", "50", "100", "200"])
def test_original_four_sizes(size):
    assert parse_list_filter_query({"kind": "OPERATOR", "page_size": size}) == RuleListFilterQuery(
        "OPERATOR", int(size)
    )


@pytest.mark.parametrize(
    "value,status",
    [
        ({}, 422),
        ({"kind": None}, 422),
        ({"kind": "VENDOR"}, 422),
        ({"kind": "OPERATOR", "q": "name"}, 400),
        ({"kind": "OPERATOR", "action": "CREATE"}, 400),
        ({"kind": "OPERATOR", "page_size": True}, 422),
        ({"kind": "OPERATOR", "page_size": "020"}, 422),
        ({"kind": "OPERATOR", "page_size": 500}, 422),
        ({"kind": "OPERATOR", "cursor": ""}, 422),
        ({"kind": "OPERATOR", "cursor": "a" * 2049}, 422),
    ],
)
def test_invalid_query_no_added_semantics(value, status):
    with pytest.raises(OrbitError) as error:
        parse_list_filter_query(value)
    assert error.value.status == status


def page():
    return {
        "items": [{"id": uid(1), "label": None}],
        "next_cursor": None,
        "data_as_of": "2026-11-09T00:00:00.000Z",
        "scope_version": 1,
    }


def test_nullable_real_name_no_guess_and_no_extra_fields():
    assert response_page(page()) == page()


@pytest.mark.parametrize(
    "change",
    [
        {"items": [{"id": "bad", "label": None}]},
        {"items": [{"id": uid(2), "label": None}, {"id": uid(1), "label": None}]},
        {"items": [{"id": uid(1), "label": None}] * 2},
        {"items": [{"id": uid(1), "label": 12}]},
        {"items": [{"id": uid(1), "label": "x" * 256}]},
        {"items": [{"id": uid(1), "label": None, "name": "invented"}]},
        {"scope_version": True},
        {"data_as_of": "2026-11-09"},
        {"unknown": True},
    ],
)
def test_bad_stored_projection_is_503(change):
    with pytest.raises(OrbitError) as error:
        response_page(page() | change)
    assert error.value.status == 503


def access(role="USER", managed=()):
    return SimpleNamespace(
        current=SimpleNamespace(
            data_role=role, tenant_id=uid(1), actor_id=12, subject_id=uid(2), team_id=uid(3)
        ),
        managed_team_ids=managed,
        auth_fingerprint="current",
        auth_version=4,
    )


def test_visible_predicate_never_gives_user_team_or_unmanaged_team():
    sql, values = core.visible_clause(access())
    assert "owner_user_id=:subject" in sql and "owner_team_id" not in sql
    assert "teams" not in values
    sql, values = core.visible_clause(access("TEAM_ADMIN", (uid(8),)))
    assert "owner_user_id=:subject OR h.owner_team_id IN :teams" in sql
    assert values["teams"] == [uid(8)]
    assert core.visible_clause(access("SUPER_ADMIN"))[0] == "h.tenant_id=:tenant"


class Tokens:
    def session_binding(self, auth, actor, tenant):
        return auth

    def issue(self, purpose, claims):
        assert purpose == PURPOSE
        self.claims = claims | {"exp": 9999999999, "kid": "fixture"}
        return "opaque-next"

    def verify(self, purpose, token):
        assert purpose == PURPOSE
        return self.claims


def setup(monkeypatch, ids, *, role="USER", kind="OPERATOR", labels=None):
    current = access(role)
    monkeypatch.setattr(core, "transaction", lambda session: object())
    authorize = AsyncMock(return_value=current)
    final = AsyncMock()
    monkeypatch.setattr(core, "authorize_rule", authorize)
    monkeypatch.setattr(core, "revalidate_access", final)
    monkeypatch.setattr(
        core.RuleStore,
        "_clock",
        AsyncMock(return_value={"revision": 7, "now": datetime(2026, 11, 9, tzinfo=UTC)}),
    )
    statements = []

    async def execute(sql, values):
        statements.append((str(sql), values))
        found = (
            [{"id": key, "display_name": value} for key, value in (labels or {}).items()]
            if "orbit_business_user" in str(sql)
            else [{"id": item} for item in ids]
        )
        return SimpleNamespace(mappings=lambda: found)

    connection = SimpleNamespace(get_isolation_level=AsyncMock(return_value="READ COMMITTED"))
    session = SimpleNamespace(connection=AsyncMock(return_value=connection), execute=execute)
    tokens = Tokens()
    return core.RuleListFilterStore(tokens), session, tokens, authorize, final, statements


def test_read_only_two_bounded_queries_and_final_authorization(monkeypatch):
    store, session, tokens, auth, final, statements = setup(
        monkeypatch, [uid(i) for i in range(1, 22)], labels={uid(1): "真实名称"}
    )
    result = asyncio.run(
        store.options(session, 12, "Bearer first", RuleListFilterQuery("OPERATOR", 20))
    )
    assert len(result["items"]) == 20 and result["next_cursor"] == "opaque-next"
    assert result["items"][0]["label"] == "真实名称" and result["items"][1]["label"] is None
    auth.assert_awaited_once_with(session, 12, "rules.read")
    final.assert_awaited_once()
    assert len(statements) == 2 and statements[0][1]["limit"] == 21
    assert "DISTINCT" in statements[0][0] and "OFFSET" not in statements[0][0]
    assert "account" not in statements[0][0] and "state" not in statements[0][0]
    assert "enabled" not in statements[1][0]
    assert tokens.claims["revision"] == 7


def test_profiles_use_only_referenced_ids_no_registry_or_guessed_name(monkeypatch):
    store, session, _, _, _, statements = setup(monkeypatch, [uid(5)])
    result = asyncio.run(
        store.options(session, 12, "session", RuleListFilterQuery("METRIC_PROFILE"))
    )
    assert result["items"] == [{"id": uid(5), "label": None}]
    assert len(statements) == 1 and "metric_profile_id" in statements[0][0]
    assert "profile_version" not in statements[0][0]


@pytest.mark.parametrize(
    "change,status",
    [
        ({"binding": "another"}, 409),
        ({"revision": 8}, 409),
        ({"revision": True}, 400),
        ({"extra": True}, 400),
        ({"after_id": "bad"}, 400),
        ({"as_of": "yesterday"}, 400),
    ],
)
def test_cursor_exact_claim_binding_and_revision(change, status):
    tokens = Tokens()
    tokens.claims = {
        "binding": "same",
        "revision": 7,
        "after_id": uid(1),
        "as_of": "2026-11-09T00:00:00.000Z",
        "kid": "fixture",
        "exp": 100,
    }
    tokens.claims.update(change)
    with pytest.raises(OrbitError) as error:
        core.cursor_claims(tokens, "opaque", "same", 7)
    assert error.value.status == status


def test_purpose_binding_domain_session_kind_and_size_are_independent(monkeypatch):
    bindings = []
    for auth, kind, size in [
        ("A", "OPERATOR", 20),
        ("B", "OPERATOR", 20),
        ("A", "METRIC_PROFILE", 20),
        ("A", "OPERATOR", 50),
    ]:
        store, session, tokens, _, _, _ = setup(monkeypatch, [uid(i) for i in range(1, size + 2)])
        asyncio.run(store.options(session, 12, auth, RuleListFilterQuery(kind, size)))
        bindings.append(tokens.claims["binding"])
    assert len(set(bindings)) == 4
    assert DOMAIN != "RULE_CURSOR_V1"


def test_final_revocation_never_returns_partial_result(monkeypatch):
    store, session, _, _, final, _ = setup(monkeypatch, [uid(1)])
    final.side_effect = OrbitError(403, "PERMISSION_DENIED", "撤销")
    with pytest.raises(OrbitError) as error:
        asyncio.run(store.options(session, 12, "session", RuleListFilterQuery("OPERATOR")))
    assert error.value.status == 403


def test_repeatable_read_is_refused_before_business_authorization(monkeypatch):
    store, session, _, auth, _, _ = setup(monkeypatch, [])
    connection = SimpleNamespace(get_isolation_level=AsyncMock(return_value="REPEATABLE READ"))
    session.connection = AsyncMock(return_value=connection)
    with pytest.raises(ValueError, match="READ_COMMITTED_REQUIRED"):
        asyncio.run(store.options(session, 12, "session", RuleListFilterQuery("OPERATOR")))
    auth.assert_not_awaited()
