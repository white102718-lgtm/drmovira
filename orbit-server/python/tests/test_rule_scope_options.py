"""规则候选纯协议/SQL形状测试；不替代真实RC/双主体SQL验收。"""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

import orbit_api.rule_scope_options_store as core
from orbit_api.errors import OrbitError
from orbit_api.rule_scope_options_contract import (
    OPERATOR_FIELDS,
    PAGE_FIELDS,
    VENDOR_FIELDS,
    parse_scope_options_query,
)


def uid(n):
    return str(UUID(int=n))


def query(**changes):
    return parse_scope_options_query(
        {
            "kind": "OPERATOR",
            "action": "CREATE",
            "owner_user_id": uid(2),
            "owner_team_id": uid(3),
        }
        | changes
    )


@pytest.mark.parametrize("size", [20, 50, 100, 200, "20", "50", "100", "200"])
def test_four_sizes_original_context_and_exact_uuid(size):
    value = query(page_size=size, q=uid(255).upper())
    assert value.page_size == int(size) and value.exact_id == uid(255)
    assert value.context.owner_team_id == uid(3)
    assert query(q="名称%_!").exact_id is None
    assert query(action="UPDATE", rule_id=uid(4)).context.rule_id == uid(4)


@pytest.mark.parametrize(
    "change,status",
    [
        ({"kind": "OWNER"}, 422),
        ({"kind": None}, 422),
        ({"kind": []}, 422),
        ({"page_size": True}, 422),
        ({"page_size": 500}, 422),
        ({"page_size": "020"}, 422),
        ({"cursor": ""}, 422),
        ({"cursor": "a" * 2049}, 422),
        ({"cursor": 1}, 422),
        ({"action": "UPDATE"}, 422),
        ({"rule_id": uid(4)}, 422),
        ({"owner_user_id": None}, 422),
        ({"owner_team_id": None}, 422),
        ({"q": "x" * 101}, 422),
        ({"q": None}, 422),
        ({"q": True}, 422),
        ({"q": []}, 422),
        ({"operator_user_id": uid(2)}, 400),
        ({"team_id": uid(3)}, 400),
        ({"vendor_id": uid(4)}, 400),
        ({"status": "ACTIVE"}, 400),
        ({"auth_status": "AUTHORIZED"}, 400),
    ],
)
def test_strict_request_rejects_unknown_filters(change, status):
    with pytest.raises(OrbitError) as caught:
        query(**change)
    assert caught.value.status == status


def operator(**changes):
    return {
        "id": uid(11),
        "name": "真实姓名",
        "team_id": uid(3),
        "team_name": "真实团队",
        "enabled": 1,
        "invited": 0,
        "status": "0",
        "del_flag": "0",
        "team_enabled": 1,
        "scope_enabled": 1,
    } | changes


def vendor(**changes):
    return {
        "id": uid(20),
        "name": "真实户商",
        "alias": None,
        "availability": "UNAVAILABLE",
    } | changes


def test_history_not_assignment_and_no_alias_guess():
    assert set(core.public_operator(operator())) == OPERATOR_FIELDS
    assert core.public_operator(operator(enabled=0))["active"] is False
    assert core.public_operator(operator(invited=1))["active"] is False
    assert core.public_operator(operator(del_flag="2"))["active"] is False
    assert core.public_vendor(vendor())["alias"] is None
    assert set(core.public_vendor(vendor())) == VENDOR_FIELDS
    assert core.public_vendor(vendor(alias="真代称"))["alias"] == "真代称"


@pytest.mark.parametrize(
    "change",
    [
        {"id": "bad"},
        {"name": ""},
        {"team_name": None},
        {"enabled": True},
        {"invited": 2},
        {"scope_enabled": None},
        {"status": "bad"},
        {"del_flag": "1"},
    ],
)
def test_bad_persistent_operator_is_503(change):
    with pytest.raises(OrbitError) as caught:
        core.public_operator(operator(**change))
    assert caught.value.status == 503


@pytest.mark.parametrize(
    "change",
    [
        {"id": "bad"},
        {"name": ""},
        {"alias": ""},
        {"alias": "x" * 31},
        {"alias": 1},
        {"alias": "e\u0301"},
        {"availability": "UNKNOWN"},
    ],
)
def test_bad_persistent_vendor_is_503(change):
    with pytest.raises(OrbitError) as caught:
        core.public_vendor(vendor(**change))
    assert caught.value.status == 503


def scope(role="USER", managed=(), subject=2):
    return SimpleNamespace(
        current=SimpleNamespace(
            data_role=role, subject_id=uid(subject), actor_id=1, tenant_id=uid(1)
        ),
        managed_team_ids=managed,
        auth_fingerprint="fingerprint-" + str(subject),
        auth_version=7,
    )


def test_reference_scope_explicit_manage_not_same_team():
    own, params = core.ref_visibility(scope(), "caller")
    assert "orbit_reference_owner" in own and "owner_team_id" not in own
    assert params == {"caller_ref_subject": uid(2)}
    own, params = core.ref_visibility(scope("TEAM_ADMIN", (uid(8),)), "owner")
    assert "owner_team_id IN (:owner_ref_team_0)" in own and params["owner_ref_team_0"] == uid(8)
    assert core.ref_visibility(scope("SUPER_ADMIN"), "caller") == ("1=1", {})
    with pytest.raises(ValueError):
        core.ref_visibility(scope(), "injected")


def test_literal_prefix_has_no_contains_or_wildcard_injection():
    assert core.prefix("名称%_!'") == "名称!%!_!!'%"


class Connection:
    def __init__(self, isolation="READ COMMITTED"):
        self.sync_connection = SimpleNamespace(
            get_execution_options=lambda: {"isolation_level": isolation}
        )


class Tokens:
    def __init__(self):
        self.claims = None

    def session_binding(self, authorization, actor, tenant):
        return authorization + str(actor) + tenant

    def issue(self, purpose, claims):
        self.claims = claims
        return "opaque-next"

    def verify(self, purpose, token):
        return self.claims


def setup(monkeypatch, found):
    monkeypatch.setattr(core, "AsyncConnection", Connection)
    session = SimpleNamespace(bind=Connection(), in_transaction=lambda: True)
    tokens = Tokens()
    store = core.RuleScopeOptionsStore(tokens)
    access, owner = scope(), scope(subject=2)
    store.scopes = SimpleNamespace(
        _begin=AsyncMock(return_value=(access, owner, None)),
        _finish=AsyncMock(),
        _watermark=AsyncMock(return_value=(9, "2026-11-09T00:00:00.000Z")),
    )
    store.clocks = AsyncMock(return_value=([3, 4, 9], "2026-11-09T00:00:00.000Z"))
    fetch = AsyncMock(return_value=found)
    monkeypatch.setattr(core, "rows", fetch)
    return session, store, fetch


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE", None])
def test_reject_rr_before_auth_or_source(monkeypatch, isolation):
    session, store, fetch = setup(monkeypatch, [])
    session.bind = Connection(isolation)
    with pytest.raises(ValueError):
        asyncio.run(store.options(session, 1, "auth", query()))
    store.scopes._begin.assert_not_awaited()
    fetch.assert_not_awaited()


@pytest.mark.parametrize("kind", ["OPERATOR", "VENDOR"])
def test_read_bounds_exists_dual_scope_and_final_auth(monkeypatch, kind):
    session, store, fetch = setup(monkeypatch, [operator() if kind == "OPERATOR" else vendor()])
    result = asyncio.run(store.options(session, 1, "auth", query(kind=kind, q="字面%_!")))
    assert set(result) == PAGE_FIELDS and len(result["items"]) == 1
    assert result["next_cursor"] is None and result["scope_version"] == 7
    sql, values = fetch.await_args.args[1:]
    assert "EXISTS (SELECT 1 FROM orbit_ad_account a" in sql
    assert "caller_subject" in sql and "owner_subject" in sql
    assert "OFFSET" not in sql and "DISTINCT" not in sql and values["limit"] == 51
    assert values["q"] == "字面!%!_!!%"
    if kind == "VENDOR":
        assert "caller_ref_subject" in sql and "owner_ref_subject" in sql
        assert "r.availability='AVAILABLE'" not in sql
    else:
        assert "b.enabled=1" not in sql
    store.scopes._finish.assert_awaited_once()


def test_all_corrupt_page_no_partial_success_and_end_revoke(monkeypatch):
    session, store, fetch = setup(monkeypatch, [operator(), operator(id="bad")])
    with pytest.raises(OrbitError) as caught:
        asyncio.run(store.options(session, 1, "auth", query()))
    assert caught.value.status == 503
    store.scopes._finish.assert_not_awaited()
    fetch.return_value = [operator()]
    store.scopes._finish.side_effect = OrbitError(403, "PERMISSION_DENIED", "无权")
    with pytest.raises(OrbitError) as caught:
        asyncio.run(store.options(session, 1, "auth", query()))
    assert caught.value.status == 403


def test_signed_keyset_binds_size_kind_filter_session_and_watermarks(monkeypatch):
    session, store, fetch = setup(monkeypatch, [operator(id=uid(n)) for n in range(100, 121)])
    original = query(page_size=20)
    first = asyncio.run(store.options(session, 1, "auth", original))
    assert len(first["items"]) == 20 and first["next_cursor"] == "opaque-next"
    claims = dict(store.tokens.claims)
    fetch.return_value = [operator(id=uid(120))]
    second = asyncio.run(store.options(session, 1, "auth", replace(original, cursor="opaque-next")))
    assert second["items"][0]["id"] == uid(120) and second["next_cursor"] is None
    assert second["data_as_of"] == first["data_as_of"]
    assert fetch.await_args.args[2]["after"] == uid(119)
    for change in ({"q": "other"}, {"page_size": 50}, {"kind": "VENDOR"}):
        store.tokens.claims = claims
        with pytest.raises(OrbitError) as caught:
            asyncio.run(
                store.options(session, 1, "auth", replace(original, cursor="opaque-next", **change))
            )
        assert caught.value.status == 409
    store.tokens.claims = claims
    with pytest.raises(OrbitError) as caught:
        asyncio.run(
            store.options(session, 1, "other-session", replace(original, cursor="opaque-next"))
        )
    assert caught.value.status == 409
    store.tokens.claims = claims
    store.clocks.return_value = ([3, 4, 10], "2026-11-09T00:00:00.000Z")
    with pytest.raises(OrbitError) as caught:
        asyncio.run(store.options(session, 1, "auth", replace(original, cursor="opaque-next")))
    assert caught.value.status == 409


def test_clock_order_and_corrupt_clock_rejects_before_account(monkeypatch):
    session, store, _ = setup(monkeypatch, [])
    method = core.RuleScopeOptionsStore.clocks.__get__(store)
    fetch = AsyncMock(side_effect=[[{"revision": 0}], [{"revision": 3}]])
    monkeypatch.setattr(core, "rows", fetch)
    result = asyncio.run(method(session, scope()))
    assert result[0] == [0, 3, 9]
    assert "orbit_reference_clock" in fetch.await_args_list[0].args[1]
    assert "orbit_directory_clock" in fetch.await_args_list[1].args[1]
    store.scopes._watermark.assert_awaited_once()
    store.scopes._watermark.reset_mock()
    fetch.side_effect = [[{"revision": True}], [{"revision": 3}]]
    with pytest.raises(OrbitError) as caught:
        asyncio.run(method(session, scope()))
    assert caught.value.status == 503
    store.scopes._watermark.assert_not_awaited()
