"""规则展示元数据纯合同/实际路由函数适配；不运行SQL/HTTP服务或私有env。"""

import importlib.util
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from test_rule_editor_definition import request, result, sample, uid

import orbit_api.rule_access as access_core
import orbit_api.rule_display_metadata_contract as contract
import orbit_api.rule_display_metadata_store as core
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError

NOW = datetime(2026, 11, 9, 1, 2, 3, 123000)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        uid(1) + ",",
        uid(1) + "," + uid(1),
        uid(1) + ", " + uid(2),
        "{not-uuid}",
        "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB",
        ",".join(uid(i) for i in range(201)),
    ],
)
def test_csv_is_canonical_unique_bounded_and_never_trimmed(value):
    with pytest.raises(OrbitError) as error:
        contract.parse_rule_ids(value)
    assert (error.value.status, error.value.code) == (422, "FIELD_INVALID")


def test_csv_preserves_requested_order_and_accepts_full_two_hundred():
    ids = tuple(uid(i) for i in reversed(range(200)))
    assert contract.parse_rule_ids(",".join(ids)) == ids


def item(**changes):
    return {
        "rule_id": uid(2),
        "revision": 3,
        "owner_user_name": "真实投手",
        "owner_team_name": "真实团队",
        "created_by": 91,
        "created_by_name": None,
        "created_at": "2026-11-09T01:02:03.123Z",
    } | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"created_by": True},
        {"revision": 0},
        {"created_at": "2026-11-09T01:02:03Z"},
        {"created_at": "2026-02-30T01:02:03.123Z"},
        {"owner_user_name": "x" * 51},
        {"owner_team_name": "x" * 101},
        {"created_by_name": "n\n"},
        {"owner_team_name": "e\u0301"},
        {"owner_user_name": " name"},
        {"owner_user_name": "a\u200b"},
        {"unexpected": "value"},
    ],
)
def test_bad_persistent_metadata_is_exact503_without_fake_defaults(changes):
    with pytest.raises(OrbitError) as error:
        contract.metadata_response([item(**changes)])
    assert (error.value.status, error.value.code) == (503, "RULE_DISPLAY_METADATA_UNAVAILABLE")


def test_nullable_actual_labels_and_unicode_codepoint_boundary():
    value = item(owner_user_name=None, owner_team_name=None, created_by_name="😀" * 50)
    assert contract.metadata_response([value]) == {"items": [value]}
    assert (
        contract.created_at_text(NOW)
        == contract.created_at_text(NOW.replace(tzinfo=UTC))
        == value["created_at"]
    )
    for invalid in (
        NOW.replace(microsecond=123499),
        NOW.replace(tzinfo=timezone(timedelta(hours=1))),
        None,
    ):
        with pytest.raises(OrbitError):
            contract.created_at_text(invalid)


class Fixture:
    def __init__(self, monkeypatch, session, count=2):
        head, version, _ = sample()
        self.rows = [
            dict(head) | dict(version) | {"id": uid(100 + i), "created_by": 91, "created_at": NOW}
            for i in range(count)
        ]
        self.ids = tuple(row["id"] for row in reversed(self.rows))
        current = BusinessContext(
            91, head["tenant_id"], "USER", head["owner_user_id"], head["owner_team_id"]
        )
        self.access = access_core.RuleAccess(
            current,
            "rules.read",
            1,
            (),
            "a" * 64,
            session,
            session.sync_session.get_transaction(),
            access_core._ISSUER,
        )
        self.names = [
            {"resource_kind": "OWNER", "ref_id": head["owner_user_id"], "label": "投手甲"},
            {"resource_kind": "TEAM", "ref_id": head["owner_team_id"], "label": "团队甲"},
            {"resource_kind": "CREATOR", "ref_id": "91", "label": "创建者甲"},
        ]
        self.calls = []
        self.auth = AsyncMock(return_value=self.access)
        self.final = AsyncMock()
        monkeypatch.setattr(core, "authorize_rule", self.auth)
        monkeypatch.setattr(core, "revalidate_access", self.final)

        async def execute(statement, params):
            statement = str(statement)
            self.calls.append((statement, params))
            if "FROM orbit_rule_clock" in statement:
                return result([{"revision": 7, "now": NOW}])
            if "FROM orbit_rule_head" in statement:
                return result(self.rows)
            if "UNION ALL" in statement:
                return result(self.names)
            raise AssertionError("unexpected_query")

        session.execute = execute


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 200])
async def test_batch_head_version_and_single_name_union_no_n_plus_one_preserve_original_read_scope(
    monkeypatch, count
):
    async with AsyncSession() as session, session.begin():
        fixture = Fixture(monkeypatch, session, count)
        actual = await core.RuleDisplayMetadataStore().get(session, 91, fixture.ids)
        assert [row["rule_id"] for row in actual["items"]] == list(fixture.ids)
        assert all(
            row["owner_user_name"] == "投手甲"
            and row["owner_team_name"] == "团队甲"
            and row["created_by_name"] == "创建者甲"
            for row in actual["items"]
        )
        fixture.auth.assert_awaited_once_with(session, 91, "rules.read")
        fixture.final.assert_awaited_once_with(session, fixture.access)
        assert len(fixture.calls) == 3
        assert "FOR SHARE OF h,v" in fixture.calls[1][0]
        assert (
            fixture.calls[2][0].count("UNION ALL") == 2 and "FOR SHARE" not in fixture.calls[2][0]
        )
        # 实际MySQL1271回归：九个UNION输出显式同字符集/collation，
        # CAST保留nativeID全精度，不lower/截断/重命名真实字段。
        from sqlalchemy.dialects.mysql import dialect

        names_sql = fixture.calls[2][0]
        assert names_sql.count("COLLATE utf8mb4_0900_as_cs") == 9
        assert names_sql.count("USING utf8mb4") == 8
        assert "CAST(b.user_id AS CHAR CHARACTER SET utf8mb4)" in names_sql
        assert "LOWER(" not in names_sql and "CHAR(36)" not in names_sql
        assert str(core.text(names_sql).compile(dialect=dialect())).count("UNION ALL") == 2
        assert fixture.calls[2][1]["tenant"] == fixture.access.current.tenant_id
        assert all(sql.startswith("SELECT") for sql, _ in fixture.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["absent", "foreign_owner", "foreign_tenant", "bad_payload", "created_at", "created_by"]
)
async def test_any_invisible_or_bad_rule_rejects_entire_batch_before_names(monkeypatch, kind):
    async with AsyncSession() as session, session.begin():
        fixture = Fixture(monkeypatch, session)
        if kind == "absent":
            fixture.rows.pop()
        elif kind == "foreign_owner":
            fixture.rows[1]["owner_user_id"] = uid(99)
        elif kind == "foreign_tenant":
            fixture.rows[1]["tenant_id"] = uid(99)
        elif kind == "bad_payload":
            fixture.rows[1]["payload_hash"] = "0" * 64
        elif kind == "created_at":
            fixture.rows[1]["created_at"] = None
        else:
            fixture.rows[1]["created_by"] = True
        with pytest.raises(OrbitError) as error:
            await core.RuleDisplayMetadataStore().get(session, 91, fixture.ids)
        assert error.value.status == (404 if kind.startswith(("absent", "foreign")) else 503)
        assert len(fixture.calls) == 2


@pytest.mark.asyncio
async def test_names_are_nullable_without_fallback_and_bad_or_unrequested_name_rows_reject(
    monkeypatch,
):
    async with AsyncSession() as session, session.begin():
        fixture = Fixture(monkeypatch, session)
        fixture.names = []
        actual = await core.RuleDisplayMetadataStore().get(session, 91, fixture.ids)
        assert all(
            row["owner_user_name"] is None
            and row["owner_team_name"] is None
            and row["created_by_name"] is None
            for row in actual["items"]
        )
        fixture.names = [{"resource_kind": "OWNER", "ref_id": uid(999), "label": "foreign"}]
        with pytest.raises(OrbitError) as error:
            await core.RuleDisplayMetadataStore().get(session, 91, fixture.ids)
        assert error.value.status == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["initial", "final"])
async def test_current_read_revocation_is_never_bypassed(monkeypatch, when):
    async with AsyncSession() as session, session.begin():
        fixture = Fixture(monkeypatch, session)
        failure = OrbitError(403, "PERMISSION_DENIED", "无")
        (fixture.auth if when == "initial" else fixture.final).side_effect = failure
        with pytest.raises(OrbitError) as error:
            await core.RuleDisplayMetadataStore().get(session, 91, fixture.ids)
        assert error.value is failure
        assert len(fixture.calls) == (0 if when == "initial" else 3)


@pytest.fixture
def route(monkeypatch):
    async def dep():
        pass

    def boundary(request, allowed):
        assert allowed == {"rule_ids"}
        if set(request.query_params) - allowed:
            raise OrbitError(400, "UNKNOWN_FIELD", "未知")
        if "x-target-tenant" in request.headers:
            raise OrbitError(403, "PERMISSION_DENIED", "无")
        for key in request.query_params:
            if len(request.query_params.getlist(key)) != 1:
                raise OrbitError(400, "INVALID_STRUCTURE", "重复")

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dep)},
        "config.database": {"DataSourceRegistry": SimpleNamespace()},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {"_read_boundary": boundary},
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(core.__file__).with_name("rule_display_metadata_routes.py")
    spec = importlib.util.spec_from_file_location("pure_rule_metadata_routes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,status,code",
    [
        ({"query": b"q=unknown"}, 400, "UNKNOWN_FIELD"),
        (
            {"query": ("rule_ids=" + uid(1) + "&rule_ids=" + uid(2)).encode()},
            400,
            "INVALID_STRUCTURE",
        ),
        ({"query": ("rule_ids=" + uid(1)).encode(), "body": b"{}"}, 400, "INVALID_STRUCTURE"),
        (
            {"query": ("rule_ids=" + uid(1)).encode(), "headers": [(b"x-target-tenant", b"other")]},
            403,
            "PERMISSION_DENIED",
        ),
        ({}, 422, "FIELD_INVALID"),
    ],
)
async def test_actual_route_boundary_rejects_before_database(route, values, status, code):
    with pytest.raises(OrbitError) as error:
        await route.display_metadata(request(**values), SimpleNamespace())
    assert (error.value.status, error.value.code) == (status, code)


@pytest.mark.asyncio
async def test_actual_route_exact_ids_one_outer_transaction_no_env_or_cipher(route, monkeypatch):
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

    async def get(self, actual, actor, ids):
        assert actual is session and actor == 91 and ids == (uid(2), uid(1)) and events == ["begin"]
        return {"items": [item()]}

    monkeypatch.setattr(route.RuleDisplayMetadataStore, "get", get)
    actual = await route.display_metadata(
        request(query=("rule_ids=" + uid(2) + "," + uid(1)).encode()),
        SimpleNamespace(user=SimpleNamespace(user_id=91)),
    )
    assert actual == {"items": [item()]} and events == ["begin", "end"]


@pytest.mark.asyncio
async def test_unexpected_database_diagnostic_keeps_original_error_and_never_sql(
    route, monkeypatch, capsys
):
    import json

    from sqlalchemy.exc import OperationalError

    session = SimpleNamespace()

    @asynccontextmanager
    async def begin():
        yield

    @asynccontextmanager
    async def sessions(**kwargs):
        yield session

    session.begin = begin
    route.DataSourceRegistry.session = sessions
    original = OperationalError(
        "secret-statement", {"token": "secret-param"}, Exception(1271, "secret-driver-message")
    )

    async def get(*args):
        raise original

    monkeypatch.setattr(route.RuleDisplayMetadataStore, "get", get)
    with pytest.raises(OperationalError) as failure:
        await route.display_metadata(
            request(query=("rule_ids=" + uid(1)).encode()),
            SimpleNamespace(user=SimpleNamespace(user_id=91)),
        )
    assert failure.value is original
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output) == {
        "scope": "rule-display-metadata",
        "phase": "unexpected",
        "category": "DBAPIError",
        "errno": 1271,
        "store_line": None,
    }
