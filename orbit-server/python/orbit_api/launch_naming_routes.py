"""系列命名原无正文200接口；独立router须主线显式注册。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.launch_naming import LaunchNamingStore
from orbit_api.reference_routes import transaction, write_boundary

router = APIRouter(prefix="/api/v1/launch-plans", tags=["ORBIT系列命名"])


@router.post("/{plan_id}/campaign-names", status_code=200)
async def reserve_names(
    plan_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    key, csrf, expected, _ = await write_boundary(request, updating=True, empty=True, limit=1024)
    return await transaction(
        lambda session: LaunchNamingStore(DirectoryTokens(credential_cipher())).reserve(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            plan_id,
            expected,
            request.state.orbit_request_id,
        )
    )
