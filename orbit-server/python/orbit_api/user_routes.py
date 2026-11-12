"""人员列表和详情：原若依认证，独立业务范围，不允许浏览器扩大租户。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.team_routes import list_filters, save
from orbit_api.user_create_store import UserCreateStore
from orbit_api.user_credentials import parse_local_user, parse_password_reset
from orbit_api.user_password_store import UserPasswordStore
from orbit_api.user_store import UserStore
from orbit_api.user_update_store import UserUpdateStore

router = APIRouter(prefix="/api/v1/users", tags=["ORBIT人员管理"])


def create_store():
    return UserCreateStore(DirectoryTokens(credential_cipher()))


def update_store():
    return UserUpdateStore(DirectoryTokens(credential_cipher()))


@router.get("/capabilities")
async def user_capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await create_store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )


@router.post("", status_code=201)
async def create_user(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    return await save(
        request, user, None, kind="USER", store_factory=create_store, parser=parse_local_user
    )


@router.get("/reference-options")
async def user_reference_options(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"kind", "q", "page_size", "cursor", "ids"})
    params = request.query_params
    kind = params.get("kind")
    if kind not in {"TEAM", "ROLE"}:
        raise OrbitError(422, "FIELD_INVALID", "请选择团队或功能角色选项", "/kind")
    size = params.get("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "每页数量只允许20、50、100或200", "/page_size")
    cursor = params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "选项游标无效", "/cursor")
    query = short_text(params.get("q", ""), 100, "/q", required=False)
    selected = None
    if "ids" in params:
        raw = params["ids"]
        if not raw or len(raw) > 3700 or len(raw.split(",")) > 100:
            raise OrbitError(422, "FIELD_INVALID", "名称回显每次最多100个UUID", "/ids")
        selected = sorted(_uuid(value, "/ids") for value in raw.split(","))
        if len(set(selected)) != len(selected):
            raise OrbitError(422, "DUPLICATE_VALUE", "名称回显UUID不能重复", "/ids")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await create_store().options(
            session, user.user.user_id, kind, query, int(size), cursor, selected
        )


@router.get("")
async def list_users(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    filters, cursor = list_filters(request, label="人员", statuses=("ENABLED", "DISABLED"))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await UserStore(DirectoryTokens(credential_cipher())).list(
            session, user.user.user_id, filters, cursor
        )


@router.get("/{user_id}")
async def get_user(
    user_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await UserStore(DirectoryTokens(credential_cipher())).get(
            session, user.user.user_id, user_id
        )


@router.put("/{user_id}")
async def update_user(
    user_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, user_id, kind="USER", store_factory=update_store)


@router.post("/{user_id}/password")
async def reset_user_password(
    user_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(
        request,
        user,
        user_id,
        kind="USER",
        parser=parse_password_reset,
        store_factory=lambda: UserPasswordStore(DirectoryTokens(credential_cipher())),
    )
