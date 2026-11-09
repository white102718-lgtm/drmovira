"""规则账户筛选候选独立只读扩展；主线显式注册在动态rule_id路由前。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.read_sessions import read_committed_session
from orbit_api.rule_editor_scope_routes import read
from orbit_api.rule_scope_options_contract import parse_scope_options_query
from orbit_api.rule_scope_options_store import RuleScopeOptionsStore

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则筛选候选"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/editor-scope-options")
async def options(request: Request, user: User):
    query = parse_scope_options_query(
        await read(
            request,
            {
                "kind",
                "action",
                "rule_id",
                "owner_user_id",
                "owner_team_id",
                "q",
                "page_size",
                "cursor",
            },
        )
    )
    async with read_committed_session(DataSourceRegistry) as session, session.begin():
        return await RuleScopeOptionsStore(DirectoryTokens(credential_cipher())).options(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            query,
        )
