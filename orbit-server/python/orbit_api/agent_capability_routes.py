"""原环境动作能力只读接口；发行仅由受控实际验收程序操作。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.agent_capability_contract import parse_filters
from orbit_api.agent_capability_store import AgentCapabilityStore
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.reference_routes import transaction

router = APIRouter(prefix="/api/v1/environment-capabilities", tags=["ORBIT环境动作能力"])


@router.get("")
async def list_capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"cursor", "page_size"})
    size, cursor = parse_filters(dict(request.query_params))
    return await transaction(
        lambda session: AgentCapabilityStore(DirectoryTokens(credential_cipher())).list(
            session, user.user.user_id, size, cursor
        )
    )
