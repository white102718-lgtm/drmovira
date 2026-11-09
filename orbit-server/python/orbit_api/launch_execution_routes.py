"""原execute入口：完整私有准备完成后，原子受理Task才返回202；不发送广告。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.launch_contract import parse_plan_action, uuid_field
from orbit_api.launch_execution_store import LaunchExecutionStore
from orbit_api.reference_routes import transaction, write_boundary

router = APIRouter(prefix="/api/v1/launch-plans", tags=["ORBIT执行受理"])


@router.post("/{plan_id}/execute", status_code=202)
async def execute_plan(
    plan_id: str,
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    key, csrf, expected, raw = await write_boundary(request, updating=True)
    value = parse_plan_action(raw, "execute")
    identifier = uuid_field(plan_id, ("id",))
    service = LaunchExecutionStore(
        DirectoryTokens(credential_cipher()),
        provider=getattr(request.app.state, "launch_execution_provider", None),
    )
    actor = user.user.user_id
    authorization = request.headers.get("authorization", "")
    request_id = request.state.orbit_request_id
    # 捕获来源的网络阶段在事务外；每个有界持久块使用自身短事务，未受理前不公开Task。
    prepared = await service.prepare(
        lambda: DataSourceRegistry.session(log_sql=False),
        actor,
        authorization,
        csrf,
        key,
        value,
        identifier,
        expected,
        request_id,
    )
    # 最终事务重核当前权限、完整分配/名称与封存来源，再一并写计划/Task/引用/审计。
    # transaction成功提交之前不会返回202；默认无Provider明确503，绝不构造空Task。
    return await transaction(
        lambda session: service.accept(
            session,
            actor,
            authorization,
            csrf,
            key,
            value,
            identifier,
            expected,
            request_id,
            prepared,
        )
    )
