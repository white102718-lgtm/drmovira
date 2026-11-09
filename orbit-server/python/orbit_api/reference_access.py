"""引用资料与渠道共享的数据范围交集；管理员功能授权不能越过租户或归属。"""

from sqlalchemy import bindparam, text

from orbit_api.authorization import require_business_access, require_system_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.team_store import state_hash


async def reference_context(session, actor, kind, *, maintenance=False):
    if maintenance:
        return await require_system_access(session, actor, 31089, "system.dictionaries.manage")
    try:
        return await require_business_access(
            session,
            actor,
            "accounts" if kind == "VENDOR" else "channels",
            "accounts.read" if kind == "VENDOR" else "channels.read",
        )
    except OrbitError as error:
        if error.status != 403:
            raise
        return await reference_context(session, actor, kind, maintenance=True)


async def managed_teams(session, context):
    return list(
        (
            await session.execute(
                text("""
                     SELECT team_id FROM orbit_business_team_manager WHERE tenant_id=:tenant AND
                     manager_user_id=:actor AND enabled=1 ORDER BY team_id FOR SHARE
                     """),
                {"tenant": context.tenant_id, "actor": context.actor_id},
            )
        ).scalars()
    )


def readable(context, managed, value):
    return (
        context.data_role == "SUPER_ADMIN"
        or (context.data_role == "TEAM_ADMIN" and value["owner_team_id"] in managed)
        or context.subject_id in value["data_owner_user_ids"]
    )


def scope_clause(context, alias, owner_table, foreign_column):
    """只接受代码中的固定表名；普通用户走拥有者覆盖索引，团队管理员叠加显式授权。"""
    if context.data_role == "SUPER_ADMIN":
        return "1=1"
    own = (
        f"EXISTS(SELECT 1 FROM {owner_table} o WHERE o.tenant_id={alias}.tenant_id "
        f"AND o.{foreign_column}={alias}.id AND o.user_id=:subject)"
    )
    if context.data_role == "TEAM_ADMIN":
        return (
            own
            + " OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
            + f"WHERE tm.tenant_id={alias}.tenant_id AND tm.team_id={alias}.owner_team_id "
            + "AND tm.manager_user_id=:actor AND tm.enabled=1)"
        )
    return own


def assert_write_ownership(context, managed, value, *, previous=None):
    """纯归属门禁供批量预检复用；读取包含本人不表示允许扩大共享集合。"""
    if context.data_role == "USER":
        # 普通用户可保留原归属，创建时只允许自己；不能借编辑动作扩大共享集合。
        allowed = previous or {
            "owner_team_id": context.team_id,
            "data_owner_user_ids": [context.subject_id],
        }
        if value != allowed:
            raise OrbitError(403, "OWNERSHIP_DENIED", "普通用户不能变更或扩大资料归属")
    elif context.data_role == "TEAM_ADMIN" and value["owner_team_id"] not in managed:
        allowed = previous or {
            "owner_team_id": context.team_id,
            "data_owner_user_ids": [context.subject_id],
        }
        if context.subject_id not in value["data_owner_user_ids"] or value != allowed:
            raise OrbitError(403, "OWNERSHIP_DENIED", "未授权管理的团队只能保留本人原有归属")


async def validate_ownership(session, context, value, *, previous=None):
    managed = await managed_teams(session, context)
    assert_write_ownership(context, managed, value, previous=previous)
    rows = list(
        (
            await session.execute(
                text("""
                SELECT b.id FROM orbit_business_user b JOIN orbit_business_team
                t ON t.tenant_id=b.tenant_id AND t.id=b.team_id AND t.enabled=1
                JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND
                u.del_flag='0' JOIN orbit_user_scope s ON s.user_id=u.user_id
                AND s.tenant_id=b.tenant_id AND s.enabled=1 WHERE
                b.tenant_id=:tenant AND b.team_id=:team AND b.enabled=1 AND
                b.invited=0 AND b.id IN :ids FOR SHARE
                """).bindparams(bindparam("ids", expanding=True)),
                {
                    "tenant": context.tenant_id,
                    "team": value["owner_team_id"],
                    "ids": value["data_owner_user_ids"],
                },
            )
        ).scalars()
    )
    if set(rows) != set(value["data_owner_user_ids"]):
        raise OrbitError(422, "OWNER_UNAVAILABLE", "拥有者必须为同租户、同团队、启用且已激活的人员")


async def clock(session, context, *, write=False):
    return (
        (
            await session.execute(
                text(
                    """
                    SELECT revision,channel_revision FROM orbit_reference_clock WHERE
                    tenant_id=:tenant
                    """
                    + ("FOR UPDATE" if write else "FOR SHARE")
                ),
                {"tenant": context.tenant_id},
            )
        )
        .mappings()
        .one()
    )


async def scope_version(session, context):
    return (
        await session.execute(
            text("SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"),
            {"tenant": context.tenant_id},
        )
    ).scalar_one()


def verify_csrf(tokens, context, authorization, csrf):
    claims = tokens.verify("DIRECTORY_CSRF_V1", csrf)
    if claims.get("binding") != tokens.session_binding(
        authorization, context.actor_id, context.tenant_id
    ):
        raise OrbitError(403, "CSRF_INVALID", "会话校验已失效，请刷新")


async def active_owner_teams(session, context, identifiers):
    """500个UUID一批读取当前有效归属，避免预览重放逐行查人员。"""
    people = {}
    identifiers = sorted(set(identifiers))
    for offset in range(0, len(identifiers), 500):
        rows = (
            await session.execute(
                text("""
            SELECT b.id,b.team_id FROM orbit_business_user b
            JOIN orbit_business_team t ON t.tenant_id=b.tenant_id
             AND t.id=b.team_id AND t.enabled=1
            JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0'
            JOIN orbit_user_scope s ON s.user_id=u.user_id
             AND s.tenant_id=b.tenant_id AND s.enabled=1
            WHERE b.tenant_id=:tenant AND b.enabled=1 AND b.invited=0 AND b.id IN :ids
            FOR SHARE
        """).bindparams(bindparam("ids", expanding=True)),
                {"tenant": context.tenant_id, "ids": identifiers[offset : offset + 500]},
            )
        ).mappings()
        people.update({row["id"]: row["team_id"] for row in rows})
    return people


async def replay(session, context, key, digest):
    row = (
        (
            await session.execute(
                text("""SELECT payload_hash,response_json FROM orbit_reference_idempotency
        WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE"""),
                {"tenant": context.tenant_id, "actor": context.actor_id, "key": key},
            )
        )
        .mappings()
        .first()
    )
    if row:
        if row["payload_hash"] != digest:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同业务意图")
        return _decode(row["response_json"])
    return None


async def remember(session, context, key, digest, result):
    await session.execute(
        text("""
             INSERT INTO orbit_reference_idempotency
             (tenant_id,actor_id,request_key,payload_hash,response_json)
             VALUES(:tenant,:actor,:key,:hash,:result)
             """),
        {
            "tenant": context.tenant_id,
            "actor": context.actor_id,
            "key": key,
            "hash": digest,
            "result": canonical(result),
        },
    )


async def event(
    session,
    context,
    resource_type,
    resource_id,
    revision,
    before,
    after,
    reason,
    request_id,
    details,
):
    from uuid import uuid4

    await session.execute(
        text("""
                INSERT INTO orbit_reference_event
                (id,tenant_id,resource_type,resource_id,revision,actor_id,request_id,before_hash,after_hash,reason,details_json,created_at)
                VALUES(:event,:tenant,:type,:id,:revision,:actor,:request,:before,:after,:reason,:details,UTC_TIMESTAMP(3))
                """),
        {
            "event": str(uuid4()),
            "tenant": context.tenant_id,
            "type": resource_type,
            "id": resource_id,
            "revision": revision,
            "actor": context.actor_id,
            "request": request_id,
            "before": state_hash(before),
            "after": state_hash(after),
            "reason": reason,
            "details": canonical(details),
        },
    )
