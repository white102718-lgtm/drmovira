"""OIDC授权事务持久化：认领先提交，外部网络不在数据库锁内执行。"""

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.auth_audit import append_auth_audit
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import (
    AUTHORIZATION_SECONDS,
    credential_digest,
    opaque_token,
    safe_return_to,
)


@dataclass(frozen=True, repr=False)
class AuthorizationAttempt:
    id: str
    state: str
    nonce: str
    challenge: str


@dataclass(frozen=True, repr=False)
class ClaimedAuthorization:
    id: str
    tenant_id: str
    provider_id: str
    provider_revision: int
    verifier: str
    nonce: str
    return_to: str
    created_at: datetime
    invitation_id: str | None = None


class AuthorizationStore:
    def __init__(self, cipher):
        self.cipher = cipher

    @staticmethod
    async def _provider(session, tenant, provider, revision):
        available = (
            await session.execute(
                text("""SELECT id FROM orbit_system_configuration
                    WHERE id=:provider AND tenant_id=:tenant AND section='OIDC'
                        AND enabled=1 AND revision=:revision FOR SHARE"""),
                {"provider": provider, "tenant": tenant, "revision": revision},
            )
        ).first()
        if available is None:
            raise OrbitError(409, "OIDC_CONFIGURATION_CHANGED", "登录配置已变更，请重新发起登录")

    async def start(
        self,
        session,
        tenant,
        provider,
        revision,
        binding,
        return_to,
        request_id,
        *,
        invitation_id=None,
    ):
        """提供者和租户只能由可信配置选择器传入；本方法不接受浏览器身份字段。"""
        return_to = safe_return_to(return_to)
        bound = credential_digest("BROWSER_BINDING", binding)
        await self._provider(session, tenant, provider, revision)
        flow, state, verifier, nonce = str(uuid4()), opaque_token(), opaque_token(), opaque_token()
        envelope = self.cipher.encrypt(
            canonical({"verifier": verifier, "nonce": nonce, "return_to": return_to}),
            tenant,
            flow,
            "oidc_authorization",
        )
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        await session.execute(
            text("""INSERT INTO orbit_oidc_authorization
                (id,tenant_id,provider_id,provider_revision,state_digest,binding_digest,
                 protected_json,status,expires_at,created_at,invitation_id)
                VALUES(:id,:tenant,:provider,:revision,:state,:binding,:protected,'PENDING',
                 :expires,:created,:invitation)"""),
            {
                "id": flow,
                "tenant": tenant,
                "provider": provider,
                "revision": revision,
                "state": credential_digest("AUTHORIZATION_STATE", state),
                "binding": bound,
                "protected": canonical({"envelope": envelope}),
                "expires": now + timedelta(seconds=AUTHORIZATION_SECONDS),
                "created": now,
                "invitation": invitation_id,
            },
        )
        await append_auth_audit(
            session, tenant, None, "AUTHORIZATION", flow, "STARTED", 1, request_id
        )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        return AuthorizationAttempt(flow, state, nonce, challenge.rstrip(b"=").decode())

    async def claim(self, session, state, binding, request_id):
        """调用者必须先提交此短事务，再交换授权码；重复回调不能重新认领。"""
        row = (
            (
                await session.execute(
                    text("""SELECT *,UTC_TIMESTAMP(3) AS checked_at
                        FROM orbit_oidc_authorization WHERE state_digest=:state FOR UPDATE"""),
                    {"state": credential_digest("AUTHORIZATION_STATE", state)},
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or not hmac.compare_digest(
                bytes(row["binding_digest"]), credential_digest("BROWSER_BINDING", binding)
            )
            or row["status"] != "PENDING"
            or row["expires_at"] <= row["checked_at"]
        ):
            raise OrbitError(401, "OIDC_AUTHORIZATION_INVALID", "登录授权无效或已使用，请重新登录")
        await self._provider(
            session, row["tenant_id"], row["provider_id"], row["provider_revision"]
        )
        protected = row["protected_json"]
        if isinstance(protected, str):
            protected = json.loads(protected)
        payload = json.loads(
            self.cipher.decrypt_internal(
                protected["envelope"], row["tenant_id"], row["id"], "oidc_authorization"
            )
        )
        await session.execute(
            text("""UPDATE orbit_oidc_authorization SET status='EXCHANGING',
                claimed_at=UTC_TIMESTAMP(3) WHERE id=:id"""),
            {"id": row["id"]},
        )
        await append_auth_audit(
            session, row["tenant_id"], None, "AUTHORIZATION", row["id"], "CLAIMED", 2, request_id
        )
        return ClaimedAuthorization(
            row["id"],
            row["tenant_id"],
            row["provider_id"],
            row["provider_revision"],
            payload["verifier"],
            payload["nonce"],
            payload["return_to"],
            row["created_at"],
            row["invitation_id"],
        )

    @staticmethod
    async def fail(session, claimed: ClaimedAuthorization, code, request_id):
        """只保存固定失败类别，不接收外部响应、授权码或异常正文。"""
        if code not in {
            "EXCHANGE_FAILED",
            "EXCHANGE_UNKNOWN",
            "TOKEN_INVALID",
            "IDENTITY_REJECTED",
            "CONFIGURATION_CHANGED",
        }:
            raise ValueError("未知授权失败类别")
        changed = await session.execute(
            text("""UPDATE orbit_oidc_authorization SET status='FAILED',
                failure_code=:code,finished_at=UTC_TIMESTAMP(3)
                WHERE id=:id AND tenant_id=:tenant AND status='EXCHANGING'"""),
            {"id": claimed.id, "tenant": claimed.tenant_id, "code": code},
        )
        if changed.rowcount:
            await append_auth_audit(
                session,
                claimed.tenant_id,
                None,
                "AUTHORIZATION",
                claimed.id,
                "FAILED",
                3,
                request_id,
            )
