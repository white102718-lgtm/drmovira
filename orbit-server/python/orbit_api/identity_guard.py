"""原若依身份事件与ORBIT目录的事务桥接，防止从原菜单绕过最后管理员保护。"""

from sqlalchemy import bindparam, text

from orbit_api.configuration_store import MAX_REVISION
from orbit_api.identity_policy import has_recoverable_administrator
from orbit_api.native_session import current_auth_snapshot, verify_actor_snapshot


async def reject_orphaned_business_history(session, user_ids):
    """缺少当前授权映射的历史业务身份必须先整理，不能退回原技术账户写入分支。"""
    from exceptions.exception import ServiceException

    if not user_ids:
        return
    orphaned = (
        await session.execute(
            text("""SELECT b.user_id FROM orbit_business_user b
                WHERE b.user_id IN :users AND NOT EXISTS (
                    SELECT 1 FROM orbit_user_scope s WHERE s.user_id=b.user_id
                ) LIMIT 1 FOR SHARE""").bindparams(bindparam("users", expanding=True)),
            {"users": list(user_ids)},
        )
    ).first()
    if orphaned:
        raise ServiceException(message="历史业务人员当前授权映射缺失，请先核对目录")


async def business_contact_uniqueness_required(session, user_id):
    """已有业务人员按稳定身份区分，联系方式可重复，不将其用作身份合并或验证。"""
    mapped = (
        await session.execute(
            text("SELECT 1 FROM orbit_user_scope WHERE user_id=:user"), {"user": user_id}
        )
    ).first()
    return mapped is None


async def protect_business_role_assignment(session, user_ids):
    """原单人/批量角色入口连空操作也必须有人员管理权限，且整批目标只限当前租户。"""
    from exceptions.exception import ServiceException

    from orbit_api.authorization import require_system_access
    from orbit_api.errors import OrbitError

    await reject_orphaned_business_history(session, user_ids)
    tenants = set(
        (
            await session.execute(
                text(
                    "SELECT tenant_id FROM orbit_user_scope WHERE user_id IN :ids FOR SHARE"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": user_ids},
            )
        ).scalars()
    )
    if not tenants:
        return  # 未映射原系统用户保留原框架授权，不自动成为业务身份。
    snapshot = current_auth_snapshot()
    if snapshot is None:
        raise ServiceException(message="业务角色分配缺少可信登录身份")
    try:
        context = await require_system_access(
            session, snapshot.actor_id, 31082, "system.users.manage", super_admin=True
        )
    except OrbitError as error:
        raise ServiceException(message=error.message) from None
    if tenants != {context.tenant_id}:
        raise ServiceException(message="原系统入口不能跨业务租户分配角色")


async def protect_business_profile_edit(session, value):
    """原普通编辑及自服务资料不能绕过业务租户；密码与启停仍由原安全事件保护。"""
    from exceptions.exception import ServiceException

    from orbit_api.authorization import require_system_access

    if value.type in {"status", "pwd", "avatar"}:
        return
    await reject_orphaned_business_history(session, [value.user_id])
    tenants = set(
        (
            await session.execute(
                text("SELECT tenant_id FROM orbit_user_scope WHERE user_id=:id FOR SHARE"),
                {"id": value.user_id},
            )
        ).scalars()
    )
    if not tenants:
        return  # 未映射的原系统用户保留原若依流程，不自动创建业务身份。
    snapshot = current_auth_snapshot()
    if snapshot is None:
        raise ServiceException(message="业务资料编辑缺少可信登录身份")
    principal = (
        (
            await session.execute(
                text("""
        SELECT s.tenant_id,i.auth_version FROM sys_user u
        JOIN sys_identity_subject i ON i.user_id=u.user_id
        JOIN orbit_user_scope s ON s.user_id=u.user_id AND s.enabled=1
        JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1
        JOIN orbit_business_user b ON b.user_id=u.user_id
            AND b.tenant_id=s.tenant_id AND b.enabled=1
        JOIN orbit_business_team bt ON bt.id=b.team_id AND bt.tenant_id=b.tenant_id AND bt.enabled=1
        WHERE u.user_id=:actor AND u.status='0' AND u.del_flag='0' FOR SHARE
    """),
                {"actor": snapshot.actor_id},
            )
        )
        .mappings()
        .first()
    )
    if principal is None:
        raise ServiceException(message="当前业务身份已失效")
    verify_actor_snapshot(snapshot.actor_id, principal["auth_version"])
    if tenants != {principal["tenant_id"]}:
        raise ServiceException(message="原系统入口不能跨业务租户修改资料")
    if value.user_id != snapshot.actor_id:
        await require_system_access(
            session, snapshot.actor_id, 31082, "system.users.manage", super_admin=True
        )
    from email_validator import EmailNotValidError, validate_email

    from orbit_api.configuration import short_text
    from orbit_api.errors import OrbitError

    try:
        if value.type != "profile" and "role_ids" in value.model_fields_set:
            roles = value.role_ids or []
            if len(roles) > 20:
                raise ServiceException(message="业务人员最多分配20个功能角色")
            if any(type(role) is not int or not 0 < role < 2**63 for role in roles):
                raise ServiceException(message="功能角色引用无效")
            if len(set(roles)) != len(roles):
                raise ServiceException(message="功能角色引用不能重复")
        for native, field, maximum, required in (
            ("nick_name", "nickname", 50, False),
            ("email", "email", 254, True),
            ("phonenumber", "phone", 32, False),
        ):
            if native not in value.model_fields_set:
                continue
            normalized = short_text(
                getattr(value, native) or "", maximum, "/" + field, required=required
            )
            if native == "email":
                try:
                    normalized = validate_email(normalized, check_deliverability=False).normalized
                except EmailNotValidError:
                    raise OrbitError(422, "FIELD_INVALID", "请输入有效邮箱", "/email") from None
            setattr(value, native, normalized)
    except OrbitError as error:
        raise ServiceException(message=error.message) from None


async def protect_business_identity_event(
    session, user_ids, event, *, actor=None, actor_is_system=False
):
    """不提交调用方事务；当前读避免旧MVCC快照误判并发团队停用后的管理员数量。"""
    from exceptions.exception import ServiceException

    # 上游Session关闭autoflush，角色关联DAO使用add()；检查前必须看到完整拟提交状态。
    # flush不是commit，后续拒绝会将用户、关联、身份版本及目录修改一并回滚。
    await session.flush()
    await reject_orphaned_business_history(session, user_ids)
    # 原若依服务可能已经更新用户；当前读锁住对应scope，防止租户切换漏掉目标租户。
    tenants = (
        (
            await session.execute(
                text("""
        SELECT tenant_id FROM orbit_user_scope WHERE user_id IN :users FOR SHARE
    """).bindparams(bindparam("users", expanding=True)),
                {"users": list(user_ids)},
            )
        )
        .scalars()
        .all()
    )
    tenants = sorted(set(tenants))
    if not tenants:
        return
    if event == "role_assignment_changed":
        foreign_role = (
            await session.execute(
                text("""
            SELECT ur.role_id FROM sys_user_role ur
            JOIN orbit_user_scope s ON s.user_id=ur.user_id AND s.enabled=1
            JOIN orbit_business_role br ON br.native_role_id=ur.role_id
            WHERE ur.user_id IN :users AND br.tenant_id<>s.tenant_id FOR SHARE
        """).bindparams(bindparam("users", expanding=True)),
                {"users": list(user_ids)},
            )
        ).first()
        if foreign_role:
            raise ServiceException(message="不能分配其他业务租户的功能角色")
    # 管理actor由原控制器写入，不采信浏览器tenant或actor字段；原用户名必须唯一解析。
    # 原身份交互已验证本人密码的流程没有管理actor，不能将其误判为管理员改密。
    if actor_is_system and event != "password_changed":
        raise ServiceException(message="业务身份管理缺少可信操作身份")
    if event != "password_changed" or not actor_is_system:
        if not isinstance(actor, str) or not actor.strip():
            raise ServiceException(message="业务身份管理缺少可信操作身份")
        actors = (
            (
                await session.execute(
                    text("""
            SELECT u.user_id,s.tenant_id,s.data_role,i.auth_version FROM sys_user u
            JOIN sys_identity_subject i ON i.user_id=u.user_id
            JOIN orbit_user_scope s ON s.user_id=u.user_id AND s.enabled=1
            JOIN orbit_business_user b ON b.user_id=u.user_id
                AND b.tenant_id=s.tenant_id AND b.enabled=1
            WHERE u.user_name=:actor AND u.status='0' AND u.del_flag='0' FOR SHARE
        """),
                    {"actor": actor},
                )
            )
            .mappings()
            .all()
        )
        if len(actors) != 1:
            raise ServiceException(message="当前原系统操作缺少有效业务管理身份")
        principal = actors[0]
        verify_actor_snapshot(principal["user_id"], principal["auth_version"])
        self_password = event == "password_changed" and set(user_ids) == {principal["user_id"]}
        if not self_password and principal["data_role"] != "SUPER_ADMIN":
            raise ServiceException(message="业务身份管理仅限授权的超级管理员")
        if tenants != [principal["tenant_id"]]:
            raise ServiceException(
                message="原系统入口不能跨业务租户修改身份，请使用受控业务管理入口"
            )
        if principal["user_id"] in user_ids and event in {
            "role_assignment_changed",
            "role_claim_changed",
        }:
            raise ServiceException(message="不能修改自己的业务角色")
    # 先完成操作者与目标租户授权，再验证邀请状态，避免向越租户调用者暴露目标状态。
    if event == "password_changed":
        external = (
            await session.execute(
                text(
                    "SELECT id FROM orbit_external_identity "
                    "WHERE user_id IN :users LIMIT 1 FOR SHARE"
                ).bindparams(bindparam("users", expanding=True)),
                {"users": list(user_ids)},
            )
        ).first()
        if external:
            raise ServiceException(
                message="OIDC人员的登录凭据由身份提供者管理，不能从原系统重设密码"
            )
    if event == "user_enabled":
        pending = (
            await session.execute(
                text("""
            SELECT user_id FROM orbit_business_user
            WHERE user_id IN :users AND invited=1 FOR SHARE
        """).bindparams(bindparam("users", expanding=True)),
                {"users": list(user_ids)},
            )
        ).first()
        if pending:
            raise ServiceException(message="待邀请验证身份不能通过原账号启用入口绕过验证")
    if 1 in user_ids:
        # 保留若依内置管理员保护；新旧入口都不能移除其基础管理角色或业务管理员身份。
        bootstrap = (
            await session.execute(
                text("""
            SELECT u.user_id FROM sys_user u
            JOIN orbit_user_scope s ON s.user_id=u.user_id
                AND s.enabled=1 AND s.data_role='SUPER_ADMIN'
            JOIN orbit_business_user b ON b.user_id=u.user_id
                AND b.tenant_id=s.tenant_id AND b.enabled=1
            JOIN sys_user_role ur ON ur.user_id=u.user_id AND ur.role_id=1
            JOIN sys_role r ON r.role_id=ur.role_id AND r.status='0' AND r.del_flag='0'
            WHERE u.user_id=1 AND u.status='0' AND u.del_flag='0' FOR SHARE
        """)
            )
        ).scalar_one_or_none()
        if bootstrap is None:
            raise ServiceException(message="若依内置管理员的账号与管理授权受保护")
    for tenant in tenants:
        revision = (
            await session.execute(
                text("""
            SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE
        """),
                {"tenant": tenant},
            )
        ).scalar_one_or_none()
        if revision is None or revision >= MAX_REVISION:
            raise ServiceException(message="组织目录版本尚不可用，请联系管理员")
        if event in {
            "user_disabled",
            "user_deleted",
            "role_assignment_changed",
            "role_claim_changed",
            "role_disabled",
            "role_deleted",
        }:
            if not await has_recoverable_administrator(session, tenant):
                raise ServiceException(message="必须保留至少一名启用且有团队管理权限的超级管理员")
        await session.execute(
            text("""
            UPDATE orbit_directory_clock SET revision=revision+1,updated_at=UTC_TIMESTAMP(3)
            WHERE tenant_id=:tenant
        """),
            {"tenant": tenant},
        )
