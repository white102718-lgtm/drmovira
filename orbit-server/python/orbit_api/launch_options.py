"""投放当前本人和单拥有者候选；只依赖投放原动作，不借系统人员目录扩权。"""

from sqlalchemy import text

from orbit_api import launch_access as access
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import uuid_field
from orbit_api.reference_access import scope_version


async def actor_label(session, current):
    label = (
        await session.execute(
            text("""SELECT COALESCE(NULLIF(b.display_name,''),
    NULLIF(u.nick_name,''),u.user_name) FROM orbit_business_user b
    JOIN sys_user u ON u.user_id=b.user_id WHERE b.tenant_id=:tenant
    AND b.id=:subject AND b.user_id=:actor FOR SHARE"""),
            access.parameters(current),
        )
    ).scalar_one()
    return {
        "actor_user_id": current.subject_id,
        "actor_team_id": current.team_id,
        "actor_label": label,
    }


async def ownership_context(session, actor):
    try:
        return await access.context(session, actor, "launch.create")
    except OrbitError as error:
        if error.status != 403:
            raise
        return await access.context(session, actor, "launch.edit")


async def ownership_options(session, tokens, actor, *, cursor=None, page_size=200):
    current = await ownership_context(session, actor)
    scope = await scope_version(session, current)
    teams = await access.teams(session, current)
    binding = access.digest(
        [
            "LAUNCH_OWNER_OPTIONS_V1",
            actor,
            current.tenant_id,
            current.subject_id,
            current.team_id,
            current.data_role,
            teams,
            scope,
            page_size,
        ]
    )
    after = ""
    if cursor:
        claims = tokens.verify("LAUNCH_CURSOR_V1", cursor)
        if claims.get("scope") != binding:
            raise OrbitError(409, "SCOPE_CHANGED", "人员或当前管理范围已变化，请重新加载")
        after = uuid_field(claims.get("after"), ("cursor",))
    values = access.parameters(current) | {"after": after, "limit": page_size + 1}
    clause = "1=1" if current.data_role == "SUPER_ADMIN" else "b.id=:subject"
    if current.data_role == "TEAM_ADMIN":
        clause += """ OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm
        WHERE tm.tenant_id=b.tenant_id AND tm.team_id=b.team_id
        AND tm.manager_user_id=:actor AND tm.enabled=1)"""
    rows = (
        (
            await session.execute(
                text(
                    """SELECT b.id,b.team_id,t.name AS team_name,
    COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name) AS name
    FROM orbit_business_user b JOIN orbit_business_team t ON t.tenant_id=b.tenant_id
    AND t.id=b.team_id AND t.enabled=1 JOIN sys_user u ON u.user_id=b.user_id
    AND u.status='0' AND u.del_flag='0' JOIN orbit_user_scope s ON s.user_id=b.user_id
    AND s.tenant_id=b.tenant_id AND s.enabled=1 WHERE b.tenant_id=:tenant
    AND b.enabled=1 AND b.invited=0 AND b.id>:after AND ("""
                    + clause
                    + ") ORDER BY b.id LIMIT :limit FOR SHARE"
                ),
                values,
            )
        )
        .mappings()
        .all()
    )
    page = rows[:page_size]
    token = (
        tokens.issue("LAUNCH_CURSOR_V1", {"scope": binding, "after": page[-1]["id"]})
        if len(rows) > len(page)
        else None
    )
    return {"items": [dict(row) for row in page], "next_cursor": token, "scope_version": scope}
