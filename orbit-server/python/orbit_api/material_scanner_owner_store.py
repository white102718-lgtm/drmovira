"""仅供显式可信所有者调用的全局运维审计；没有HTTP、租户权限或进程I/O。"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from orbit_api.errors import OrbitError

FIELDS = frozenset(
    {
        "event_id",
        "profile_id",
        "definition_revision",
        "instance_id",
        "action",
        "source_sha256",
        "executable_sha256",
        "config_sha256",
        "release_receipt_sha256",
        "occurred_at",
    }
)
SOURCE_FIELDS = ("source_sha256", "executable_sha256", "config_sha256", "release_receipt_sha256")
SEQUENCES = {"STARTING": 1, "STARTED": 2, "STOPPED": 3, "INVALIDATED": 3}


def _reject(code="SCANNER_OWNER_AUDIT_INVALID"):
    return OrbitError(503, code, "受控扫描运维审计未能完整持久化")


def validate_owner_event(event):
    """精确十字段白名单；拒绝把连接信息、路径、凭据或请求原文混入审计。"""
    try:
        if not isinstance(event, dict) or set(event) != FIELDS:
            raise ValueError
        values = dict(event)
        for field in ("event_id", "instance_id"):
            if not isinstance(values[field], str) or str(UUID(values[field])) != values[field]:
                raise ValueError
        if not isinstance(values["profile_id"], str) or not re.fullmatch(
            r"[a-z0-9_-]{1,40}", values["profile_id"]
        ):
            raise ValueError
        version = values["definition_revision"]
        if type(version) is not int or not 1 <= version <= 9_007_199_254_740_991:
            raise ValueError
        if not isinstance(values["action"], str) or values["action"] not in SEQUENCES:
            raise ValueError
        for field in SOURCE_FIELDS:
            if not isinstance(values[field], str) or not re.fullmatch(
                r"[0-9a-f]{64}", values[field]
            ):
                raise ValueError
        raw = values["occurred_at"]
        if not isinstance(raw, str) or len(raw) > 40:
            raise ValueError
        occurred = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if occurred.tzinfo is None or occurred.utcoffset() != timedelta(0):
            raise ValueError
        values["occurred_at"] = occurred.astimezone(UTC).isoformat().replace("+00:00", "Z")
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            **values,
            "occurred_at": occurred.replace(tzinfo=None),
            "payload_sha256": digest,
            "sequence_no": SEQUENCES[values["action"]],
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _reject() from None


@dataclass(frozen=True)
class StoredOwnerEvent:
    event_id: str
    sequence_no: int
    replayed: bool


async def _one(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().one_or_none()


async def append_owner_event(session, event):
    """外层事务提交实例阶段+审计+outbox；只做SQL，严禁从此调用进程或provider。"""
    if not session.in_transaction():
        raise RuntimeError("扫描所有者审计需要显式事务")
    values = validate_owner_event(event)
    now = (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one()
    if values["occurred_at"] > now + timedelta(seconds=5):
        raise _reject()
    await session.execute(
        text("""INSERT INTO orbit_scanner_owner_instance
      (profile_id,definition_revision,instance_id,source_sha256,executable_sha256,config_sha256,
       release_receipt_sha256,state,sequence_no,last_occurred_at)
      SELECT :profile_id,:definition_revision,:instance_id,:source_sha256,:executable_sha256,
       :config_sha256,:release_receipt_sha256,'STARTING',1,:occurred_at
      WHERE :action='STARTING'
      ON DUPLICATE KEY UPDATE instance_id=instance_id"""),
        values,
    )
    head = await _one(
        session,
        """SELECT * FROM orbit_scanner_owner_instance
      WHERE profile_id=:profile_id AND definition_revision=:definition_revision
      AND instance_id=:instance_id FOR UPDATE""",
        values,
    )
    if head is None or any(head[field] != values[field] for field in SOURCE_FIELDS):
        raise _reject("SCANNER_OWNER_AUDIT_SOURCE_CHANGED")
    existing = await _one(
        session,
        """SELECT payload_sha256,sequence_no FROM orbit_scanner_owner_audit
      WHERE event_id=:event_id""",
        values,
    )
    if existing is not None:
        if existing["payload_sha256"] != values["payload_sha256"]:
            raise _reject("SCANNER_OWNER_AUDIT_CONFLICT")
        return StoredOwnerEvent(values["event_id"], existing["sequence_no"], True)
    prior = await _one(
        session,
        """SELECT event_id FROM orbit_scanner_owner_audit
      WHERE profile_id=:profile_id AND definition_revision=:definition_revision
      AND instance_id=:instance_id AND action=:action""",
        values,
    )
    if prior is not None:
        raise _reject("SCANNER_OWNER_AUDIT_CONFLICT")
    expected = {
        "STARTING": "STARTING",
        "STARTED": "STARTING",
        "STOPPED": "STARTED",
        "INVALIDATED": "STARTED",
    }
    if (
        head["state"] != expected[values["action"]]
        or (values["action"] != "STARTING" and head["sequence_no"] + 1 != values["sequence_no"])
        or values["occurred_at"] < head["last_occurred_at"]
    ):
        raise _reject("SCANNER_OWNER_AUDIT_SEQUENCE_INVALID")
    await session.execute(
        text("""INSERT INTO orbit_scanner_owner_audit
      (event_id,profile_id,definition_revision,instance_id,sequence_no,action,source_sha256,
       executable_sha256,config_sha256,release_receipt_sha256,payload_sha256,occurred_at)
      VALUES(:event_id,:profile_id,:definition_revision,:instance_id,:sequence_no,:action,
       :source_sha256,:executable_sha256,:config_sha256,:release_receipt_sha256,
       :payload_sha256,:occurred_at)"""),
        values,
    )
    await session.execute(
        text("""INSERT INTO orbit_scanner_owner_outbox(event_id)
      VALUES(:event_id)"""),
        values,
    )
    await session.execute(
        text("""UPDATE orbit_scanner_owner_instance
      SET state=:action,sequence_no=:sequence_no,last_occurred_at=:occurred_at
      WHERE profile_id=:profile_id AND definition_revision=:definition_revision
      AND instance_id=:instance_id"""),
        values,
    )
    return StoredOwnerEvent(values["event_id"], values["sequence_no"], False)


def create_owner_audit_sink(sessions, *, timeout_seconds=5):
    """短独占事务sink；commit完成才返回，失败/超时传播给owner阻止publish。"""
    if not callable(sessions) or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise ValueError("所有者审计需要显式session工厂与有界超时")

    async def persist(event):
        try:
            async with asyncio.timeout(timeout_seconds):
                async with sessions() as session, session.begin():
                    result = await append_owner_event(session, event)
                return result
        except asyncio.CancelledError:
            raise
        except Exception:
            raise _reject("SCANNER_OWNER_AUDIT_UNAVAILABLE") from None

    return persist


async def read_owner_events(
    session, profile_id, definition_revision, instance_id, *, after_sequence=0, limit=100
):
    """可信内部运维读取；实例唯一键加顺序水位，最多200，不能作为用户权限绕过入口。"""
    probe = {
        "event_id": instance_id,
        "profile_id": profile_id,
        "definition_revision": definition_revision,
        "instance_id": instance_id,
        "action": "STARTING",
        "occurred_at": datetime.now(UTC).isoformat(),
        **{field: "0" * 64 for field in SOURCE_FIELDS},
    }
    values = validate_owner_event(probe)
    if (
        type(after_sequence) is not int
        or not 0 <= after_sequence <= 3
        or type(limit) is not int
        or not 1 <= limit <= 200
    ):
        raise ValueError("运维事件读取水位或数量无效")
    result = await session.execute(
        text("""SELECT event_id,profile_id,definition_revision,instance_id,
      sequence_no,action,source_sha256,executable_sha256,config_sha256,release_receipt_sha256,
      occurred_at,created_at FROM orbit_scanner_owner_audit
      WHERE profile_id=:profile_id AND definition_revision=:definition_revision
      AND instance_id=:instance_id AND sequence_no>:after_sequence
      ORDER BY sequence_no LIMIT :limit"""),
        {**values, "after_sequence": after_sequence, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]
