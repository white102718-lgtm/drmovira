"""原账户分配/同步/本地解绑路径；由主线统一注册，禁止平台广告写调用。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_actions_contract import (
    MAX_BODY,
    parse_assignment,
    parse_reason,
    write_headers,
)
from orbit_api.account_actions_store import PERMISSIONS, AccountActionsStore
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户本地动作"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def store():
    return AccountActionsStore(DirectoryTokens(credential_cipher()))


@router.get("/{account_id}/actions/capabilities")
async def capabilities(account_id: str, request: Request, user: User):
    _read_boundary(request, {"action"})
    kind = request.query_params.get("action")
    if kind not in PERMISSIONS:
        raise OrbitError(422, "FIELD_INVALID", "请选择明确的账户动作", "/action")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", ""), account_id, kind
        )


async def save(account_id, request, user, kind):
    _read_boundary(request)
    csrf, key, revision = write_headers(request.headers)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "账户动作请求超过正文上限")
        raw.extend(chunk)
    value = parse_assignment(bytes(raw)) if kind == "ASSIGNMENT" else parse_reason(bytes(raw))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        service = store()
        method = {"ASSIGNMENT": service.assign, "SYNC": service.sync, "UNBIND": service.unbind}[
            kind
        ]
        return await method(
            session,
            user.user.user_id,
            account_id,
            revision,
            key,
            request.headers.get("authorization", ""),
            csrf,
            value,
            request.state.orbit_request_id,
        )


@router.put("/{account_id}/assignment")
async def assignment(account_id: str, request: Request, user: User):
    return await save(account_id, request, user, "ASSIGNMENT")


@router.post("/{account_id}/sync", status_code=202)
async def sync(account_id: str, request: Request, user: User):
    return await save(account_id, request, user, "SYNC")


@router.post("/{account_id}/unbind")
async def unbind(account_id: str, request: Request, user: User):
    return await save(account_id, request, user, "UNBIND")
