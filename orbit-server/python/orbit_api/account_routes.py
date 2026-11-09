"""账户导入API：只受理和读取真实持久化批次，未执行不能返回平台成功。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from config.orbit_runtime import private_values
from fastapi import APIRouter, Depends, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_contract import parse_import
from orbit_api.account_import_store import AccountImportStore
from orbit_api.account_objects import AccountImportObjects
from orbit_api.account_store import AccountStore
from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid

router = APIRouter(prefix="/api/v1/account-imports", tags=["ORBIT账户导入"])
accounts_router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户目录"])


def account_import_store():
    root = private_values().get("ORBIT_PYTHON_ACCOUNT_IMPORT_OBJECT_ROOT")
    if not isinstance(root, str) or not root.strip():
        raise OrbitError(503, "ACCOUNT_OBJECT_STORAGE_REQUIRED", "账户导入原始对象存储尚未配置")
    try:
        objects = AccountImportObjects(root)
    except (ValueError, OSError):
        raise OrbitError(
            503, "ACCOUNT_OBJECT_STORAGE_REQUIRED", "账户导入原始对象存储不可用"
        ) from None
    return AccountImportStore(DirectoryTokens(credential_cipher()), objects)


Store = Annotated[AccountImportStore, Depends(account_import_store)]
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/capabilities")
async def capabilities(request: Request, user: User, store: Store):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store.capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )


@router.get("/owner-options")
async def owner_options(request: Request, user: User, store: Store):
    _read_boundary(request, {"q", "cursor"})
    query = short_text(request.query_params.get("q", ""), 100, "/q", required=False)
    cursor = request.query_params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "投手候选游标无效", "/cursor")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store.owner_options(session, user.user.user_id, query, cursor)


@router.post("", status_code=202)
async def create_import(request: Request, user: User, store: Store):
    _read_boundary(request)
    csrf, keys = request.headers.getlist("x-csrf-token"), request.headers.getlist("idempotency-key")
    if len(csrf) != 1:
        raise OrbitError(403, "CSRF_INVALID", "账户导入需要唯一会话校验值")
    if (
        len(keys) != 1
        or not 16 <= len(keys[0]) <= 128
        or not all(" " <= ch <= "~" for ch in keys[0])
    ):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "账户导入需要16至128位可见ASCII幂等键")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 100000:
            raise OrbitError(413, "BODY_TOO_LARGE", "账户导入请求超过正文上限")
        raw.extend(chunk)
    value = parse_import(bytes(raw))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store.create(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf[0],
            keys[0],
            value,
            request.state.orbit_request_id,
        )


@router.get("/{batch_id}")
async def get_import(batch_id: str, request: Request, user: User, store: Store):
    # cursor是批次详情的独立技术扩展，原ImportBatch正文保持原字段。
    _read_boundary(request, {"cursor"})
    cursor = request.query_params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "导入行游标长度无效", "/cursor")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store.get(session, user.user.user_id, _uuid(batch_id, "/id"), cursor)


@accounts_router.get("")
async def list_accounts(request: Request, user: User):
    from orbit_api.account_details_contract import filters as details_filters

    _read_boundary(
        request,
        {
            "q",
            "status",
            "auth_status",
            "operator_user_id",
            "vendor_id",
            "page_size",
            "cursor",
            "mode",
            "date_from",
            "date_to",
        },
    )
    query = details_filters(request.query_params)
    cursor = request.query_params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "账户游标无效", "/cursor")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountStore(DirectoryTokens(credential_cipher())).list(
            session, user.user.user_id, query, cursor
        )


@accounts_router.get("/{account_id}")
async def get_account(account_id: str, request: Request, user: User):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountStore(DirectoryTokens(credential_cipher())).get(
            session, user.user.user_id, _uuid(account_id, "/id")
        )
