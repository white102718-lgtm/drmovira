"""投放计划原HTTP入口；新router由主线显式登记，禁止本模块自动迁移或外发广告。"""

from typing import Annotated
from urllib.parse import urlencode

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from starlette.requests import Request as StarletteRequest

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.launch_contract import MAX_CONFIG_BYTES, parse_plan, uuid_field
from orbit_api.launch_options import ownership_options
from orbit_api.launch_store import LaunchStore
from orbit_api.reference_routes import transaction, write_boundary
from orbit_api.team_routes import list_filters

router = APIRouter(prefix="/api/v1/launch-plans", tags=["ORBIT投放计划"])


def store(request):
    return LaunchStore(
        DirectoryTokens(credential_cipher()),
        metric_profile_fixture=getattr(request.app.state, "metric_profile_fixture_mode", False),
    )


def collection_filters(request, *, templates=False):
    extra = {"operator_user_id"} | (set() if templates else {"channel_id"})
    _read_boundary(request, {"q", "cursor", "page_size", "status", "date_from", "date_to"} | extra)
    scope = dict(request.scope)
    scope["query_string"] = urlencode(
        [(key, value) for key, value in request.query_params.multi_items() if key not in extra]
    ).encode()
    filters, cursor = list_filters(
        StarletteRequest(scope),
        "模板" if templates else "计划",
        statuses=("ACTIVE", "ARCHIVED")
        if templates
        else ("DRAFT", "VALIDATED", "SUBMITTED", "ARCHIVED"),
    )
    for key in extra:
        if key in request.query_params:
            filters[key] = uuid_field(request.query_params[key], (key,))
    return filters, cursor


@router.get("/capabilities")
async def capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store(request).capabilities(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            validation_provider=getattr(request.app.state, "launch_validation_provider", None),
        )
    )


@router.get("")
async def list_plans(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    filters, cursor = collection_filters(request)
    return await transaction(
        lambda session: store(request).list(session, user.user.user_id, filters, cursor)
    )


@router.get("/ownership-options")
async def owner_options(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request, {"cursor", "page_size"})
    size = request.query_params.get("page_size", "200")
    if size not in {"20", "50", "100", "200"}:
        from orbit_api.errors import OrbitError

        raise OrbitError(422, "FIELD_VALIDATION_FAILED", "每页数量无效", "/page_size")
    return await transaction(
        lambda session: ownership_options(
            session,
            store(request).tokens,
            user.user.user_id,
            cursor=request.query_params.get("cursor"),
            page_size=int(size),
        )
    )


@router.get("/{plan_id}")
async def get_plan(
    plan_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store(request).get(session, user.user.user_id, plan_id)
    )


async def save(request, user, plan_id=None):
    key, csrf, expected, raw = await write_boundary(
        request, updating=plan_id is not None, limit=MAX_CONFIG_BYTES
    )
    value = parse_plan(raw)
    return await transaction(
        lambda session: store(request).save(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            plan_id,
            expected,
            request.state.orbit_request_id,
        )
    )


@router.post("", status_code=201)
async def create_plan(request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]):
    return await save(request, user)


@router.put("/{plan_id}")
async def update_plan(
    plan_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, plan_id)
