"""原规则列表read-only筛选候选；主线在动态rule_id前显式注册。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.read_sessions import read_committed_session
from orbit_api.rule_editor_scope_routes import read
from orbit_api.rule_list_filter_contract import RuleListFilterPage, parse_list_filter_query
from orbit_api.rule_list_filter_store import RuleListFilterStore

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则列表筛选"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/list-filter-options", response_model=RuleListFilterPage)
async def options(request: Request, user: User):
    query = parse_list_filter_query(await read(request, {"kind", "page_size", "cursor"}))
    async with read_committed_session(DataSourceRegistry) as session, session.begin():
        return await RuleListFilterStore(DirectoryTokens(credential_cipher())).options(
            session, user.user.user_id, request.headers.get("authorization", ""), query
        )
