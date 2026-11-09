"""独立命令诊断GET，不创建Task、不取消或重发；公共注册由主线执行。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request, Response
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_command_store import AccountCommandStore
from orbit_api.configuration_routes import _read_boundary

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT本人账户命令状态"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/{account_id}/actions/status")
async def status(account_id: str, request: Request, response: Response, user: User):
    _read_boundary(request, {"kind", "request_id"})
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountCommandStore().get(
            session, user.user.user_id, account_id, dict(request.query_params)
        )
