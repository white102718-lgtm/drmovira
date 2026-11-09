"""未注册的账户18列独立API；主任务统一接入，原Account和identities合同保持。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Depends, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from starlette.responses import JSONResponse

from orbit_api.account_details_contract import filters
from orbit_api.account_details_store import AccountDetailsStore
from orbit_api.account_read_identity import account_read_identity
from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_publication_summary import IdentityPublicationSummary
from orbit_api.read_sessions import read_committed_session

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户18列"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]
ReadUser = Annotated[CurrentUserModel, Depends(account_read_identity)]
PARAMETERS = {
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
}


def details_store():
    """列表与详情共用已封印摘要；未知来源仍返回UNKNOWN/null，不现场扫描资源。"""
    cipher = credential_cipher()
    return AccountDetailsStore(
        DirectoryTokens(cipher), identity_summary=IdentityPublicationSummary(cipher)
    )


@router.get("/owner-options")
async def owner_options(request: Request, user: User):
    _read_boundary(request, {"q", "page_size", "cursor"})
    params = request.query_params
    if params.get("page_size", "50") not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "投手每页只允许20、50、100或200条", "/page_size")
    cursor = params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "投手游标长度无效", "/cursor")
    query = short_text(params.get("q", ""), 100, "/q", required=False)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await AccountDetailsStore(DirectoryTokens(credential_cipher())).owner_options(
            session, user.user.user_id, query, int(params.get("page_size", "50")), cursor
        )


@router.get("/extended")
async def extended(request: Request, user: ReadUser):
    _read_boundary(request, PARAMETERS)
    query = filters(request.query_params)
    cursor = request.query_params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "账户日期游标长度无效", "/cursor")
    async with read_committed_session(DataSourceRegistry) as session, session.begin():
        value = await details_store().list(session, user.user.user_id, query, cursor)
        # Store已生成严格JSON值：Money/UUID/时间都是字符串；避免对200行嵌套DTO再次递归转换。
        # JSONResponse仍严格拒绝非JSON值及NaN；提交和统一安全响应头保持原外层生命周期。
        return JSONResponse(value)


@router.get("/{account_id}/details")
async def details(account_id: str, request: Request, user: ReadUser):
    _read_boundary(request, {"mode", "date_from", "date_to"})
    query = filters(request.query_params)
    async with read_committed_session(DataSourceRegistry) as session, session.begin():
        value = await details_store().list(session, user.user.user_id, query, identifier=account_id)
        return value["items"][0]
