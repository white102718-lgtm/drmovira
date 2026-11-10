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


@router.get("/publication-options")
async def publication_options(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    import json

    from config.orbit_runtime import private_values
    from sqlalchemy import text

    from orbit_api.cookie_identity import current_cookie_identity
    from orbit_api.meta_connection_routes import boundary
    from orbit_api.meta_metric_profile_source import (
        ADAPTER_VERSION,
        REPORT_TIMES,
        WINDOW_MAPPING,
        publisher,
    )
    from orbit_api.meta_read_contract import MetaReadFailure, validate_api_version

    boundary(request, user.user.user_id)
    version = private_values().get("ORBIT_META_GRAPH_VERSION", "")
    configured = credential_cipher().ready
    try:
        validate_api_version(version)
    except MetaReadFailure:
        configured = False
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await publisher(session, user.user.user_id)
        configs = (
            (
                await session.execute(
                    text(
                        "SELECT c.id,c.name,c.revision,c.settings_json,COALESCE(h.revision,0) "
                        "head_revision FROM orbit_system_configuration c LEFT JOIN "
                        "orbit_metric_profile_head h ON h.tenant_id=c.tenant_id AND h.id=c.id "
                        "WHERE c.tenant_id=:tenant AND c.section='METRICS' AND c.enabled=1 "
                        "ORDER BY c.id LIMIT 201"
                    ),
                    {"tenant": current.tenant_id},
                )
            )
            .mappings()
            .all()
        )
        connections = (
            (
                await session.execute(
                    text(
                        "SELECT id,revision,kind,status FROM orbit_meta_connection WHERE "
                        "tenant_id=:tenant AND status='ACTIVE' ORDER BY id LIMIT 201"
                    ),
                    {"tenant": current.tenant_id},
                )
            )
            .mappings()
            .all()
        )
        if len(configs) > 200 or len(connections) > 200:
            from orbit_api.errors import OrbitError

            raise OrbitError(
                503, "METRIC_PUBLICATION_OPTIONS_LIMIT", "可选来源超过当前容量，请先整理配置"
            )
    return {
        "csrf_token": current_cookie_identity().csrf_token,
        "configured": configured,
        "api_version": version if configured else None,
        "adapter_version": ADAPTER_VERSION,
        "attribution_windows": list(WINDOW_MAPPING),
        "action_report_times": list(REPORT_TIMES),
        "configurations": [
            {
                "id": r["id"],
                "name": r["name"],
                "revision": r["revision"],
                "head_revision": r["head_revision"],
                "settings": json.loads(r["settings_json"])
                if isinstance(r["settings_json"], str)
                else r["settings_json"],
            }
            for r in configs
        ],
        "connections": [dict(r) for r in connections],
    }


@router.post("/publications")
async def publish_metric_profile(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    import json

    from config.orbit_runtime import private_values

    from orbit_api.account_platform import AccountReadFailure
    from orbit_api.errors import OrbitError
    from orbit_api.meta_connection_routes import body, boundary
    from orbit_api.meta_metric_profile_source import MetaMetricProfileService
    from orbit_api.meta_read_contract import MetaReadFailure

    key = boundary(request, user.user.user_id, write=True)
    try:
        value = json.loads(await body(request))
    except (ValueError, UnicodeError):
        raise OrbitError(400, "BODY_INVALID", "发布请求正文无效") from None
    try:
        return await MetaMetricProfileService(
            lambda: DataSourceRegistry.session(log_sql=False),
            credential_cipher(),
            private_values().get("ORBIT_META_GRAPH_VERSION", ""),
        ).publish(user.user.user_id, value, key, request.state.orbit_request_id)
    except (MetaReadFailure, AccountReadFailure):
        raise OrbitError(
            503,
            "METRIC_PROFILE_SOURCE_NOT_VERIFIED",
            "Meta真实来源尚未通过读取验证，请检查连接授权与Graph版本后重试",
        ) from None


@router.get("/history-candidates")
async def historical_metric_profiles(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"q", "metric_profile_id", "cursor", "page_size"})
    service = MetricProfileQuery(DirectoryTokens(credential_cipher()), historical=True)
    async with DataSourceRegistry.session(log_sql=False) as session:
        return await service.page(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            dict(request.query_params),
        )
