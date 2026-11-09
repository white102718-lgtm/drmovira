"""ORBIT功能角色接口；原若依认证和布局保留，业务角色由受控事务维护。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.role_store import RoleStore
from orbit_api.team_routes import list_filters, save

router = APIRouter(prefix="/api/v1/roles", tags=["ORBIT功能角色"])


def store():
    return RoleStore(DirectoryTokens(credential_cipher()))


@router.get("/capabilities")
async def role_capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )


@router.get("")
async def list_roles(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    filters, cursor = list_filters(request, label="角色")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().list(session, user.user.user_id, filters, cursor)


@router.get("/{role_id}")
async def get_role(
    role_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().get(session, user.user.user_id, role_id)


@router.post("", status_code=201)
async def create_role(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    return await save(request, user, None, kind="ROLE", store_factory=store)


@router.put("/{role_id}")
async def update_role(
    role_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, role_id, kind="ROLE", store_factory=store)
