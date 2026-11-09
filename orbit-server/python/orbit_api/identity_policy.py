"""身份与团队共用管理员存续策略，检查实际可恢复组织访问的权限。"""

from sqlalchemy import text

from orbit_api.authorization import require_system_access
from orbit_api.errors import OrbitError


async def has_recoverable_administrator(session, tenant: str) -> bool:
    """启用SUPER_ADMIN须实际可维护团队；原菜单/动作并集与当前数据范围共同生效。

    团队停用会阻断整个成员上下文，留下一个无团队维护动作的SUPER_ADMIN仍可能锁死系统。
    当前读与调用方目录锁共同持有。通常先命中内置管理员；这里不扫描业务账户或统计事实。
    """
    candidates = (
        (
            await session.execute(
                text("""
        SELECT s.user_id FROM orbit_user_scope s
        JOIN sys_user u ON u.user_id=s.user_id AND u.status='0' AND u.del_flag='0'
        JOIN orbit_business_user b ON b.tenant_id=s.tenant_id
            AND b.user_id=s.user_id AND b.enabled=1
        JOIN orbit_business_team t ON t.tenant_id=b.tenant_id AND t.id=b.team_id AND t.enabled=1
        WHERE s.tenant_id=:tenant AND s.enabled=1 AND s.data_role='SUPER_ADMIN'
        ORDER BY s.user_id FOR SHARE
    """),
                {"tenant": tenant},
            )
        )
        .scalars()
        .all()
    )
    for actor in candidates:
        try:
            context = await require_system_access(
                session, actor, 31083, "system.teams.manage", super_admin=True, acting_subject=False
            )
            if context.tenant_id == tenant:
                return True
        except OrbitError as error:
            if error.status != 403:
                raise
    return False
