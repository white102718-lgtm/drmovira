"""业务功能角色真实事务；原数字ID仅用于内部桥接，数据角色不由本接口修改。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.authorization import require_system_access
from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_write import append_directory_change, public_hash
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _REGISTRY
from orbit_api.role_bridge import compiled_menu_ids


class RoleStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def context(self, session, actor):
        return await require_system_access(
            session, actor, 31084, "system.roles.manage", super_admin=True
        )

    async def _row(self, session, tenant, role_id):
        row = (
            (
                await session.execute(
                    text("""
            SELECT b.id,b.native_role_id,b.revision,b.built_in,r.role_name AS name
            FROM orbit_business_role b JOIN sys_role r ON r.role_id=b.native_role_id
            WHERE b.tenant_id=:tenant AND b.id=:id AND r.del_flag='0' AND r.status='0' FOR SHARE
        """),
                    {"tenant": tenant, "id": _uuid(role_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "角色不存在或不可见")
        return row

    async def _public(self, session, tenant, rows):
        if not rows:
            return []
        values = {
            row["id"]: {
                "id": row["id"],
                "name": row["name"],
                "revision": row["revision"],
                "menu_codes": [],
                "permission_codes": [],
            }
            for row in rows
        }
        # 页内两次批量读取，不按每个角色查询菜单/动作；所有关联均带同一可信租户。
        for table, column, target in (
            ("orbit_business_role_menu", "menu_code", "menu_codes"),
            ("orbit_business_role_action", "permission_code", "permission_codes"),
        ):
            grants = (
                (
                    await session.execute(
                        text(
                            f"SELECT role_id,{column} AS code FROM {table} "
                            f"WHERE tenant_id=:tenant AND role_id IN :ids "
                            f"ORDER BY role_id,{column} FOR SHARE"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"tenant": tenant, "ids": list(values)},
                    )
                )
                .mappings()
                .all()
            )
            for grant in grants:
                values[grant["role_id"]][target].append(grant["code"])
        return [values[row["id"]] for row in rows]

    async def capabilities(self, session, actor, authorization):
        context = await self.context(session, actor)
        built_in = (
            (
                await session.execute(
                    text("""
            SELECT id FROM orbit_business_role WHERE tenant_id=:tenant AND built_in=1 ORDER BY id
        """),
                    {"tenant": context.tenant_id},
                )
            )
            .scalars()
            .all()
        )
        return {
            "menus": _REGISTRY["menus"],
            "permissions": _REGISTRY["permissions"],
            "built_in_role_ids": built_in,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, context.tenant_id)},
            ),
        }

    async def get(self, session, actor, role_id):
        context = await self.context(session, actor)
        return (
            await self._public(
                session, context.tenant_id, [await self._row(session, context.tenant_id, role_id)]
            )
        )[0]

    async def list(self, session, actor, filters, cursor=None):
        context = await self.context(session, actor)
        revision = (
            await session.execute(
                text("""
            SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE
        """),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        binding = public_hash(
            [
                "ROLE",
                actor,
                context.tenant_id,
                context.subject_id,
                context.team_id,
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
        clauses = ["b.tenant_id=:tenant", "b.id>:after", "r.del_flag='0'", "r.status=:status"]
        params = {
            "tenant": context.tenant_id,
            "after": after,
            "limit": filters["page_size"] + 1,
            "status": "1" if filters.get("status") == "DISABLED" else "0",
        }
        if filters.get("q"):
            clauses.append("INSTR(r.role_name,:q)>0")
            params["q"] = filters["q"]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"b.created_at {operator} :{field}")
                params[field] = filters[field]
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT b.id,b.revision,r.role_name AS name FROM orbit_business_role b "
                        "JOIN sys_role r ON r.role_id=b.native_role_id WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY b.id LIMIT :limit"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        page = rows[: filters["page_size"]]
        next_cursor = (
            self.tokens.issue(
                "DIRECTORY_CURSOR_V1",
                {"scope": binding, "after": page[-1]["id"], "as_of": watermark},
            )
            if len(rows) > len(page)
            else None
        )
        return {
            "items": await self._public(session, context.tenant_id, page),
            "next_cursor": next_cursor,
            "data_as_of": watermark,
            "scope_version": revision,
        }

    async def save(
        self, session, actor, authorization, csrf, key, value, role_id, expected, request_id
    ):
        from module_identity.service.identity_service import IdentitySecurityEventService

        context = await self.context(session, actor)
        claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        if claims.get("binding") != self.tokens.session_binding(
            authorization, actor, context.tenant_id
        ):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败，请重新加载")
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
        role_id = _uuid(role_id) if role_id else None
        row = await self._row(session, context.tenant_id, role_id) if role_id else None
        if row and row["built_in"]:
            raise OrbitError(403, "BUILT_IN_ROLE", "内置角色只读，请复制为新业务角色")
        if (
            row
            and (
                await session.execute(
                    text("""
            SELECT user_id FROM sys_user_role WHERE role_id=:role AND user_id=:actor FOR SHARE
        """),
                    {"role": row["native_role_id"], "actor": actor},
                )
            ).first()
        ):
            raise OrbitError(403, "SELF_ROLE_CHANGE", "不能修改自己已关联的功能角色")
        digest = public_hash(["ROLE", role_id, expected, value.model_dump()])
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
            await self._row(session, context.tenant_id, response["id"])
            return response
        before = (await self._public(session, context.tenant_id, [row]))[0] if row else None
        if before and before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "角色已被修改，请刷新后重试")
        if expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "角色版本已达上限")
        response = {"id": role_id or str(uuid4()), "revision": expected + 1, **value.model_dump()}
        actor_name = (
            await session.execute(
                text("SELECT user_name FROM sys_user WHERE user_id=:actor"), params
            )
        ).scalar_one()
        if row:
            native_id = row["native_role_id"]
            await session.execute(
                text("""
                UPDATE sys_role SET role_name=:name,update_by=:name_actor,
                update_time=UTC_TIMESTAMP(3)
                WHERE role_id=:native
            """),
                {"name": value.name, "name_actor": actor_name, "native": native_id},
            )
            await session.execute(
                text("""
                UPDATE orbit_business_role SET revision=:revision,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant AND id=:id
            """),
                {"tenant": context.tenant_id, "id": role_id, "revision": response["revision"]},
            )
        else:
            result = await session.execute(
                text("""
                INSERT INTO sys_role
                (role_name,role_key,role_sort,data_scope,status,del_flag,create_by,create_time)
                VALUES(:name,:role_key,100,'5','0','0',:actor,UTC_TIMESTAMP(3))
            """),
                {"name": value.name, "role_key": "orbit:" + response["id"], "actor": actor_name},
            )
            native_id = result.lastrowid
            await session.execute(
                text("""
                INSERT INTO orbit_business_role(tenant_id,id,native_role_id,created_at,updated_at)
                VALUES(:tenant,:id,:native,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))
            """),
                {"tenant": context.tenant_id, "id": response["id"], "native": native_id},
            )
        for table, column, grants in (
            ("orbit_business_role_menu", "menu_code", value.menu_codes),
            ("orbit_business_role_action", "permission_code", value.permission_codes),
        ):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id=:tenant AND role_id=:id"),
                {"tenant": context.tenant_id, "id": response["id"]},
            )
            for code in grants:
                await session.execute(
                    text(
                        f"INSERT INTO {table}(tenant_id,role_id,{column}) VALUES(:tenant,:id,:code)"
                    ),
                    {"tenant": context.tenant_id, "id": response["id"], "code": code},
                )
        await session.execute(
            text("DELETE FROM sys_role_menu WHERE role_id=:native"), {"native": native_id}
        )
        for menu_id in compiled_menu_ids(value.menu_codes, value.permission_codes):
            await session.execute(
                text("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(:native,:menu)"),
                {"native": native_id, "menu": menu_id},
            )
        if before and any(
            before[field] != response[field] for field in ("menu_codes", "permission_codes")
        ):
            await IdentitySecurityEventService.handle_role_event(
                session, native_id, "role_claim_changed", actor=actor_name
            )
        await append_directory_change(
            session,
            context,
            key,
            digest,
            before,
            response,
            ("name", "menu_codes", "permission_codes"),
            request_id,
            "ROLE",
        )
        return response
