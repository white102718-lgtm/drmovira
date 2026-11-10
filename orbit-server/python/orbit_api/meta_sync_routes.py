"""Meta采集设置与状态HTTP入口；原指标查询合同不变。"""

from datetime import UTC, datetime
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request, Response
from module_admin.entity.vo.user_vo import CurrentUserModel
from sqlalchemy import text

from orbit_api.account_access import clock, parameters, visible_clause
from orbit_api.authorization import require_business_access
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.cookie_identity import current_cookie_identity
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.meta_connection_routes import body, boundary
from orbit_api.meta_sync_store import (
    parse_policy,
    policy_access,
    policy_choices,
    public_job,
    public_policy,
    read_policy,
    save_policy,
    stamp,
)

router = APIRouter(tags=["Meta只读采集设置与状态"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@router.get("/api/v1/integrations/meta/sync-settings")
async def get_settings(request: Request, response: Response, user: User):
    boundary(request, user.user.user_id)
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await policy_access(session, user.user.user_id)
        row = await read_policy(session, current)
        choices = await policy_choices(session, current)
        return public_policy(row) | {
            "csrf_token": current_cookie_identity().csrf_token,
            "choices": choices,
        }


@router.put("/api/v1/integrations/meta/sync-settings")
async def put_settings(request: Request, user: User):
    key = boundary(request, user.user.user_id, write=True)
    value = parse_policy(await body(request))
    matches = request.headers.getlist("if-match")
    if len(matches) != 1 or matches[0] != '"' + str(value["revision"]) + '"':
        raise OrbitError(400, "IF_MATCH_REQUIRED", "请携带读取时的完整采集设置版本")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await policy_access(session, user.user.user_id)
        return await save_policy(session, current, value, key, request.state.orbit_request_id)


@router.get("/api/v1/metrics/sync-status")
async def sync_status(request: Request, response: Response, user: User):
    _read_boundary(request, {"account_id", "cursor"})
    account = request.query_params.get("account_id")
    if account is not None:
        account = _uuid(account, "/account_id")
    cursor = request.query_params.get("cursor")
    tokens = DirectoryTokens(credential_cipher())
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await require_business_access(
            session, user.user.user_id, "monitor", "monitor.read"
        )
        version = await clock(session, current)
        binding = tokens.session_binding(
            request.headers.get("authorization", ""), current.actor_id, current.tenant_id
        )
        after = ""
        if cursor is not None:
            payload = tokens.verify("META_SYNC_STATUS_CURSOR_V1", cursor)
            if (
                payload.get("tenant") != current.tenant_id
                or payload.get("actor") != current.actor_id
                or payload.get("binding") != binding
                or payload.get("account") != account
                or payload.get("scope_version") != version
            ):
                raise OrbitError(409, "CURSOR_STALE", "账户范围或当前会话已变化，请刷新采集状态")
            if not isinstance(payload.get("after"), str):
                raise OrbitError(400, "CURSOR_INVALID", "采集状态游标无效")
            after = _uuid(payload["after"], "/cursor")
        params = parameters(current) | {"after": after, "account": account}
        where = (
            "a.tenant_id=:tenant AND a.unbound_at IS NULL AND ("
            + visible_clause(current, "a")
            + ")"
        )
        if account is not None:
            visible = (
                await session.execute(
                    text(
                        "SELECT a.id FROM orbit_ad_account a WHERE "
                        + where
                        + " AND a.id=:account FOR SHARE OF a"
                    ),
                    params,
                )
            ).scalar_one_or_none()
            if visible is None:
                raise OrbitError(404, "NOT_FOUND", "账户不存在或当前不可见")
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT a.id account_id,a.name account_name,j.id job_id,j.state,j.upd"
                        "ated_at,j.checkpoint_json,"
                        "j.attempts,j.next_run_at,j.page_number,j.date_from,j.date_to,j.profi"
                        "le_id,j.profile_version,"
                        "j.adapter_version,(SELECT MAX(p.updated_at) FROM orbit_meta_metric_job p "
                        "WHERE p.tenant_id=a.tenant_id AND p.account_id=a.id AND p.state='PUB"
                        "LISHED') last_published_at "
                        "FROM orbit_ad_account a JOIN orbit_meta_account_source s ON s.tenant"
                        "_id=a.tenant_id AND s.account_id=a.id "
                        "LEFT JOIN orbit_meta_metric_job j ON j.tenant_id=a.tenant_id AND j.i"
                        "d=(SELECT n.id FROM orbit_meta_metric_job n "
                        "WHERE n.tenant_id=a.tenant_id AND n.account_id=a.id ORDER BY n.creat"
                        "ed_at DESC,n.id DESC LIMIT 1) "
                        "WHERE "
                        + where
                        + " AND a.id>:after "
                        + ("AND a.id=:account " if account is not None else "")
                        + "ORDER BY a.id LIMIT 51"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        page = rows[:50]
        next_cursor = (
            tokens.issue(
                "META_SYNC_STATUS_CURSOR_V1",
                {
                    "tenant": current.tenant_id,
                    "actor": current.actor_id,
                    "binding": binding,
                    "account": account,
                    "scope_version": version,
                    "after": page[-1]["account_id"],
                },
            )
            if len(rows) > 50
            else None
        )
        return {
            "items": [
                {
                    "account_id": r["account_id"],
                    "account_name": r["account_name"],
                    "latest_job": public_job(r),
                    "last_published_at": stamp(r["last_published_at"]),
                }
                for r in page
            ],
            "next_cursor": next_cursor,
            "scope_version": version,
            "data_as_of": stamp(datetime.now(UTC)),
        }


@router.get("/api/v1/integrations/meta/connections/{identifier}/sync-settings")
async def get_connection_settings(
    identifier: str, request: Request, response: Response, user: User
):
    boundary(request, user.user.user_id)
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await policy_access(session, user.user.user_id)
        row = await read_policy(session, current, connection_id=identifier)
        choices = await policy_choices(session, current, connection_id=identifier)
        return public_policy(row) | {
            "csrf_token": current_cookie_identity().csrf_token,
            "choices": choices,
        }


@router.put("/api/v1/integrations/meta/connections/{identifier}/sync-settings")
async def put_connection_settings(identifier: str, request: Request, user: User):
    key = boundary(request, user.user.user_id, write=True)
    value = parse_policy(await body(request))
    matches = request.headers.getlist("if-match")
    if len(matches) != 1 or matches[0] != '"' + str(value["revision"]) + '"':
        raise OrbitError(400, "IF_MATCH_REQUIRED", "请携带当前连接采集设置版本")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        current = await policy_access(session, user.user.user_id)
        return await save_policy(
            session, current, value, key, request.state.orbit_request_id, connection_id=identifier
        )
