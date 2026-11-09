"""规则编辑辅助GET技术扩展；root须先于原/{rule_id}注册。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.rule_editor_contract import parse_editor_query
from orbit_api.rule_editor_store import RuleEditorStore

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则编辑辅助"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


async def boundary(request, *, options=False):
    allowed = {"action", "rule_id"}
    if options:
        allowed |= {"kind", "owner_user_id", "owner_team_id", "q", "page_size", "cursor"}
    _read_boundary(request, allowed)
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "规则辅助GET不接受正文")
    return parse_editor_query(dict(request.query_params), options=options)


def store(request):
    return RuleEditorStore(
        DirectoryTokens(credential_cipher()),
        isolated_fixture=getattr(request.app.state, "rule_editor_fixture", False),
    )


@router.get("/edit-context")
async def edit_context(request: Request, user: User):
    query = await boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store(request).context(
            session, user.user.user_id, request.headers.get("authorization", ""), query
        )


@router.get("/editor-options")
async def editor_options(request: Request, user: User):
    query = await boundary(request, options=True)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store(request).options(
            session, user.user.user_id, request.headers.get("authorization", ""), query
        )
