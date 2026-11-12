"""人员编辑：完整替换字段、CAS、事务幂等及身份撤销；密码通过独立重置接口设置。"""

from sqlalchemy import text

from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_tokens import canonical
from orbit_api.directory_write import append_directory_change, public_hash
from orbit_api.errors import OrbitError
from orbit_api.identity_policy import has_recoverable_administrator
from orbit_api.user_create_store import UserCreateStore

_CLAIMS = ("team_id", "role_ids", "data_role", "managed_team_ids")


class UserUpdateStore(UserCreateStore):
    async def save(
        self, session, actor, authorization, csrf, key, value, user_id, expected, request_id
    ):
        from module_identity.service.identity_service import IdentitySecurityEventService

        context, _ = await self.context(session, actor)
        if context.data_role != "SUPER_ADMIN":
            raise OrbitError(403, "PERMISSION_DENIED", "人员管理编辑仅限授权的超级管理员")
        claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        if claims.get("binding") != self.tokens.session_binding(
            authorization, actor, context.tenant_id
        ):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败，请重新加载")
        user_id = _uuid(user_id)
        clock = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE"
                ),
                {"tenant": context.tenant_id},
            )
        ).scalar_one()
        if clock >= MAX_REVISION or expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "人员或目录版本已达上限")
        digest = public_hash(["USER_UPDATE", user_id, expected, value.model_dump()])
        params = {"tenant": context.tenant_id, "actor": actor, "key": key}
        previous = (
            (
                await session.execute(
                    text(
                        "SELECT payload_hash,response_json FROM orbit_directory_idempotency "
                        "WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND request_key=:key FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        before = await self.get(session, actor, user_id)
        if previous:
            if previous["payload_hash"] != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同操作")
            return _decode(previous["response_json"])
        if before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "人员已被修改，请刷新后重试")
        target = (
            (
                await session.execute(
                    text(
                        "SELECT b.user_id,b.invited FROM orbit_business_user b "
                        "WHERE b.tenant_id=:tenant AND b.id=:id FOR UPDATE"
                    ),
                    {"tenant": context.tenant_id, "id": user_id},
                )
            )
            .mappings()
            .one()
        )
        changed_claims = any(before[field] != getattr(value, field) for field in _CLAIMS)
        changed_status = before["status"] != value.status
        if target["user_id"] == actor and changed_status:
            raise OrbitError(403, "SELF_STATUS_CHANGE", "不能停用自己的账号")
        if target["user_id"] == actor and changed_claims:
            raise OrbitError(403, "SELF_ROLE_CHANGE", "不能修改自己的角色或数据范围")
        if target["user_id"] == 1 and (changed_claims or changed_status):
            raise OrbitError(403, "BUILT_IN_USER", "基础管理员账号及管理授权受保护")
        if value.status == "ENABLED" and before["identity_status"] == "UNVERIFIED":
            raise OrbitError(
                422, "IDENTITY_UNVERIFIED", "请先通过重置密码设置登录密码，再开启账号", "/status"
            )
        if value.status == "INVITED":
            raise OrbitError(422, "FIELD_INVALID", "请选择开启或停用", "/status")
        native_roles = await self._references(session, context.tenant_id, value, before)
        fields = tuple(type(value).model_fields)
        if all(before[field] == getattr(value, field) for field in fields):
            # 空操作仍记录可重放结果，但不制造人员版本、审计或目录变化。
            await session.execute(
                text(
                    "INSERT INTO orbit_directory_idempotency "
                    "(tenant_id,actor_id,request_key,payload_hash,response_json) "
                    "VALUES(:tenant,:actor,:key,:hash,:response)"
                ),
                {**params, "hash": digest, "response": canonical(before)},
            )
            return before
        actor_name = (
            await session.execute(
                text("SELECT user_name FROM sys_user WHERE user_id=:actor"), {"actor": actor}
            )
        ).scalar_one()
        if changed_claims or changed_status:
            event = (
                "role_assignment_changed"
                if changed_claims or value.status == "INVITED"
                else ("user_enabled" if value.status == "ENABLED" else "user_disabled")
            )
            # 先验证原可信操作者并撤销身份版本；所有拟提交状态随后再次检查管理员存续。
            # 自停用时不能在更新后再把已停用的本人当成仍有效的管理主体。
            await IdentitySecurityEventService.handle_user_event(
                session, target["user_id"], event, actor=actor_name
            )
        await session.execute(
            text(
                "UPDATE sys_user SET nick_name=:nickname,email=:email,phonenumber=:phone,"
                "status=:status,update_by=:actor,update_time=UTC_TIMESTAMP(3) WHERE user_id=:user"
            ),
            {
                "nickname": value.nickname,
                "email": value.email,
                "phone": value.phone,
                "status": "0" if value.status == "ENABLED" else "1",
                "actor": actor_name,
                "user": target["user_id"],
            },
        )
        enabled = int(value.status != "DISABLED")
        await session.execute(
            text(
                "UPDATE orbit_user_scope SET data_role=:role,enabled=:enabled "
                "WHERE tenant_id=:tenant AND user_id=:user"
            ),
            {
                "role": value.data_role,
                "enabled": enabled,
                "tenant": context.tenant_id,
                "user": target["user_id"],
            },
        )
        await session.execute(
            text(
                "UPDATE orbit_business_user SET display_name=:name,team_id=:team,enabled=:enabled,"
                "revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "name": value.display_name,
                "team": value.team_id,
                "enabled": enabled,
                "tenant": context.tenant_id,
                "id": user_id,
            },
        )
        if before["role_ids"] != value.role_ids:
            await session.execute(
                text("DELETE FROM sys_user_role WHERE user_id=:user"), {"user": target["user_id"]}
            )
            await session.execute(
                text("INSERT INTO sys_user_role(user_id,role_id) VALUES(:user,:role)"),
                [{"user": target["user_id"], "role": role} for role in native_roles],
            )
        if before["managed_team_ids"] != value.managed_team_ids:
            await session.execute(
                text(
                    "DELETE FROM orbit_business_team_manager "
                    "WHERE tenant_id=:tenant AND manager_user_id=:user"
                ),
                {"tenant": context.tenant_id, "user": target["user_id"]},
            )
            if value.managed_team_ids:
                await session.execute(
                    text(
                        "INSERT INTO orbit_business_team_manager"
                        "(tenant_id,manager_user_id,team_id) "
                        "VALUES(:tenant,:user,:team)"
                    ),
                    [
                        {"tenant": context.tenant_id, "user": target["user_id"], "team": team}
                        for team in value.managed_team_ids
                    ],
                )
        if changed_claims or changed_status:
            if not await has_recoverable_administrator(session, context.tenant_id):
                raise OrbitError(
                    409, "LAST_ADMIN_REQUIRED", "必须保留至少一名启用且有团队管理权限的超级管理员"
                )
        response = await self.get(session, actor, user_id)
        await append_directory_change(
            session, context, key, digest, before, response, fields, request_id, "USER"
        )
        return response
