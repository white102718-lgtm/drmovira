"""渠道HTTP合同：完整列表/创建/详情/编辑/分配/停用和候选技术扩展。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.channel_contract import parse_channel
from orbit_api.channel_store import ChannelStore
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import uuid_value
from orbit_api.reference_routes import transaction, write_boundary
from orbit_api.team_routes import list_filters

router = APIRouter(prefix="/api/v1/channels", tags=["ORBIT渠道"])


def store():
    return ChannelStore(DirectoryTokens(credential_cipher()))


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


@router.get("/ownership-options")
async def ownership_options(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"after", "page_size"})
    size = request.query_params.get("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "每页数量无效")
    return await transaction(
        lambda session: store().ownership_options(
            session, user.user.user_id, request.query_params.get("after", ""), int(size)
        )
    )


@router.get("")
async def list_channels(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    filters, cursor = list_filters(request, "渠道")
    return await transaction(
        lambda session: store().list(session, user.user.user_id, filters, cursor)
    )


@router.get("/display-labels")
async def display_labels(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"ids"})
    raw = request.query_params.get("ids", "")
    if len(raw) > 7_400:
        raise OrbitError(422, "FIELD_INVALID", "一次最多读取200个渠道名称")
    identifiers = raw.split(",")
    if not 1 <= len(identifiers) <= 200 or len(set(identifiers)) != len(identifiers):
        raise OrbitError(422, "FIELD_INVALID", "渠道UUID必须为1至200个不重复值")
    identifiers = [uuid_value(value, "/ids") for value in identifiers]
    return await transaction(
        lambda session: store().display_labels(session, user.user.user_id, identifiers)
    )


@router.get("/{channel_id}")
async def get_channel(
    channel_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(lambda session: store().get(session, user.user.user_id, channel_id))


@router.get("/{channel_id}/edit-context")
async def edit_context(
    channel_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store().edit_context(session, user.user.user_id, channel_id)
    )


async def save(request, user, channel_id=None, mode="save"):
    key, csrf, expected, raw = await write_boundary(
        request, updating=channel_id is not None, limit=131_072
    )
    value = parse_channel(raw, mode)
    return await transaction(
        lambda session: store().save(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            channel_id,
            expected,
            request.state.orbit_request_id,
            mode,
        )
    )


@router.post("", status_code=201)
async def create_channel(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user)


@router.put("/{channel_id}")
async def update_channel(
    channel_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, channel_id)


@router.put("/{channel_id}/owners")
async def assign_channel(
    channel_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, channel_id, "owners")


@router.post("/{channel_id}/archive")
async def archive_channel(
    channel_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, channel_id, "archive")
