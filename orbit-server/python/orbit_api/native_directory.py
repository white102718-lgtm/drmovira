"""原菜单人员目录读取：部门权限与业务范围相交，缓存命中前重核当前授权。"""

import json

from sqlalchemy import select, text

from orbit_api.authorization import require_system_access
from orbit_api.errors import OrbitError
from orbit_api.native_session import current_auth_snapshot


async def describe_native_directory_object(session, kind, identifier):
    """仅提示已授权详情的字段规则，写入仍从数据库重新判断业务归属。"""
    if kind != "USER":
        return {}
    mapped = (
        await session.execute(
            text("SELECT 1 FROM orbit_user_scope WHERE user_id=:user_id LIMIT 1"),
            {"user_id": identifier},
        )
    ).first()
    return {"business_managed": mapped is not None}


async def _context(session, kind="USER"):
    snapshot = current_auth_snapshot()
    if snapshot is None:
        raise OrbitError(403, "PERMISSION_DENIED", "缺少可信目录读取身份")
    mapped = (
        await session.execute(
            text("""
            SELECT 1 FROM orbit_user_scope WHERE user_id=:actor
            UNION ALL SELECT 1 FROM orbit_business_user WHERE user_id=:actor LIMIT 1
        """),
            {"actor": snapshot.actor_id},
        )
    ).first()
    if mapped is None:
        return None
    if kind == "ROLE":
        return await require_system_access(
            session, snapshot.actor_id, 31084, "system.roles.manage", super_admin=True
        )
    return await require_system_access(session, snapshot.actor_id, 31082, "system.users.manage")


async def native_directory_scope(session, kind):
    """只读取当前scope成员；历史成员既不能扩大范围，也不能误伤当前其他租户。"""
    if kind not in {"USER", "USER_ROLE_OPTION", "ROLE"}:
        raise ValueError("未知原人员目录类型")
    context = await _context(session, kind)
    if kind in {"USER_ROLE_OPTION", "ROLE"}:
        # 原技术角色没有租户，不伪造业务归属；其他租户已映射角色绝不作为选项返回。
        condition = (
            "NOT EXISTS (SELECT 1 FROM orbit_business_role nr "
            "WHERE nr.native_role_id=sys_role.role_id)"
        )
        if context is not None:
            predicate = text(
                "(" + condition + " OR EXISTS (SELECT 1 FROM orbit_business_role nr "
                "WHERE nr.native_role_id=sys_role.role_id AND nr.tenant_id=:native_tenant))"
            ).bindparams(native_tenant=context.tenant_id)
            if kind == "USER_ROLE_OPTION" and context.data_role != "SUPER_ADMIN":
                # 普通人员/团队管理员读取资料不等于可枚举所有可授予角色。
                from sqlalchemy import and_

                predicate = and_(
                    predicate,
                    text("""sys_role.role_id IN (SELECT role_id FROM sys_user_role
                        WHERE user_id=:native_option_actor)""").bindparams(
                        native_option_actor=context.actor_id
                    ),
                )
            return predicate
        return text(condition)
    technical = """NOT EXISTS (SELECT 1 FROM orbit_user_scope ns WHERE ns.user_id=sys_user.user_id)
        AND NOT EXISTS (SELECT 1 FROM orbit_business_user nb WHERE nb.user_id=sys_user.user_id)"""
    if context is None:
        return text(technical)
    params = {"native_tenant": context.tenant_id, "native_actor": context.actor_id}
    scope = "nb.user_id=:native_actor"
    if context.data_role == "SUPER_ADMIN":
        scope = "1=1"
    elif context.data_role == "TEAM_ADMIN":
        scope = """(nb.user_id=:native_actor OR EXISTS (
            SELECT 1 FROM orbit_business_team_manager nm
            WHERE nm.tenant_id=nb.tenant_id AND nm.team_id=nb.team_id
                AND nm.manager_user_id=:native_actor AND nm.enabled=1))"""
    business = (
        """EXISTS (SELECT 1 FROM orbit_business_user nb
        JOIN orbit_user_scope ns ON ns.user_id=nb.user_id AND ns.tenant_id=nb.tenant_id
        WHERE nb.user_id=sys_user.user_id AND nb.tenant_id=:native_tenant AND """
        + scope
        + ")"
    )
    if context.data_role == "SUPER_ADMIN":
        business = "(" + business + " OR (" + technical + "))"
    return text(business).bindparams(**{k: v for k, v in params.items() if ":" + k in business})


async def guard_native_directory_object(session, kind, identifier):
    from module_admin.entity.do.role_do import SysRole
    from module_admin.entity.do.user_do import SysUser

    if kind not in {"USER", "ROLE"}:
        raise ValueError("未知原目录对象")
    model, column = (SysRole, SysRole.role_id) if kind == "ROLE" else (SysUser, SysUser.user_id)
    predicate = await native_directory_scope(session, kind)
    visible = (
        await session.execute(
            select(column).where(column == identifier, model.del_flag == "0", predicate)
        )
    ).first()
    if visible is None:
        raise OrbitError(404, "NOT_FOUND", "目录对象不存在或不可见")
    if kind == "USER":
        foreign_grant = (
            await session.execute(
                text("""
                SELECT 1 FROM sys_user_role ur
                JOIN orbit_business_role br ON br.native_role_id=ur.role_id
                LEFT JOIN orbit_user_scope s ON s.user_id=ur.user_id
                WHERE ur.user_id=:target AND (s.tenant_id IS NULL OR br.tenant_id<>s.tenant_id)
                LIMIT 1
            """),
                {"target": identifier},
            )
        ).first()
        if foreign_grant:
            # 不把旧的错误跨租户角色关系变成原详情或选择器中的角色名称泄露。
            raise OrbitError(409, "DIRECTORY_MAPPING_REQUIRED", "人员角色归属待核对，请先整理目录")


async def native_cache_scope(request):
    """在Redis读取前执行；旧用户ID缓存不能越过当前授权或目录版本。"""
    from config.database import DataSourceRegistry

    snapshot = current_auth_snapshot()
    if snapshot is None:
        return ""
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        # 缓存命中也重新核对目标对象；历史损坏/缺失scope不能靠旧对象缓存继续读取。
        targets = []
        if request.url.path.startswith("/system/user/") and "user_id" in request.path_params:
            targets.append(("USER", request.path_params["user_id"]))
        if request.url.path.startswith(("/system/role/", "/system/menu/roleMenuTreeselect/")):
            if "role_id" in request.path_params:
                targets.append(("ROLE", request.path_params["role_id"]))
            elif request.url.path.startswith("/system/role/authUser/"):
                targets.append(("ROLE", request.query_params.get("roleId")))
        for kind, value in targets:
            try:
                identifier = int(value)
            except (TypeError, ValueError):
                continue  # 非法路径/查询参数保留原框架结构校验，不能产生有效缓存对象。
            await guard_native_directory_object(session, kind, identifier)
        if request.url.path.startswith(("/system/role/", "/system/menu/roleMenuTreeselect/")):
            await _context(session, "ROLE")
            if request.url.path.startswith("/system/role/authUser/"):
                await _context(session)  # 成员选择器还会返回人员资料，角色动作不能代替人员动作。
        if request.url.path.startswith("/system/user/") and request.url.path not in {
            "/system/user/profile",
            "/system/user/profile/",
        }:
            await _context(session)  # 缓存命中同样检查人员管理动作，不依赖过期时间。
        row = (
            (
                await session.execute(
                    text("""
                    SELECT s.tenant_id,s.data_role,s.enabled,c.revision,
                        b.team_id,b.revision AS user_revision
                    FROM orbit_user_scope s
                    LEFT JOIN orbit_directory_clock c ON c.tenant_id=s.tenant_id
                    LEFT JOIN orbit_business_user b
                        ON b.user_id=s.user_id AND b.tenant_id=s.tenant_id
                    WHERE s.user_id=:actor
                """),
                    {"actor": snapshot.actor_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None and request.url.path.startswith(("/system/user/", "/system/role/")):
            # 未映射技术账号的可见集合受全局映射变化影响，暂不缓存原目录，避免漏失效。
            return None
        return json.dumps(
            [snapshot.actor_id, snapshot.version, dict(row) if row else None],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
