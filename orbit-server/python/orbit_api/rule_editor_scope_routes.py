"""规则账户编辑扩展；由root在原动态Rule路由之前注册，不自动接公共入口。"""

from typing import Annotated
from uuid import uuid4

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.account_scope_contract import MAX_BODY
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.rule_editor_scope_contract import (
    FILTER_FIELDS,
    parse_scope_query,
    parse_scope_write,
)
from orbit_api.rule_editor_scope_store import RuleEditorScopeStore
from orbit_api.rule_routes import write_headers

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则账户选择"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def store():
    return RuleEditorScopeStore(DirectoryTokens(credential_cipher()))


async def read(request, allowed):
    _read_boundary(request, allowed)
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "规则账户GET不接受正文")
    return dict(request.query_params)


@router.get("/editor-accounts")
async def accounts(request: Request, user: User):
    query = parse_scope_query(
        await read(
            request,
            FILTER_FIELDS
            | {"action", "rule_id", "owner_user_id", "owner_team_id", "page_size", "cursor"},
        )
    )
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().accounts(
            session, user.user.user_id, request.headers.get("authorization", ""), query
        )


@router.post("/editor-scope-snapshots", status_code=201)
async def create(request: Request, user: User):
    _read_boundary(request)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise OrbitError(413, "BODY_TOO_LARGE", "规则账户冻结请求超过正文上限")
        raw.extend(chunk)
    value = parse_scope_write(bytes(raw))
    key, csrf, expected = write_headers(request, updating=value.context.action == "UPDATE")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().create(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            csrf,
            key,
            value,
            expected,
            getattr(request.state, "orbit_request_id", str(uuid4())),
        )


@router.get("/editor-scope-snapshots/{snapshot_id}/members")
async def members(snapshot_id: str, request: Request, user: User):
    query = parse_scope_query(await read(request, {"q", "page_size", "cursor"}), members=True)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().members(
            session, user.user.user_id, request.headers.get("authorization", ""), snapshot_id, query
        )
