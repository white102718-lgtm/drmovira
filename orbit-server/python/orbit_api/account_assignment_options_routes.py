"""只注册分配候选辅助接口；由主线统一接入，原028路由保持冻结。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_assignment_options import AccountAssignmentOptions, parse_options
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户分配候选"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/{account_id}/assignment-options")
async def assignment_options(account_id: str, request: Request, user: User):
    _read_boundary(request, {"kind", "q", "owner_user_id", "page_size", "cursor"})
    query = parse_options(request.query_params)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountAssignmentOptions(DirectoryTokens(credential_cipher())).list(
            session, user.user.user_id, account_id, query
        )
