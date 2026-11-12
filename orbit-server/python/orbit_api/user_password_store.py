"""管理员重置本地密码；完整权限/CAS/幂等、密码哈希和身份撤销同事务提交。"""

from sqlalchemy import text
from utils.pwd_util import PwdUtil

from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_write import append_directory_change
from orbit_api.errors import OrbitError
from orbit_api.user_create_store import UserCreateStore
from orbit_api.user_credentials import secret_request_digest


class UserPasswordStore(UserCreateStore):
    async def save(
        self, session, actor, authorization, csrf, key, value, user_id, expected, request_id
    ):
        from module_identity.service.identity_service import IdentitySecurityEventService

        context, _ = await self.context(session, actor)
        if context.data_role != "SUPER_ADMIN":
            raise OrbitError(403, "PERMISSION_DENIED", "只有授权的超级管理员可重置人员密码")
        claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        if claims.get("binding") != self.tokens.session_binding(
            authorization, actor, context.tenant_id
        ):
            raise OrbitError(403, "CSRF_INVALID", "会话校验失败，请刷新")
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
            raise OrbitError(409, "REVISION_EXHAUSTED", "目录版本已达上限")
        params = {"tenant": context.tenant_id, "actor": actor, "key": key, "id": user_id}
        before = await self.get(session, actor, user_id)
        if before["identity_status"] == "OIDC_VERIFIED":
            raise OrbitError(422, "EXTERNAL_IDENTITY_MANAGED", "企业登录账号的密码由身份提供者管理")
        previous = (
            (
                await session.execute(
                    text(
                        "SELECT payload_hash,response_json,digest_key_id FROM orbit_directory_idempotency WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        kid = previous["digest_key_id"] if previous else self.tokens.cipher.active_key_id
        if not kid:
            raise OrbitError(503, "SIGNING_UNAVAILABLE", "密码操作签名密钥不可用")
        digest = secret_request_digest(
            self.tokens,
            "USER_PASSWORD_RESET",
            context.tenant_id,
            actor,
            [user_id, expected],
            value.password,
            kid,
        )
        if previous:
            if previous["payload_hash"] != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同密码")
            return _decode(previous["response_json"])
        if before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "人员已变化，请重新读取后重试")
        target = (
            await session.execute(
                text(
                    "SELECT user_id FROM orbit_business_user WHERE tenant_id=:tenant AND id=:id FOR UPDATE"
                ),
                params,
            )
        ).scalar_one()
        if target == actor or target == 1:
            raise OrbitError(403, "PROTECTED_USER", "本人及基础管理员请通过个人中心修改密码")
        actor_name = (
            await session.execute(
                text("SELECT user_name FROM sys_user WHERE user_id=:actor"), params
            )
        ).scalar_one()
        # 原生身份服务撤销会话、refresh token 和身份版本；不在浏览器假定已失效。
        await IdentitySecurityEventService.handle_user_event(
            session, target, "password_changed", actor=actor_name
        )
        await session.execute(
            text(
                "UPDATE sys_user SET password=:password,pwd_update_date=UTC_TIMESTAMP(3),update_by=:actor_name,update_time=UTC_TIMESTAMP(3) WHERE user_id=:user"
            ),
            {
                "user": target,
                "password": PwdUtil.get_password_hash(value.password.get_secret_value()),
                "actor_name": actor_name,
            },
        )
        await session.execute(
            text(
                "UPDATE orbit_business_user SET invited=0,revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id"
            ),
            params,
        )
        # 重置密码不擅自开启停用账号；旧邀请失效，不能再通过旧链接切换身份。
        await session.execute(
            text(
                "UPDATE orbit_user_invitation SET status='REVOKED',revision=revision+1,revoked_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND user_id=:native AND status='ACTIVE'"
            ),
            params | {"native": target},
        )
        response = await self.get(session, actor, user_id)
        await append_directory_change(
            session,
            context,
            key,
            digest,
            before,
            response,
            ("revision", "identity_status"),
            request_id,
            "USER",
        )
        await session.execute(
            text(
                "UPDATE orbit_directory_audit SET changed_fields_json=:fields WHERE tenant_id=:tenant AND resource_type='USER' AND resource_id=:id AND revision=:revision AND request_id=:request"
            ),
            params
            | {"fields": '["password"]', "revision": response["revision"], "request": request_id},
        )
        await session.execute(
            text(
                "UPDATE orbit_directory_idempotency SET digest_key_id=:kid WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key"
            ),
            params | {"kid": kid},
        )
        return response
