"""预览未来五次运行POST；只读技术扩展，不持久/幂等写或接真实调度。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.rule_schedule_preview import (
    MAX_BODY,
    RuleSchedulePreviewStore,
    parse_preview_request,
)

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则调度预览"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


async def preview_boundary(request):
    _read_boundary(request)
    if "if-match" in request.headers or "idempotency-key" in request.headers:
        raise OrbitError(400, "INVALID_STRUCTURE", "只读时间预览仅使用正文规则版本")
    csrf = request.headers.getlist("x-csrf-token")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_INVALID", "时间预览需要唯一当前会话校验")
    raw = bytearray()
    async for part in request.stream():
        if len(raw) + len(part) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "时间预览正文超过内部大小限制")
        raw.extend(part)
    return parse_preview_request(bytes(raw)), csrf[0]


@router.post("/editor-schedule-preview")
async def editor_schedule_preview(request: Request, user: User):
    parsed, csrf = await preview_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await RuleSchedulePreviewStore(DirectoryTokens(credential_cipher())).preview(
            session, user.user.user_id, request.headers.get("authorization", ""), csrf, parsed
        )
