"""原分配202/查询200入口；受理对象为Allocation，不冒充执行Task。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api import launch_access as access
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation_runtime import AllocationRuntime
from orbit_api.launch_contract import parse_plan_action, uuid_field
from orbit_api.launch_store import LaunchStore
from orbit_api.reference_access import verify_csrf
from orbit_api.reference_routes import transaction, write_boundary

router = APIRouter(prefix="/api/v1/launch-plans", tags=["ORBIT素材分配"])


async def enqueue_allocation(
    session, runtime, tokens, actor, authorization, csrf, key, value, plan_id, expected, request_id
):
    # 缺Provider也先核当前动作、会话和对象，不能以全局503掩盖越权请求。
    current = await access.context(session, actor, "launch.edit")
    try:
        verify_csrf(tokens, current, authorization, csrf)
    except OrbitError as error:
        if error.status == 400:
            raise OrbitError(403, "CSRF_INVALID", "会话校验已失效，请刷新") from None
        raise
    await LaunchStore(tokens).row(session, current, plan_id, unlocked=True)
    return await runtime.enqueue(session, actor, plan_id, value, expected, key, request_id)


@router.post("/{plan_id}/allocations", status_code=202)
async def create_allocation(
    plan_id: str,
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    key, csrf, expected, raw = await write_boundary(request, updating=True)
    value = parse_plan_action(raw, "allocation")
    identifier = uuid_field(plan_id, ("id",))
    runtime = AllocationRuntime(getattr(request.app.state, "launch_allocation_provider", None))
    tokens = DirectoryTokens(credential_cipher())
    return await transaction(
        lambda session: enqueue_allocation(
            session,
            runtime,
            tokens,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            identifier,
            expected,
            request.state.orbit_request_id,
        )
    )


@router.get("/{plan_id}/allocations/{allocation_id}")
async def get_allocation(
    plan_id: str,
    allocation_id: str,
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    _read_boundary(request)
    # 查询不启动Worker、不要求Provider可用，仍按当前launch.read及对象范围重核。
    return await transaction(
        lambda session: AllocationRuntime().get(session, user.user.user_id, plan_id, allocation_id)
    )
