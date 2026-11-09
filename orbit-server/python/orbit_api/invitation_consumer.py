"""邀请接收：验证一次性凭据、当前授权快照和已验证邮箱，再原子绑定与激活。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orbit_api.auth_audit import append_auth_audit
from orbit_api.authorization import BusinessContext, require_system_access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_write import append_directory_change, public_hash
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import credential_digest
from orbit_api.user_store import _COLUMNS, _FROM, UserStore


def invalid_invitation():
    return OrbitError(401, "INVITATION_INVALID", "邀请无效或已过期，请联系管理员重新发送")


class InvitationConsumer:
    @staticmethod
    async def _resolve(session, condition, parameters, *, lock=False):
        # condition仅为本类固定SQL片段，参数一律绑定；摘要唯一索引或主键定位，不扫描邀请表。
        row = (
            (
                await session.execute(
                    text(
                        """SELECT i.*,b.id AS business_user_id,b.team_id,
                        b.revision AS current_revision,
                    b.invited,s.data_role,subject.auth_version AS current_auth_version,u.email,
                    JSON_UNQUOTE(JSON_EXTRACT(c.settings_json,'$.issuer')) AS issuer,
                    sender.auth_version AS current_sender_version
                FROM orbit_user_invitation i
                JOIN orbit_business_user b ON b.user_id=i.user_id AND b.tenant_id=i.tenant_id
                    AND b.enabled=1 AND b.invited=1
                JOIN sys_user u ON u.user_id=b.user_id AND u.status='1' AND u.del_flag='0'
                JOIN orbit_user_scope s ON s.user_id=u.user_id
                    AND s.tenant_id=b.tenant_id AND s.enabled=1
                JOIN orbit_business_team team ON team.id=b.team_id
                    AND team.tenant_id=b.tenant_id AND team.enabled=1
                JOIN orbit_tenant tenant ON tenant.id=b.tenant_id AND tenant.enabled=1
                JOIN sys_identity_subject subject ON subject.user_id=u.user_id
                JOIN sys_identity_subject sender ON sender.user_id=i.created_by
                JOIN orbit_system_configuration c ON c.id=i.provider_id AND c.tenant_id=i.tenant_id
                    AND c.enabled=1 AND c.section='OIDC' AND c.revision=i.provider_revision
                WHERE i.status='ACTIVE' AND i.expires_at>UTC_TIMESTAMP(3) AND """
                        + condition
                        + (" FOR UPDATE" if lock else " FOR SHARE")
                    ),
                    parameters,
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["current_revision"] != row["user_revision"]
            or row["current_auth_version"] != row["auth_version"]
            or row["email"] != row["recipient_email"]
            or row["created_by_auth_version"] is None
            or row["current_sender_version"] != row["created_by_auth_version"]
            or row["data_role"] not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}
        ):
            raise invalid_invitation()
        try:
            context = await require_system_access(
                session,
                row["created_by"],
                31082,
                "system.users.manage",
                super_admin=True,
                acting_subject=False,
            )
        except OrbitError as error:
            if error.status in {401, 403}:
                raise invalid_invitation() from None
            raise
        if context.tenant_id != row["tenant_id"]:
            raise invalid_invitation()
        return dict(row)

    async def resolve_token(self, session, token):
        return await self._resolve(
            session,
            "i.token_digest=:digest",
            {
                "digest": credential_digest("INVITATION", token),
            },
        )

    async def consume(self, session, invitation_id, tenant, verified, request_id):
        # 与全部组织写共用租户目录锁；回调在锁外完成网络，不占业务锁等待提供者。
        clock = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR UPDATE"
                ),
                {"tenant": tenant},
            )
        ).scalar_one()
        row = await self._resolve(
            session,
            "i.id=:id AND i.tenant_id=:tenant",
            {"id": invitation_id, "tenant": tenant},
            lock=True,
        )
        if verified.issuer != row["issuer"]:
            raise invalid_invitation()
        if verified.verified_email is None:
            raise OrbitError(
                401, "INVITATION_EMAIL_UNVERIFIED", "身份提供者未返回已验证邮箱，请先完成邮箱验证"
            )
        if verified.verified_email != row["recipient_email"]:
            raise OrbitError(
                401, "INVITATION_EMAIL_MISMATCH", "请使用受邀邮箱对应的企业账号完成登录"
            )
        if max(clock, row["user_revision"], row["auth_version"], row["revision"]) >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "邀请或人员安全版本已达上限")
        for statement, parameters in [
            (
                "SELECT id FROM orbit_external_identity WHERE issuer_digest=:issuer "
                "AND subject_digest=:subject FOR UPDATE",
                {
                    "issuer": hashlib.sha256(verified.issuer.encode()).digest(),
                    "subject": hashlib.sha256(verified.subject.encode()).digest(),
                },
            ),
            (
                "SELECT id FROM orbit_external_identity WHERE user_id=:user FOR UPDATE",
                {"user": row["user_id"]},
            ),
        ]:
            if (await session.execute(text(statement), parameters)).first() is not None:
                raise invalid_invitation()
        before_row = (
            (
                await session.execute(
                    text(
                        "SELECT "
                        + _COLUMNS
                        + _FROM
                        + " WHERE b.id=:id AND b.tenant_id=:tenant FOR SHARE"
                    ),
                    {"id": row["business_user_id"], "tenant": tenant},
                )
            )
            .mappings()
            .one()
        )
        before = (await UserStore(None)._public(session, tenant, [before_row]))[0]
        try:
            await session.execute(
                text("""INSERT INTO orbit_external_identity
                (id,tenant_id,user_id,issuer,issuer_digest,subject,subject_digest,
                 provider_id,verified_email,verified_at)
                VALUES(:id,:tenant,:user,:issuer,:issuer_digest,:subject,:subject_digest,
                 :provider,:email,UTC_TIMESTAMP(3))"""),
                {
                    "id": str(uuid4()),
                    "tenant": tenant,
                    "user": row["user_id"],
                    "issuer": verified.issuer,
                    "issuer_digest": hashlib.sha256(verified.issuer.encode()).digest(),
                    "subject": verified.subject,
                    "subject_digest": hashlib.sha256(verified.subject.encode()).digest(),
                    "provider": row["provider_id"],
                    "email": verified.verified_email,
                },
            )
        except IntegrityError:
            raise invalid_invitation() from None
        await session.execute(
            text(
                "UPDATE sys_user SET status='0',password=NULL,update_time=UTC_TIMESTAMP(3) "
                "WHERE user_id=:user"
            ),
            {"user": row["user_id"]},
        )
        await session.execute(
            text("UPDATE sys_identity_subject SET auth_version=auth_version+1 WHERE user_id=:user"),
            {"user": row["user_id"]},
        )
        await session.execute(
            text(
                "UPDATE orbit_business_user SET invited=0,revision=revision+1,"
                "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND user_id=:user"
            ),
            {"tenant": tenant, "user": row["user_id"]},
        )
        await session.execute(
            text(
                "UPDATE orbit_user_invitation SET status='CONSUMED',revision=revision+1,"
                "consumed_at=UTC_TIMESTAMP(3) WHERE id=:id"
            ),
            {"id": invitation_id},
        )
        after = {
            **before,
            "revision": row["user_revision"] + 1,
            "status": "ENABLED",
            "identity_status": "OIDC_VERIFIED",
        }
        context = BusinessContext(
            row["user_id"], tenant, row["data_role"], row["business_user_id"], row["team_id"]
        )
        await append_directory_change(
            session,
            context,
            None,
            public_hash(["INVITATION_CONSUMED", invitation_id]),
            before,
            after,
            ["status", "identity_status"],
            request_id,
            "USER",
            record_idempotency=False,
        )
        await append_auth_audit(
            session,
            tenant,
            row["user_id"],
            "INVITATION",
            invitation_id,
            "INVITATION_CONSUMED",
            row["revision"] + 1,
            request_id,
        )
        return row["user_id"]
