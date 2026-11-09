"""OIDC客户端授权编排；短事务认领后交换，稳定身份核对与会话发放同事务。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from orbit_api.auth_audit import append_auth_audit
from orbit_api.authorization_store import AuthorizationStore
from orbit_api.browser_session_store import BrowserSessionStore
from orbit_api.configuration_store import _decode
from orbit_api.errors import OrbitError
from orbit_api.invitation_consumer import InvitationConsumer, invalid_invitation
from orbit_api.oidc_provider import OidcProvider, ProviderConfiguration
from orbit_api.session_read import session_payload


class AuthenticationService:
    def __init__(self, sessions, cipher, *, http=None):
        self.sessions = sessions
        self.cipher = cipher
        self.http = http

    async def _provider(self, session, provider_id, *, expected=None):
        row = (
            (
                await session.execute(
                    text("""SELECT c.* FROM orbit_system_configuration c
                        JOIN orbit_tenant tenant ON tenant.id=c.tenant_id AND tenant.enabled=1
                        WHERE c.id=:id AND c.section='OIDC' AND c.enabled=1 FOR SHARE"""),
                    {"id": provider_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None or (expected is not None and row["revision"] != expected):
            raise OrbitError(409, "OIDC_CONFIGURATION_CHANGED", "登录配置已变更，请重新登录")
        settings, secrets = _decode(row["settings_json"]), _decode(row["secrets_json"])
        if not secrets.get("clientSecret"):
            raise OrbitError(503, "OIDC_CONFIGURATION_INVALID", "登录客户端凭据尚未配置")
        provider = OidcProvider(
            ProviderConfiguration(
                settings.get("issuer"),
                settings.get("clientId"),
                settings.get("redirectUri"),
                self.cipher.decrypt_internal(
                    secrets["clientSecret"], row["tenant_id"], row["id"], "clientSecret"
                ),
            ),
            http=self.http,
        )
        return dict(row), provider

    async def providers(self, public_origin):
        async with self.sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        text("""SELECT c.id,c.name FROM orbit_system_configuration c
                            JOIN orbit_tenant tenant ON tenant.id=c.tenant_id AND tenant.enabled=1
                            WHERE c.section='OIDC' AND c.enabled=1
                                AND JSON_UNQUOTE(JSON_EXTRACT(c.settings_json,'$.redirectUri'))
                                    IN (:frontend,:backend)
                            ORDER BY c.id LIMIT 101 FOR SHARE"""),
                        {
                            "frontend": public_origin + "/auth/callback",
                            "backend": public_origin + "/api/v1/auth/callback",
                        },
                    )
                )
                .mappings()
                .all()
            )
        if len(rows) > 100:
            raise OrbitError(503, "OIDC_PROVIDER_LIMIT", "登录提供者配置超过可选上限")
        return [{"id": row["id"], "name": row["name"]} for row in rows]

    async def start(self, public_origin, binding, return_to, request_id, *, provider_id=None):
        options = await self.providers(public_origin)
        if provider_id is None:
            if len(options) != 1:
                raise OrbitError(
                    409 if options else 503,
                    "OIDC_PROVIDER_SELECTION_REQUIRED",
                    "请选择登录提供者" if options else "尚未配置可用登录提供者",
                )
            provider_id = options[0]["id"]
        if provider_id not in {option["id"] for option in options}:
            raise OrbitError(404, "OIDC_PROVIDER_NOT_FOUND", "登录提供者不可用")
        async with self.sessions() as session, session.begin():
            row, provider = await self._provider(session, provider_id)
        return await self._create_attempt(row, provider, binding, return_to, request_id)

    async def start_invitation(self, public_origin, binding, token, return_to, request_id):
        async with self.sessions() as session, session.begin():
            invitation = await InvitationConsumer().resolve_token(session, token)
            row, provider = await self._provider(
                session, invitation["provider_id"], expected=invitation["provider_revision"]
            )
            if provider.configuration.redirect_uri not in {
                public_origin + "/auth/callback",
                public_origin + "/api/v1/auth/callback",
            }:
                raise invalid_invitation()
        return await self._create_attempt(
            row, provider, binding, return_to, request_id, invitation_id=invitation["id"]
        )

    async def _create_attempt(
        self, row, provider, binding, return_to, request_id, *, invitation_id=None
    ):
        metadata = await provider.discover()
        async with self.sessions() as session, session.begin():
            if invitation_id:
                await InvitationConsumer._resolve(
                    session,
                    "i.id=:id AND i.tenant_id=:tenant",
                    {"id": invitation_id, "tenant": row["tenant_id"]},
                )
            attempt = await AuthorizationStore(self.cipher).start(
                session,
                row["tenant_id"],
                row["id"],
                row["revision"],
                binding,
                return_to,
                request_id,
                invitation_id=invitation_id,
            )
            url = provider.authorization_url(
                metadata,
                attempt.state,
                attempt.nonce,
                attempt.challenge,
                choose_account=invitation_id is not None,
            )
            if len(url) > 2048:
                raise OrbitError(503, "OIDC_CONFIGURATION_INVALID", "授权地址超过合同长度上限")
            expires = (
                await session.execute(
                    text("SELECT expires_at FROM orbit_oidc_authorization WHERE id=:id"),
                    {"id": attempt.id},
                )
            ).scalar_one()
        return {
            "authorize_url": url,
            "expires_at": expires.isoformat(timespec="milliseconds") + "Z",
        }

    async def callback(self, state, code, binding, request_id):
        flow_store = AuthorizationStore(self.cipher)
        async with self.sessions() as session, session.begin():
            claimed = await flow_store.claim(session, state, binding, request_id)
        try:
            async with self.sessions() as session, session.begin():
                row, provider = await self._provider(
                    session, claimed.provider_id, expected=claimed.provider_revision
                )
            metadata = await provider.discover()
            import time
            from datetime import UTC

            verified = await provider.exchange(
                metadata,
                code,
                claimed.verifier,
                nonce=claimed.nonce,
                now=time.time(),
                issued_after=claimed.created_at.replace(tzinfo=UTC).timestamp(),
            )
            async with self.sessions() as session, session.begin():
                current = (
                    await session.execute(
                        text("""SELECT id FROM orbit_oidc_authorization WHERE id=:id
                            AND tenant_id=:tenant AND status='EXCHANGING'
                            AND expires_at>UTC_TIMESTAMP(3) FOR UPDATE"""),
                        {"id": claimed.id, "tenant": claimed.tenant_id},
                    )
                ).first()
                if current is None:
                    raise OrbitError(401, "OIDC_AUTHORIZATION_INVALID", "授权已过期，请重新登录")
                await self._provider(
                    session, claimed.provider_id, expected=claimed.provider_revision
                )
                if claimed.invitation_id:
                    await InvitationConsumer().consume(
                        session, claimed.invitation_id, claimed.tenant_id, verified, request_id
                    )
                identity = (
                    (
                        await session.execute(
                            text("""SELECT user_id,issuer,subject FROM orbit_external_identity
                                WHERE issuer_digest=:issuer AND subject_digest=:subject
                                    AND tenant_id=:tenant FOR SHARE"""),
                            {
                                "issuer": hashlib.sha256(verified.issuer.encode()).digest(),
                                "subject": hashlib.sha256(verified.subject.encode()).digest(),
                                "tenant": claimed.tenant_id,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    identity is None
                    or identity["issuer"] != verified.issuer
                    or identity["subject"] != verified.subject
                ):
                    raise OrbitError(
                        403,
                        "OIDC_INVITATION_REQUIRED",
                        "此身份尚未绑定有效人员，请联系管理员发送邀请",
                    )
                cookie, principal = await BrowserSessionStore(self.cipher).issue(
                    session,
                    claimed.tenant_id,
                    identity["user_id"],
                    claimed.provider_id,
                    claimed.provider_revision,
                    binding,
                    request_id,
                )
                await session.execute(
                    text("""UPDATE orbit_oidc_authorization SET status='CONSUMED',
                    finished_at=UTC_TIMESTAMP(3) WHERE id=:id"""),
                    {"id": claimed.id},
                )
                await append_auth_audit(
                    session,
                    claimed.tenant_id,
                    identity["user_id"],
                    "AUTHORIZATION",
                    claimed.id,
                    "VERIFIED",
                    3,
                    request_id,
                )
                payload = await session_payload(session, principal)
            return cookie, payload, claimed.return_to
        except Exception as error:
            code = {
                "OIDC_EXCHANGE_UNKNOWN": "EXCHANGE_UNKNOWN",
                "OIDC_TOKEN_INVALID": "TOKEN_INVALID",
                "OIDC_CONFIGURATION_CHANGED": "CONFIGURATION_CHANGED",
                "OIDC_INVITATION_REQUIRED": "IDENTITY_REJECTED",
                "INVITATION_INVALID": "IDENTITY_REJECTED",
                "INVITATION_EMAIL_UNVERIFIED": "IDENTITY_REJECTED",
                "INVITATION_EMAIL_MISMATCH": "IDENTITY_REJECTED",
            }.get(getattr(error, "code", ""), "EXCHANGE_FAILED")
            async with self.sessions() as session, session.begin():
                await flow_store.fail(session, claimed, code, str(uuid4()))
            raise
