"""一次性人员邀请：CAS/幂等、版本绑定、加密投递意图与最小审计同事务提交。"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.auth_audit import append_auth_audit
from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_tokens import canonical
from orbit_api.directory_write import append_directory_change, public_hash
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import INVITATION_SECONDS, credential_digest, opaque_token
from orbit_api.oidc_http import secure_url
from orbit_api.oidc_provider import OidcProvider, ProviderConfiguration
from orbit_api.user_store import UserStore


class InvitationStore(UserStore):
    async def _configuration(self, session, tenant, origin):
        if not self.tokens.cipher.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端认证主密钥尚未配置")
        providers = (
            (
                await session.execute(
                    text("""SELECT id,revision,secrets_json,settings_json
                        FROM orbit_system_configuration
                    WHERE tenant_id=:tenant AND section='OIDC' AND enabled=1
                        AND JSON_UNQUOTE(JSON_EXTRACT(settings_json,'$.redirectUri'))
                            IN (:frontend,:backend) ORDER BY id LIMIT 2 FOR SHARE"""),
                    {
                        "tenant": tenant,
                        "frontend": origin + "/auth/callback",
                        "backend": origin + "/api/v1/auth/callback",
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(providers) != 1 or not _decode(providers[0]["secrets_json"]).get("clientSecret"):
            raise OrbitError(
                409,
                "INVITATION_PROVIDER_REQUIRED",
                "当前租户需配置唯一有效的OIDC登录提供者及客户端凭据",
            )
        settings = _decode(providers[0]["settings_json"])
        OidcProvider(
            ProviderConfiguration(
                settings.get("issuer"),
                settings.get("clientId"),
                settings.get("redirectUri"),
                self.tokens.cipher.decrypt_internal(
                    _decode(providers[0]["secrets_json"])["clientSecret"],
                    tenant,
                    providers[0]["id"],
                    "clientSecret",
                ),
            )
        )
        channels = (
            (
                await session.execute(
                    text("""SELECT id,revision,settings_json FROM orbit_system_configuration
                    WHERE tenant_id=:tenant AND section='NOTIFICATIONS' AND enabled=1
                        AND JSON_UNQUOTE(JSON_EXTRACT(settings_json,'$.channel'))='WEBHOOK'
                    ORDER BY id LIMIT 2 FOR SHARE"""),
                    {"tenant": tenant},
                )
            )
            .mappings()
            .all()
        )
        if len(channels) != 1:
            raise OrbitError(
                409,
                "INVITATION_CHANNEL_REQUIRED",
                "邀请需配置唯一启用的Webhook通知渠道，站内通知不能送达未登录人员",
            )
        endpoint = _decode(channels[0]["settings_json"]).get("webhookUrl")
        if secure_url(endpoint).query:
            raise OrbitError(
                409,
                "INVITATION_CHANNEL_REQUIRED",
                "邀请通知地址不接受查询参数，认证信息请配置Webhook Token",
            )
        return providers[0], channels[0]

    async def status(self, session, actor, user_id, origin):
        context, _ = await self.context(session, actor)
        user = await self.get(session, actor, user_id)
        reason = None
        if context.data_role != "SUPER_ADMIN":
            reason = "仅有权限的超级管理员可发送邀请"
        elif user["identity_status"] != "UNVERIFIED" or user["status"] != "INVITED":
            reason = "仅待邀请验证的人员可发送邀请；停用人员请先明确恢复到待邀请状态"
        else:
            try:
                await self._configuration(session, context.tenant_id, origin)
            except OrbitError as error:
                reason = error.message
        row = (
            (
                await session.execute(
                    text("""SELECT i.id,i.status,i.created_at,i.expires_at,
                        UTC_TIMESTAMP(3) AS checked_at,
                    d.status AS delivery_state,d.failure_code FROM orbit_user_invitation i
                    JOIN orbit_business_user b ON b.user_id=i.user_id AND b.tenant_id=i.tenant_id
                    LEFT JOIN orbit_invitation_delivery d ON d.invitation_id=i.id
                    WHERE i.tenant_id=:tenant AND b.id=:id
                    ORDER BY i.created_at DESC,i.id DESC LIMIT 1 FOR SHARE"""),
                    {"tenant": context.tenant_id, "id": user["id"]},
                )
            )
            .mappings()
            .first()
        )
        invitation = None
        if row:
            invitation = {
                "id": row["id"],
                "state": "EXPIRED"
                if row["status"] == "ACTIVE" and row["expires_at"] <= row["checked_at"]
                else row["status"],
                "created_at": row["created_at"].isoformat(timespec="milliseconds") + "Z",
                "expires_at": row["expires_at"].isoformat(timespec="milliseconds") + "Z",
                "delivery_state": row["delivery_state"],
                "failure_code": row["failure_code"],
            }
        return {"can_invite": reason is None, "blocked_reason": reason, "invitation": invitation}

    async def create(
        self, session, actor, authorization, csrf, key, user_id, expected, request_id, origin
    ):
        context, _ = await self.context(session, actor)
        if context.data_role != "SUPER_ADMIN":
            raise OrbitError(403, "PERMISSION_DENIED", "人员邀请仅限有权限的超级管理员")
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
        user_id = _uuid(user_id)
        digest = public_hash(["USER_INVITATION", user_id, expected])
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
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于其他邀请请求")
            return _decode(previous["response_json"])
        if before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "人员已被修改，请刷新后重试")
        if clock >= MAX_REVISION or expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "人员或目录版本已达上限")
        if before["identity_status"] != "UNVERIFIED" or before["status"] != "INVITED":
            raise OrbitError(409, "INVITATION_STATE_INVALID", "仅待邀请验证的人员可发送邀请")
        provider, channel = await self._configuration(session, context.tenant_id, origin)
        target = (
            (
                await session.execute(
                    text("""SELECT b.user_id,subject.auth_version FROM orbit_business_user b
                JOIN sys_identity_subject subject ON subject.user_id=b.user_id
                WHERE b.id=:id AND b.tenant_id=:tenant FOR UPDATE"""),
                    {"id": before["id"], "tenant": context.tenant_id},
                )
            )
            .mappings()
            .one()
        )
        actor_version = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": actor},
            )
        ).scalar_one()
        old = (
            (
                await session.execute(
                    text(
                        "SELECT id,revision FROM orbit_user_invitation "
                        "WHERE tenant_id=:tenant AND user_id=:user "
                        "AND status='ACTIVE' FOR UPDATE"
                    ),
                    {"tenant": context.tenant_id, "user": target["user_id"]},
                )
            )
            .mappings()
            .all()
        )
        for identifier in old:
            if identifier["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "旧邀请状态版本已达上限")
            await session.execute(
                text(
                    "UPDATE orbit_user_invitation SET status='REVOKED',"
                    "revoked_at=UTC_TIMESTAMP(3),revision=revision+1 WHERE id=:id"
                ),
                {"id": identifier["id"]},
            )
            await append_auth_audit(
                session,
                context.tenant_id,
                actor,
                "INVITATION",
                identifier["id"],
                "INVITATION_REVOKED",
                identifier["revision"] + 1,
                request_id,
            )
        invitation, delivery, token = str(uuid4()), str(uuid4()), opaque_token()
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        revision = expected + 1
        await session.execute(
            text("""INSERT INTO orbit_user_invitation
            (id,tenant_id,user_id,user_revision,auth_version,recipient_email,provider_id,provider_revision,
             token_digest,status,expires_at,created_at,created_by,created_by_auth_version)
            VALUES(:id,:tenant,:user,:revision,:version,:email,:provider,:provider_revision,
             :digest,'ACTIVE',:expires,:created,:actor,:actor_version)"""),
            {
                "id": invitation,
                "tenant": context.tenant_id,
                "user": target["user_id"],
                "revision": revision,
                "version": target["auth_version"],
                "email": before["email"],
                "provider": provider["id"],
                "provider_revision": provider["revision"],
                "digest": credential_digest("INVITATION", token),
                "expires": now + timedelta(seconds=INVITATION_SECONDS),
                "created": now,
                "actor": actor,
                "actor_version": actor_version,
            },
        )
        envelope = self.tokens.cipher.encrypt(
            canonical(
                {
                    "invitation_token": token,
                    "recipient_email": before["email"],
                    "public_origin": origin,
                }
            ),
            context.tenant_id,
            delivery,
            "invitation_delivery",
        )
        await session.execute(
            text("""INSERT INTO orbit_invitation_delivery
            (id,tenant_id,invitation_id,notification_id,notification_revision,protected_json,status,created_at)
            VALUES(:id,:tenant,:invitation,:notification,:revision,:protected,'QUEUED',:created)"""),
            {
                "id": delivery,
                "tenant": context.tenant_id,
                "invitation": invitation,
                "notification": channel["id"],
                "revision": channel["revision"],
                "protected": canonical({"envelope": envelope}),
                "created": now,
            },
        )
        await session.execute(
            text(
                "UPDATE orbit_business_user SET revision=:revision,"
                "updated_at=UTC_TIMESTAMP(3) WHERE id=:id AND tenant_id=:tenant"
            ),
            {"revision": revision, "id": before["id"], "tenant": context.tenant_id},
        )
        after = {**before, "revision": revision}
        await append_directory_change(
            session,
            context,
            key,
            digest,
            before,
            after,
            [],
            request_id,
            "USER",
            record_idempotency=False,
        )
        await append_auth_audit(
            session,
            context.tenant_id,
            actor,
            "INVITATION",
            invitation,
            "INVITATION_QUEUED",
            1,
            request_id,
        )
        result = {
            "id": before["id"],
            "revision": revision,
            "state": "INVITATION_QUEUED",
            "request_id": request_id,
        }
        await session.execute(
            text("""INSERT INTO orbit_directory_idempotency
            (tenant_id,actor_id,request_key,payload_hash,response_json)
            VALUES(:tenant,:actor,:key,:hash,:response)"""),
            {**params, "hash": digest, "response": canonical(result)},
        )
        return result
