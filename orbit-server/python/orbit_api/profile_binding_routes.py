"""Profile关联原接口及明确解绑扩展，不接受客户端探测证明。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.material_routes import bounded_body, write_headers
from orbit_api.profile_binding_contract import identifier, parse_unbind, parse_write
from orbit_api.profile_binding_store import ProfileBindingStore

router = APIRouter(prefix="/api/v1/profile-bindings", tags=["ORBIT环境账户关联"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def store():
    return ProfileBindingStore(DirectoryTokens(credential_cipher()))


@router.get("")
async def list_bindings(request: Request, user: User):
    _read_boundary(request, {"cursor", "page_size"})
    size = request.query_params.get("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "分页数量必须为20/50/100/200", "/page_size")
    cursor = request.query_params.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "游标长度无效", "/cursor")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().list(session, user.user.user_id, int(size), cursor)


@router.get("/{resource_id}")
async def get_binding(resource_id: str, request: Request, user: User):
    _read_boundary(request)
    identifier(resource_id)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().get(session, user.user.user_id, resource_id)


async def write(request, user, resource_id=None, unbind=False):
    _read_boundary(request)
    if resource_id is not None:
        identifier(resource_id)
    authorization, csrf, key, revision = write_headers(request, version=resource_id is not None)
    value = (parse_unbind if unbind else parse_write)(await bounded_body(request, 16384))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        if unbind:
            return await store().unbind(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                resource_id,
                revision,
                value,
                request.state.orbit_request_id,
            )
        return await store().save(
            session,
            user.user.user_id,
            authorization,
            csrf,
            key,
            value,
            resource_id,
            revision,
            request.state.orbit_request_id,
        )


@router.post("", status_code=201)
async def create_binding(request: Request, user: User):
    return await write(request, user)


@router.put("/{resource_id}")
async def update_binding(resource_id: str, request: Request, user: User):
    return await write(request, user, resource_id)


@router.post("/{resource_id}/unbind")
async def unbind_binding(resource_id: str, request: Request, user: User):
    return await write(request, user, resource_id, True)
