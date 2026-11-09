"""真实设备监测事务；证书、启动及观察时效均当前核验，永不创建广告命令。"""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid5

from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import bindparam, text

from orbit_api import execution_agent_access as access
from orbit_api.agent_monitor_contract import MAX_SEQ, observed_time, recovery_streak
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import uuid_value


async def one(session, sql, params):
    return (await session.execute(text(sql), params)).mappings().first()


async def many(session, sql, params):
    return (await session.execute(text(sql), params)).mappings().all()


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def stamp(value):
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z") if value else None


async def now_utc(session):
    return utc((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())


def fresh(observed, now):
    delta = (now - observed_time(observed)).total_seconds()
    if not -5 <= delta < 90:
        raise OrbitError(409, "AGENT_OBSERVATION_STALE", "观察已过期或位于未来，请重新采集")


def certificate_metadata(certificate_pem, issuer_ca_pem, tenant_id, agent_id, now=None):
    """运维证书注册边界：验证受控CA签名、CN/SAN/EKU/有效期，不接受自报指纹。"""
    try:
        tenant_id = uuid_value(tenant_id, "/tenant_id")
        agent_id = uuid_value(agent_id, "/agent_id")
        cert = x509.load_pem_x509_certificate(certificate_pem)
        issuer = x509.load_pem_x509_certificate(issuer_ca_pem)
        cert.verify_directly_issued_by(issuer)
        now = now or datetime.now(UTC)
        if not issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError
        if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if (
            len(cn) != 1
            or cn[0].value != agent_id
            or f"urn:orbit:tenant:{tenant_id}"
            not in sans.get_values_for_type(x509.UniformResourceIdentifier)
            or ExtendedKeyUsageOID.CLIENT_AUTH not in eku
            or not issuer.not_valid_before_utc <= now < issuer.not_valid_after_utc
            or not cert.not_valid_before_utc <= now < cert.not_valid_after_utc
        ):
            raise ValueError
        from cryptography.hazmat.primitives import hashes

        return {
            "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "not_before": cert.not_valid_before_utc.replace(tzinfo=None),
            "not_after": cert.not_valid_after_utc.replace(tzinfo=None),
        }
    except Exception:
        raise OrbitError(
            422, "DEVICE_CERTIFICATE_INVALID", "设备证书签名、用途、绑定或有效期无效"
        ) from None


async def register_device_certificate(
    session, certificate_pem, *, issuer_ca_pem, tenant_id, agent_id
):
    """只供部署运维调用，外层负责受控配置及事务；网页不能提交私钥或直接填指纹。"""
    values = certificate_metadata(
        certificate_pem, issuer_ca_pem, tenant_id, agent_id, await now_utc(session)
    )
    current = SimpleNamespace(tenant_id=tenant_id, actor_id=0, subject_id=agent_id)
    await access.clock(session, current, write=True)
    agent = await one(
        session,
        "SELECT state FROM orbit_execution_agent WHERE tenant_id=:tenant AND id=:agent FOR SHARE",
        {"tenant": tenant_id, "agent": agent_id},
    )
    if agent is None or agent["state"] == "REVOKED":
        raise OrbitError(404, "DEVICE_UNAVAILABLE", "设备不存在或已撤销")
    old = await one(
        session,
        "SELECT tenant_id,agent_id,revoked_at FROM "
        "orbit_agent_certificate WHERE "
        "fingerprint_sha256=:fingerprint_sha256 FOR SHARE",
        values,
    )
    if old:
        if (
            old["tenant_id"] != tenant_id
            or old["agent_id"] != agent_id
            or old["revoked_at"] is not None
        ):
            raise OrbitError(409, "DEVICE_CERTIFICATE_CONFLICT", "证书已登记到其他设备或已经撤销")
        return values["fingerprint_sha256"]
    await session.execute(
        text(
            "INSERT INTO "
            "orbit_agent_certificate(fingerprint_sha256,tenant_id,agent_id,not"
            "_before,not_after,created_at) "
            "VALUES(:fingerprint_sha256,:tenant_id,:agent_id,:not_before,:not_"
            "after,UTC_TIMESTAMP(6))"
        ),
        values,
    )
    return values["fingerprint_sha256"]


async def revoke_device_certificate(session, *, tenant_id, agent_id, fingerprint_sha256):
    """受控运维撤销；同一指纹重复撤销保持原时刻，立即阻断新请求及旧身份证明。"""
    import re

    tenant_id = uuid_value(tenant_id, "/tenant_id")
    agent_id = uuid_value(agent_id, "/agent_id")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint_sha256):
        raise OrbitError(422, "DEVICE_CERTIFICATE_INVALID", "证书指纹格式无效")
    current = SimpleNamespace(tenant_id=tenant_id, actor_id=0, subject_id=agent_id)
    await access.clock(session, current, write=True)
    params = {"tenant": tenant_id, "agent": agent_id, "fingerprint": fingerprint_sha256}
    existing = await one(
        session,
        "SELECT revoked_at FROM orbit_agent_certificate WHERE tenant_id=:tenant "
        "AND agent_id=:agent AND fingerprint_sha256=:fingerprint FOR UPDATE",
        params,
    )
    if existing is None:
        raise OrbitError(404, "DEVICE_CERTIFICATE_UNREGISTERED", "该设备证书未登记")
    revoked_at = existing["revoked_at"]
    if revoked_at is None:
        revoked_at = await now_utc(session)
        await session.execute(
            text(
                "UPDATE orbit_agent_certificate SET revoked_at=:now WHERE tenant_id=:tenant "
                "AND agent_id=:agent AND fingerprint_sha256=:fingerprint"
            ),
            params | {"now": utc(revoked_at).replace(tzinfo=None)},
        )
        await session.execute(
            text(
                "UPDATE orbit_execution_agent_clock SET revision=revision+1 WHERE tenant_id=:tenant"
            ),
            params,
        )
    return {"fingerprint_sha256": fingerprint_sha256, "revoked_at": stamp(revoked_at)}


class AgentMonitorStore:
    async def authenticate(self, session, der, *, write=False):
        fingerprint = hashlib.sha256(der).hexdigest()
        probe = await one(
            session,
            "SELECT tenant_id,agent_id FROM orbit_agent_certificate WHERE "
            "fingerprint_sha256=:fingerprint",
            {"fingerprint": fingerprint},
        )
        if probe is None:
            raise OrbitError(401, "DEVICE_CERTIFICATE_UNREGISTERED", "设备证书未登记")
        current = SimpleNamespace(
            tenant_id=probe["tenant_id"], actor_id=0, subject_id=probe["agent_id"]
        )
        await access.clock(session, current, write=write)
        params = {
            "tenant": probe["tenant_id"],
            "agent": probe["agent_id"],
            "fingerprint": fingerprint,
        }
        agent = await one(
            session,
            "SELECT g.state,t.enabled FROM orbit_execution_agent g JOIN "
            "orbit_tenant t ON t.id=g.tenant_id WHERE g.tenant_id=:tenant AND "
            "g.id=:agent FOR SHARE",
            params,
        )
        cert = await one(
            session,
            "SELECT * FROM orbit_agent_certificate WHERE fingerprint_sha256=:fingerprint FOR SHARE",
            params,
        )
        now = await now_utc(session)
        if (
            agent is None
            or not agent["enabled"]
            or agent["state"] == "REVOKED"
            or cert is None
            or cert["tenant_id"] != params["tenant"]
            or cert["agent_id"] != params["agent"]
            or cert["revoked_at"] is not None
            or not utc(cert["not_before"]) <= now < utc(cert["not_after"])
        ):
            raise OrbitError(403, "DEVICE_CERTIFICATE_REVOKED", "设备证书、租户或设备已失效")
        return params, now

    async def head(self, session, p):
        return await one(
            session,
            "SELECT * FROM orbit_agent_monitor_head WHERE tenant_id=:tenant "
            "AND agent_id=:agent FOR UPDATE",
            p,
        )

    def match(self, p, value):
        if value["agent_id"] != p["agent"]:
            raise OrbitError(403, "DEVICE_AGENT_MISMATCH", "证书不属于请求设备")

    def current_report(self, head, value, now):
        if head is None or value["boot_id"] != head["boot_id"]:
            raise OrbitError(409, "AGENT_BOOT_MISMATCH", "启动已变化，请重新读取设备配置")
        if (
            value["seq"] != head["last_seq"]
            or (now - utc(head["received_at"])).total_seconds() >= 90
        ):
            raise OrbitError(409, "AGENT_SEQUENCE_STALE", "上报不属于当前新鲜心跳")
        fresh(value["observed_at"], now)

    async def tick(self, session, p):
        await session.execute(
            text(
                "UPDATE orbit_execution_agent_clock SET revision=revision+1 WHERE tenant_id=:tenant"
            ),
            p,
        )

    async def heartbeat(self, session, der, value, request_id):
        p, now = await self.authenticate(session, der, write=True)
        self.match(p, value)
        p = p | {"boot": value["boot_id"], "seq": value["seq"]}
        head = await self.head(session, p)
        boot = await one(
            session,
            "SELECT retired_at FROM orbit_agent_boot WHERE tenant_id=:tenant "
            "AND agent_id=:agent AND boot_id=:boot FOR SHARE",
            p,
        )
        if boot and boot["retired_at"] is not None:
            raise OrbitError(409, "AGENT_BOOT_RETIRED", "旧启动已永久退役")
        same = head is not None and head["boot_id"] == value["boot_id"]
        if not same and (value["seq"] != 1 or boot is not None):
            raise OrbitError(
                409, "AGENT_BOOT_SEQUENCE_REQUIRED", "新启动必须以未使用boot和序号1登记"
            )
        intent = access.digest(value)
        receipt = await one(
            session,
            "SELECT payload_hash,ack_json FROM orbit_agent_heartbeat_receipt "
            "WHERE tenant_id=:tenant AND agent_id=:agent AND boot_id=:boot "
            "AND seq=:seq FOR SHARE",
            p,
        )
        if receipt:
            if receipt["payload_hash"] != intent:
                raise OrbitError(409, "AGENT_SEQUENCE_CONFLICT", "同序号心跳内容不同")
            return _decode(receipt["ack_json"])
        if same and value["seq"] <= head["last_seq"]:
            raise OrbitError(409, "AGENT_SEQUENCE_STALE", "心跳序号过旧")
        # observed_at仅为证据，客户端时刻不能推进在线；拒明显未来但允许断网历史重复回执。
        if (observed_time(value["observed_at"]) - now).total_seconds() > 5:
            raise OrbitError(422, "AGENT_OBSERVATION_FUTURE", "观察时间位于未来")
        assignments = await many(
            session,
            "SELECT b.profile_external_id,b.account_id FROM "
            "orbit_profile_binding b JOIN orbit_ad_account a ON "
            "a.tenant_id=b.tenant_id AND a.id=b.account_id WHERE "
            "b.tenant_id=:tenant AND b.agent_id=:agent AND b.unbound_at IS "
            "NULL AND a.unbound_at IS NULL AND "
            "a.owner_user_id=b.owner_user_id AND "
            "a.owner_team_id=b.owner_team_id FOR SHARE",
            p,
        )
        allowed = {(r["profile_external_id"], r["account_id"]) for r in assignments}
        for profile in value["profiles"]:
            if profile["id"] != str(uuid5(UUID(p["agent"]), profile["external_profile_id"])) or any(
                (profile["external_profile_id"], a) not in allowed for a in profile["account_ids"]
            ):
                raise OrbitError(
                    422, "PROFILE_SCOPE_INVALID", "Profile标识或账户引用不属于当前设备关联"
                )
            if (observed_time(profile["observed_at"]) - now).total_seconds() > 5:
                raise OrbitError(422, "AGENT_OBSERVATION_FUTURE", "Profile观察时间位于未来")
        if not same:
            if head:
                await session.execute(
                    text(
                        "UPDATE orbit_agent_boot SET retired_at=:now WHERE "
                        "tenant_id=:tenant AND agent_id=:agent AND boot_id=:old_boot"
                    ),
                    p | {"now": now.replace(tzinfo=None), "old_boot": head["boot_id"]},
                )
            await session.execute(
                text(
                    "INSERT INTO "
                    "orbit_agent_boot(tenant_id,agent_id,boot_id,created_at) "
                    "VALUES(:tenant,:agent,:boot,:now)"
                ),
                p | {"now": now.replace(tzinfo=None)},
            )
        streak = recovery_streak(
            head["last_seq"] if same else None,
            value["seq"],
            (now - utc(head["received_at"])).total_seconds() if same else 0,
            head["recovery_streak"] if same else 0,
        )
        revision = (head["revision"] if head else 0) + 1
        if revision > MAX_SEQ:
            raise OrbitError(409, "REVISION_EXHAUSTED", "设备监测版本耗尽")
        state = "READY" if streak == 2 else "SUSPECT"
        ack = {"id": p["agent"], "revision": revision, "state": state, "request_id": request_id}
        params = p | {
            "now": now.replace(tzinfo=None),
            "streak": streak,
            "revision": revision,
            "hash": intent,
            "ack": canonical(ack),
            "state": state,
        }
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_agent_heartbeat_receipt(tenant_id,agent_id,boot_id,seq,payl"
                "oad_hash,ack_json,received_at) "
                "VALUES(:tenant,:agent,:boot,:seq,:hash,:ack,:now)"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_agent_monitor_head(tenant_id,agent_id,boot_id,last_seq,reco"
                "very_streak,revision,received_at) "
                "VALUES(:tenant,:agent,:boot,:seq,:streak,:revision,:now) ON "
                "DUPLICATE KEY UPDATE "
                "boot_id=:boot,last_seq=:seq,recovery_streak=:streak,revision=:rev"
                "ision,received_at=:now,diagnostic_seq=NULL,diagnostic_hash=NULL,d"
                "iagnostic_json=NULL,diagnostic_ack=NULL,diagnostic_received_at=NU"
                "LL"
            ),
            params,
        )
        await session.execute(
            text(
                "UPDATE orbit_execution_agent SET "
                "state=:state,last_heartbeat=:now WHERE tenant_id=:tenant AND "
                "id=:agent"
            ),
            params,
        )
        for profile in value["profiles"]:
            await session.execute(
                text(
                    "INSERT INTO "
                    "orbit_agent_profile_observation(tenant_id,agent_id,id,external_pr"
                    "ofile_id,boot_id,seq,process_state,observed_at,received_at) "
                    "VALUES(:tenant,:agent,:id,:external_profile_id,:boot,:seq,:proces"
                    "s_state,:observed,:now) ON DUPLICATE KEY UPDATE "
                    "boot_id=:boot,seq=:seq,process_state=:process_state,observed_at=:"
                    "observed,received_at=:now"
                ),
                params
                | profile
                | {
                    "observed": observed_time(profile["observed_at"])
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                },
            )
        await self.tick(session, p)
        return ack

    async def configuration(self, session, der):
        p, _ = await self.authenticate(session, der)
        rows = await many(
            session,
            "SELECT "
            "b.id,b.revision,b.account_id,b.profile_external_id,a.external_id "
            "AS external_account_id,a.currency FROM orbit_profile_binding b "
            "JOIN orbit_ad_account a ON a.tenant_id=b.tenant_id AND "
            "a.id=b.account_id WHERE b.tenant_id=:tenant AND "
            "b.agent_id=:agent AND b.unbound_at IS NULL AND a.unbound_at IS "
            "NULL AND b.owner_user_id=a.owner_user_id AND "
            "b.owner_team_id=a.owner_team_id ORDER BY b.id LIMIT 5001 FOR "
            "SHARE",
            p,
        )
        if len(rows) > 5000:
            raise OrbitError(
                503, "AGENT_CONFIGURATION_LIMIT", "设备关联超过单次安全读取上限，需要分页扩展"
            )
        return {"agent_id": p["agent"], "bindings": [dict(r) for r in rows]}

    async def diagnostics(self, session, der, value, request_id):
        p, now = await self.authenticate(session, der, write=True)
        self.match(p, value)
        head = await self.head(session, p)
        self.current_report(head, value, now)
        intent = access.digest(value)
        if head["diagnostic_seq"] == value["seq"]:
            if head["diagnostic_hash"] != intent:
                raise OrbitError(409, "AGENT_SEQUENCE_CONFLICT", "诊断序号已用于不同内容")
            return _decode(head["diagnostic_ack"])
        ack = {
            "id": p["agent"],
            "revision": head["revision"],
            "state": "DIAGNOSTICS_ACCEPTED",
            "request_id": request_id,
        }
        await session.execute(
            text(
                "UPDATE orbit_agent_monitor_head SET "
                "diagnostic_seq=:seq,diagnostic_hash=:hash,diagnostic_json=:value,"
                "diagnostic_ack=:ack,diagnostic_received_at=:now WHERE "
                "tenant_id=:tenant AND agent_id=:agent"
            ),
            p
            | {
                "seq": value["seq"],
                "hash": intent,
                "value": canonical(value),
                "ack": canonical(ack),
                "now": now.replace(tzinfo=None),
            },
        )
        await self.tick(session, p)
        return ack

    async def identity_report(self, session, der, value, request_id):
        p, now = await self.authenticate(session, der, write=True)
        self.match(p, value)
        head = await self.head(session, p)
        self.current_report(head, value, now)
        if head["recovery_streak"] < 2:
            raise OrbitError(409, "AGENT_RECOVERY_REQUIRED", "设备尚未完成两次连续心跳恢复")
        rows = await many(
            session,
            "SELECT b.*,a.external_id,a.currency,a.owner_user_id AS "
            "current_owner,a.owner_team_id AS current_team,a.unbound_at AS "
            "account_unbound FROM orbit_profile_binding b JOIN "
            "orbit_ad_account a ON a.tenant_id=b.tenant_id AND "
            "a.id=b.account_id WHERE b.tenant_id=:tenant AND b.id=:binding "
            "FOR SHARE",
            p | {"binding": value["binding_id"]},
        )
        if not rows:
            raise OrbitError(404, "PROFILE_BINDING_UNAVAILABLE", "绑定不存在")
        b = rows[0]
        if (
            b["agent_id"] != p["agent"]
            or b["unbound_at"] is not None
            or b["account_unbound"] is not None
            or b["owner_user_id"] != b["current_owner"]
            or b["owner_team_id"] != b["current_team"]
        ):
            raise OrbitError(404, "PROFILE_BINDING_UNAVAILABLE", "绑定或当前账户归属已失效")
        if (
            b["revision"] != value["binding_revision"]
            or b["profile_external_id"] != value["profile_external_id"]
        ):
            raise OrbitError(409, "PROFILE_BINDING_CHANGED", "绑定版本或Profile已变化")
        if value["identity_state"] == "VALID" and (
            value["external_account_id"] != b["external_id"] or value["currency"] != b["currency"]
        ):
            raise OrbitError(422, "IDENTITY_MISMATCH", "实际平台账户或币种不匹配")
        old = await one(
            session,
            "SELECT payload_hash,ack_json FROM orbit_agent_identity_report "
            "WHERE tenant_id=:tenant AND agent_id=:agent AND event_id=:event FOR SHARE",
            p | {"event": value["event_id"]},
        )
        intent = access.digest(value)
        if old:
            if old["payload_hash"] != intent:
                raise OrbitError(409, "IDENTITY_EVENT_CONFLICT", "身份事件ID已用于不同内容")
            return _decode(old["ack_json"])
        latest = await one(
            session,
            "SELECT r.observed_at FROM orbit_agent_identity_head ih JOIN "
            "orbit_agent_identity_report r ON r.tenant_id=ih.tenant_id AND "
            "r.agent_id=ih.agent_id AND r.event_id=ih.event_id WHERE "
            "ih.tenant_id=:tenant AND ih.binding_id=:binding FOR SHARE",
            p | {"binding": value["binding_id"]},
        )
        if latest and observed_time(value["observed_at"]) < utc(latest["observed_at"]):
            raise OrbitError(409, "AGENT_OBSERVATION_STALE", "身份报告不能回写更旧观察")
        ack = {
            "id": p["agent"],
            "revision": head["revision"],
            "state": "IDENTITY_RECORDED",
            "request_id": request_id,
        }
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_agent_identity_report(tenant_id,agent_id,event_id,boot_id,s"
                "eq,binding_id,binding_revision,profile_external_id,external_accou"
                "nt_id,currency,identity_state,adapter_version,evidence_sha256,fin"
                "gerprint_sha256,observed_at,received_at,payload_hash,ack_json) "
                "VALUES(:tenant,:agent,:event_id,:boot_id,:seq,:binding_id,:bindin"
                "g_revision,:profile_external_id,:external_account_id,:currency,:i"
                "dentity_state,:adapter_version,:evidence_sha256,:fingerprint,:obs"
                "erved,:now,:hash,:ack)"
            ),
            p
            | value
            | {
                "observed": observed_time(value["observed_at"])
                .astimezone(UTC)
                .replace(tzinfo=None),
                "now": now.replace(tzinfo=None),
                "hash": intent,
                "ack": canonical(ack),
            },
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_agent_identity_head(tenant_id,binding_id,agent_id,event_id)"
                " VALUES(:tenant,:binding_id,:agent,:event_id) ON DUPLICATE KEY "
                "UPDATE agent_id=:agent,event_id=:event_id"
            ),
            p | value,
        )
        await self.tick(session, p)
        return ack


async def batch_binding_identities(session, tenant_id, bindings):
    """有界单次当前锁读；绑定失配、证书撤销、重启或90秒过期均派生UNKNOWN。"""
    if len(bindings) > 200:
        raise ValueError("身份批量读取最多200条")
    result = {b["id"]: {"identity_state": "UNKNOWN", "verified_at": None} for b in bindings}
    if not result:
        return result
    query = text("""SELECT b.id,r.identity_state,r.received_at FROM orbit_profile_binding b
        JOIN orbit_ad_account a ON a.tenant_id=b.tenant_id AND a.id=b.account_id
        JOIN orbit_execution_agent g ON g.tenant_id=b.tenant_id AND g.id=b.agent_id
        JOIN orbit_agent_monitor_head h ON h.tenant_id=g.tenant_id AND h.agent_id=g.id
        JOIN orbit_agent_identity_head ih ON ih.tenant_id=b.tenant_id AND ih.binding_id=b.id
        JOIN orbit_agent_identity_report r ON r.tenant_id=ih.tenant_id AND r.agent_id=ih.agent_id
        AND r.event_id=ih.event_id
        JOIN orbit_agent_certificate c ON c.fingerprint_sha256=r.fingerprint_sha256
        WHERE b.tenant_id=:tenant AND b.id IN :ids AND b.unbound_at IS NULL AND a.unbound_at IS NULL
        AND b.owner_user_id=a.owner_user_id AND b.owner_team_id=a.owner_team_id
        AND r.agent_id=b.agent_id AND r.binding_revision=b.revision
        AND r.profile_external_id=b.profile_external_id
        AND c.tenant_id=b.tenant_id AND c.agent_id=b.agent_id AND c.revoked_at IS NULL
        AND c.not_before<=UTC_TIMESTAMP(6) AND c.not_after>UTC_TIMESTAMP(6)
        AND r.boot_id=h.boot_id AND r.seq<=h.last_seq AND h.recovery_streak=2
        AND g.state='READY' AND h.received_at>UTC_TIMESTAMP(6)-INTERVAL 90 SECOND
        AND r.received_at>UTC_TIMESTAMP(6)-INTERVAL 90 SECOND
        AND r.observed_at>UTC_TIMESTAMP(6)-INTERVAL 90 SECOND
        AND (r.identity_state<>'VALID' OR (r.adapter_version='ADSPOWER_META_DOM_V2'
        AND r.external_account_id=a.external_id
        AND r.currency=a.currency))
        FOR SHARE""").bindparams(bindparam("ids", expanding=True))
    rows = (
        (await session.execute(query, {"tenant": tenant_id, "ids": sorted(result)}))
        .mappings()
        .all()
    )
    for row in rows:
        result[row["id"]] = {
            "identity_state": row["identity_state"],
            "verified_at": stamp(row["received_at"])
            if row["identity_state"] != "UNKNOWN"
            else None,
        }
    return result


async def read_monitor(session, actor, agent_id):
    from orbit_api.execution_agent_contract import heartbeat_state
    from orbit_api.execution_agent_store import ExecutionAgentStore

    current = await access.context(session, actor, "environments.read")
    await access.clock(session, current)
    agent = await ExecutionAgentStore(None).row(session, current, agent_id)
    now = await now_utc(session)
    state = heartbeat_state(
        revoked=agent["state"] == "REVOKED",
        received_at=utc(agent["last_heartbeat"]) if agent["last_heartbeat"] else None,
        now=now,
    )
    if state == "READY" and agent["state"] == "SUSPECT":
        state = "SUSPECT"
    head = await one(
        session,
        "SELECT * FROM orbit_agent_monitor_head WHERE tenant_id=:tenant "
        "AND agent_id=:agent FOR SHARE",
        {"tenant": current.tenant_id, "agent": agent_id},
    )
    valid = (
        head
        and state != "REVOKED"
        and head["diagnostic_json"] is not None
        and (now - utc(head["diagnostic_received_at"])).total_seconds() < 90
        and (now - utc(head["received_at"])).total_seconds() < 90
    )
    diagnostic = _decode(head["diagnostic_json"]) if valid else {}
    return {
        "agent_id": agent_id,
        "machine_state": state,
        "last_heartbeat": stamp(agent["last_heartbeat"]),
        "api_status": diagnostic.get("api_status", "UNKNOWN"),
        "inventory_coverage": diagnostic.get("inventory_coverage", "UNAVAILABLE"),
        "last_error": diagnostic.get("error_code"),
        "received_at": stamp(head["diagnostic_received_at"]) if valid else None,
    }


async def list_profiles(session, actor, agent_id, filters, cursor, tokens):
    """只返回当前可见绑定Profile；账户列表来自服务端关联，不信设备提供的account_ids。"""
    from orbit_api.execution_agent_store import ExecutionAgentStore
    from orbit_api.profile_binding_access import fingerprint

    current = await access.context(session, actor, "environments.read")
    revision = await access.clock(session, current)
    await ExecutionAgentStore(tokens).row(session, current, agent_id)
    for field in (
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    ):
        if field in filters:
            raise OrbitError(
                503,
                "ENVIRONMENT_FILTER_DEPENDENCY_UNAVAILABLE",
                "Profile关联筛选尚未接通",
                "/" + field,
            )
    size = filters.get("page_size", 50)
    binding = access.digest(
        [await fingerprint(session, current, revision, size), agent_id, filters]
    )
    after = ""
    as_of = stamp(await now_utc(session))
    if cursor:
        claims = tokens.verify("AGENT_PROFILE_CURSOR_V1", cursor)
        if claims.get("binding") != binding:
            raise OrbitError(409, "SCOPE_CHANGED", "设备观察或账户范围已变化")
        after = uuid_value(claims.get("after"), "/cursor")
        as_of = claims["data_as_of"]
    p = access.parameters(current) | {"agent": agent_id, "after": after, "limit": size + 1}
    where = ["p.tenant_id=:tenant", "p.agent_id=:agent", "p.id>:after"]
    current_scope = access.account_access.visible_clause(current, "a").replace(
        "AND tm.enabled=1)", "AND tm.enabled=1 FOR SHARE)"
    )
    scope = (
        "b.unbound_at IS NULL AND a.unbound_at IS NULL AND "
        "b.owner_user_id=a.owner_user_id AND "
        "b.owner_team_id=a.owner_team_id AND (" + current_scope + ")"
    )
    if current.data_role != "SUPER_ADMIN":
        where.append(
            "EXISTS(SELECT 1 FROM orbit_profile_binding b JOIN "
            "orbit_ad_account a ON a.tenant_id=b.tenant_id AND "
            "a.id=b.account_id WHERE b.tenant_id=p.tenant_id AND "
            "b.agent_id=p.agent_id AND "
            "b.profile_external_id=p.external_profile_id AND " + scope + " FOR SHARE)"
        )
    if filters.get("q"):
        where.append("LOCATE(:q,p.external_profile_id)>0")
        p["q"] = filters["q"]
    effective = (
        "CASE WHEN g.state='REVOKED' OR p.boot_id<>h.boot_id OR "
        "p.received_at<=UTC_TIMESTAMP(6)-INTERVAL 90 SECOND OR "
        "p.observed_at<=UTC_TIMESTAMP(6)-INTERVAL 90 SECOND OR "
        "h.received_at<=UTC_TIMESTAMP(6)-INTERVAL 90 SECOND THEN "
        "'UNKNOWN' ELSE p.process_state END"
    )
    if filters.get("status"):
        where.append("(" + effective + ")=:status")
        p["status"] = filters["status"]
    rows = await many(
        session,
        "SELECT p.*," + effective + " AS effective_process FROM orbit_agent_profile_observation p "
        "JOIN orbit_agent_monitor_head h ON h.tenant_id=p.tenant_id AND "
        "h.agent_id=p.agent_id JOIN orbit_execution_agent g ON "
        "g.tenant_id=p.tenant_id AND g.id=p.agent_id WHERE "
        + " AND ".join(where)
        + " ORDER BY p.id LIMIT :limit FOR SHARE",
        p,
    )
    page = rows[:size]
    items = []
    # 每页一次批量关联查询；身份证明再按200绑定一批读取，Profile原上限账户500。
    if page:
        query = text(
            "SELECT b.* FROM orbit_profile_binding b JOIN orbit_ad_account a "
            "ON a.tenant_id=b.tenant_id AND a.id=b.account_id WHERE "
            "b.tenant_id=:tenant AND b.agent_id=:agent AND "
            "b.profile_external_id IN :external AND "
            + scope
            + " ORDER BY b.id LIMIT :binding_limit FOR SHARE"
        ).bindparams(bindparam("external", expanding=True))
        bindings = (
            (
                await session.execute(
                    query,
                    p
                    | {
                        "external": [r["external_profile_id"] for r in page],
                        "binding_limit": len(page) * 500 + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        from collections import Counter

        counts = Counter(b["profile_external_id"] for b in bindings)
        if len(bindings) > len(page) * 500 or any(count > 500 for count in counts.values()):
            raise OrbitError(503, "PROFILE_ACCOUNT_LIMIT", "Profile关联超过原合同500账户限制")
        identities = {}
        for start in range(0, len(bindings), 200):
            identities.update(
                await batch_binding_identities(
                    session, current.tenant_id, bindings[start : start + 200]
                )
            )
        for row in page:
            selected = [
                b for b in bindings if b["profile_external_id"] == row["external_profile_id"]
            ]
            accounts = sorted({b["account_id"] for b in selected})
            if len(accounts) > 500:
                raise OrbitError(503, "PROFILE_ACCOUNT_LIMIT", "单Profile关联超过原合同500账户限制")
            states = {identities[b["id"]]["identity_state"] for b in selected}
            identity = (
                "VALID"
                if states == {"VALID"}
                else next(
                    (
                        s
                        for s in ("CHALLENGE", "LOGIN_REQUIRED", "IDENTITY_MISMATCH", "UNKNOWN")
                        if s in states
                    ),
                    "UNKNOWN",
                )
            )
            items.append(
                {
                    "id": row["id"],
                    "agent_id": agent_id,
                    "external_profile_id": row["external_profile_id"],
                    "process_state": row["effective_process"],
                    "identity_state": identity,
                    "account_ids": accounts,
                    "observed_at": stamp(row["observed_at"]),
                }
            )
    token = (
        tokens.issue(
            "AGENT_PROFILE_CURSOR_V1",
            {"binding": binding, "after": page[-1]["id"], "data_as_of": as_of},
        )
        if len(rows) > size
        else None
    )
    return {"items": items, "next_cursor": token, "data_as_of": as_of, "scope_version": revision}
