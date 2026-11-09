"""户商代称独立技术扩展路由，注册由主线在隔离集成窗口处理。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.reference_routes import transaction, write_boundary
from orbit_api.vendor_alias_contract import parse_vendor_alias, vendor_ids
from orbit_api.vendor_alias_store import VendorAliasStore

router = APIRouter(prefix="/api/v1/vendor-aliases", tags=["ORBIT户商代称扩展"])


def store():
    return VendorAliasStore(DirectoryTokens(credential_cipher()))


@router.get("/capabilities")
async def capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store().capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )
    )


@router.get("")
async def batch(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    _read_boundary(request, {"ids"})
    identifiers = vendor_ids(request.query_params.get("ids", ""))
    return await transaction(lambda session: store().read(session, user.user.user_id, identifiers))


@router.get("/{vendor_id}")
async def get_alias(
    vendor_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store().read(session, user.user.user_id, [vendor_id], single=True)
    )


@router.put("/{vendor_id}")
async def put_alias(
    vendor_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    key, csrf, expected, raw = await write_boundary(request, updating=True, limit=8192)
    value = parse_vendor_alias(raw)
    return await transaction(
        lambda session: store().save(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            vendor_id,
            expected,
            value,
            request.state.orbit_request_id,
        )
    )
