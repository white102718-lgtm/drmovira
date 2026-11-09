"""原validate写入口；外部只读采集不占数据库事务，缺可信来源明确503。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.launch_contract import parse_plan_action
from orbit_api.launch_validation_store import LaunchValidationStore
from orbit_api.reference_routes import transaction, write_boundary

router = APIRouter(prefix="/api/v1/launch-plans", tags=["ORBIT投放预检"])


@router.post("/{plan_id}/validate")
async def validate_plan(
    plan_id: str,
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    key, csrf, expected, raw = await write_boundary(request, updating=True)
    value = parse_plan_action(raw, "validate")
    service = LaunchValidationStore(
        DirectoryTokens(credential_cipher()),
        provider=getattr(request.app.state, "launch_validation_provider", None),
    )
    actor = user.user.user_id
    authorization = request.headers.get("authorization", "")
    # prepare自行结束授权/源快照短事务后才进行外部capture；不把网络I/O放进transaction。
    prepared = await service.prepare(
        lambda: DataSourceRegistry.session(log_sql=False),
        actor,
        authorization,
        csrf,
        key,
        value,
        plan_id,
        expected,
    )
    return await transaction(
        lambda session: service.validate(
            session,
            actor,
            authorization,
            csrf,
            key,
            value,
            plan_id,
            expected,
            request.state.orbit_request_id,
            prepared,
        )
    )
