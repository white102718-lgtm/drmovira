"""标签分类独立能力入口，不借assets.read，不读取或写入对象存储。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.material_taxonomy_capabilities import (
    TaxonomyCapabilities,
    current_taxonomy_capabilities,
    operation,
)

router = APIRouter(prefix="/api/v1/material-taxonomy", tags=["ORBIT标签分类能力"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/capabilities", response_model=TaxonomyCapabilities)
async def capabilities(request: Request, user: User):
    _read_boundary(request, {"operation"})
    selected = operation(request.query_params.get("operation"))
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "标签分类能力GET不接受正文")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await current_taxonomy_capabilities(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            selected,
            DirectoryTokens(credential_cipher()),
        )
