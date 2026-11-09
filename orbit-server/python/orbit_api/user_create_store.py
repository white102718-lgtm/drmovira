"""人员创建：完整字段、受控角色/团队、无密码预置账号与同事务审计；不发送邀请。"""

import base64
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text

from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_write import append_directory_change, public_hash
from orbit_api.errors import OrbitError
from orbit_api.user_store import UserStore


class UserCreateStore(UserStore):
    async def options(self, session, actor, kind, query, size, cursor, selected_ids=None):
        """人员表单专用选项；只授予选择能力，不借用团队/角色维护权限。"""
        context, _ = await self.context(session, actor)
        if context.data_role != "SUPER_ADMIN":
            raise OrbitError(403, "PERMISSION_DENIED", "无人员创建权限")
        revision = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"
                ),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        binding = public_hash(
            ["USER_OPTIONS", actor, context.tenant_id, revision, kind, query, size, selected_ids]
        )
        after = ""
        if cursor:
            claims = self.tokens.verify("DIRECTORY_CURSOR_V1", cursor)
            if claims.get("scope") != binding:
                raise OrbitError(409, "CURSOR_STALE", "选项或授权已变化，请重新查询")
            after = claims["after"]
        if kind == "TEAM":
            source = "orbit_business_team b"
            active = "b.enabled=1"
            name = "b.name"
        else:
            source = "orbit_business_role b JOIN sys_role r ON r.role_id=b.native_role_id"
            active = "b.built_in=0 AND r.status='0' AND r.del_flag='0'"
            name = "r.role_name"
        params = {"tenant": context.tenant_id, "after": after, "q": query, "limit": size + 1}
        if selected_ids:
            # 有界回显本租户已知引用名称；不放宽写入时对停用/基础角色的新分配限制。
            active = "b.id IN :selected" + (" AND r.del_flag='0'" if kind == "ROLE" else "")
            params["selected"] = selected_ids
        statement = text(
            "SELECT b.id,"
            + name
            + " AS name FROM "
            + source
            + " WHERE b.tenant_id=:tenant AND "
            + active
            + " AND b.id>:after AND (:q='' OR INSTR("
            + name
            + ",:q)>0)"
            " ORDER BY b.id LIMIT :limit"
        )
        if selected_ids:
            statement = statement.bindparams(bindparam("selected", expanding=True))
        rows = (await session.execute(statement, params)).mappings().all()
        page = [dict(row) for row in rows[:size]]
        return {
            "items": page,
            "next_cursor": self.tokens.issue(
                "DIRECTORY_CURSOR_V1",
                {
                    "scope": binding,
                    "after": page[-1]["id"],
                },
            )
            if len(rows) > size
            else None,
        }

    async def capabilities(self, session, actor, authorization):
        context, managed = await self.context(session, actor)
        protected = list(
            (
                await session.execute(
                    text("""
            SELECT id FROM orbit_business_user WHERE tenant_id=:tenant AND user_id=1
        """),
                    {"tenant": context.tenant_id},
                )
            ).scalars()
        )
        return {
            "data_role": context.data_role,
            "managed_team_ids": managed,
            "can_create": context.data_role == "SUPER_ADMIN",
            "actor_user_id": context.subject_id,
            "protected_user_ids": protected,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, context.tenant_id)},
            ),
        }

    async def _references(self, session, tenant, value, before=None):
        # 编辑时保留已分配的停用引用；不能将停用/基础角色新授予其他人员。
        preserved_teams = [before["team_id"], *before["managed_team_ids"]] if before else []
        preserved_roles = before["role_ids"] if before else []
        teams = set(value.managed_team_ids) | {value.team_id}
        found = set(
            (
                await session.execute(
                    text("""
            SELECT id FROM orbit_business_team
            WHERE tenant_id=:tenant AND id IN :ids
              AND (enabled=1 OR id IN :preserved) FOR SHARE
        """).bindparams(bindparam("ids", expanding=True), bindparam("preserved", expanding=True)),
                    {"tenant": tenant, "ids": sorted(teams), "preserved": preserved_teams},
                )
            ).scalars()
        )
        if found != teams:
            pointer = "/team_id" if value.team_id not in found else "/managed_team_ids"
            raise OrbitError(422, "REFERENCE_NOT_AVAILABLE", "请选择本租户启用团队", pointer)
        roles = (
            (
                await session.execute(
                    text("""
            SELECT b.id,b.native_role_id,b.built_in FROM orbit_business_role b
            JOIN sys_role r ON r.role_id=b.native_role_id AND r.del_flag='0'
            WHERE b.tenant_id=:tenant AND b.id IN :ids
              AND (r.status='0' OR b.id IN :preserved) FOR SHARE
        """).bindparams(bindparam("ids", expanding=True), bindparam("preserved", expanding=True)),
                    {"tenant": tenant, "ids": value.role_ids, "preserved": preserved_roles},
                )
            )
            .mappings()
            .all()
        )
        if {row["id"] for row in roles} != set(value.role_ids):
            raise OrbitError(
                422, "REFERENCE_NOT_AVAILABLE", "请选择本租户有效功能角色", "/role_ids"
            )
        if any(row["built_in"] and row["id"] not in preserved_roles for row in roles):
            raise OrbitError(
                422, "BUILT_IN_ROLE", "基础管理员角色只读，请先复制业务角色", "/role_ids"
            )
        return [row["native_role_id"] for row in roles]

    async def save(
        self, session, actor, authorization, csrf, key, value, user_id, expected, request_id
    ):
        context, _ = await self.context(session, actor)
        if context.data_role != "SUPER_ADMIN":
            raise OrbitError(403, "PERMISSION_DENIED", "人员创建仅限授权的超级管理员")
        if user_id or expected:
            raise ValueError("创建服务不能作为人员更新接口使用")
        claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        if claims.get("binding") != self.tokens.session_binding(
            authorization, actor, context.tenant_id
        ):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败，请重新加载")
        clock = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE"
                ),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        if clock >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "目录版本已达上限")
        digest = public_hash(["USER_CREATE", value.model_dump()])
        params = {"tenant": context.tenant_id, "actor": actor, "key": key}
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
            response = _decode(previous["response_json"])
            await self.get(session, actor, response["id"])
            return response
        if value.status == "ENABLED":
            raise OrbitError(
                422, "IDENTITY_UNVERIFIED", "新人员须先完成受信身份验证，不能直接启用", "/status"
            )
        native_roles = await self._references(session, context.tenant_id, value)
        identifier = str(uuid4())
        # 保留完整128位随机UUID，生成小于30字符的内部账号；不把邮箱/手机号当身份键。
        username = "o_" + base64.b32encode(UUID(identifier).bytes).decode().rstrip("=").lower()
        actor_name = (
            await session.execute(
                text("SELECT user_name FROM sys_user WHERE user_id=:actor"), {"actor": actor}
            )
        ).scalar_one()
        native = await session.execute(
            text("""
            INSERT INTO sys_user
            (user_name,nick_name,email,phonenumber,password,status,del_flag,user_type,create_by,create_time)
            VALUES(:username,:nickname,:email,:phone,NULL,'1','0','00',:actor_name,UTC_TIMESTAMP(3))
        """),
            {
                "username": username,
                "nickname": value.nickname,
                "email": value.email,
                "phone": value.phone,
                "actor_name": actor_name,
            },
        )
        native_id = native.lastrowid
        await session.execute(
            text("""
            INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time)
            VALUES(:user,:subject,1,UTC_TIMESTAMP(3))
        """),
            {"user": native_id, "subject": str(uuid4())},
        )
        enabled = int(value.status == "INVITED")
        await session.execute(
            text("""
            INSERT INTO orbit_user_scope(user_id,tenant_id,data_role,enabled)
            VALUES(:user,:tenant,:role,:enabled)
        """),
            {
                "user": native_id,
                "tenant": context.tenant_id,
                "role": value.data_role,
                "enabled": enabled,
            },
        )
        await session.execute(
            text("""
            INSERT INTO orbit_business_user
            (tenant_id,id,user_id,team_id,enabled,display_name,invited,created_at,updated_at)
            VALUES(:tenant,:id,:user,:team,:enabled,:name,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))
        """),
            {
                "tenant": context.tenant_id,
                "id": identifier,
                "user": native_id,
                "team": value.team_id,
                "enabled": enabled,
                "name": value.display_name,
            },
        )
        if native_roles:
            await session.execute(
                text("INSERT INTO sys_user_role(user_id,role_id) VALUES(:user,:role)"),
                [{"user": native_id, "role": role} for role in native_roles],
            )
        if value.managed_team_ids:
            await session.execute(
                text("""
                INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id)
                VALUES(:tenant,:user,:team)
            """),
                [
                    {"tenant": context.tenant_id, "user": native_id, "team": team}
                    for team in value.managed_team_ids
                ],
            )
        response = {
            "id": identifier,
            "revision": 1,
            **value.model_dump(),
            "identity_status": "UNVERIFIED",
        }
        await append_directory_change(
            session,
            context,
            key,
            digest,
            None,
            response,
            tuple(type(value).model_fields),
            request_id,
            "USER",
        )
        return response
