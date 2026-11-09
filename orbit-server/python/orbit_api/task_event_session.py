"""显式短会话的原认证适配；注入原服务便于无私有配置协议单测。"""

from orbit_api.cookie_identity import current_cookie_identity
from orbit_api.errors import OrbitError


async def resolve_actor(session, request, login_service, auth_error):
    identity = current_cookie_identity()
    if identity is not None:
        # 当前Cookie授权/退出/提供者版本将在Task authorize的ensure_cookie_current再次核验。
        return identity.actor_id
    bearer = request.headers.get("authorization", "")
    try:
        if bearer.startswith("Bearer "):
            user = await login_service.get_current_user_for_plugin_session(request, bearer, session)
        else:
            # 首次Cookie请求尚未绑定ContextVar，须调用原注册external resolver；
            # 本方法显式短会话，不能引入随整条SSE存活的yield依赖。
            user = await login_service.get_current_user(request, None, session)
    except auth_error:
        raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "事件会话已失效，请重新登录") from None
    if user is None:
        raise OrbitError(401, "SESSION_REQUIRED", "事件流需要真实登录会话")
    return user.user.user_id
