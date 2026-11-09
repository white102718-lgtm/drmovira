"""团队HTTP合同：原若依会话、严格请求边界及独立CSRF，不自动迁移现有预览。"""

import asyncio
import re
from datetime import date, timedelta
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from sqlalchemy.exc import OperationalError

from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import parse_identity_write
from orbit_api.team_store import TeamStore

router = APIRouter(prefix="/api/v1/teams", tags=["ORBIT团队管理"])


def store():
    return TeamStore(DirectoryTokens(credential_cipher()))


def list_filters(request, label="团队", *, statuses=("ENABLED", "DISABLED")):
    allowed = {
        "q",
        "cursor",
        "page_size",
        "status",
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    }
    _read_boundary(request, allowed)
    values = dict(request.query_params)
    # 通用列表合同中的广告指标筛选不适用于团队；显式报错，不能默默返回未过滤结果。
    for field in ("operator_user_id", "channel_id", "metric_profile_id", "entity_type"):
        if field in values:
            raise OrbitError(
                422, "FILTER_NOT_APPLICABLE", f"此筛选不适用于{label}目录", "/" + field
            )
    filters = {"q": short_text(values.get("q", ""), 100, "/q", required=False), "page_size": 50}
    if "page_size" in values:
        if values["page_size"] not in {"20", "50", "100", "200"}:
            raise OrbitError(422, "FIELD_INVALID", "每页数量只允许20、50、100或200", "/page_size")
        filters["page_size"] = int(values["page_size"])
    if "status" in values:
        if values["status"] not in statuses:
            raise OrbitError(422, "FIELD_INVALID", "目录状态无效", "/status")
        filters["status"] = values["status"]
    dates = {}
    for field in ("date_from", "date_to"):
        if field in values:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values[field]):
                    raise ValueError
                dates[field] = date.fromisoformat(values[field])
                boundary = dates[field] + timedelta(days=field == "date_to")
                filters[field] = boundary.isoformat() + " 00:00:00"
            except (ValueError, OverflowError):
                raise OrbitError(422, "FIELD_INVALID", "请选择有效UTC日期", "/" + field) from None
    if "date_from" in dates and "date_to" in dates and dates["date_from"] > dates["date_to"]:
        raise OrbitError(422, "FIELD_INVALID", "开始日期不能晚于结束日期", "/date_from")
    cursor = values.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "游标长度无效", "/cursor")
    return filters, cursor


@router.get("/capabilities")
async def team_capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )


@router.get("")
async def list_teams(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    filters, cursor = list_filters(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().list(session, user.user.user_id, filters, cursor)


@router.get("/{team_id}")
async def get_team(
    team_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().get(session, user.user.user_id, team_id)


async def save(request, user, team_id, *, kind="TEAM", store_factory=store):
    _read_boundary(request)
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or not re.fullmatch(r"[ -~]{16,128}", keys[0]):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "请提供16至128位ASCII幂等键")
    csrf = request.headers.getlist("x-csrf-token")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_REQUIRED", "请重新加载有效的会话校验")
    matches = request.headers.getlist("if-match")
    expected = 0
    if team_id:
        if len(matches) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,15}"', matches[0]):
            raise OrbitError(400, "REVISION_REQUIRED", "请提供带引号的目录对象版本")
        expected = int(matches[0][1:-1])
        if expected > 9_007_199_254_740_991:
            raise OrbitError(422, "FIELD_INVALID", "目录对象版本超出范围")
    elif matches:
        raise OrbitError(400, "INVALID_STRUCTURE", "创建目录对象不能指定已有版本")
    raw = bytearray()
    limit = 65_536 if kind == "USER" else 16_384
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise OrbitError(413, "BODY_TOO_LARGE", "目录请求超过大小限制")
        raw.extend(chunk)
    value = parse_identity_write(kind, bytes(raw))
    # 原若依身份服务先锁身份行再进入目录锁；同一团队并发维护可能被MySQL选为死锁牺牲者。
    # 仅在数据库确认回滚后，重开整个事务并重新授权；外部副作用不在此事务，幂等键保持不变。
    for attempt in range(3):
        try:
            async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
                return await store_factory().save(
                    session,
                    user.user.user_id,
                    request.headers.get("authorization", ""),
                    csrf[0],
                    keys[0],
                    value,
                    team_id,
                    expected,
                    request.state.orbit_request_id,
                )
        except OperationalError as error:
            if not error.orig.args or error.orig.args[0] not in {1205, 1213}:
                raise
            if attempt == 2:
                raise OrbitError(
                    503, "DIRECTORY_BUSY", "目录正在被其他操作修改，请稍后重试"
                ) from None
            await asyncio.sleep(0.01 * (attempt + 1))


@router.post("", status_code=201)
async def create_team(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    return await save(request, user, None)


@router.put("/{team_id}")
async def update_team(
    team_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, team_id)
