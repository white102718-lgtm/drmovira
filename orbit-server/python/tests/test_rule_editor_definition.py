"""原定义元数据纯合同；真实RowMapping，不证明实际SQL/HTTP业务验收。"""

import copy
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
from starlette.requests import Request
from test_rule_contract import sample_rule

import orbit_api.rule_access as access_core
import orbit_api.rule_editor_definition as core
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_store import digest


def uid(n):
    return str(UUID(int=n))


def result(rows):
    keys = tuple(rows[0]) if rows else ()
    return IteratorResult(
        SimpleResultMetaData(keys), iter(tuple(row[key] for key in keys) for row in rows)
    )


def sample(state="DRAFT", source="RULE"):
    body = sample_rule()
    head = {
        "tenant_id": uid(1),
        "id": uid(2),
        "revision": 3,
        "name": body["name"],
        **body["ownership"],
        "target_level": body["target_level"],
        "state": state,
        "manifest_id": uid(3),
        "metric_profile_id": body["metric_profile_id"],
        "next_run_at": None,
    }
    version = dict(head) | {
        "rule_id": head["id"],
        "payload_json": canonical(body),
        "payload_hash": digest(body),
        "metric_profile_version": "historical-disabled-profile-v1",
        "metric_profile_hash": "a" * 64,
        "profile_proof_hash": "b" * 64,
        "event_id": uid(4),
    }
    manifest = {
        "tenant_id": head["tenant_id"],
        "id": head["manifest_id"],
        "rule_id": head["id"],
        "source_kind": source,
        "source_snapshot_id": body["scope_snapshot_id"],
        "member_count": 50000,
        "sealed": 1,
        "owner_user_id": uid(7),  # 历史owner不同；不得假装其仍当前可用。
        "owner_team_id": uid(8),
        "source_snapshot_hash": "c" * 64,
        "member_ids_hash": "d" * 64,
        "creator_auth_fingerprint": "e" * 64,
        "owner_auth_fingerprint": "f" * 64,
        "account_source_snapshot_id": body["scope_snapshot_id"] if source == "ACCOUNT" else None,
        "rule_source_snapshot_id": body["scope_snapshot_id"] if source == "RULE" else None,
    }
    return head, version, manifest


@pytest.mark.parametrize("state", ["DRAFT", "PAUSED", "ENABLED", "ARCHIVED"])
@pytest.mark.parametrize("source", ["ACCOUNT", "RULE"])
def test_original_fifteen_and_scope_current_owner_without_profile_or_member_scan(state, source):
    head, version, manifest = sample(state, source)
    value = core.definition_response(head, version, manifest)
    assert set(value) == {"rule", "stored_scope"} and len(value["rule"]) == 15
    assert value["rule"]["state"] == state and value["rule"]["next_run_at"] is None
    assert value["stored_scope"] == {
        "id": value["rule"]["scope_snapshot_id"],
        "count": 50000,
        **value["rule"]["ownership"],
    }
    assert value["stored_scope"]["owner_user_id"] != manifest["owner_user_id"]


@pytest.mark.parametrize(
    "part,key,value",
    [
        (0, "revision", None),
        (1, "state", "PAUSED"),
        (1, "manifest_id", uid(99)),
        (1, "payload_hash", "0" * 64),
        (1, "payload_json", "{}"),
        (1, "metric_profile_version", None),
        (1, "metric_profile_hash", "not-hash"),
        (2, "tenant_id", uid(99)),
        (2, "rule_id", uid(99)),
        (2, "source_snapshot_id", uid(99)),
        (2, "sealed", 0),
        (2, "sealed", True),
        (2, "member_count", None),
        (2, "member_count", 0),
        (2, "member_count", True),
        (2, "member_count", 50001),
        (2, "source_kind", "UNKNOWN"),
        (2, "member_ids_hash", None),
        (2, "account_source_snapshot_id", uid(99)),
        (2, "rule_source_snapshot_id", None),
    ],
)
def test_corruption_exact503_not_zero_or_partial_result(part, key, value):
    rows = list(sample())
    rows[part][key] = value
    with pytest.raises(OrbitError) as caught:
        core.definition_response(*rows)
    assert (caught.value.status, caught.value.code) == (503, "RULE_DEFINITION_UNAVAILABLE")


@pytest.mark.parametrize("part", [1, 2])
def test_missing_version_or_manifest_is_corruption_not_foreign404(part):
    rows = list(sample())
    rows[part] = None
    with pytest.raises(OrbitError) as caught:
        core.definition_response(*rows)
    assert caught.value.code == "RULE_DEFINITION_UNAVAILABLE"


class Session:
    def __init__(self):
        self.rows = sample()
        self.sql = []

    async def execute(self, statement, values):
        sql = str(statement)
        self.sql.append((sql, copy.deepcopy(values)))
        if "orbit_rule_clock" in sql:
            return result([{"revision": 3}])
        for index, table in enumerate(("head", "version", "scope_manifest")):
            if "FROM orbit_rule_" + table in sql:
                value = self.rows[index]
                return result([value] if value is not None else [])
        raise AssertionError("UNEXPECTED_QUERY")


@pytest.mark.asyncio
async def test_exact_current_lock_order_real_rowmapping_and_final_original_action(monkeypatch):
    session = Session()
    access = SimpleNamespace(current=SimpleNamespace(tenant_id=uid(1)))
    authorize = AsyncMock(return_value=access)
    finish = AsyncMock()
    monkeypatch.setattr(core, "authorize_rule", authorize)
    monkeypatch.setattr(core, "require_rule_visible", lambda a, row: None)
    monkeypatch.setattr(core, "revalidate_access", finish)
    value = await core.RuleEditorDefinitionStore().get(session, 91, uid(2))
    authorize.assert_awaited_once_with(session, 91, "rules.edit")
    finish.assert_awaited_once_with(session, access)
    assert value["rule"]["revision"] == 3
    assert len(session.sql) == 4 and all("FOR SHARE" in sql for sql, _ in session.sql)
    assert [sql.split(" FROM ")[1].split()[0] for sql, _ in session.sql] == [
        "orbit_rule_clock",
        "orbit_rule_head",
        "orbit_rule_version",
        "orbit_rule_scope_manifest",
    ]
    assert all("scope_member" not in sql and "profile" not in sql for sql, _ in session.sql)


@pytest.mark.asyncio
async def test_revoked_action_before_business_sql_and_again_after_read(monkeypatch):
    session = Session()
    denied = OrbitError(403, "PERMISSION_DENIED", "pure")
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(side_effect=denied))
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorDefinitionStore().get(session, 91, uid(2))
    assert caught.value is denied and session.sql == []
    monkeypatch.setattr(
        core,
        "authorize_rule",
        AsyncMock(return_value=SimpleNamespace(current=SimpleNamespace(tenant_id=uid(1)))),
    )
    monkeypatch.setattr(core, "require_rule_visible", lambda a, row: None)
    monkeypatch.setattr(core, "revalidate_access", AsyncMock(side_effect=denied))
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorDefinitionStore().get(session, 91, uid(2))
    assert caught.value is denied and len(session.sql) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["owner", "tenant", "absent"])
async def test_original_real_visibility_hides_foreign_before_version_or_manifest(
    monkeypatch, foreign
):
    session = Session()
    head, _, _ = session.rows
    current = BusinessContext(91, uid(1), "USER", head["owner_user_id"], head["owner_team_id"])
    access = access_core.RuleAccess(
        current, "rules.edit", 1, (), "a" * 64, session, object(), access_core._ISSUER
    )
    if foreign == "absent":
        session.rows = (None, *session.rows[1:])
    elif foreign == "tenant":
        head["tenant_id"] = uid(88)
    else:
        head["owner_user_id"] = uid(99)
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(return_value=access))
    with pytest.raises(OrbitError) as caught:
        await core.RuleEditorDefinitionStore().get(session, 91, uid(2))
    assert (caught.value.status, caught.value.code) == (404, "NOT_FOUND")
    assert len(session.sql) == 2


@pytest.fixture
def route(monkeypatch):
    from starlette.datastructures import Headers

    async def dep():
        pass

    def read_boundary(request):
        if request.query_params:
            raise OrbitError(400, "UNKNOWN_FIELD", "pure")
        if "x-target-tenant" in Headers(scope=request.scope):
            raise OrbitError(403, "PERMISSION_DENIED", "pure")

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dep)},
        "config.database": {"DataSourceRegistry": SimpleNamespace()},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {"_read_boundary": read_boundary},
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(core.__file__).with_name("rule_editor_definition_routes.py")
    spec = importlib.util.spec_from_file_location("pure_definition_route", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(*, query=b"", headers=(), body=b""):
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "GET", "path": "/", "query_string": query, "headers": headers},
        receive,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,status",
    [
        ({"query": b"owner=untrusted"}, 400),
        ({"body": b"{}"}, 400),
        ({"headers": [(b"x-target-tenant", b"other")]}, 403),
    ],
)
async def test_actual_route_boundary_before_database(route, values, status):
    with pytest.raises(OrbitError) as caught:
        await route.edit_definition(uid(2), request(**values), SimpleNamespace())
    assert caught.value.status == status


@pytest.mark.asyncio
async def test_actual_route_one_outer_transaction_and_no_cipher_env_dependency(route, monkeypatch):
    events = []
    session = SimpleNamespace()

    @asynccontextmanager
    async def begin():
        events.append("begin")
        yield
        events.append("end")

    @asynccontextmanager
    async def sessions(*, log_sql):
        assert log_sql is False
        yield session

    session.begin = begin
    route.DataSourceRegistry.session = sessions
    expected = core.definition_response(*sample())

    async def get(self, _session, actor, rule_id):
        assert events == ["begin"] and _session is session and actor == 91 and rule_id == uid(2)
        return expected

    monkeypatch.setattr(route.RuleEditorDefinitionStore, "get", get)
    value = await route.edit_definition(
        uid(2), request(), SimpleNamespace(user=SimpleNamespace(user_id=91))
    )
    assert value == expected and events == ["begin", "end"]
