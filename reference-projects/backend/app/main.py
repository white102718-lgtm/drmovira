import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

from app.api.router import api_router
from app.conf import Env, IdpConf, env
from app.conf.log_conf import init
from app.db.clients import doris_db, erp_db
from app.middleware.profiler import SlowRequestProfilerMiddleware


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}" if route.tags else route.name


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await doris_db.init_pool()
    await erp_db.init_pool()
    yield
    doris_db.pool.close()
    await doris_db.pool.wait_closed()
    erp_db.pool.close()
    await erp_db.pool.wait_closed()


app = FastAPI(
    title="广告智投平台",
    description="",
    version="1.0.0",
    openapi_url="/openapi.json" if os.name == "nt" else None,
    generate_unique_id_function=custom_generate_unique_id,
    debug=True,
    lifespan=lifespan,
)
init("app")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"{request.client.host} 请求验证失败: {exc.errors()}")
    message = "请求参数验证失败" if env != Env.DEV else f"{exc.errors()}"
    return JSONResponse(
        status_code=200,
        content={
            "code": 422,
            "message": message,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logging.error(
        f"{request.client.host} {request.method} {request.url.path} HTTP异常: {exc.detail}, 状态码: {exc.status_code}"
    )
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.detail},
        )
    return JSONResponse(
        status_code=200,
        content={"code": exc.status_code, "message": exc.detail},
    )


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        error_msg = traceback.format_exc()
        logging.error(error_msg)
        return JSONResponse(
            status_code=200,
            content={
                "code": 500,
                "message": "服务器内部错误",
            },
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=IdpConf.SESSION_SECRET,
    session_cookie="backend_session",
    max_age=600,
    same_site="lax",
)
app.add_middleware(SlowRequestProfilerMiddleware)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return ""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
