"""账户当前渠道独立扩展，复用原生身份和账户分配授权。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_actions_contract import MAX_BODY, write_headers
from orbit_api.account_channel import AccountChannelStore, parse_write
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户当前渠道"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/{account_id}/current-channel")
async def current_channel(account_id: str, request: Request, user: User):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountChannelStore(DirectoryTokens(credential_cipher())).read(
            session, user.user.user_id, account_id, request.headers.get("authorization", "")
        )


@router.put("/{account_id}/current-channel")
async def save_channel(account_id: str, request: Request, user: User):
    _read_boundary(request)
    csrf, key, revision = write_headers(request.headers)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "账户渠道正文超过上限")
        raw.extend(chunk)
    value = parse_write(bytes(raw))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountChannelStore(DirectoryTokens(credential_cipher())).write(
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
