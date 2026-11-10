"""产品不透明Cookie会话：只存摘要、独立CSRF、30分钟闲置/12小时绝对上限与即时撤权。"""

import hashlib
import hmac
import json
import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.auth_audit import append_auth_audit
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.cookie_identity import CookieIdentity
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import ABSOLUTE_SECONDS, IDLE_SECONDS, credential_digest, opaque_token


class BrowserSessionStore:
    def __init__(self, cipher):
        self.cipher = cipher

    def _identity(self, row):
        body = canonical(
            [
                row["id"],
                row["tenant_id"],
                row["user_id"],
                row["auth_version"],
                bytes(row["token_digest"]).hex(),
                bytes(row["binding_digest"]).hex(),
            ]
        ).encode()
        csrf = (
            row["csrf_key_id"]
            + "."
            + self.cipher.application_mac("BROWSER_SESSION_CSRF_V1", body, row["csrf_key_id"])
        )
        return CookieIdentity(
            row["user_id"],
            row["tenant_id"],
            row["auth_version"],
            row["id"],
            csrf,
            min(row["idle_expires_at"], row["absolute_expires_at"]),
        )

    @staticmethod
    async def _principal(session, tenant, actor, provider_id, provider_revision):
        row = (
            (
                await session.execute(
                    text("""SELECT i.subject_id,i.auth_version,s.data_role,e.issuer,
                        JSON_UNQUOTE(JSON_EXTRACT(c.settings_json,'$.issuer')) AS provider_issuer
                    FROM sys_user u
                    JOIN sys_identity_subject i ON i.user_id=u.user_id
                    JOIN orbit_user_scope s ON s.user_id=u.user_id AND s.tenant_id=:tenant
                    JOIN orbit_business_user b ON b.user_id=u.user_id AND b.tenant_id=s.tenant_id
                    JOIN orbit_business_team t ON t.id=b.team_id AND t.tenant_id=b.tenant_id
                    JOIN orbit_tenant tenant ON tenant.id=s.tenant_id
                    JOIN orbit_external_identity e ON e.user_id=u.user_id
                        AND e.tenant_id=s.tenant_id
                    JOIN orbit_system_configuration c ON c.id=:provider AND c.tenant_id=s.tenant_id
                    WHERE u.user_id=:actor AND u.status='0' AND u.del_flag='0'
                        AND b.enabled=1 AND b.invited=0 AND s.enabled=1 AND t.enabled=1
                        AND tenant.enabled=1 AND s.data_role IN ('USER','TEAM_ADMIN','SUPER_ADMIN')
                        AND c.section='OIDC' AND c.enabled=1 AND c.revision=:provider_revision
                    FOR SHARE"""),
                    {
                        "tenant": tenant,
                        "actor": actor,
                        "provider": provider_id,
                        "provider_revision": provider_revision,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "登录身份或登录配置已失效")
        if row["issuer"] != row["provider_issuer"]:
            raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "登录身份与受信提供者不一致")
        return row

    @staticmethod
    async def native_principal(session, tenant, actor):
        """原生认证主体仍须复核租户、人员、团队和安全版本，不伪造OIDC映射。"""
        row = (
            (
                await session.execute(
                    text("""SELECT i.subject_id,i.auth_version
            FROM sys_user u JOIN sys_identity_subject i ON i.user_id=u.user_id
            JOIN orbit_user_scope s ON s.user_id=u.user_id AND s.tenant_id=:tenant
            JOIN orbit_business_user b ON b.user_id=u.user_id AND b.tenant_id=s.tenant_id
            JOIN orbit_business_team t ON t.id=b.team_id AND t.tenant_id=b.tenant_id
            JOIN orbit_tenant tenant ON tenant.id=s.tenant_id
            WHERE u.user_id=:actor AND u.status='0' AND u.del_flag='0'
            AND b.enabled=1 AND b.invited=0 AND s.enabled=1 AND t.enabled=1
            AND tenant.enabled=1 AND s.data_role IN ('USER','TEAM_ADMIN','SUPER_ADMIN')
            FOR SHARE"""),
                    {"tenant": tenant, "actor": actor},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "本地登录身份已失效")
        return row

    async def issue(
        self,
        session,
        tenant,
        actor,
        provider_id,
        provider_revision,
        binding,
        request_id,
        *,
        native=False,
    ):
        """仅供已验证回调同事务调用；邀请绑定、启用、会话及审计任一失败均回滚。"""
        if native:
            from orbit_api.native_session import current_auth_snapshot

            snapshot = current_auth_snapshot()
            principal = await self.native_principal(session, tenant, actor)
            if (
                snapshot is None
                or snapshot.actor_id != actor
                or snapshot.version != principal["auth_version"]
            ):
                raise OrbitError(401, "SESSION_REQUIRED", "需要已验证的本地登录")
            if provider_id is not None or provider_revision is not None:
                raise OrbitError(400, "INVALID_STRUCTURE", "原生会话不能指定OIDC配置")
        else:
            principal = await self._principal(
                session, tenant, actor, provider_id, provider_revision
            )
        if not self.cipher.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端认证主密钥尚未配置")
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        cookie = opaque_token()
        row = {
            "id": str(uuid4()),
            "tenant_id": tenant,
            "user_id": actor,
            "auth_version": principal["auth_version"],
            "provider_id": provider_id,
            "provider_revision": provider_revision,
            "authentication_kind": "NATIVE" if native else "OIDC",
            "token_digest": credential_digest("SESSION", cookie),
            "binding_digest": credential_digest("BROWSER_BINDING", binding),
            "csrf_key_id": self.cipher.active_key_id,
            "created_at": now,
            "last_seen_at": now,
            "idle_expires_at": now + timedelta(seconds=IDLE_SECONDS),
            "absolute_expires_at": now + timedelta(seconds=ABSOLUTE_SECONDS),
        }
        await session.execute(
            text("""INSERT INTO orbit_browser_session
                (id,tenant_id,user_id,auth_version,provider_id,provider_revision,authentication_kind,token_digest,
                 binding_digest,csrf_key_id,status,created_at,last_seen_at,idle_expires_at,absolute_expires_at)
                VALUES(:id,:tenant_id,:user_id,:auth_version,:provider_id,:provider_revision,:authentication_kind,:token_digest,
                 :binding_digest,:csrf_key_id,'ACTIVE',:created_at,:last_seen_at,:idle_expires_at,:absolute_expires_at)"""),
            row,
        )
        await append_auth_audit(
            session, tenant, actor, "SESSION", row["id"], "SESSION_CREATED", 1, request_id
        )
        return cookie, self._identity(row)

    @staticmethod
    async def _owned_row(session, cookie, binding, *, lock=False):
        digest = credential_digest("SESSION", cookie)
        row = (
            (
                await session.execute(
                    text(
                        "SELECT *,UTC_TIMESTAMP(3) AS checked_at FROM orbit_browser_session "
                        "WHERE token_digest=:digest" + (" FOR UPDATE" if lock else " FOR SHARE")
                    ),
                    {"digest": digest},
                )
            )
            .mappings()
            .first()
        )
        if row is None or not hmac.compare_digest(
            bytes(row["binding_digest"]), credential_digest("BROWSER_BINDING", binding)
        ):
            raise OrbitError(401, "SESSION_REQUIRED", "会话无效，请重新登录")
        return dict(row)

    async def resolve(self, session, cookie, binding, *, touch=True):
        """由短认证事务调用，不能在持有会话锁时等待外部网络。"""
        row = await self._owned_row(session, cookie, binding, lock=touch)
        now = row["checked_at"]
        if (
            row["status"] != "ACTIVE"
            or min(row["idle_expires_at"], row["absolute_expires_at"]) <= now
        ):
            raise OrbitError(401, "SESSION_REQUIRED", "会话已退出或过期，请重新登录")
        if row.get("authentication_kind", "OIDC") == "NATIVE":
            principal = await self.native_principal(session, row["tenant_id"], row["user_id"])
        else:
            principal = await self._principal(
                session,
                row["tenant_id"],
                row["user_id"],
                row["provider_id"],
                row["provider_revision"],
            )
        if principal["auth_version"] != row["auth_version"]:
            raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "授权已更新，请重新登录")
        if touch and row["last_seen_at"] <= now - timedelta(seconds=60):
            idle = min(now + timedelta(seconds=IDLE_SECONDS), row["absolute_expires_at"])
            updated = await session.execute(
                text("""UPDATE orbit_browser_session SET last_seen_at=:now,idle_expires_at=:idle
                    WHERE id=:id AND status='ACTIVE' AND revision=:revision
                        AND idle_expires_at>UTC_TIMESTAMP(3)
                        AND absolute_expires_at>UTC_TIMESTAMP(3)"""),
                {"now": now, "idle": idle, "id": row["id"], "revision": row["revision"]},
            )
            if updated.rowcount != 1:
                raise OrbitError(401, "SESSION_REQUIRED", "会话已失效，请重新登录")
            row.update(last_seen_at=now, idle_expires_at=idle)
        return self._identity(row)

    async def logout(self, session, cookie, binding, csrf, key, request_id):
        """允许原会话归属的退出回执重放；任何分支都不恢复会话或返回用户资料。"""
        if not isinstance(key, str) or not re.fullmatch(r"[ -~]{16,128}", key):
            raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "退出请求需要有效幂等键")
        row = await self._owned_row(session, cookie, binding, lock=True)
        identity = self._identity(row)
        if (
            not isinstance(csrf, str)
            or not csrf.isascii()
            or not hmac.compare_digest(csrf, identity.csrf_token)
        ):
            raise OrbitError(403, "CSRF_INVALID", "请求会话校验失败")
        digest = hashlib.sha256(canonical(["SIGN_OUT", row["id"]]).encode()).digest()
        previous = (
            (
                await session.execute(
                    text(
                        "SELECT payload_hash,response_json FROM orbit_auth_idempotency "
                        "WHERE session_id=:id AND request_key=:key FOR UPDATE"
                    ),
                    {"id": row["id"], "key": key},
                )
            )
            .mappings()
            .first()
        )
        if previous:
            if bytes(previous["payload_hash"]) != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他退出请求")
            return (
                json.loads(previous["response_json"])
                if isinstance(previous["response_json"], str)
                else previous["response_json"]
            )
        revision = row["revision"]
        if row["status"] == "ACTIVE":
            if revision >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "会话版本已达上限")
            revision += 1
            await session.execute(
                text(
                    "UPDATE orbit_browser_session SET status='REVOKED',revision=:revision,"
                    "revoked_at=UTC_TIMESTAMP(3) WHERE id=:id"
                ),
                {"revision": revision, "id": row["id"]},
            )
            await append_auth_audit(
                session,
                row["tenant_id"],
                row["user_id"],
                "SESSION",
                row["id"],
                "SIGNED_OUT",
                revision,
                request_id,
            )
        result = {
            "id": row["id"],
            "revision": revision,
            "state": "SIGNED_OUT",
            "request_id": request_id,
        }
        await session.execute(
            text(
                "INSERT INTO orbit_auth_idempotency "
                "(session_id,request_key,payload_hash,response_json,created_at) "
                "VALUES(:id,:key,:hash,:response,UTC_TIMESTAMP(3))"
            ),
            {"id": row["id"], "key": key, "hash": digest, "response": canonical(result)},
        )
        return result
