"""模板原二级页HTTP合同，挂launch菜单，独立模板动作而非隐含计划读授权。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.launch_contract import MAX_CONFIG_BYTES
from orbit_api.launch_routes import collection_filters
from orbit_api.reference_routes import transaction, write_boundary
from orbit_api.template_contract import parse_template, parse_template_action
from orbit_api.template_store import TemplateStore

router = APIRouter(prefix="/api/v1/templates", tags=["ORBIT投放配置模板"])


def store(request):
    return TemplateStore(
        DirectoryTokens(credential_cipher()),
        metric_profile_fixture=getattr(request.app.state, "metric_profile_fixture_mode", False),
    )


@router.get("/capabilities")
async def capabilities(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store(request).capabilities(
            session, user.user.user_id, request.headers.get("authorization", "")
        )
    )


@router.get("")
async def list_templates(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    filters, cursor = collection_filters(request, templates=True)
    return await transaction(
        lambda session: store(request).list(session, user.user.user_id, filters, cursor)
    )


@router.get("/{template_id}")
async def get_template(
    template_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    return await transaction(
        lambda session: store(request).get(session, user.user.user_id, template_id)
    )


async def save(request, user, template_id=None, mode="save"):
    key, csrf, expected, raw = await write_boundary(
        request, updating=template_id is not None, limit=MAX_CONFIG_BYTES
    )
    value = parse_template(raw) if mode == "save" else parse_template_action(raw, mode)
    method = store(request).apply if mode == "apply" else store(request).save
    if mode == "apply":
        return await transaction(
            lambda session: method(
                session,
                user.user.user_id,
                request.headers.get("authorization", ""),
                csrf,
                key,
                template_id,
                expected,
                value,
                request.state.orbit_request_id,
            )
        )
    return await transaction(
        lambda session: method(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            template_id,
            expected,
            request.state.orbit_request_id,
            mode,
        )
    )


@router.post("", status_code=201)
async def create_template(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user)


@router.put("/{template_id}")
async def update_template(
    template_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, template_id)


@router.post("/{template_id}/archive")
async def archive_template(
    template_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, template_id, "archive")


@router.post("/{template_id}/share")
async def share_template(
    template_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, template_id, "share")


@router.post("/{template_id}/apply", status_code=201)
async def apply_template(
    template_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await save(request, user, template_id, "apply")
