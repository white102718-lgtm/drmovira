"""独立mTLS设备监听应用；没有用户Cookie、Bearer、代理证书头或业务管理路由。"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.exc import OperationalError
from starlette.responses import JSONResponse

from orbit_api.agent_monitor_contract import parse_diagnostics, parse_heartbeat, parse_identity
from orbit_api.agent_monitor_store import AgentMonitorStore
from orbit_api.agent_monitor_transport import peer_certificate
from orbit_api.errors import OrbitError
from orbit_api.http_boundary import OrbitApiBoundary, error_body


@asynccontextmanager
async def device_session(session_factory):
    if session_factory is None:
        from config.database import DataSourceRegistry

        factory = DataSourceRegistry.session(log_sql=False)
    else:
        factory = session_factory()
    async with factory as session, session.begin():
        yield session


def create_device_app(session_factory=None):
    """传给Uvicorn的独立ASGI；必须http=PeerCertificateH11Protocol且CERT_REQUIRED。"""
    app = FastAPI(title="ORBIT device mTLS", docs_url=None, redoc_url=None, openapi_url=None)
    store = AgentMonitorStore()

    app.add_middleware(OrbitApiBoundary)

    @app.exception_handler(OrbitError)
    async def business_error(request, error):
        return JSONResponse(
            error_body(
                request.url.path,
                request.state.orbit_request_id,
                error.status,
                error.code,
                error.message,
                error.pointer,
            ),
            status_code=error.status,
        )

    async def transact(operation):
        for attempt in range(3):
            try:
                async with device_session(session_factory) as session:
                    return await operation(session)
            except OperationalError as error:
                if not error.orig.args or error.orig.args[0] not in {1205, 1213}:
                    raise
                if attempt == 2:
                    raise OrbitError(
                        503, "AGENT_MONITOR_BUSY", "设备观察正在并发处理，请保留原序号重试"
                    ) from None
                await asyncio.sleep(0.01 * (attempt + 1))

    async def body(request, limit):
        if request.query_params:
            raise OrbitError(400, "UNKNOWN_FIELD", "设备写入不接受查询字段")
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
            raise OrbitError(415, "CONTENT_TYPE_INVALID", "设备上报必须为JSON")
        if request.headers.get("content-encoding", "identity") != "identity":
            raise OrbitError(415, "CONTENT_ENCODING_INVALID", "设备上报不接受压缩")
        result = bytearray()
        async for chunk in request.stream():
            if len(result) + len(chunk) > limit:
                raise OrbitError(413, "BODY_TOO_LARGE", "设备上报超过有界容量")
            result.extend(chunk)
        return bytes(result)

    @app.get("/api/v1/agent-api/configuration")
    async def configuration(request: Request):
        der = peer_certificate(request.scope)
        if request.query_params:
            raise OrbitError(400, "UNKNOWN_FIELD", "设备配置不接受查询字段")
        return await transact(lambda session: store.configuration(session, der))

    @app.post("/api/v1/agent-api/heartbeats")
    async def heartbeat(request: Request):
        der = peer_certificate(request.scope)
        value = parse_heartbeat(await body(request, 128 * 1024 * 1024))
        return await transact(
            lambda session: store.heartbeat(session, der, value, request.state.orbit_request_id)
        )

    @app.post("/api/v1/agent-api/diagnostics")
    async def diagnostics(request: Request):
        der = peer_certificate(request.scope)
        value = parse_diagnostics(await body(request, 8192))
        return await transact(
            lambda session: store.diagnostics(session, der, value, request.state.orbit_request_id)
        )

    @app.post("/api/v1/agent-api/identity-reports")
    async def identities(request: Request):
        der = peer_certificate(request.scope)
        value = parse_identity(await body(request, 8192))
        return await transact(
            lambda session: store.identity_report(
                session, der, value, request.state.orbit_request_id
            )
        )

    return app
