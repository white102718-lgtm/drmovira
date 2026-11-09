"""规则原九入口与专属CSRF读取；单次外层事务，不重试写操作或伪造模拟。

公共application/菜单注册由主线负责。定义Store不就绪的simulate/enable/runs
原样503，不返回空记录或假资格；本模块不启动调度、AI或平台调用。
"""

import re
from datetime import date
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import pointer
from orbit_api.rule_contract import (
    MAX_SAFE,
    Rule,
    RulePage,
    RuleRunPage,
    Simulation,
    _text,
    identifier,
    invalid,
    parse_rule_action,
    parse_rule_response,
    parse_rule_write,
)
from orbit_api.rule_store import PERMISSIONS, RuleQuery, RuleStore, parse_rule_query

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则定义"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]
MAX_BODY = 2 * 1024 * 1024
QUERIES = set(RuleQuery.__dataclass_fields__) | {"date_from", "date_to", "channel_id"}


def store():
    return RuleStore(DirectoryTokens(credential_cipher()))


def query_boundary(request, allowed=()):
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "此入口不接受指定租户")
    unknown = set(request.query_params) - set(allowed)
    if unknown:
        raise OrbitError(
            400, "UNKNOWN_FIELD", "请求包含未定义查询参数", pointer((sorted(unknown)[0],))
        )
    for key in request.query_params:
        if len(request.query_params.getlist(key)) != 1:
            raise OrbitError(400, "INVALID_STRUCTURE", "查询参数不能重复", pointer((key,)))
    return dict(request.query_params)


async def read_body(request, *, empty=False):
    raw = bytearray()
    async for part in request.stream():
        if empty and part:
            raise OrbitError(400, "INVALID_STRUCTURE", "此入口不接受正文")
        if len(raw) + len(part) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "规则正文超过大小限制")
        raw.extend(part)
    return bytes(raw)


def write_headers(request, *, updating):
    keys, csrf, matches = (
        request.headers.getlist("idempotency-key"),
        request.headers.getlist("x-csrf-token"),
        request.headers.getlist("if-match"),
    )
    if len(keys) != 1 or re.fullmatch(r"[ -~]{16,128}", keys[0]) is None:
        raise OrbitError(400, "IDEMPOTENCY_KEY_INVALID", "需要单一16至128位ASCII幂等键")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_INVALID", "规则会话校验已失效")
    expected = None
    if updating:
        if len(matches) != 1 or re.fullmatch(r'"[1-9][0-9]*"', matches[0]) is None:
            raise OrbitError(400, "REVISION_REQUIRED", "需要单一带引号正整数业务版本")
        digits = matches[0][1:-1]
        if len(digits) > 16 or int(digits) > MAX_SAFE:
            invalid("/If-Match", "业务版本超出安全整数范围")
        expected = int(digits)
    elif matches:
        raise OrbitError(400, "INVALID_STRUCTURE", "新建不能携带If-Match", "/If-Match")
    return keys[0], csrf[0], expected


def collection_query(request, *, runs=False):
    values = query_boundary(request, QUERIES)
    if "q" in values:
        q = values["q"]
        # 原通用query允许空串且最多100码点，不能沿Store内部200上限放宽公开合同。
        if q == "":
            del values["q"]
        else:
            values["q"] = _text(q, "/q", 100, trim=True)
    if not runs:
        return parse_rule_query(values)
    # 运行记录尚无真实Store；合法原query仍503，结构/字段错误不能被依赖错误吞掉。
    status = values.pop("status", None)
    if status is not None and status not in {
        "RUNNING",
        "SUCCEEDED",
        "SKIPPED",
        "UNKNOWN",
        "FAILED",
    }:
        invalid("/status")
    dates = {}
    for field in ("date_from", "date_to"):
        if field in values:
            text = values.pop(field)
            try:
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
                    raise ValueError
                dates[field] = date.fromisoformat(text)
            except (ValueError, OverflowError):
                invalid("/" + field, "请输入真实日期")
    if dates.get("date_from", date.min) > dates.get("date_to", date.max):
        invalid("/date_from", "开始日期不能晚于结束日期")
    if "channel_id" in values:
        _text(values.pop("channel_id"), "/channel_id", 64, trim=True)
    parse_rule_query(values)
    return None


async def response(operation, model):
    # 不借reference_routes.transaction自动重试1205/1213；原错误保留给统一错误边界。
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        value = await operation(session)
        try:
            return parse_rule_response(model, value).model_dump()
        except (OrbitError, TypeError, ValueError):
            raise OrbitError(503, "RULE_STATE_UNAVAILABLE", "规则持久响应不符合原合同") from None


@router.get("/capabilities")
async def capabilities(request: Request, user: User):
    action = query_boundary(request, {"action"}).get("action")
    if action not in PERMISSIONS | {"SIMULATE": "rules.read"}:
        invalid("/action")
    await read_body(request, empty=True)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        value = await store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", ""), action
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"csrf_token"}
            or not isinstance(value["csrf_token"], str)
            or not 16 <= len(value["csrf_token"]) <= 255
        ):
            raise OrbitError(503, "RULE_STATE_UNAVAILABLE", "规则会话元数据尚未就绪")
        return value


@router.get("")
async def list_rules(request: Request, user: User):
    query = collection_query(request)
    await read_body(request, empty=True)
    return await response(lambda session: store().list(session, user.user.user_id, query), RulePage)


@router.get("/{rule_id}")
async def get_rule(rule_id: str, request: Request, user: User):
    query_boundary(request)
    rule_id = identifier(rule_id, "/id")
    await read_body(request, empty=True)
    return await response(lambda session: store().get(session, user.user.user_id, rule_id), Rule)


async def save(request, user, rule_id=None):
    query_boundary(request)
    if rule_id is not None:
        rule_id = identifier(rule_id, "/id")
    key, csrf, expected = write_headers(request, updating=rule_id is not None)
    value = parse_rule_write(await read_body(request))
    return await response(
        lambda session: store().save(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            rule_id,
            expected,
            request.state.orbit_request_id,
        ),
        Rule,
    )


@router.post("", status_code=201)
async def create_rule(request: Request, user: User):
    return await save(request, user)


@router.put("/{rule_id}")
async def update_rule(rule_id: str, request: Request, user: User):
    return await save(request, user, rule_id)


async def action(kind, rule_id, request, user):
    query_boundary(request)
    rule_id = identifier(rule_id, "/id")
    key, csrf, expected = write_headers(request, updating=True)
    raw = await read_body(request, empty=kind == "SIMULATE")
    value = None if kind == "SIMULATE" else parse_rule_action(kind, raw)
    service = store()
    common = (
        user.user.user_id,
        request.headers.get("authorization", ""),
        csrf,
        key,
        rule_id,
        expected,
    )
    request_id = request.state.orbit_request_id
    if kind == "SIMULATE":
        return await response(
            lambda session: service.simulate(session, *common, request_id), Simulation
        )
    if kind == "ENABLE":
        return await response(
            lambda session: service.enable(session, *common, value.simulation_id, request_id), Rule
        )
    return await response(
        lambda session: service.stop(
            session, *common, value.reason, request_id, archive=kind == "ARCHIVE"
        ),
        Rule,
    )


@router.post("/{rule_id}/archive")
async def archive_rule(rule_id: str, request: Request, user: User):
    return await action("ARCHIVE", rule_id, request, user)


@router.post("/{rule_id}/simulate")
async def simulate_rule(rule_id: str, request: Request, user: User):
    return await action("SIMULATE", rule_id, request, user)


@router.post("/{rule_id}/enable")
async def enable_rule(rule_id: str, request: Request, user: User):
    return await action("ENABLE", rule_id, request, user)


@router.post("/{rule_id}/pause")
async def pause_rule(rule_id: str, request: Request, user: User):
    return await action("PAUSE", rule_id, request, user)


@router.get("/{rule_id}/runs")
async def list_runs(rule_id: str, request: Request, user: User):
    collection_query(request, runs=True)
    rule_id = identifier(rule_id, "/id")
    await read_body(request, empty=True)
    return await response(
        lambda session: store().runs(session, user.user.user_id, rule_id), RuleRunPage
    )
