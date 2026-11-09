"""规则未确认动作的当前本人/租户确认；不改变原capabilities或幂等业务意图。"""

from typing import Annotated
from uuid import UUID

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from pydantic import Field, ValidationError, field_validator

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput
from orbit_api.rule_access import authorize_rule, revalidate_access, transaction
from orbit_api.rule_contract import MAX_SAFE
from orbit_api.rule_store import PERMISSIONS

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则动作恢复上下文"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]
ACTIONS = PERMISSIONS | {"SIMULATE": "rules.read"}


class RuleRecoveryContext(StrictInput):
    actor_id: int = Field(ge=1, le=MAX_SAFE)
    tenant_id: str
    csrf_token: str = Field(min_length=16, max_length=255)

    @field_validator("tenant_id")
    @classmethod
    def canonical_tenant(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("canonical UUID required")
        return value


def unavailable():
    raise OrbitError(503, "RULE_RECOVERY_CONTEXT_UNAVAILABLE", "当前规则恢复上下文尚未就绪")


async def recovery_boundary(request):
    _read_boundary(request, {"action"})
    action = request.query_params.get("action")
    if type(action) is not str or action not in ACTIONS:
        raise OrbitError(422, "FIELD_INVALID", "请选择原规则动作", "/action")
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "规则恢复上下文GET不接受正文")
    return action


async def current_recovery_context(session, actor, authorization, action, tokens):
    transaction(session)
    if type(action) is not str or action not in ACTIONS:
        raise OrbitError(422, "FIELD_INVALID", "请选择原规则动作", "/action")
    access = await authorize_rule(session, actor, ACTIONS[action])
    if type(actor) is not int or not 1 <= actor <= MAX_SAFE or access.current.actor_id != actor:
        unavailable()
    value = {
        "actor_id": actor,
        "tenant_id": access.current.tenant_id,
        "csrf_token": tokens.issue(
            "DIRECTORY_CSRF_V1",
            {
                "binding": tokens.session_binding(authorization, actor, access.current.tenant_id),
            },
        ),
    }
    try:
        result = RuleRecoveryContext.model_validate(value).model_dump()
    except (ValidationError, TypeError, ValueError):
        unavailable()
    # 令牌只确认当前会话；最后仍复核原动作及完整当前范围，不替代具体Rule重放门禁。
    await revalidate_access(session, access)
    return result


@router.get("/recovery-context", response_model=RuleRecoveryContext)
async def recovery_context(request: Request, user: User):
    action = await recovery_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await current_recovery_context(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            action,
            DirectoryTokens(credential_cipher()),
        )
