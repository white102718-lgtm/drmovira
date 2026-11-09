"""调度预览纯合同/真实路由适配，不能当SQL/浏览器调度验收。"""

import base64
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from pydantic import BaseModel
from starlette.requests import Request
from test_rule_editor_definition import result, sample, uid
from test_rule_schedule import schedule

import orbit_api.rule_schedule_preview as core
from orbit_api.authorization import BusinessContext
from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError

NOW = datetime(2026, 3, 7, 0, 0, 0, 123499, tzinfo=UTC)
CURRENT = BusinessContext(91, uid(1), "USER", uid(3), uid(4))


def body(**updates):
    return {
        "action": "CREATE",
        "rule_id": None,
        "rule_revision": None,
        "schedule": schedule(),
    } | updates


def parsed(**updates):
    return core.parse_preview_request(canonical(body(**updates)).encode())


@pytest.mark.parametrize(
    "update,status",
    [
        ({"action": "EDIT"}, 422),
        ({"rule_id": uid(1)}, 422),
        ({"rule_revision": 1}, 422),
        ({"action": "UPDATE"}, 422),
        ({"action": "UPDATE", "rule_id": uid(2), "rule_revision": True}, 422),
        ({"schedule": {**schedule(), "weekday": True}}, 400),
        ({"extra": 1}, 400),
    ],
)
def test_strict_four_keys_original_schedule_and_action_revision(update, status):
    with pytest.raises(OrbitError) as caught:
        parsed(**update)
    assert caught.value.status == status


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b'{"action":"CREATE","action":"UPDATE"}',
        b'{"schedule":{"timezone":"UTC","timezone":"Asia/Shanghai"}}',
    ],
)
def test_duplicate_or_nonobject_json_not_silently_overwritten(raw):
    with pytest.raises(OrbitError) as caught:
        core.parse_preview_request(raw)
    assert caught.value.status == 400


def test_original_schedule_limits_and_internal_body_bound():
    value = body()
    del value["rule_revision"]
    with pytest.raises(OrbitError) as caught:
        core.parse_preview_request(canonical(value).encode())
    assert caught.value.status == 400
    with pytest.raises(OrbitError) as caught:
        core.parse_preview_request(b" " * (core.MAX_BODY + 1))
    assert caught.value.status == 413


def test_future_five_local_offset_zone_utc_and_reference_exact_microseconds():
    value = core.schedule_preview_response(
        schedule(start_date="2026-03-07", end_date="2026-03-20"), NOW
    )
    assert set(value) == {"reference_at", "timezone", "slots", "skipped_local_times"}
    assert value["reference_at"] == "2026-03-07T00:00:00.123499Z"
    assert value["timezone"] == "Asia/Shanghai" and len(value["slots"]) == 5
    assert value["slots"][0] == {
        "local_time": "2026-03-07T10:00:00+08:00",
        "utc_time": "2026-03-07T02:00:00.000000Z",
    }
    assert value["skipped_local_times"] == []


def test_nonexistent_dst_wall_not_assigned_fake_offset_or_utc_and_overlap_once():
    value = core.schedule_preview_response(
        schedule(
            timezone="America/New_York",
            time_of_day="02:30",
            start_date="2026-03-07",
            end_date="2026-03-09",
        ),
        NOW,
    )
    assert value["skipped_local_times"] == [
        {"local_time": "2026-03-08T02:30:00", "reason_code": "DST_NONEXISTENT_LOCAL_TIME"}
    ]
    assert [slot["utc_time"] for slot in value["slots"]] == [
        "2026-03-07T07:30:00.000000Z",
        "2026-03-09T06:30:00.000000Z",
    ]
    overlap = core.schedule_preview_response(
        schedule(
            timezone="America/New_York",
            time_of_day="01:30",
            start_date="2026-11-01",
            end_date="2026-11-02",
        ),
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert overlap["slots"][0]["utc_time"] == "2026-11-01T05:30:00.000000Z"
    assert len(overlap["slots"]) == 2


def test_expired_schedule_is_real_empty_not_manufactured_future_slots():
    value = core.schedule_preview_response(schedule(), NOW)
    assert value["slots"] == [] and value["skipped_local_times"] == []


class Session:
    def __init__(self, *, clock=True):
        self.clock = {"revision": 1, "reference_at": NOW.replace(tzinfo=None)} if clock else None
        self.head, self.version, _ = sample()
        self.sql = []

    async def execute(self, statement, values=None):
        sql = str(statement)
        self.sql.append(sql)
        if "FROM orbit_rule_clock" in sql:
            return result([self.clock] if self.clock else [])
        if "FROM orbit_rule_head" in sql:
            return result([self.head] if self.head else [])
        if "FROM orbit_rule_version" in sql:
            return result([self.version] if self.version else [])
        if sql == "SELECT UTC_TIMESTAMP(6)":
            return result([{"now": NOW.replace(tzinfo=None)}])
        raise AssertionError("UNEXPECTED_PREVIEW_SQL")


@pytest.fixture
def harness(monkeypatch):
    cipher = CredentialCipher("pure", {"pure": base64.b64encode(b"s" * 32).decode()})
    tokens = DirectoryTokens(cipher)
    access = SimpleNamespace(current=CURRENT)
    authorization = "Bearer preview-pure-session"
    csrf = tokens.issue(
        "DIRECTORY_CSRF_V1", {"binding": tokens.session_binding(authorization, 91, uid(1))}
    )
    auth, finish = AsyncMock(return_value=access), AsyncMock()
    monkeypatch.setattr(core, "authorize_rule", auth)
    monkeypatch.setattr(
        core,
        "require_rule_visible",
        lambda a, row: None if row else (_ for _ in ()).throw(OrbitError(404, "NOT_FOUND", "pure")),
    )
    monkeypatch.setattr(core, "revalidate_access", finish)
    return core.RuleSchedulePreviewStore(tokens), authorization, csrf, auth, finish


@pytest.mark.asyncio
@pytest.mark.parametrize("clock", [True, False])
async def test_create_first_use_without_clock_never_inserts_or_forces_revision_zero(harness, clock):
    store, authorization, csrf, auth, finish = harness
    session = Session(clock=clock)
    value = await store.preview(session, 91, authorization, csrf, parsed())
    auth.assert_awaited_once_with(session, 91, "rules.create")
    finish.assert_awaited_once()
    assert value["reference_at"] == "2026-03-07T00:00:00.123499Z"
    assert len(session.sql) == (1 if clock else 2)
    assert all(sql.startswith("SELECT ") for sql in session.sql)


@pytest.mark.asyncio
async def test_update_current_cas_only_edit_no_profile_or_scope_reads(harness):
    store, authorization, csrf, auth, _ = harness
    session = Session()
    await store.preview(
        session, 91, authorization, csrf, parsed(action="UPDATE", rule_id=uid(2), rule_revision=3)
    )
    auth.assert_awaited_once_with(session, 91, "rules.edit")
    assert len(session.sql) == 3 and all("FOR SHARE" in sql for sql in session.sql)
    assert all("profile" not in sql and "scope_" not in sql for sql in session.sql)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,status,code",
    [
        ("cas", 409, "REVISION_CONFLICT"),
        ("version", 503, "RULE_SCHEDULE_PREVIEW_UNAVAILABLE"),
        ("clock", 503, "RULE_SCHEDULE_PREVIEW_UNAVAILABLE"),
        ("foreign", 404, "NOT_FOUND"),
    ],
)
async def test_update_real_missing_or_foreign_not_swallowed(harness, case, status, code):
    store, authorization, csrf, _, _ = harness
    session = Session(clock=case != "clock")
    if case == "version":
        session.version = None
    if case == "foreign":
        session.head = None
    with pytest.raises(OrbitError) as caught:
        await store.preview(
            session,
            91,
            authorization,
            csrf,
            parsed(action="UPDATE", rule_id=uid(2), rule_revision=2 if case == "cas" else 3),
        )
    assert (caught.value.status, caught.value.code) == (status, code)


@pytest.mark.asyncio
async def test_bad_csrf_before_business_sql_and_revocation_at_end(harness):
    store, authorization, csrf, _, finish = harness
    session = Session()
    with pytest.raises(OrbitError) as caught:
        await store.preview(session, 91, authorization, "bad-token", parsed())
    assert caught.value.code == "CSRF_INVALID" and session.sql == []
    finish.side_effect = OrbitError(403, "PERMISSION_DENIED", "pure")
    with pytest.raises(OrbitError) as caught:
        await store.preview(session, 91, authorization, csrf, parsed())
    assert caught.value.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_cancel_propagates_no_response_and_input_schedule_detached(harness):
    import asyncio

    store, authorization, csrf, auth, _ = harness
    session, request = (
        Session(),
        parsed(schedule=schedule(start_date="2026-03-07", end_date="2026-03-20")),
    )

    async def change(*args):
        request.schedule.timezone = "UTC"
        return SimpleNamespace(current=CURRENT)

    auth.side_effect = change
    value = await store.preview(session, 91, authorization, csrf, request)
    assert value["timezone"] == "Asia/Shanghai"
    auth.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await store.preview(session, 91, authorization, csrf, parsed())


@pytest.fixture
def route(monkeypatch):
    async def dependency():
        pass

    def boundary(request):
        if request.query_params:
            raise OrbitError(400, "UNKNOWN_FIELD", "pure")
        if "x-target-tenant" in request.headers:
            raise OrbitError(403, "PERMISSION_DENIED", "pure")

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dependency)},
        "config.database": {"DataSourceRegistry": SimpleNamespace()},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {
            "_read_boundary": boundary,
            "credential_cipher": lambda: None,
        },
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(core.__file__).with_name("rule_schedule_preview_routes.py")
    spec = importlib.util.spec_from_file_location("pure_schedule_preview_route", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(headers=(), *, query=b"", raw=None):
    async def receive():
        return {
            "type": "http.request",
            "body": canonical(body()).encode() if raw is None else raw,
            "more_body": False,
        }

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": list(headers),
            "query_string": query,
        },
        receive,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers,status",
    [
        ([], 403),
        ([(b"x-csrf-token", b"x" * 20)] * 2, 403),
        ([(b"if-match", b'"1"')], 400),
        ([(b"idempotency-key", b"x" * 20)], 400),
        ([(b"x-target-tenant", b"foreign")], 403),
    ],
)
async def test_actual_route_head_contract_before_database(route, headers, status):
    with pytest.raises(OrbitError) as caught:
        await route.editor_schedule_preview(request(headers), SimpleNamespace())
    assert caught.value.status == status


@pytest.mark.asyncio
async def test_actual_route_bounded_body_query_and_parser(route):
    headers = [(b"x-csrf-token", b"x" * 20)]
    value, csrf = await route.preview_boundary(request(headers))
    assert value.action == "CREATE" and csrf == "x" * 20
    for kwargs, status in (({"raw": b" " * (core.MAX_BODY + 1)}, 413), ({"query": b"q=1"}, 400)):
        with pytest.raises(OrbitError) as caught:
            await route.preview_boundary(request(headers, **kwargs))
        assert caught.value.status == status
