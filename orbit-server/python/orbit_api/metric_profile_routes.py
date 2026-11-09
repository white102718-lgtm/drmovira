"""原指标配置只读目录；当前租户共享配置，公开读取仍要求原monitor.read。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.metric_profile_query import MetricProfileQuery

router = APIRouter(prefix="/api/v1/metric-profiles", tags=["ORBIT指标配置"])


@router.get("")
async def list_metric_profiles(
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    # 原通用参数中尚无业务定义的状态、日期、渠道等不静默吞掉；接口剩余缺口单列。
    _read_boundary(request, {"q", "metric_profile_id", "cursor", "page_size"})
    service = MetricProfileQuery(
        DirectoryTokens(credential_cipher()),
        isolated_fixture=getattr(request.app.state, "metric_profile_fixture_mode", False) is True,
    )
    # page内部要求新会话并自有事务，使首个一致读在水位锁后建立，避免RR旧快照。
    async with DataSourceRegistry.session(log_sql=False) as session:
        return await service.page(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            dict(request.query_params),
        )
