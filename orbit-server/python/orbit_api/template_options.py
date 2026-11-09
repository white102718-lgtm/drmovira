"""模板共享的受控同团队候选；模板动作不依赖投放创建或系统人员目录。"""

from sqlalchemy import text

from orbit_api import launch_access as access
from orbit_api.errors import OrbitError
from orbit_api.reference_access import scope_version
from orbit_api.reference_contract import uuid_value
from orbit_api.template_store import TemplateStore


async def recipient_options(
    session, tokens, actor, authorization, *, template_id=None, cursor=None, page_size=200
):
    current = await access.context(session, actor, "templates.share")
    target_team, template_revision = current.team_id, None
    if template_id is not None:
        template_id = uuid_value(template_id, "/template_id")
        row = await TemplateStore(tokens).row(session, current, template_id, unlocked=True)
        if row["owner_user_id"] != current.subject_id:
            raise OrbitError(403, "TEMPLATE_OWNER_REQUIRED", "仅所有者可维护此模板共享")
        if row["state"] != "ACTIVE":
            raise OrbitError(409, "TEMPLATE_ARCHIVED", "归档模板不能新增共享")
        target_team, template_revision = row["owner_team_id"], row["revision"]
        await access.owner(
            session, current, {"owner_user_id": current.subject_id, "owner_team_id": target_team}
        )
    version = await scope_version(session, current)
    scope = access.digest(
        [
            "TEMPLATE_RECIPIENTS_V1",
            actor,
            current.tenant_id,
            current.subject_id,
            current.team_id,
            current.data_role,
            await access.teams(session, current),
            version,
            template_id,
            template_revision,
            target_team,
            page_size,
        ]
    )
    after = ""
    if cursor:
        claims = tokens.verify("TEMPLATE_CURSOR_V1", cursor)
        if claims.get("scope") != scope:
            raise OrbitError(409, "SCOPE_CHANGED", "团队成员、模板版本或共享权限范围已变化")
        after = uuid_value(claims.get("after"), "/cursor")
    rows = (
        (
            await session.execute(
                text("""SELECT b.id,t.id AS team_id,t.name AS team_name,
    COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name) AS name
    FROM orbit_business_user b JOIN orbit_business_team t ON t.tenant_id=b.tenant_id
    AND t.id=b.team_id AND t.enabled=1 JOIN sys_user u ON u.user_id=b.user_id
    AND u.status='0' AND u.del_flag='0' JOIN orbit_user_scope s ON s.user_id=b.user_id
    AND s.tenant_id=b.tenant_id AND s.enabled=1 WHERE b.tenant_id=:tenant
    AND b.team_id=:team AND b.enabled=1 AND b.invited=0 AND b.id>:after
    ORDER BY b.id LIMIT :limit FOR SHARE"""),
                access.parameters(current)
                | {"team": target_team, "after": after, "limit": page_size + 1},
            )
        )
        .mappings()
        .all()
    )
    page = rows[:page_size]
    token = (
        tokens.issue("TEMPLATE_CURSOR_V1", {"scope": scope, "after": page[-1]["id"]})
        if len(rows) > len(page)
        else None
    )
    return {
        "items": [dict(row) for row in page],
        "next_cursor": token,
        "scope_version": version,
        "owner_team_id": target_team,
        "csrf_token": tokens.issue(
            "DIRECTORY_CSRF_V1",
            {"binding": tokens.session_binding(authorization, actor, current.tenant_id)},
        ),
    }
