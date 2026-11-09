"""ORBIT实时菜单与可信租户复核，不把缓存权限字符串或浏览器tenant参数当作授权。"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from orbit_api.errors import OrbitError
from orbit_api.native_session import verify_actor_snapshot


@dataclass(frozen=True, repr=False)
class BusinessContext:
    actor_id: int
    tenant_id: str
    data_role: str
    subject_id: str
    team_id: str


async def _require_access(
    session: AsyncSession,
    actor_id: int,
    leaf_menu_id: int,
    permission: str,
    *,
    parent_menu_id: int,
    menu_code: str,
    menu_permission: str,
    super_admin: bool = False,
    acting_subject: bool = True,
) -> BusinessContext:
    """授权查询使用共享锁与调用方事务共同持有；功能角色并集不能扩展数据角色。"""
    scope = (
        (
            await session.execute(
                text("""
        SELECT s.tenant_id,s.data_role,b.id AS subject_id,b.team_id,i.auth_version
        FROM orbit_user_scope s
        JOIN sys_user u ON u.user_id=s.user_id AND u.status='0' AND u.del_flag='0'
        JOIN sys_identity_subject i ON i.user_id=u.user_id
        JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1
        JOIN orbit_business_user b ON b.tenant_id=s.tenant_id
            AND b.user_id=s.user_id AND b.enabled=1 AND b.invited=0
        JOIN orbit_business_team bt ON bt.tenant_id=b.tenant_id AND bt.id=b.team_id AND bt.enabled=1
        WHERE s.user_id=:actor AND s.enabled=1 FOR SHARE
    """),
                {"actor": actor_id},
            )
        )
        .mappings()
        .first()
    )
    if (
        scope is None
        or scope["data_role"] not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}
        or (super_admin and scope["data_role"] != "SUPER_ADMIN")
    ):
        raise OrbitError(403, "PERMISSION_DENIED", "当前业务授权已失效")
    verify_actor_snapshot(actor_id, scope["auth_version"], acting_subject=acting_subject)
    from orbit_api.cookie_identity import ensure_cookie_current

    await ensure_cookie_current(session, actor_id, acting_subject=acting_subject)
    rows = (
        (
            await session.execute(
                text("""
        SELECT m.menu_id,m.parent_id,m.perms FROM sys_user_role ur
        JOIN sys_role r ON r.role_id=ur.role_id AND r.status='0' AND r.del_flag='0'
        LEFT JOIN orbit_business_role br ON br.native_role_id=r.role_id
        JOIN sys_menu m ON m.menu_id IN(31000,:parent,:leaf) AND m.status='0'
        LEFT JOIN sys_role_menu rm ON rm.role_id=r.role_id AND rm.menu_id=m.menu_id
        WHERE ur.user_id=:actor AND ((:actor=1 AND r.role_id=1) OR rm.menu_id IS NOT NULL)
          AND (br.native_role_id IS NULL OR br.tenant_id=:tenant)
          AND (br.native_role_id IS NULL OR (:actor=1 AND r.role_id=1)
            OR (m.menu_id=31000 AND EXISTS(SELECT 1 FROM orbit_business_role_menu bg
                WHERE bg.tenant_id=br.tenant_id AND bg.role_id=br.id FOR SHARE))
            OR (m.menu_id=:parent AND EXISTS(SELECT 1 FROM orbit_business_role_menu bg
                WHERE bg.tenant_id=br.tenant_id AND bg.role_id=br.id
                    AND bg.menu_code=:menu_code FOR SHARE))
            OR (m.menu_id=:leaf AND EXISTS(SELECT 1 FROM orbit_business_role_action ba
                WHERE ba.tenant_id=br.tenant_id AND ba.role_id=br.id
                    AND ba.permission_code=:permission FOR SHARE)))
        FOR SHARE
    """),
                {
                    "actor": actor_id,
                    "leaf": leaf_menu_id,
                    "tenant": scope["tenant_id"],
                    "permission": permission,
                    "parent": parent_menu_id,
                    "menu_code": menu_code,
                },
            )
        )
        .mappings()
        .all()
    )
    granted = {row["menu_id"]: row for row in rows}
    if (
        set(granted) != {31000, parent_menu_id, leaf_menu_id}
        or granted[31000]["parent_id"] != 0
        or granted[parent_menu_id]["parent_id"] != 31000
        or granted[leaf_menu_id]["parent_id"] != parent_menu_id
        or granted[parent_menu_id]["perms"] != menu_permission
        or granted[leaf_menu_id]["perms"] != permission
    ):
        raise OrbitError(403, "PERMISSION_DENIED", "当前身份无此业务权限")
    return BusinessContext(
        actor_id, scope["tenant_id"], scope["data_role"], scope["subject_id"], scope["team_id"]
    )


async def require_system_access(
    session: AsyncSession,
    actor_id: int,
    leaf_menu_id: int,
    permission: str,
    *,
    super_admin: bool = False,
    acting_subject: bool = True,
) -> BusinessContext:
    """保留系统管理入口及原编号，授权仍由实时数据库角色并集决定。"""
    return await _require_access(
        session,
        actor_id,
        leaf_menu_id,
        permission,
        parent_menu_id=31080,
        menu_code="system",
        menu_permission="system.read",
        super_admin=super_admin,
        acting_subject=acting_subject,
    )


async def require_business_access(
    session: AsyncSession,
    actor_id: int,
    menu_code: str,
    permission: str,
    *,
    super_admin: bool = False,
    acting_subject: bool = True,
) -> BusinessContext:
    """跨模块统一授权；菜单与动作分别求角色并集，不能用系统权限替代。"""
    from orbit_api.role_bridge import BUSINESS_MENUS

    registration = BUSINESS_MENUS.get(menu_code)
    if registration is None or permission not in registration[2]:
        raise OrbitError(403, "PERMISSION_DENIED", "业务菜单或动作未注册")
    parent, read_permission, actions = registration
    return await _require_access(
        session,
        actor_id,
        actions[permission],
        permission,
        parent_menu_id=parent,
        menu_code=menu_code,
        menu_permission=read_permission,
        super_admin=super_admin,
        acting_subject=acting_subject,
    )


async def require_configuration_access(session: AsyncSession, actor_id: int) -> BusinessContext:
    """配置权限不能因共用系统授权解析而放宽到普通用户或团队管理员。"""
    return await require_system_access(
        session, actor_id, 31081, "system.integrations.manage", super_admin=True
    )
