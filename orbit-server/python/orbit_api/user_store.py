"""人员只读目录：真实若依资料、业务UUID及功能角色桥接，不推断外部OIDC身份。"""

import json
from datetime import UTC, datetime

from sqlalchemy import bindparam, text

from orbit_api.authorization import require_system_access
from orbit_api.configuration_store import _uuid
from orbit_api.directory_write import public_hash
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import parse_identity_write

_COLUMNS = """
b.id,b.user_id,b.team_id,b.revision,b.invited,s.data_role,
COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name) AS display_name,
COALESCE(u.nick_name,'') AS nickname,COALESCE(u.email,'') AS email,
COALESCE(u.phonenumber,'') AS phone,
CASE WHEN b.invited=1 AND b.enabled=1 AND s.enabled=1 THEN 'INVITED'
     WHEN u.status='0' AND b.enabled=1 AND s.enabled=1 THEN 'ENABLED' ELSE 'DISABLED' END AS status,
CASE WHEN EXISTS(SELECT 1 FROM orbit_external_identity e
                  WHERE e.user_id=b.user_id AND e.tenant_id=b.tenant_id)
     THEN 'OIDC_VERIFIED'
     WHEN b.invited=0 AND u.password IS NOT NULL AND u.password<>''
     THEN 'LOCAL_ACCOUNT' ELSE 'UNVERIFIED' END AS identity_status
"""
_FROM = """
FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id AND u.del_flag='0'
JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id
"""


class UserStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def context(self, session, actor):
        context = await require_system_access(session, actor, 31082, "system.users.manage")
        managed = list(
            (
                await session.execute(
                    text("""
            SELECT team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id=:actor AND enabled=1
            ORDER BY team_id FOR SHARE
        """),
                    {"tenant": context.tenant_id, "actor": actor},
                )
            ).scalars()
        )
        return context, managed

    @staticmethod
    def _scope(context, managed):
        if context.data_role == "SUPER_ADMIN":
            return "1=1", {}
        if context.data_role == "TEAM_ADMIN" and managed:
            # 所在团队不会自动获得他人资料范围；本人始终按本人条件读取。
            return "(b.user_id=:actor OR b.team_id IN :managed)", {"managed": managed}
        return "b.user_id=:actor", {}

    async def _public(self, session, tenant, rows):
        if not rows:
            return []
        native = [r["user_id"] for r in rows]
        roles = {n: [] for n in native}
        grants = (
            (
                await session.execute(
                    text("""
            SELECT ur.user_id,br.id FROM sys_user_role ur
            LEFT JOIN sys_role r ON r.role_id=ur.role_id AND r.del_flag='0'
            LEFT JOIN orbit_business_role br ON br.native_role_id=r.role_id
                AND br.tenant_id=:tenant
            WHERE ur.user_id IN :users ORDER BY ur.user_id,br.id FOR SHARE
        """).bindparams(bindparam("users", expanding=True)),
                    {"tenant": tenant, "users": native},
                )
            )
            .mappings()
            .all()
        )
        for grant in grants:
            if grant["id"] is None:
                raise OrbitError(
                    409, "DIRECTORY_MAPPING_REQUIRED", "原功能角色尚未完成业务映射，请先核对目录"
                )
            roles[grant["user_id"]].append(grant["id"])
        managed = {n: [] for n in native}
        links = (
            (
                await session.execute(
                    text("""
            SELECT manager_user_id,team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id IN :users AND enabled=1
            ORDER BY manager_user_id,team_id FOR SHARE
        """).bindparams(bindparam("users", expanding=True)),
                    {"tenant": tenant, "users": native},
                )
            )
            .mappings()
            .all()
        )
        for link in links:
            managed[link["manager_user_id"]].append(link["team_id"])
        result = []
        for row in rows:
            value = {
                k: row[k]
                for k in (
                    "display_name",
                    "nickname",
                    "email",
                    "phone",
                    "team_id",
                    "data_role",
                    "status",
                )
            }
            value.update(role_ids=roles[row["user_id"]], managed_team_ids=managed[row["user_id"]])
            # 历史资料不合法时明确要求整理，不伪造邮箱、不截断字段或静默漏掉人员。
            try:
                normalized = parse_identity_write(
                    "USER", json.dumps(value, ensure_ascii=False).encode()
                )
            except OrbitError:
                raise OrbitError(
                    409,
                    "DIRECTORY_MAPPING_REQUIRED",
                    "原人员资料尚不符合业务字段要求，请先核对目录",
                ) from None
            result.append(
                {
                    "id": row["id"],
                    "revision": row["revision"],
                    **normalized.model_dump(),
                    "identity_status": row["identity_status"],
                }
            )
        return result

    async def get(self, session, actor, user_id):
        context, managed = await self.context(session, actor)
        scope, params = self._scope(context, managed)
        statement = text(
            "SELECT "
            + _COLUMNS
            + _FROM
            + " WHERE b.tenant_id=:tenant AND b.id=:id AND "
            + scope
            + " FOR SHARE"
        )
        if "managed" in params:
            statement = statement.bindparams(bindparam("managed", expanding=True))
        row = (
            (
                await session.execute(
                    statement,
                    {**params, "tenant": context.tenant_id, "actor": actor, "id": _uuid(user_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "人员不存在或不可见")
        return (await self._public(session, context.tenant_id, [row]))[0]

    async def list(self, session, actor, filters, cursor=None):
        context, managed = await self.context(session, actor)
        revision = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"
                ),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        binding = public_hash(
            [
                "USER",
                actor,
                context.tenant_id,
                context.team_id,
                context.data_role,
                managed,
                revision,
                filters,
            ]
        )
        after, watermark = "", datetime.now(UTC).isoformat(timespec="milliseconds")
        if cursor:
            claims = self.tokens.verify("DIRECTORY_CURSOR_V1", cursor)
            if claims.get("scope") != binding:
                raise OrbitError(409, "CURSOR_STALE", "筛选或授权目录已变化，请从首页重新加载")
            after, watermark = _uuid(claims.get("after")), claims.get("as_of")
        scope, params = self._scope(context, managed)
        clauses = ["b.tenant_id=:tenant", "b.id>:after", scope]
        params.update(
            tenant=context.tenant_id, actor=actor, after=after, limit=filters["page_size"] + 1
        )
        if filters.get("q"):
            clauses.append(
                "(INSTR(COALESCE(NULLIF(b.display_name,''),"
                "NULLIF(u.nick_name,''),u.user_name),:q)>0 "
                "OR INSTR(u.nick_name,:q)>0 OR INSTR(u.email,:q)>0 OR INSTR(u.phonenumber,:q)>0)"
            )
            params["q"] = filters["q"]
        if filters.get("status"):
            status_sql = (
                "CASE WHEN b.invited=1 AND b.enabled=1 AND s.enabled=1 THEN 'INVITED' "
                "WHEN u.status='0' AND b.enabled=1 AND s.enabled=1 "
                "THEN 'ENABLED' ELSE 'DISABLED' END"
            )
            clauses.append("(" + status_sql + ")=:status")
            params["status"] = filters["status"]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"b.created_at {operator} :{field}")
                params[field] = filters[field]
        statement = text(
            "SELECT "
            + _COLUMNS
            + _FROM
            + " WHERE "
            + " AND ".join(clauses)
            + " ORDER BY b.id LIMIT :limit"
        )
        if "managed" in params:
            statement = statement.bindparams(bindparam("managed", expanding=True))
        rows = (await session.execute(statement, params)).mappings().all()
        page = rows[: filters["page_size"]]
        return {
            "items": await self._public(session, context.tenant_id, page),
            "next_cursor": self.tokens.issue(
                "DIRECTORY_CURSOR_V1",
                {"scope": binding, "after": page[-1]["id"], "as_of": watermark},
            )
            if len(rows) > len(page)
            else None,
            "data_as_of": watermark,
            "scope_version": revision,
        }
