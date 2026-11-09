"""原若依认证的可选Cookie适配；身份由存储校验，不能降级使用另一个Bearer主体。"""

from urllib.parse import urlsplit

from orbit_api.browser_session_store import BrowserSessionStore
from orbit_api.cookie_identity import bind_verified_cookie, verify_cookie_csrf
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import SESSION_COOKIE, credential_digest

BINDING_COOKIE = "__Host-orbit_browser"


def has_cookie_session(request):
    return any(
        part.strip().partition("=")[0] == SESSION_COOKIE
        for header in request.headers.getlist("cookie")
        for part in header.split(";")
    )


def read_cookie(request, name):
    values = [
        part.strip().partition("=")[2]
        for header in request.headers.getlist("cookie")
        for part in header.split(";")
        if part.strip().partition("=")[0] == name
    ]
    if len(values) != 1:
        raise OrbitError(401, "SESSION_REQUIRED", "登录Cookie缺失或存在歧义")
    credential_digest("SESSION" if name == SESSION_COOKIE else "BROWSER_BINDING", values[0])
    return values[0]


def public_origin():
    from config.orbit_runtime import private_values

    expected = private_values().get("ORBIT_PYTHON_PUBLIC_ORIGIN", "")
    try:
        target = urlsplit(expected)
        if (
            target.scheme != "https"
            or not target.hostname
            or target.username is not None
            or target.password is not None
            or target.path
            or target.query
            or target.fragment
            or target.port not in {None, 443}
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise OrbitError(503, "PUBLIC_ORIGIN_UNAVAILABLE", "服务端HTTPS登录来源尚未配置") from None
    return expected


def require_same_origin(request):
    if request.headers.getlist("origin") != [public_origin()]:
        raise OrbitError(403, "ORIGIN_INVALID", "请求来源校验失败")


async def resolve_cookie_user(request, query_db):
    from common.context import RequestContext
    from config.database import DataSourceRegistry
    from module_admin.service.login_service import LoginService

    from orbit_api.configuration_routes import credential_cipher

    cookie = read_cookie(request, SESSION_COOKIE)
    binding = read_cookie(request, BINDING_COOKIE)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        identity = await BrowserSessionStore(credential_cipher()).resolve(session, cookie, binding)
    bind_verified_cookie(identity)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_same_origin(request)
        csrf = request.headers.getlist("x-csrf-token")
        if len(csrf) != 1:
            raise OrbitError(403, "CSRF_INVALID", "请求需要唯一的会话校验值")
        verify_cookie_csrf(identity.actor_id, csrf[0])
    current = await LoginService._get_current_user_from_db(query_db, identity.actor_id)
    RequestContext.set_current_user(current)
    return current
