"""规则编辑定义GET技术扩展；不新增原Rule/Scope字段或其它动作依赖。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary
from orbit_api.errors import OrbitError
from orbit_api.rule_editor_definition import RuleEditorDefinitionStore

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则编辑定义"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


async def definition_boundary(request):
    _read_boundary(request)
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "规则编辑定义GET不接受正文")


@router.get("/{rule_id}/edit-definition")
async def edit_definition(rule_id: str, request: Request, user: User):
    await definition_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await RuleEditorDefinitionStore().get(session, user.user.user_id, rule_id)
