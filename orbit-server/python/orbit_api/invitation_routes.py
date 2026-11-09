"""人员邀请接口；原POST无正文，状态查询是独立技术扩展，不返回邀请凭据。"""

import re
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.cookie_auth import public_origin
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.invitation_store import InvitationStore

router = APIRouter(prefix="/api/v1/users", tags=["ORBIT人员邀请"])


@router.get("/{user_id}/invitation")
async def invitation_status(
    user_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await InvitationStore(DirectoryTokens(credential_cipher())).status(
            session, user.user.user_id, user_id, public_origin()
        )


@router.post("/{user_id}/invitation")
async def send_invitation(
    user_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    keys = request.headers.getlist("idempotency-key")
    csrf = request.headers.getlist("x-csrf-token")
    revisions = request.headers.getlist("if-match")
    if len(keys) != 1 or not re.fullmatch(r"[ -~]{16,128}", keys[0]):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "邀请需要唯一有效的幂等键")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_INVALID", "邀请需要唯一有效的会话校验值")
    if len(revisions) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,15}"', revisions[0]):
        raise OrbitError(400, "REVISION_REQUIRED", "邀请需要带引号的人员版本")
    revision = int(revisions[0][1:-1])
    if revision > 9_007_199_254_740_991:
        raise OrbitError(400, "REVISION_REQUIRED", "人员版本超过合同上限")
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "邀请接口不接受正文或身份字段")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await InvitationStore(DirectoryTokens(credential_cipher())).create(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf[0],
            keys[0],
            user_id,
            revision,
            request.state.orbit_request_id,
            public_origin(),
        )
