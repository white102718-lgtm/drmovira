"""团队目录：当前授权、显式管理范围、键集分页、CAS及原子审计；不调用外部平台。"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api.authorization import require_system_access
from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.directory_write import append_directory_change
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import TeamWrite
from orbit_api.identity_policy import has_recoverable_administrator


def public_team(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "status": "ENABLED" if row["enabled"] else "DISABLED",
        "revision": row["revision"],
    }


def state_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest() if value else None


class TeamStore:
    def __init__(self, tokens: DirectoryTokens):
        self.tokens = tokens

    async def context(self, session, actor):
        context = await require_system_access(session, actor, 31083, "system.teams.manage")
        managed = (
            (
                await session.execute(
                    text("""
            SELECT team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id=:actor AND enabled=1
            ORDER BY team_id FOR SHARE
        """),
                    {"tenant": context.tenant_id, "actor": actor},
                )
            )
            .scalars()
            .all()
        )
        return context, managed

    @staticmethod
    def visible(context, managed, team_id):
        return (
            context.data_role == "SUPER_ADMIN"
            or team_id == context.team_id
            or context.data_role == "TEAM_ADMIN"
            and team_id in managed
        )

    async def _row(self, session, context, managed, team_id):
        team_id = _uuid(team_id)
        if not self.visible(context, managed, team_id):
            raise OrbitError(404, "NOT_FOUND", "团队不存在或不可见")
        row = (
            (
                await session.execute(
                    text("""
            SELECT id,name,enabled,revision FROM orbit_business_team
            WHERE tenant_id=:tenant AND id=:id FOR SHARE
        """),
                    {"tenant": context.tenant_id, "id": team_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "团队不存在或不可见")
        return row

    async def get(self, session, actor, team_id):
        context, managed = await self.context(session, actor)
        return public_team(await self._row(session, context, managed, team_id))

    async def capabilities(self, session, actor, authorization):
        context, managed = await self.context(session, actor)
        binding = self.tokens.session_binding(authorization, actor, context.tenant_id)
        return {
            "data_role": context.data_role,
            "managed_team_ids": managed,
            "can_create": context.data_role == "SUPER_ADMIN",
            "csrf_token": self.tokens.issue("DIRECTORY_CSRF_V1", {"binding": binding}),
        }

    async def list(self, session, actor, filters, cursor=None):
        context, managed = await self.context(session, actor)
        revision = (
            await session.execute(
                text("""
            SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE
        """),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        scope = state_hash(
            [
                actor,
                context.tenant_id,
                context.data_role,
                context.team_id,
                managed,
                revision,
                filters,
            ]
        )
        after = ""
        watermark = datetime.now(UTC).isoformat(timespec="milliseconds")
        if cursor:
            claims = self.tokens.verify("DIRECTORY_CURSOR_V1", cursor)
            if claims.get("scope") != scope:
                raise OrbitError(409, "CURSOR_STALE", "筛选或授权目录已变化，请从首页重新加载")
            after = _uuid(claims.get("after"))
            watermark = claims.get("as_of")
            if not isinstance(watermark, str):
                raise OrbitError(400, "TOKEN_INVALID", "游标水位无效")
        clauses = ["t.tenant_id=:tenant", "t.id>:after"]
        params = {
            "tenant": context.tenant_id,
            "actor": actor,
            "own": context.team_id,
            "after": after,
            "limit": filters["page_size"] + 1,
        }
        if context.data_role != "SUPER_ADMIN":
            clauses.append("""(t.id=:own OR (:is_manager=1 AND EXISTS(
                SELECT 1 FROM orbit_business_team_manager m WHERE m.tenant_id=t.tenant_id
                AND m.team_id=t.id AND m.manager_user_id=:actor AND m.enabled=1)))""")
            params["is_manager"] = int(context.data_role == "TEAM_ADMIN")
        if filters.get("q"):
            # INSTR按字面子串处理，不把%/_当通配符；租户/游标先走主键有界续页。
            clauses.append("INSTR(t.name,:q)>0")
            params["q"] = filters["q"]
        if filters.get("status"):
            clauses.append("t.enabled=:enabled")
            params["enabled"] = int(filters["status"] == "ENABLED")
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"t.created_at {operator} :{field}")
                params[field] = filters[field]
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT t.id,t.name,t.enabled,t.revision FROM orbit_business_team t WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY t.id LIMIT :limit"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        page = rows[: filters["page_size"]]
        token = (
            self.tokens.issue(
                "DIRECTORY_CURSOR_V1", {"scope": scope, "after": page[-1]["id"], "as_of": watermark}
            )
            if len(rows) > len(page)
            else None
        )
        return {
            "items": [public_team(row) for row in page],
            "next_cursor": token,
            "data_as_of": watermark,
            "scope_version": revision,
        }

    async def save(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        value: TeamWrite,
        team_id,
        expected,
        request_id,
    ):
        context, managed = await self.context(session, actor)
        claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        if claims.get("binding") != self.tokens.session_binding(
            authorization, actor, context.tenant_id
        ):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败，请重新加载")
        if team_id:
            team_id = _uuid(team_id)
            if not self.visible(context, managed, team_id):
                raise OrbitError(404, "NOT_FOUND", "团队不存在或不可见")
        can_edit = context.data_role == "SUPER_ADMIN" or (
            team_id and context.data_role == "TEAM_ADMIN" and team_id in managed
        )
        if not can_edit:
            raise OrbitError(403, "PERMISSION_DENIED", "当前身份没有此团队的维护权限")
        # 目录锁串行化跨团队的最后管理员检查与所有目录写；原若依保护也使用该锁。
        clock = (
            await session.execute(
                text("""
            SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE
        """),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        if clock >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "目录版本已达上限")
        digest = state_hash(["TEAM", team_id, expected, value.model_dump()])
        params = {"tenant": context.tenant_id, "actor": actor, "key": key, "hash": digest}
        previous = (
            (
                await session.execute(
                    text("""
            SELECT payload_hash,response_json FROM orbit_directory_idempotency
            WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE
        """),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if previous:
            if previous["payload_hash"] != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同操作")
            result = _decode(previous["response_json"])
            await self._row(session, context, managed, result["id"])
            return result
        before = (
            public_team(await self._row(session, context, managed, team_id)) if team_id else None
        )
        if before and before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "团队已被修改，请刷新后重试")
        if before and before["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "团队版本已达上限")
        result = {
            "id": team_id or str(uuid4()),
            "name": value.name,
            "status": value.status,
            "revision": expected + 1,
        }
        write = {
            "tenant": context.tenant_id,
            "id": result["id"],
            "name": value.name,
            "enabled": int(value.status == "ENABLED"),
            "revision": result["revision"],
        }
        if before:
            await session.execute(
                text("""
                UPDATE orbit_business_team SET name=:name,enabled=:enabled,revision=:revision,
                updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id
            """),
                write,
            )
        else:
            await session.execute(
                text("""
                INSERT INTO orbit_business_team
                (tenant_id,id,name,enabled,revision,created_at,updated_at)
                VALUES(:tenant,:id,:name,:enabled,:revision,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))
            """),
                write,
            )
        if value.status == "DISABLED":
            if not await has_recoverable_administrator(session, context.tenant_id):
                raise OrbitError(
                    409, "LAST_ADMIN_REQUIRED", "必须保留至少一名启用且有团队管理权限的超级管理员"
                )
            if before and before["status"] != "DISABLED":
                # 与团队状态、审计及outbox同事务批量撤销成员身份；恢复团队不能复活旧JWT。
                # 名称修改和已停用团队的空状态保存不反复注销成员，亦不逐人发SQL。
                await session.execute(
                    text("""
                    UPDATE sys_identity_subject i
                    JOIN orbit_business_user b ON b.user_id=i.user_id
                    JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id
                    JOIN sys_user actor ON actor.user_id=:actor
                    SET i.auth_version=i.auth_version+1,
                        i.update_by=actor.user_name,i.update_time=UTC_TIMESTAMP(3)
                    WHERE b.tenant_id=:tenant AND b.team_id=:id
                """),
                    {"actor": actor, "tenant": context.tenant_id, "id": team_id},
                )
        await append_directory_change(
            session, context, key, digest, before, result, ("name", "status"), request_id, "TEAM"
        )
        return result
