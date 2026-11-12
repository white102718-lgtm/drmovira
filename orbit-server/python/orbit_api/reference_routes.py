"""受控导入HTTP边界；预览与提交严格分离，不从请求接受租户或操作者。"""

import asyncio
import re
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from sqlalchemy.exc import OperationalError

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import parse_import
from orbit_api.reference_store import ReferenceStore

router = APIRouter(prefix="/api/v1", tags=["ORBIT最小引用资料"])


def store():
    return ReferenceStore(DirectoryTokens(credential_cipher()))


async def write_boundary(request, *, updating=False, empty=False, limit=2 * 1024 * 1024):
    _read_boundary(request)
    keys = request.headers.getlist("idempotency-key")
    csrf = request.headers.getlist("x-csrf-token")
    matches = request.headers.getlist("if-match")
    if len(keys) != 1 or not re.fullmatch(r"[ -~]{16,128}", keys[0]):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "请提供16至128位ASCII幂等键")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_REQUIRED", "请重新加载会话校验")
    expected = 0
    if updating:
        if len(matches) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,15}"', matches[0]):
            raise OrbitError(400, "REVISION_REQUIRED", "请提供带引号的业务版本")
        expected = int(matches[0][1:-1])
        if expected > 9_007_199_254_740_991:
            raise OrbitError(422, "FIELD_INVALID", "业务版本超出范围")
    elif matches:
        raise OrbitError(400, "INVALID_STRUCTURE", "新建不能指定已有版本")
    raw = bytearray()
    async for part in request.stream():
        if len(raw) + len(part) > limit:
            raise OrbitError(413, "BODY_TOO_LARGE", "导入或渠道正文超过大小限制")
        raw.extend(part)
    if empty and raw:
        raise OrbitError(400, "INVALID_STRUCTURE", "提交已冻结预览时不能携带新业务正文")
    return keys[0], csrf[0], expected, bytes(raw)


async def transaction(operation):
    for attempt in range(3):
        try:
            async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
                return await operation(session)
        except OperationalError as error:
            if not error.orig.args or error.orig.args[0] not in {1205, 1213}:
                raise
            if attempt == 2:
                raise OrbitError(
                    503, "REFERENCE_BUSY", "资料正在并发修改，请保留幂等键稍后重试"
                ) from None
            await asyncio.sleep(0.01 * (attempt + 1))


@router.get("/reference-catalog-imports/capabilities")
async def capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )
    )


@router.get("/reference-catalogs/{kind}")
async def list_references(
    kind: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"owner_user_id", "page_size", "cursor"})
    query = dict(request.query_params)
    size = query.pop("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "每页数量只允许20、50、100或200")
    cursor = query.pop("cursor", None)
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "游标长度无效")
    return await transaction(
        lambda session: store().list(
            session, user.user.user_id, kind, {**query, "page_size": int(size)}, cursor
        )
    )


@router.post("/reference-catalog-imports", status_code=201)
async def preview_import(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    key, csrf, _, raw = await write_boundary(request)
    value = parse_import(raw)
    return await transaction(
        lambda session: store().preview(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            request.state.orbit_request_id,
        )
    )


@router.get("/reference-catalog-imports/{import_id}")
async def get_import(
    import_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(lambda session: store().get(session, user.user.user_id, import_id))


@router.get("/reference-catalog-imports/{import_id}/differences")
async def get_differences(
    import_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store().get(session, user.user.user_id, import_id, differences=True)
    )


@router.post("/reference-catalog-imports/{import_id}/commit")
async def commit_import(
    import_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    key, csrf, expected, _ = await write_boundary(request, updating=True, empty=True)
    return await transaction(
        lambda session: store().commit(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            import_id,
            expected,
            request.state.orbit_request_id,
        )
    )
