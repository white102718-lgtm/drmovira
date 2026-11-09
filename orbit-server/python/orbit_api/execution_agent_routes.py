"""环境登记原HTTP接口及精确动作capabilities；不连接执行机地址。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.execution_agent_contract import LIST_FIELDS, parse_agent, parse_agent_filters
from orbit_api.execution_agent_store import ExecutionAgentStore
from orbit_api.reference_routes import transaction, write_boundary

router = APIRouter(prefix="/api/v1/execution-agents", tags=["ORBIT执行机登记"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def store():
    return ExecutionAgentStore(DirectoryTokens(credential_cipher()))


@router.get("/capabilities")
async def capabilities(request: Request, user: User):
    _read_boundary(request, {"operation"})
    return await transaction(
        lambda session: store().capabilities(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            request.query_params.get("operation", "READ"),
        )
    )


@router.get("")
async def list_agents(request: Request, user: User):
    _read_boundary(request, set(LIST_FIELDS))
    filters, cursor = parse_agent_filters(dict(request.query_params))
    return await transaction(
        lambda session: store().list(session, user.user.user_id, filters, cursor)
    )


@router.get("/{resource_id}")
async def get_agent(resource_id: str, request: Request, user: User):
    _read_boundary(request)
    return await transaction(lambda session: store().get(session, user.user.user_id, resource_id))


async def save(request, user, resource_id=None, mode="save"):
    key, csrf, expected, raw = await write_boundary(
        request, updating=resource_id is not None, limit=8192
    )
    value = parse_agent(raw, mode)
    return await transaction(
        lambda session: store().save(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            resource_id,
            expected,
            request.state.orbit_request_id,
            mode=mode,
        )
    )


@router.post("", status_code=201)
async def create_agent(request: Request, user: User):
    return await save(request, user)


@router.put("/{resource_id}")
async def update_agent(resource_id: str, request: Request, user: User):
    return await save(request, user, resource_id)


@router.post("/{resource_id}/revoke")
async def revoke_agent(resource_id: str, request: Request, user: User):
    return await save(request, user, resource_id, "revoke")


@router.post("/{resource_id}/probe")
async def probe_agent(resource_id: str, request: Request, user: User):
    _, csrf, expected, _ = await write_boundary(request, updating=True, empty=True, limit=0)
    return await transaction(
        lambda session: store().unavailable(
            session,
            user.user.user_id,
            resource_id,
            "probe",
            request.headers.get("authorization", ""),
            csrf,
            expected,
        )
    )


@router.get("/{resource_id}/profiles")
async def profiles(resource_id: str, request: Request, user: User):
    _read_boundary(request, set(LIST_FIELDS))
    return await transaction(
        lambda session: store().unavailable(session, user.user.user_id, resource_id, "profiles")
    )
