"""原规则HTTP适配合同纯测；框架/Store替身不是真实鉴权、SQL或来源验收。"""

import copy
import importlib.util
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.requests import Request
from test_rule_contract import ID, sample_rule

from orbit_api.errors import OrbitError

KEY = "original-rule-key-0001"
CSRF = "original-rule-csrf-0001"
BEARER = "Bearer original-rule-session"


def request(*, value=None, raw=None, query="", headers=None, method="POST"):
    data = json.dumps(value).encode() if value is not None else raw or b""
    delivered = False

    async def receive():
        nonlocal delivered
        assert not delivered
        delivered = True
        return {"type": "http.request", "body": data, "more_body": False}

    values = [
        (b"authorization", BEARER.encode()),
        (b"idempotency-key", KEY.encode()),
        (b"x-csrf-token", CSRF.encode()),
    ]
    if headers is not None:
        values = [(key.lower().encode(), value.encode()) for key, value in headers]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/rules",
            "query_string": query.encode(),
            "headers": values,
            "state": {"orbit_request_id": ID},
        },
        receive,
    )


@pytest.fixture
def harness(monkeypatch):
    events = []
    session = SimpleNamespace()

    @asynccontextmanager
    async def begin():
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    session.begin = begin

    @asynccontextmanager
    async def sessions(*, log_sql):
        assert log_sql is False
        events.append("session")
        try:
            yield session
        finally:
            events.append("exit")

    async def dependency():
        return None

    for name, attrs in {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dependency)},
        "config.database": {"DataSourceRegistry": SimpleNamespace(session=sessions)},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {"credential_cipher": lambda: None},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "rule_routes_pure_under_test", Path(__file__).parents[1] / "orbit_api/rule_routes.py"
    )
    route = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(route)
    rule = sample_rule() | {"id": ID, "revision": 1, "state": "DRAFT", "next_run_at": None}
    page = {
        "items": [rule],
        "next_cursor": None,
        "data_as_of": "2026-11-09T00:00:00.000Z",
        "scope_version": 1,
    }
    service = SimpleNamespace(
        **{
            name: AsyncMock(return_value=copy.deepcopy(rule))
            for name in ("get", "save", "stop", "enable")
        }
    )
    service.list = AsyncMock(return_value=page)
    service.runs = AsyncMock(return_value=dict(page, items=[]))
    service.capabilities = AsyncMock(return_value={"csrf_token": CSRF})
    service.simulate = AsyncMock(
        return_value={
            "id": ID,
            "rule_id": ID,
            "revision": 1,
            "snapshot_id": ID,
            "hash": "a" * 64,
            "account_count": 1,
            "scanned_count": 1,
            "hit_count": 0,
            "unknown_count": 1,
            "false_count": 0,
            "conditions": [],
            "expires_at": "2026-11-09T00:15:00.000Z",
            "next_cursor": None,
        }
    )
    monkeypatch.setattr(route, "store", lambda: service)
    return SimpleNamespace(
        route=route,
        service=service,
        events=events,
        session=session,
        user=SimpleNamespace(user=SimpleNamespace(user_id=31)),
        rule=rule,
    )


def write_request(*, value=None, raw=None, query="", revision='"1"', extra=()):
    headers = [("Authorization", BEARER), ("Idempotency-Key", KEY), ("X-CSRF-Token", CSRF)]
    if revision is not None:
        headers.append(("If-Match", revision))
    headers.extend(extra)
    return request(value=value, raw=raw, query=query, headers=headers)


def test_original_nine_routes_plus_capabilities_and_create_status(harness):
    routes = {
        (tuple(sorted(item.methods)), item.path): item for item in harness.route.router.routes
    }
    assert len(routes) == 10
    assert routes[(("POST",), "/api/v1/rules")].status_code == 201
    assert routes[(("GET",), "/api/v1/rules/capabilities")]
    paths = [item.path for item in harness.route.router.routes]
    assert paths.index("/api/v1/rules/capabilities") < paths.index("/api/v1/rules/{rule_id}")
    for name in ("archive", "simulate", "enable", "pause"):
        assert (("POST",), "/api/v1/rules/{rule_id}/" + name) in routes


async def test_create_strict_original_body_and_actor_are_forwarded_once(harness):
    result = await harness.route.create_rule(request(value=sample_rule()), harness.user)
    assert result == harness.rule and len(result) == 15
    args = harness.service.save.await_args.args
    assert args[:5] == (harness.session, 31, BEARER, CSRF, KEY)
    assert args[5].model_dump() == sample_rule()
    assert args[6:] == (None, None, ID)
    assert harness.events == ["session", "begin", "commit", "exit"]


async def test_put_exact_quoted_ifmatch_and_uuid(harness):
    await harness.route.update_rule(ID.upper(), write_request(value=sample_rule()), harness.user)
    assert harness.service.save.await_args.args[6:] == (ID, 1, ID)


@pytest.mark.parametrize(
    "revision,status",
    [
        (None, 400),
        ("1", 400),
        ('"0"', 400),
        ('"01"', 400),
        ('"9007199254740992"', 422),
        ('"' + "9" * 10000 + '"', 422),
    ],
)
async def test_invalid_ifmatch_never_opens_transaction(harness, revision, status):
    with pytest.raises(OrbitError) as caught:
        await harness.route.update_rule(
            ID, write_request(value=sample_rule(), revision=revision), harness.user
        )
    assert caught.value.status == status
    assert harness.events == []


async def test_create_rejects_ifmatch_even_valid(harness):
    with pytest.raises(OrbitError) as caught:
        await harness.route.create_rule(write_request(value=sample_rule()), harness.user)
    assert (caught.value.status, caught.value.pointer) == (400, "/If-Match")
    assert harness.events == []


@pytest.mark.parametrize(
    "extra,status,code",
    [
        (("Idempotency-Key", KEY), 400, "IDEMPOTENCY_KEY_INVALID"),
        (("X-CSRF-Token", CSRF), 403, "CSRF_INVALID"),
        (("If-Match", '"1"'), 400, "REVISION_REQUIRED"),
        (("X-Target-Tenant", ID), 403, "PERMISSION_DENIED"),
    ],
)
async def test_duplicate_headers_and_target_tenant_fail_before_store(harness, extra, status, code):
    with pytest.raises(OrbitError) as caught:
        await harness.route.update_rule(
            ID, write_request(value=sample_rule(), extra=(extra,)), harness.user
        )
    assert (caught.value.status, caught.value.code) == (status, code)
    assert harness.events == []


@pytest.mark.parametrize(
    "query,status,path",
    [
        ("q=x&q=y", 400, "/q"),
        ("unexpected=yes", 400, "/unexpected"),
        ("q=" + "x" * 101, 422, "/q"),
        ("page_size=500", 422, "/page_size"),
        ("date_from=2026-01-01", 422, "/date_from"),
    ],
)
async def test_list_original_query_boundaries(harness, query, status, path):
    with pytest.raises(OrbitError) as caught:
        await harness.route.list_rules(request(query=query), harness.user)
    assert (caught.value.status, caught.value.pointer) == (status, path)
    assert harness.events == []


async def test_list_empty_q_is_unfiltered_and_hundred_char_q_retained(harness):
    await harness.route.list_rules(request(query="q="), harness.user)
    assert harness.service.list.await_args.args[2].q is None
    await harness.route.list_rules(request(query="q=" + "x" * 100), harness.user)
    assert harness.service.list.await_args.args[2].q == "x" * 100


@pytest.mark.parametrize("endpoint", ["get_rule", "list_runs"])
async def test_read_route_rejects_any_body(harness, endpoint):
    with pytest.raises(OrbitError) as caught:
        await getattr(harness.route, endpoint)(ID, request(raw=b" ", method="GET"), harness.user)
    assert caught.value.status == 400 and harness.events == []


async def test_simulate_is_original_empty_body_and_exact_store_call(harness):
    await harness.route.simulate_rule(ID, write_request(), harness.user)
    assert harness.service.simulate.await_args.args == (
        harness.session,
        31,
        BEARER,
        CSRF,
        KEY,
        ID,
        1,
        ID,
    )
    with pytest.raises(OrbitError) as caught:
        await harness.route.simulate_rule(ID, write_request(raw=b"{}"), harness.user)
    assert caught.value.status == 400


@pytest.mark.parametrize(
    "name,body,attribute",
    [
        ("archive_rule", {"reason": "归档"}, "stop"),
        ("pause_rule", {"reason": "暂停"}, "stop"),
        ("enable_rule", {"simulation_id": ID}, "enable"),
    ],
)
async def test_actions_keep_original_fields_and_no_extra_permissions(
    harness, name, body, attribute
):
    await getattr(harness.route, name)(ID, write_request(value=body), harness.user)
    call = getattr(harness.service, attribute).await_args
    assert call.args[:7] == (harness.session, 31, BEARER, CSRF, KEY, ID, 1)
    assert call.args[7:] == (body.get("reason", ID), ID)
    assert call.kwargs == ({"archive": name == "archive_rule"} if attribute == "stop" else {})


@pytest.mark.parametrize(
    "query,path",
    [
        ("status=ENABLED", "/status"),
        ("date_from=2026-02-30", "/date_from"),
        ("date_from=2026-02-02&date_to=2026-01-01", "/date_from"),
        ("metric_profile_id=not-uuid", "/metric_profile_id"),
        ("channel_id=" + "x" * 65, "/channel_id"),
    ],
)
async def test_runs_validates_original_parameters_before_unavailable(harness, query, path):
    with pytest.raises(OrbitError) as caught:
        await harness.route.list_runs(ID, request(query=query), harness.user)
    assert caught.value.status == 422 and caught.value.pointer == path
    assert harness.events == []


async def test_runs_all_original_query_parameters_are_validated_then_real_store_error_preserved(
    harness,
):
    error = OrbitError(503, "RULE_RUN_STORE_UNAVAILABLE", "未接来源")
    harness.service.runs.side_effect = error
    query = (
        "q=test&status=RUNNING&date_from=2026-01-01&date_to=2026-01-31"
        "&operator_user_id="
        + ID
        + "&metric_profile_id="
        + ID
        + "&channel_id=channel&entity_type=AD&page_size=20&cursor=opaque"
    )
    with pytest.raises(OrbitError) as caught:
        await harness.route.list_runs(ID, request(query=query), harness.user)
    assert caught.value is error
    assert harness.events == ["session", "begin", "rollback", "exit"]


@pytest.mark.parametrize("action", ["CREATE", "UPDATE", "ENABLE", "PAUSE", "ARCHIVE", "SIMULATE"])
async def test_capabilities_forwards_original_action_only(harness, action):
    assert await harness.route.capabilities(request(query="action=" + action), harness.user) == {
        "csrf_token": CSRF
    }
    assert harness.service.capabilities.await_args.args == (harness.session, 31, BEARER, action)


async def test_corrupt_success_dto_rolls_back_before_return(harness):
    harness.service.save.return_value = dict(harness.rule, unknown="PRIVATE")
    with pytest.raises(OrbitError) as caught:
        await harness.route.create_rule(request(value=sample_rule()), harness.user)
    assert (caught.value.status, caught.value.code) == (503, "RULE_STATE_UNAVAILABLE")
    assert "PRIVATE" not in caught.value.message
    assert harness.events == ["session", "begin", "rollback", "exit"]


async def test_sql_deadlock_propagates_once_without_hidden_retry(harness):
    error = OperationalError("safe", None, Exception(1213))
    harness.service.save.side_effect = error
    with pytest.raises(OperationalError) as caught:
        await harness.route.create_rule(request(value=sample_rule()), harness.user)
    assert caught.value is error and harness.service.save.await_count == 1
    assert harness.events == ["session", "begin", "rollback", "exit"]


async def test_streamed_body_limit_fails_without_transaction(harness):
    with pytest.raises(OrbitError) as caught:
        await harness.route.create_rule(
            request(raw=b"x" * (harness.route.MAX_BODY + 1)), harness.user
        )
    assert caught.value.status == 413 and harness.events == []
