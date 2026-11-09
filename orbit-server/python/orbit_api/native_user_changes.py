"""原若依人员资料更新与业务版本、审计/outbox同事务；不向原接口附加幂等假响应。"""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.authorization import BusinessContext, require_system_access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_write import append_directory_change
from orbit_api.errors import OrbitError
from orbit_api.native_session import current_auth_snapshot, verify_actor_snapshot
from orbit_api.user_store import _COLUMNS, _FROM

_FIELDS = (
    "display_name",
    "nickname",
    "email",
    "phone",
    "team_id",
    "role_ids",
    "data_role",
    "managed_team_ids",
    "status",
    "identity_status",
)


@dataclass(repr=False)
class NativeUserChange:
    context: BusinessContext
    native_id: int
    before: dict


async def _state(session, user_id, tenant):
    """固定同租户人员的审计状态；不读取密码值，也不作为HTTP响应使用。"""
    row = (
        (
            await session.execute(
                text(
                    "SELECT "
                    + _COLUMNS
                    + _FROM
                    + " WHERE b.user_id=:user AND b.tenant_id=:tenant FOR UPDATE"
                ),
                {"user": user_id, "tenant": tenant},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    value = {key: row[key] for key in _FIELDS if key not in {"role_ids", "managed_team_ids"}}
    value.update(id=row["id"], revision=row["revision"])
    # 历史未映射角色仅在本地状态摘要中区分，不返回客户端、不保存到审计正文。
    # 新User接口仍明确拒绝未整理角色，不能用原数字ID冒充业务UUID。
    roles = (
        await session.execute(
            text("""
        SELECT ur.role_id,br.id FROM sys_user_role ur
        LEFT JOIN sys_role r ON r.role_id=ur.role_id AND r.del_flag='0'
        LEFT JOIN orbit_business_role br ON br.native_role_id=r.role_id AND br.tenant_id=:tenant
        WHERE ur.user_id=:user ORDER BY ur.role_id FOR SHARE
    """),
            {"user": user_id, "tenant": tenant},
        )
    ).mappings()
    value["role_ids"] = sorted(r["id"] or "native:" + str(r["role_id"]) for r in roles)
    value["managed_team_ids"] = list(
        (
            await session.execute(
                text("""
        SELECT team_id FROM orbit_business_team_manager
        WHERE tenant_id=:tenant AND manager_user_id=:user AND enabled=1 ORDER BY team_id FOR SHARE
    """),
                {"tenant": tenant, "user": user_id},
            )
        ).scalars()
    )
    return value


async def capture_native_user_change(session, user_id):
    """在原资料DAO写入前，冻结可信操作者、当前目录锁和修改前状态。"""
    from exceptions.exception import ServiceException

    target = (
        await session.execute(
            text("SELECT tenant_id FROM orbit_user_scope WHERE user_id=:user FOR SHARE"),
            {"user": user_id},
        )
    ).scalar_one_or_none()
    if target is None:
        return None
    snapshot = current_auth_snapshot()
    if snapshot is None:
        return None  # 非HTTP的可信身份服务另有密码验证及安全审计，不伪造管理操作者。
    principal = (
        (
            await session.execute(
                text("""
        SELECT s.tenant_id,s.data_role,b.id AS subject_id,b.team_id,i.auth_version
        FROM orbit_user_scope s JOIN sys_user u ON u.user_id=s.user_id
        JOIN sys_identity_subject i ON i.user_id=u.user_id
        JOIN orbit_business_user b ON b.user_id=u.user_id AND b.tenant_id=s.tenant_id
        JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1
        JOIN orbit_business_team bt ON bt.id=b.team_id AND bt.tenant_id=b.tenant_id AND bt.enabled=1
        WHERE s.user_id=:actor AND s.enabled=1 AND b.enabled=1 AND b.invited=0
            AND u.status='0' AND u.del_flag='0' FOR SHARE
    """),
                {"actor": snapshot.actor_id},
            )
        )
        .mappings()
        .first()
    )
    if principal is None:
        raise ServiceException(message="当前业务授权已失效")
    verify_actor_snapshot(snapshot.actor_id, principal["auth_version"])
    if principal["tenant_id"] != target:
        raise ServiceException(message="原系统入口不能跨业务租户修改身份")
    context = BusinessContext(
        snapshot.actor_id,
        target,
        principal["data_role"],
        principal["subject_id"],
        principal["team_id"],
    )
    if snapshot.actor_id != user_id:
        try:
            await require_system_access(
                session, snapshot.actor_id, 31082, "system.users.manage", super_admin=True
            )
        except OrbitError as error:
            raise ServiceException(message=error.message) from None
    before = await _state(session, user_id, target)
    if before is None:
        raise ServiceException(message="业务人员目录已变化，请刷新重试")
    clock = (
        await session.execute(
            text("SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE"),
            {"tenant": target},
        )
    ).scalar_one()
    if clock >= MAX_REVISION or before["revision"] >= MAX_REVISION:
        raise ServiceException(message="业务人员目录版本已达上限")
    return NativeUserChange(context, user_id, before)


async def finish_native_user_change(session, snapshot):
    """仅真实字段变化推进版本与审计/outbox；异常由原服务整笔回滚。"""
    from exceptions.exception import ServiceException

    if snapshot is None:
        return
    # 原Session关闭autoflush，原角色关联add()必须先入拟提交视图，再比较前后状态。
    await session.flush()
    before = snapshot.before
    after = await _state(session, snapshot.native_id, snapshot.context.tenant_id)
    if after is None:
        raise ServiceException(message="业务人员目录已变化，请刷新重试")
    if len(after["role_ids"]) > 20 and before["role_ids"] != after["role_ids"]:
        raise ServiceException(message="业务人员最多分配20个功能角色")
    if all(before[field] == after[field] for field in _FIELDS):
        return
    added = set(after["role_ids"]) - set(before["role_ids"])
    if any(role.startswith("native:") for role in added):
        raise ServiceException(message="业务人员只能新增本租户已登记的功能角色")
    if before["role_ids"] and not after["role_ids"]:
        raise ServiceException(message="业务人员至少保留一个功能角色")
    if (
        added
        and (
            await session.execute(
                text("""SELECT br.id FROM orbit_business_role br
                JOIN sys_role r ON r.role_id=br.native_role_id
                WHERE br.tenant_id=:tenant AND br.id IN :ids
                    AND (r.status<>'0' OR r.del_flag<>'0') FOR SHARE""").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"tenant": snapshot.context.tenant_id, "ids": sorted(added)},
            )
        ).first()
    ):
        raise ServiceException(message="不能新增已停用或删除的功能角色")
    if (
        added
        and (
            await session.execute(
                text(
                    "SELECT id FROM orbit_business_role "
                    "WHERE tenant_id=:tenant AND id IN :ids AND built_in=1 FOR SHARE"
                ).bindparams(bindparam("ids", expanding=True)),
                {"tenant": snapshot.context.tenant_id, "ids": sorted(added)},
            )
        ).first()
    ):
        raise ServiceException(message="基础管理员角色只读，请先复制业务角色后分配")
    updated = await session.execute(
        text("""
        UPDATE orbit_business_user SET revision=revision+1,updated_at=UTC_TIMESTAMP(3)
        WHERE tenant_id=:tenant AND id=:id AND revision=:before AND revision<:maximum
    """),
        {
            "tenant": snapshot.context.tenant_id,
            "id": before["id"],
            "before": before["revision"],
            "maximum": MAX_REVISION,
        },
    )
    if updated.rowcount != 1:
        raise ServiceException(message="业务人员资料已变化，请刷新重试")
    after["revision"] = before["revision"] + 1
    await append_directory_change(
        session,
        snapshot.context,
        None,
        None,
        before,
        after,
        _FIELDS,
        str(uuid4()),
        "USER",
        record_idempotency=False,
    )
