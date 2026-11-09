"""原若依令牌绑定持久身份版本，阻止停用后启用使旧会话复活。"""

from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import text

from orbit_api.errors import OrbitError


@dataclass(frozen=True, repr=False)
class AuthSnapshot:
    actor_id: int
    version: int


_snapshot: ContextVar[AuthSnapshot | None] = ContextVar("orbit_auth_snapshot", default=None)


class AuthSnapshotBoundary:
    """请求级隔离，覆盖原若依及ORBIT路径；异常和并发请求不能继承另一身份。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = _snapshot.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            _snapshot.reset(token)


def current_auth_snapshot():
    return _snapshot.get()


def bind_verified_actor(actor_id: int, version: int):
    """Cookie适配器经数据库复核后绑定同一原身份版本，不接受前端自报用户或版本。"""
    if type(actor_id) is not int or actor_id <= 0 or type(version) is not int or version < 1:
        raise OrbitError(401, "SESSION_REQUIRED", "登录身份无效")
    _snapshot.set(AuthSnapshot(actor_id, version))


def verify_actor_snapshot(actor_id, version, *, acting_subject=True):
    snapshot = _snapshot.get()
    # 后台可信服务没有HTTP令牌；管理员存续策略需评估其他候选者，而不是冒充其会话。
    if snapshot is None or not acting_subject:
        return
    if snapshot.actor_id != actor_id or snapshot.version != version:
        raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "会话权限已更新，请重新登录")


def _actor_id(payload):
    from exceptions.exception import AuthException

    value = payload.get("user_id")
    if type(value) is int and 0 < value < 2**63:
        return value
    if (
        isinstance(value, str)
        and 1 <= len(value) <= 19
        and value.isascii()
        and value.isdigit()
        and 0 < int(value) < 2**63
    ):
        return int(value)
    raise AuthException(data="", message="登录会话已失效，请重新登录")


async def _version(actor):
    from config.database import DataSourceRegistry
    from exceptions.exception import AuthException

    # 独立短读事务：不占用原控制器事务，也不把身份行锁一直持有到外部平台网络返回。
    # 业务用户按唯一当前scope校验；历史成员行不决定别租户会话。完全未映射者保留原框架登录。
    async with DataSourceRegistry.session(log_sql=False) as session:
        version = (
            await session.execute(
                text("""
            SELECT i.auth_version FROM sys_identity_subject i JOIN sys_user u ON u.user_id=i.user_id
            WHERE i.user_id=:actor AND u.status='0' AND u.del_flag='0'
            AND (
                (NOT EXISTS (SELECT 1 FROM orbit_user_scope s WHERE s.user_id=u.user_id)
                 AND NOT EXISTS (SELECT 1 FROM orbit_business_user b WHERE b.user_id=u.user_id))
                OR EXISTS (
                    SELECT 1 FROM orbit_user_scope s
                    JOIN orbit_business_user b ON b.user_id=s.user_id AND b.tenant_id=s.tenant_id
                    JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1
                    JOIN orbit_business_team bt ON bt.tenant_id=b.tenant_id AND bt.id=b.team_id
                    WHERE s.user_id=u.user_id AND s.enabled=1 AND b.enabled=1 AND b.invited=0
                        AND bt.enabled=1 AND s.data_role IN ('USER','TEAM_ADMIN','SUPER_ADMIN')
                )
            )
        """),
                {"actor": actor},
            )
        ).scalar_one_or_none()
    if version is None:
        raise AuthException(data="", message="登录身份已失效或尚未初始化，请重新登录")
    return version


async def enrich_native_token(payload):
    """账号密码由原框架验证后调用；版本只从数据库取得，不采信登录JSON扩展字段。"""
    return {**payload, "auth_version": await _version(_actor_id(payload))}


async def validate_native_token(payload):
    from exceptions.exception import AuthException

    actor = _actor_id(payload)
    version = payload.get("auth_version")
    if type(version) is not int or version < 1 or version != await _version(actor):
        raise AuthException(data="", message="会话权限已更新，请重新登录")
    _snapshot.set(AuthSnapshot(actor, version))
