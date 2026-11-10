"""Meta读取授权入口；客户Token永远不从响应、查询回跳或日志输出。"""

from typing import Annotated
from urllib.parse import parse_qsl, urlencode

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from starlette.responses import RedirectResponse

from orbit_api.configuration_routes import credential_cipher
from orbit_api.cookie_identity import current_cookie_identity, verify_cookie_csrf
from orbit_api.errors import OrbitError
from orbit_api.meta_connection_contract import MetaApplication
from orbit_api.meta_connection_service import MetaConnectionService, access
from orbit_api.meta_oauth_transport import MetaOAuthTransport
from orbit_api.oidc_contract import parse_authorization_start

router = APIRouter(prefix="/api/v1/integrations/meta", tags=["Meta读取授权"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


def application():
    from config.orbit_runtime import private_values

    values = private_values()
    try:
        return MetaApplication(
            *(
                values.get(key, "")
                for key in (
                    "ORBIT_META_APP_ID",
                    "ORBIT_META_APP_SECRET",
                    "ORBIT_META_GRAPH_VERSION",
                    "ORBIT_META_LOGIN_CONFIG_ID",
                )
            )
        )
    except ValueError:
        raise OrbitError(
            503, "META_APP_NOT_CONFIGURED", "平台Meta应用尚未配置，请联系管理员"
        ) from None


def service():
    app = application()
    return MetaConnectionService(
        lambda: DataSourceRegistry.session(log_sql=False),
        credential_cipher(),
        app,
        MetaOAuthTransport(app),
    )


def boundary(request, actor, *, write=False):
    if request.query_params or "x-target-tenant" in request.headers:
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受租户或额外查询参数")
    identity = current_cookie_identity()
    if identity is None or identity.actor_id != actor:
        raise OrbitError(401, "SESSION_REQUIRED", "请使用浏览器会话连接Meta")
    if write:
        csrf = request.headers.getlist("x-csrf-token")
        keys = request.headers.getlist("idempotency-key")
        if len(csrf) != 1 or not verify_cookie_csrf(actor, csrf[0]):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败")
        if len(keys) != 1 or not 1 <= len(keys[0]) <= 128 or not keys[0].isascii():
            raise OrbitError(400, "IDEMPOTENCY_KEY_REQUIRED", "请求需要唯一有效幂等键")
        return keys[0]


async def body(request, maximum=4096):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > maximum:
            raise OrbitError(413, "BODY_TOO_LARGE", "请求正文超过上限")
        raw.extend(chunk)
    return bytes(raw)


@router.get("/capabilities")
async def capabilities(request: Request, user: User):
    boundary(request, user.user.user_id)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        await access(session, user.user.user_id)
    try:
        application()
        configured = credential_cipher().ready
    except OrbitError:
        configured = False
    return {"csrf_token": current_cookie_identity().csrf_token, "configured": configured}


@router.post("/authorization-sessions")
async def start(request: Request, user: User):
    key = boundary(request, user.user.user_id, write=True)
    value = parse_authorization_start(await body(request))
    return await service().start(
        user.user.user_id, value.return_to, key, request.state.orbit_request_id
    )


@router.post("/connections/{identifier}/authorization-sessions")
async def reauthorize(identifier: str, request: Request, user: User):
    key = boundary(request, user.user.user_id, write=True)
    value = parse_authorization_start(await body(request))
    return await service().start(
        user.user.user_id, value.return_to, key, request.state.orbit_request_id, identifier
    )


@router.get("/callback")
async def callback(request: Request, user: User):
    boundary(request, user.user.user_id)
    try:
        raw = request.scope["state"].get("orbit_callback_query", b"")
        if len(raw) > 16384:
            raise ValueError
        pairs = parse_qsl(
            raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True, max_num_fields=5
        )
        params = dict(pairs)
        if (
            len(pairs) != len(params)
            or "state" not in params
            or set(params) - {"state", "code", "error", "error_reason", "error_description"}
        ):
            raise ValueError
        if ("code" in params) == ("error" in params):
            raise ValueError
    except (ValueError, UnicodeError):
        raise OrbitError(400, "META_CALLBACK_INVALID", "Meta回调参数无效") from None
    target, result = await service().callback(
        user.user.user_id,
        params["state"],
        params.get("code"),
        request.state.orbit_request_id,
        cancelled="error" in params,
    )
    path, separator, fragment = target.partition("#")
    path += ("&" if "?" in path else "?") + urlencode({"meta_result": result})
    return RedirectResponse(
        path + ("#" + fragment if separator else ""),
        status_code=303,
        headers={"Referrer-Policy": "no-referrer"},
    )


@router.get("/connections")
async def connections(request: Request, user: User):
    boundary(request, user.user.user_id)
    # 已存连接可在平台应用配置被暂时撤下时查看状态。
    value = MetaConnectionService(
        lambda: DataSourceRegistry.session(log_sql=False), credential_cipher(), None, None
    )
    return await value.list_connections(user.user.user_id)


@router.post("/connections/{identifier}/disconnect")
async def disconnect(identifier: str, request: Request, user: User):
    from orbit_api.configuration import _parse_json

    key = boundary(request, user.user.user_id, write=True)
    value = _parse_json(await body(request))
    if not isinstance(value, dict) or set(value) != {"revision", "reason"}:
        raise OrbitError(422, "FIELD_INVALID", "断开连接需要版本及原因")
    instance = MetaConnectionService(
        lambda: DataSourceRegistry.session(log_sql=False), credential_cipher(), None, None
    )
    return await instance.disconnect(
        user.user.user_id,
        identifier,
        value["revision"],
        value["reason"],
        key,
        request.state.orbit_request_id,
    )


@router.get("/connections/{identifier}/accounts")
async def candidates(identifier: str, request: Request, user: User):
    boundary(request, user.user.user_id)
    return await service().candidates(user.user.user_id, identifier)


@router.post("/connections/{identifier}/accounts", status_code=202)
async def attach_accounts(identifier: str, request: Request, user: User):
    from sqlalchemy import text

    from orbit_api.account_access import clock, context
    from orbit_api.account_contract import AccountImport
    from orbit_api.account_platform import AccountReadFailure
    from orbit_api.account_routes import account_import_store
    from orbit_api.configuration import _parse_json
    from orbit_api.identity_contract import _uuid
    from orbit_api.meta_account_sources import validate_import_channel
    from orbit_api.meta_connection_contract import selected_accounts

    key = boundary(request, user.user.user_id, write=True)
    value = _parse_json(await body(request, 30000))
    if not isinstance(value, dict) or set(value) != {
        "account_ids",
        "operator_user_id",
        "owner_team_id",
        "vendor_id",
        "channel_id",
    }:
        raise OrbitError(422, "FIELD_INVALID", "请提供候选账户、投手、团队、户商及渠道")
    try:
        ids = selected_accounts(value["account_ids"])
    except ValueError:
        raise OrbitError(422, "FIELD_INVALID", "请选择1至500个不同的可访问账户") from None
    owner, team, vendor = (
        _uuid(value[field], "/" + field)
        for field in ("operator_user_id", "owner_team_id", "vendor_id")
    )
    channel = _uuid(value["channel_id"], "/channel_id") if value["channel_id"] is not None else None
    instance = service()
    available = await instance.candidates(user.user.user_id, identifier)
    if not set(ids) <= {item["external_id"] for item in available["items"]}:
        raise OrbitError(403, "META_ACCOUNT_NOT_ACCESSIBLE", "选择的账户不在当前Meta授权范围")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        integration = await access(session, user.user.user_id)
        current, _managed = await context(session, user.user.user_id, "accounts.import")
        if integration.tenant_id != current.tenant_id:
            raise OrbitError(403, "PERMISSION_DENIED", "集成和账户权限已变化")
        await clock(session, current, write=True)
        connection = await instance.connection(session, current, identifier, lock=True)
        instance.require_live(connection)
        if connection["revision"] != available["connection_revision"]:
            raise OrbitError(409, "META_SOURCE_CHANGED", "账户校验期间授权已更新")
        try:
            await validate_import_channel(session, current, channel)
        except AccountReadFailure:
            raise OrbitError(422, "CHANNEL_UNAVAILABLE", "渠道已停用或当前不可见") from None
        result = await account_import_store().create(
            session,
            user.user.user_id,
            request.headers.get("authorization", ""),
            request.headers["x-csrf-token"],
            key,
            AccountImport(vendor, "\n".join(ids), owner, team),
            request.state.orbit_request_id,
        )
        prior = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_meta_import_source WHERE tenant_id=:tenant AND ba"
                        "tch_id=:batch FOR UPDATE"
                    ),
                    {"tenant": current.tenant_id, "batch": result["id"]},
                )
            )
            .mappings()
            .first()
        )
        if prior:
            if (
                prior["connection_id"] != identifier
                or prior["connection_revision"] != connection["revision"]
                or prior["channel_id"] != channel
            ):
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他来源或渠道")
        else:
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_import_source (tenant_id,batch_id,connection_id,co"
                    "nnection_revision,channel_id,revision) VALUES(:tenant,:batch,:connection,"
                    ":revision,:channel,1)"
                ),
                {
                    "tenant": current.tenant_id,
                    "batch": result["id"],
                    "connection": identifier,
                    "revision": connection["revision"],
                    "channel": channel,
                },
            )
        return result


@router.post("/bm-connections")
async def connect_bm(request: Request, user: User):
    from orbit_api.configuration import _parse_json
    from orbit_api.identity_contract import _uuid

    key = boundary(request, user.user.user_id, write=True)
    value = _parse_json(await body(request))
    if (
        not isinstance(value, dict)
        or set(value) != {"configuration_id", "configuration_revision"}
        or type(value["configuration_revision"]) is not int
        or value["configuration_revision"] < 1
    ):
        raise OrbitError(422, "FIELD_INVALID", "请选择BM配置及当前版本")
    return await service().connect_bm(
        user.user.user_id,
        _uuid(value["configuration_id"], "/configuration_id"),
        value["configuration_revision"],
        key,
        request.state.orbit_request_id,
    )


async def provider_callback(request, kind):
    if request.query_params or "x-target-tenant" in request.headers:
        raise OrbitError(400, "UNKNOWN_FIELD", "回调不接受查询或租户参数")
    try:
        values = parse_qsl(
            (await body(request)).decode("utf-8"),
            strict_parsing=True,
            keep_blank_values=True,
            max_num_fields=1,
        )
        if len(values) != 1 or values[0][0] != "signed_request":
            raise ValueError
    except (ValueError, UnicodeError):
        raise OrbitError(400, "META_CALLBACK_INVALID", "回调需要签名请求") from None
    result = await service().provider_callback(values[0][1], kind)
    if kind == "DELETE":
        return {
            "url": "https://drmovira.com/api/v1/integrations/meta/deletion-status/" + result["id"],
            "confirmation_code": result["id"],
        }
    return {"status": "ok"}


@router.post("/deauthorization")
async def deauthorize(request: Request):
    return await provider_callback(request, "DEAUTHORIZE")


@router.post("/data-deletion")
async def delete_data(request: Request):
    return await provider_callback(request, "DELETE")


@router.get("/deletion-status/{confirmation}")
async def deletion_status(confirmation: str, request: Request):
    from sqlalchemy import text

    from orbit_api.identity_contract import _uuid

    if request.query_params:
        raise OrbitError(400, "UNKNOWN_FIELD", "不接受额外查询字段")
    confirmation = _uuid(confirmation, "/confirmation")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        status = (
            await session.execute(
                text(
                    "SELECT status FROM orbit_meta_callback_receipt WHERE id=:id AND kind='DELETE'"
                ),
                {"id": confirmation},
            )
        ).scalar_one_or_none()
    if status is None:
        raise OrbitError(404, "NOT_FOUND", "删除请求不存在")
    return {"confirmation_code": confirmation, "status": status}
