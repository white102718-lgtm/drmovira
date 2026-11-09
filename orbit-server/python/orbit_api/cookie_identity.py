"""已验证Cookie身份的请求上下文；不能由请求头、正文或浏览器角色声明构造授权。"""

import hmac
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from orbit_api.errors import OrbitError


@dataclass(frozen=True, repr=False)
class CookieIdentity:
    actor_id: int
    tenant_id: str
    auth_version: int
    session_id: str
    csrf_token: str
    expires_at: datetime


_identity: ContextVar[CookieIdentity | None] = ContextVar("orbit_cookie_identity", default=None)


class CookieIdentityBoundary:
    """每个请求独立清理身份，异常路径和并发不能继承上一请求Cookie上下文。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = _identity.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            _identity.reset(token)


def current_cookie_identity():
    return _identity.get()


def bind_verified_cookie(identity: CookieIdentity):
    """仅由完成数据库会话校验的认证适配器调用，不接收未验证HTTP字段。"""
    from orbit_api.native_session import bind_verified_actor

    bind_verified_actor(identity.actor_id, identity.auth_version)
    _identity.set(identity)


def effective_csrf(actor: int, legacy_token: str) -> str:
    identity = current_cookie_identity()
    if identity is None:
        return legacy_token
    if identity.actor_id != actor:
        raise OrbitError(401, "SESSION_REQUIRED", "登录身份已发生变化")
    return identity.csrf_token


def verify_cookie_csrf(actor: int, provided: str) -> bool:
    """返回False表示原Bearer兼容请求仍需原有CSRF校验，绝非免检。"""
    identity = current_cookie_identity()
    if identity is None:
        return False
    if (
        actor != identity.actor_id
        or not isinstance(provided, str)
        or not provided.isascii()
        or not hmac.compare_digest(provided, identity.csrf_token)
    ):
        raise OrbitError(403, "CSRF_INVALID", "请求会话校验失败，请重新加载")
    return True


async def ensure_cookie_current(session, actor: int, *, acting_subject=True):
    """长请求完成前再查当前会话；退出、身份或OIDC配置改变不能被旧事务快照掩盖。"""
    identity = current_cookie_identity()
    if identity is None or not acting_subject:
        return
    if actor != identity.actor_id:
        raise OrbitError(401, "SESSION_REQUIRED", "登录身份已发生变化")
    valid = (
        await session.execute(
            text("""SELECT bs.id FROM orbit_browser_session bs
                JOIN sys_identity_subject subject ON subject.user_id=bs.user_id
                    AND subject.auth_version=bs.auth_version
                JOIN orbit_system_configuration provider ON provider.id=bs.provider_id
                    AND provider.tenant_id=bs.tenant_id AND provider.section='OIDC'
                    AND provider.enabled=1 AND provider.revision=bs.provider_revision
                WHERE bs.id=:id AND bs.tenant_id=:tenant AND bs.user_id=:actor
                    AND bs.auth_version=:version AND bs.status='ACTIVE'
                    AND bs.idle_expires_at>UTC_TIMESTAMP(3)
                    AND bs.absolute_expires_at>UTC_TIMESTAMP(3) FOR SHARE"""),
            {
                "id": identity.session_id,
                "tenant": identity.tenant_id,
                "actor": actor,
                "version": identity.auth_version,
            },
        )
    ).first()
    if valid is None:
        raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "会话已退出或授权已更新，请重新登录")
