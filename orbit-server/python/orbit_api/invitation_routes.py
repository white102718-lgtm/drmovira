"""人员邀请接口；原POST无正文，状态查询是独立技术扩展，不返回邀请凭据。"""

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
from orbit_api.user_store import UserStore

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
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        await UserStore(DirectoryTokens(credential_cipher())).get(
            session, user.user.user_id, user_id
        )
    raise OrbitError(410, "INVITATION_RETIRED", "人员改为直接创建和设置密码，不再使用邀请验证")
