"""原账户范围两个接口；可信租户/公共路由注册由主线统一管理。"""

from typing import Annotated
from uuid import uuid4

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_scope_contract import MAX_BODY, parse_scope
from orbit_api.account_scope_store import AccountScopeStore
from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError

router = APIRouter(prefix="/api/v1/scope-snapshots", tags=["ORBIT账户跨页选择"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def store():
    return AccountScopeStore(DirectoryTokens(credential_cipher()))


@router.get("/capabilities")
async def capabilities(request: Request, user: User):
    # 全局ORBIT边界统一添加no-store和安全request_id；本接口不授予额外菜单或动作。
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )


@router.post("", status_code=201)
async def create(request: Request, user: User):
    _read_boundary(request)
    csrf, keys = request.headers.getlist("x-csrf-token"), request.headers.getlist("idempotency-key")
    if len(csrf) != 1:
        raise OrbitError(403, "CSRF_INVALID", "冻结账户范围需要唯一会话校验")
    if (
        len(keys) != 1
        or not 16 <= len(keys[0]) <= 128
        or not all(" " <= char <= "~" for char in keys[0])
    ):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "请提供16至128位可见ASCII幂等键")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "账户范围请求超过正文上限")
        raw.extend(chunk)
    selection = parse_scope(bytes(raw))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().create(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf[0],
            keys[0],
            selection,
            getattr(request.state, "orbit_request_id", str(uuid4())),
        )


@router.get("/{snapshot_id}/members")
async def members(snapshot_id: str, request: Request, user: User):
    _read_boundary(request, {"q", "page_size", "cursor"})
    params = request.query_params
    if params.get("page_size", "50") not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "每页只允许20、50、100或200条", "/page_size")
    query = short_text(params.get("q", ""), 100, "/q", required=False)
    cursor = params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "范围游标长度无效", "/cursor")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().members(
            session,
            user.user.user_id,
            snapshot_id,
            query,
            int(params.get("page_size", "50")),
            cursor,
        )
