"""单独注册模板共享候选静态路径，必须在/templates/{id}动态路由之前登记。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.reference_routes import transaction
from orbit_api.template_options import recipient_options

router = APIRouter(prefix="/api/v1/templates", tags=["ORBIT模板受控共享"])


@router.get("/recipient-options")
async def candidates(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    _read_boundary(request, {"template_id", "cursor", "page_size"})
    size = request.query_params.get("page_size", "200")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_VALIDATION_FAILED", "每页数量无效", "/page_size")
    after = request.query_params.get("cursor")
    if after is not None and not 1 <= len(after) <= 2048:
        raise OrbitError(422, "FIELD_VALIDATION_FAILED", "候选游标长度无效", "/cursor")
    return await transaction(
        lambda session: recipient_options(
            session,
            DirectoryTokens(credential_cipher()),
            user.user.user_id,
            request.headers.get("authorization", ""),
            template_id=request.query_params.get("template_id"),
            cursor=after,
            page_size=int(size),
        )
    )
