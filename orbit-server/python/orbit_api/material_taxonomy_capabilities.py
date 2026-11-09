"""标签分类动作独立能力；当前主体确认不依赖素材读取或对象存储。"""

from uuid import UUID

from pydantic import Field, ValidationError, field_validator

from orbit_api.authorization import require_business_access
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput

OPERATIONS = {
    "READ": "tags.read",
    "CREATE": "tags.create",
    "EDIT": "tags.edit",
    "ARCHIVE": "tags.archive",
}
MAX_SAFE = 9007199254740991


class TaxonomyCapabilities(StrictInput):
    actor_id: int = Field(ge=1, le=MAX_SAFE)
    tenant_id: str
    csrf_token: str | None = Field(min_length=16, max_length=255)

    @field_validator("tenant_id")
    @classmethod
    def canonical_tenant(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("canonical UUID required")
        return value


def operation(value):
    if type(value) is not str or value not in OPERATIONS:
        raise OrbitError(422, "FIELD_INVALID", "请选择标签分类动作", "/operation")
    return value


async def current_taxonomy_capabilities(session, actor, authorization, selected, tokens):
    """共享授权锁持至事务结束；READ无CSRF，写能力只确认本次动作和当前实际主体。"""
    if not session.in_transaction():
        raise ValueError("TAXONOMY_TRANSACTION_REQUIRED")
    selected = operation(selected)
    current = await require_business_access(session, actor, "assets", OPERATIONS[selected])
    if type(actor) is not int or not 1 <= actor <= MAX_SAFE or current.actor_id != actor:
        raise OrbitError(503, "TAXONOMY_CONTEXT_UNAVAILABLE", "当前标签分类主体尚未就绪")
    csrf = None
    if selected != "READ":
        csrf = tokens.issue(
            "DIRECTORY_CSRF_V1",
            {"binding": tokens.session_binding(authorization, actor, current.tenant_id)},
        )
    try:
        result = TaxonomyCapabilities.model_validate(
            {
                "actor_id": actor,
                "tenant_id": current.tenant_id,
                "csrf_token": csrf,
            }
        ).model_dump()
    except (ValidationError, ValueError, TypeError):
        raise OrbitError(503, "TAXONOMY_CONTEXT_UNAVAILABLE", "当前标签分类主体尚未就绪") from None
    latest = await require_business_access(session, actor, "assets", OPERATIONS[selected])
    if latest != current:
        raise OrbitError(403, "PERMISSION_DENIED", "当前标签分类权限或主体已变化")
    return result
