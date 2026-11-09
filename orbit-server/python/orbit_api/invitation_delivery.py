"""邀请投递事务Worker；短事务认领、事务外HTTPS、版本回执及崩溃保守恢复。"""

import hmac
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text

from orbit_api.auth_audit import append_auth_audit
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.errors import OrbitError
from orbit_api.invitation_consumer import InvitationConsumer
from orbit_api.notification_http import DeliveryOutcome, NotificationHttp
from orbit_api.oidc_contract import credential_digest
from orbit_api.oidc_http import secure_url


@dataclass(frozen=True, repr=False)
class DeliveryClaim:
    id: str
    tenant: str
    actor: int
    revision: int
    endpoint: str
    body: bytes
    signing_token: str | None


class InvitationDeliveryWorker:
    """仅由受控任务进程调用，不提供匿名触发接口，也不随应用启动自动发送。"""

    def __init__(self, sessions, cipher, origin, *, transport=None):
        self.sessions = sessions
        self.cipher = cipher
        self.origin = origin
        self.transport = transport or NotificationHttp()

    @staticmethod
    def _limit(value):
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("单轮投递批次仅允许1至100")
        return value

    async def _record(self, session, row, outcome):
        if outcome.status not in {"ACCEPTED", "FAILED", "UNKNOWN"}:
            raise ValueError("未知投递终态")
        if row["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "通知状态版本已达上限")
        await session.execute(
            text("""UPDATE orbit_invitation_delivery SET status=:status,revision=revision+1,
                completed_at=UTC_TIMESTAMP(3),failure_code=:failure WHERE id=:id
                AND tenant_id=:tenant AND revision=:revision"""),
            {
                "status": outcome.status,
                "failure": outcome.failure_code,
                "id": row["id"],
                "tenant": row["tenant_id"],
                "revision": row["revision"],
            },
        )
        await append_auth_audit(
            session,
            row["tenant_id"],
            row["created_by"],
            "DELIVERY",
            row["id"],
            "DELIVERY_" + outcome.status,
            row["revision"] + 1,
            str(uuid4()),
        )

    async def claim_one(self):
        """只认领一条；SKIP LOCKED允许多进程分工，数据库提交前不发送任何请求。"""
        if not self.cipher.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端认证主密钥尚未配置")
        async with self.sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text("""SELECT d.*,i.created_by
                FROM orbit_invitation_delivery d
                JOIN orbit_user_invitation i ON i.id=d.invitation_id AND i.tenant_id=d.tenant_id
                WHERE d.status='QUEUED' ORDER BY d.created_at,d.id LIMIT 1
                FOR UPDATE SKIP LOCKED""")
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None, None
            if row["revision"] >= MAX_REVISION - 1:
                raise OrbitError(409, "REVISION_EXHAUSTED", "通知状态版本已达上限")
            try:
                # 发起人授权、人员/邮箱/身份版本、提供者、有效期在发送前重新校验。
                invitation = await InvitationConsumer._resolve(
                    session,
                    "i.id=:id AND i.tenant_id=:tenant",
                    {"id": row["invitation_id"], "tenant": row["tenant_id"]},
                )
                configuration = (
                    (
                        await session.execute(
                            text("""SELECT settings_json,secrets_json
                    FROM orbit_system_configuration WHERE id=:id AND tenant_id=:tenant
                    AND section='NOTIFICATIONS' AND enabled=1 AND revision=:revision FOR SHARE"""),
                            {
                                "id": row["notification_id"],
                                "tenant": row["tenant_id"],
                                "revision": row["notification_revision"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if configuration is None:
                    raise ValueError
                settings = _decode(configuration["settings_json"])
                endpoint = settings.get("webhookUrl")
                if settings.get("channel") != "WEBHOOK" or secure_url(endpoint).query:
                    raise ValueError
                payload = json.loads(
                    self.cipher.decrypt_internal(
                        _decode(row["protected_json"])["envelope"],
                        row["tenant_id"],
                        row["id"],
                        "invitation_delivery",
                    )
                )
                if (
                    set(payload) != {"invitation_token", "recipient_email", "public_origin"}
                    or payload["recipient_email"] != invitation["recipient_email"]
                    or payload["public_origin"] != self.origin
                    or not hmac.compare_digest(
                        credential_digest("INVITATION", payload["invitation_token"]),
                        invitation["token_digest"],
                    )
                ):
                    raise ValueError
                secrets = _decode(configuration["secrets_json"])
                signing = (
                    self.cipher.decrypt_internal(
                        secrets["webhookToken"],
                        row["tenant_id"],
                        row["notification_id"],
                        "webhookToken",
                    )
                    if secrets.get("webhookToken")
                    else None
                )
                body = json.dumps(
                    {
                        "event_type": "ORBIT_USER_INVITATION_V1",
                        "delivery_id": row["id"],
                        "recipient_email": payload["recipient_email"],
                        "activation_url": self.origin + "/invite#" + payload["invitation_token"],
                        "expires_at": invitation["expires_at"].isoformat(timespec="milliseconds")
                        + "Z",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (OrbitError, ValueError, KeyError, TypeError):
                await self._record(
                    session, row, DeliveryOutcome("FAILED", "INVITATION_PREFLIGHT_REJECTED")
                )
                return row["id"], None
            await session.execute(
                text("""UPDATE orbit_invitation_delivery
                SET status='SENDING',revision=revision+1,claimed_at=UTC_TIMESTAMP(3)
                WHERE id=:id AND tenant_id=:tenant AND revision=:revision"""),
                {"id": row["id"], "tenant": row["tenant_id"], "revision": row["revision"]},
            )
            await append_auth_audit(
                session,
                row["tenant_id"],
                row["created_by"],
                "DELIVERY",
                row["id"],
                "DELIVERY_CLAIMED",
                row["revision"] + 1,
                str(uuid4()),
            )
            return row["id"], DeliveryClaim(
                row["id"],
                row["tenant_id"],
                row["created_by"],
                row["revision"] + 1,
                endpoint,
                body,
                signing,
            )

    async def complete(self, claim, outcome):
        async with self.sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text("""SELECT d.*,i.created_by
                FROM orbit_invitation_delivery d
                JOIN orbit_user_invitation i ON i.id=d.invitation_id
                WHERE d.id=:id AND d.tenant_id=:tenant FOR UPDATE"""),
                        {"id": claim.id, "tenant": claim.tenant},
                    )
                )
                .mappings()
                .first()
            )
            if row is None or row["status"] != "SENDING" or row["revision"] != claim.revision:
                return False
            await self._record(session, row, outcome)
            return True

    async def recover_interrupted(self, limit=100):
        """15秒网络上限之外留足余量；进程丢失回执只能标未知，绝不重新入队。"""
        limit = self._limit(limit)
        async with self.sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        text("""SELECT d.*,i.created_by
                FROM orbit_invitation_delivery d
                JOIN orbit_user_invitation i ON i.id=d.invitation_id
                WHERE d.status='SENDING' AND d.claimed_at<UTC_TIMESTAMP(3)-INTERVAL 60 SECOND
                ORDER BY d.claimed_at,d.id LIMIT :limit FOR UPDATE SKIP LOCKED"""),
                        {"limit": limit},
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                await self._record(session, row, DeliveryOutcome("UNKNOWN", "WORKER_INTERRUPTED"))
            return len(rows)

    async def run_once(self, limit=10):
        limit = self._limit(limit)
        counts = {"claimed": 0, "accepted": 0, "failed": 0, "unknown": 0}
        for _ in range(limit):
            identifier, claim = await self.claim_one()
            if identifier is None:
                break
            counts["claimed"] += 1
            if claim is None:
                counts["failed"] += 1
                continue
            # 单轮不会在进程中重试已发出的邀请；异常中断由后续恢复任务处理。
            outcome = await self.transport.send(
                claim.endpoint, claim.id, claim.body, claim.signing_token
            )
            if await self.complete(claim, outcome):
                counts[outcome.status.lower()] += 1
        return counts
