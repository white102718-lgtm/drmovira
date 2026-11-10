"""原Metrics查询公开入口；来源缺失明确失败，不返回模拟统计或未完成的202。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from starlette.responses import JSONResponse

from orbit_api.authorization import require_business_access
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.metrics_contract import parse_metric_query
from orbit_api.metrics_query_result_store import MetricsQueryResultStore, ResultBuildBudget
from orbit_api.metrics_query_store import MetricsQueryStore
from orbit_api.reference_access import verify_csrf
from orbit_api.reference_routes import write_boundary

router = APIRouter(prefix="/api/v1/metrics", tags=["ORBIT广告投放数据"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def result_service(request):
    """发行来源仅由可信启动代码注入；HTTP不能指定provider或授予verified资格。"""
    return MetricsQueryResultStore(
        MetricsQueryStore(getattr(request.app.state, "metrics_source_provider", None)),
        getattr(request.app.state, "metrics_expected_provider", None),
        tokens=DirectoryTokens(credential_cipher()),
        # 明确的运行资源预算，不改变原93日/字段合法范围；超预算整包503，不截断成功。
        budget=getattr(request.app.state, "metrics_result_budget", None)
        or ResultBuildBudget(5_000_000, 1_000_000, 512 * 1024 * 1024, 256 * 1024 * 1024, 45),
    )


@router.get("/capabilities")
async def capabilities(request: Request, user: User):
    _read_boundary(request)
    tokens = DirectoryTokens(credential_cipher())
    authorization = request.headers.get("authorization", "")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await require_business_access(
            session, user.user.user_id, "monitor", "monitor.read"
        )
        return {
            "csrf_token": tokens.issue(
                "DIRECTORY_CSRF_V1",
                {
                    "binding": tokens.session_binding(
                        authorization, current.actor_id, current.tenant_id
                    )
                },
            )
        }


@router.post("/query")
async def query(request: Request, user: User):
    key, csrf, _, body = await write_boundary(request)
    # 严格原13字段；逐账户当地未来日期仍由Store按真实时区复核，不猜服务器日期。
    parsed = parse_metric_query(body)
    authorization = request.headers.get("authorization", "")
    async with DataSourceRegistry.session(log_sql=False) as session:
        async with session.begin():
            current = await require_business_access(
                session, user.user.user_id, "monitor", "monitor.read"
            )
            verify_csrf(DirectoryTokens(credential_cipher()), current, authorization, csrf)
        # 短授权事务结束后才借独占连接构建；Store在每个阶段重新核当前权限和来源。
        value = await result_service(request).run(
            session.bind,
            user.user.user_id,
            parsed,
            key,
            request.state.orbit_request_id,
            authorization,
        )
        return JSONResponse(value)


@router.post("/history/query")
async def history_query(request: Request, user: User):
    from orbit_api.metrics_contract import parse_history_metric_query

    key, csrf, _, body = await write_boundary(request)
    parsed = parse_history_metric_query(body)
    authorization = request.headers.get("authorization", "")
    async with DataSourceRegistry.session(log_sql=False) as session:
        async with session.begin():
            current = await require_business_access(
                session, user.user.user_id, "monitor", "monitor.read"
            )
            verify_csrf(DirectoryTokens(credential_cipher()), current, authorization, csrf)
        value = await result_service(request).run(
            session.bind,
            user.user.user_id,
            parsed,
            key,
            request.state.orbit_request_id,
            authorization,
        )
        return JSONResponse(value)
