"""030实例证明持久层；由外层事务负责提交，不修改素材状态或补票旧收据。"""

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus_runtime import (
    RuntimeScanProof,
    RuntimeScanResult,
    TrustedRuntimeProfile,
)
from orbit_api.material_job_policy import validate_job_actor

_NAMESPACE = UUID("fdf952d9-86fc-4a04-9846-85556560901e")
_SHA = re.compile(r"[0-9a-f]{64}")


def _reject(code="MATERIAL_RUNTIME_PROOF_INVALID"):
    return OrbitError(409, code, "素材扫描实例证明不完整、过期或与当前任务不符")


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError
    return value


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError
    return value.astimezone(UTC)


def _sql_time(value):
    value = _time(value)
    return value.replace(microsecond=value.microsecond // 1000 * 1000, tzinfo=None)


def validate_runtime_binding(claim, result, profile, now):
    """纯业务校验不访问OS；profile须由服务端当前可信消费者提供，不能来自请求。"""
    try:
        if not isinstance(result, RuntimeScanResult) or not isinstance(
            profile, TrustedRuntimeProfile
        ):
            raise ValueError
        proof, receipt = result.proof, result.receipt
        if not isinstance(proof, RuntimeScanProof):
            raise ValueError
        for key in ("tenant_id", "asset_id", "claim_id", "owner_user_id", "owner_team_id"):
            _uuid(claim[key])
        for key in ("actor_id", "actor_auth_version", "revision", "byte_size"):
            if type(claim[key]) is not int or not 1 <= claim[key] <= 9_007_199_254_740_991:
                raise ValueError
        if not 1 <= claim["byte_size"] <= 500 * 1024**2:
            raise ValueError
        for key in ("sha256", "scope_digest"):
            if not isinstance(claim[key], str) or not _SHA.fullmatch(claim[key]):
                raise ValueError
        if receipt.result not in {"CLEAN", "INFECTED", "UNVERIFIED"}:
            raise ValueError
        if receipt.sha256 != claim["sha256"] or receipt.byte_size != claim["byte_size"]:
            raise ValueError
        expected = {
            "profile_id": profile.profile_id,
            "profile_revision": profile.revision,
            "instance_id": profile.instance_id,
            "profile_sha256": profile.profile_sha256,
            "source_sha256": profile.source_sha256,
            "executable_sha256": profile.executable_sha256,
            "config_sha256": profile.policy.config_sha256,
            "created_at_us": profile.created_at_us,
            "issued_at": profile.issued_at,
            "expires_at": profile.expires_at,
        }
        actual = asdict(proof)
        if any(
            actual[key] != value or type(actual[key]) is not type(value)
            for key, value in expected.items()
        ):
            raise ValueError
        before, after = _time(proof.verified_before), _time(proof.verified_after)
        start, end, current = _time(receipt.started_at), _time(receipt.completed_at), _time(now)
        if not profile.issued_at <= before <= start <= end <= after <= current < profile.expires_at:
            raise ValueError
        if not 0 <= (after - before).total_seconds() <= profile.policy.deadline_seconds:
            raise ValueError
        if receipt.policy_sha256 != profile.policy.config_sha256:
            raise ValueError
        if receipt.result in {"CLEAN", "INFECTED"} and (
            receipt.engine_version != profile.policy.engine_version
            or type(receipt.database_version) is not int
            or receipt.database_version != profile.policy.daily_db_version
            or receipt.database_built_at != profile.policy.daily_db_built_at
        ):
            raise ValueError
        if receipt.result == "CLEAN" and receipt.error_code is not None:
            raise ValueError
        if receipt.result == "INFECTED" and receipt.error_code != "ANTIVIRUS_INFECTED":
            raise ValueError
        if receipt.result == "UNVERIFIED" and (
            not isinstance(receipt.error_code, str)
            or not re.fullmatch(r"ANTIVIRUS_[A-Z_]{1,38}", receipt.error_code)
        ):
            raise ValueError
        profile.policy.validate(current)
        return proof, receipt
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OrbitError):
        raise _reject() from None


@dataclass(frozen=True)
class StoredRuntimeScan:
    receipt_id: str
    event_id: str
    replayed: bool


async def _one(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().one_or_none()


async def append_runtime_scan(session, claim, result, profile, *, selection=None):
    """先身份→clock→job→asset；纯追加原子收据/证明/审计/outbox，不负责状态迁移。"""
    if not session.in_transaction():
        raise RuntimeError("实例证明登记需要调用方显式事务")
    now = (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one().replace(tzinfo=UTC)
    proof, receipt = validate_runtime_binding(claim, result, profile, now)
    if not await validate_job_actor(session, claim):
        raise _reject("AUTHORIZATION_CHANGED")
    if selection is not None:
        from orbit_api.material_scanner_selection import verify_selection

        await verify_selection(session, selection, claim, profile)
    values = {**claim}
    clock = await _one(
        session,
        "SELECT revision FROM orbit_material_clock WHERE tenant_id=:tenant_id FOR UPDATE",
        values,
    )
    if clock is None or clock["revision"] >= 9_007_199_254_740_991:
        raise _reject("REVISION_EXHAUSTED")
    job = await _one(
        session,
        """SELECT state,claim_id,actor_id,actor_auth_version,scope_digest,claimed_at,
        claimed_at>=UTC_TIMESTAMP(3)-INTERVAL 5 MINUTE AS lease_valid
        FROM orbit_material_job WHERE tenant_id=:tenant_id AND asset_id=:asset_id FOR UPDATE""",
        values,
    )
    asset = await _one(
        session,
        """SELECT state,revision,sha256,byte_size,owner_user_id,owner_team_id,
        physical_cleanup_state FROM orbit_material_asset
        WHERE tenant_id=:tenant_id AND id=:asset_id FOR UPDATE""",
        values,
    )
    if (
        job is None
        or asset is None
        or job["claim_id"] != claim["claim_id"]
        or any(job[key] != claim[key] for key in ("actor_id", "actor_auth_version", "scope_digest"))
        or any(
            asset[key] != claim[key]
            for key in ("sha256", "byte_size", "owner_user_id", "owner_team_id")
        )
    ):
        raise _reject("MATERIAL_SCAN_STALE")
    if asset["physical_cleanup_state"] != "LIVE" or asset["state"] == "ARCHIVED":
        raise _reject("MATERIAL_SCAN_STALE")
    identifier = str(
        uuid5(_NAMESPACE, canonical([claim["tenant_id"], claim["asset_id"], claim["claim_id"]]))
    )
    event = str(uuid5(_NAMESPACE, "runtime-event:" + identifier))
    receipt_values = {
        "tenant_id": claim["tenant_id"],
        "asset_id": claim["asset_id"],
        "claim_id": claim["claim_id"],
        "id": identifier,
        "result": receipt.result,
        "sha256": receipt.sha256,
        "byte_size": receipt.byte_size,
        "engine_version": receipt.engine_version,
        "database_version": receipt.database_version,
        "database_built_at": _sql_time(receipt.database_built_at)
        if receipt.database_built_at
        else None,
        "policy_sha256": receipt.policy_sha256,
        "started_at": _sql_time(receipt.started_at),
        "completed_at": _sql_time(receipt.completed_at),
        "error_code": receipt.error_code,
    }
    proof_values = {
        "tenant_id": claim["tenant_id"],
        "asset_id": claim["asset_id"],
        "receipt_id": identifier,
        "claim_id": claim["claim_id"],
        "profile_id": proof.profile_id,
        "profile_revision": proof.profile_revision,
        "instance_id": proof.instance_id,
        "profile_sha256": proof.profile_sha256,
        "source_sha256": proof.source_sha256,
        "executable_sha256": proof.executable_sha256,
        "config_sha256": proof.config_sha256,
        "process_created_at_us": proof.created_at_us,
        "issued_at": _sql_time(proof.issued_at),
        "expires_at": _sql_time(proof.expires_at),
        "verified_before": _sql_time(proof.verified_before),
        "verified_after": _sql_time(proof.verified_after),
    }
    if selection is not None:
        proof_values.update(
            configuration_id=selection.configuration_id,
            configuration_revision=selection.configuration_revision,
        )
    # 锁等待可能跨过证明到期，不能用进入事务前的旧时间放行。
    current = (
        (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one().replace(tzinfo=UTC)
    )
    validate_runtime_binding(claim, result, profile, current)
    old = await _one(
        session,
        """SELECT * FROM orbit_material_scan_receipt
        WHERE tenant_id=:tenant_id AND asset_id=:asset_id AND claim_id=:claim_id FOR UPDATE""",
        values,
    )
    if old is not None:
        bound = await _one(
            session,
            """SELECT * FROM orbit_material_scan_runtime_proof
            WHERE tenant_id=:tenant_id AND asset_id=:asset_id AND claim_id=:claim_id FOR UPDATE""",
            values,
        )
        if bound is None:
            raise _reject("MATERIAL_RUNTIME_PROOF_REQUIRED")
        if any(old[key] != value for key, value in receipt_values.items()) or any(
            bound[key] != value for key, value in proof_values.items()
        ):
            raise _reject("MATERIAL_RUNTIME_SCAN_CONFLICT")
        return StoredRuntimeScan(identifier, event, True)
    if (
        job["state"] != "RUNNING"
        or not job["lease_valid"]
        or job["claimed_at"] is None
        or job["claimed_at"].replace(tzinfo=UTC) < current - timedelta(minutes=5)
        or asset["state"] != "SCANNING"
        or asset["revision"] != claim["revision"]
        or asset["physical_cleanup_state"] != "LIVE"
    ):
        raise _reject("MATERIAL_SCAN_STALE")
    for table, payload in (
        ("orbit_material_scan_receipt", receipt_values),
        ("orbit_material_scan_runtime_proof", proof_values),
    ):
        columns = ",".join(payload)
        await session.execute(
            text(
                f"INSERT INTO {table} ({columns}) VALUES ({','.join(':' + key for key in payload)})"
            ),
            payload,
        )
    audit = {
        **values,
        "event": event,
        "request": event,
        "change": canonical(
            {
                "reason": "可信扫描收据与当前运行实例证明原子绑定",
                "before": None,
                "after": {
                    "receipt_id": identifier,
                    "claim_id": claim["claim_id"],
                    "profile_id": proof.profile_id,
                    "profile_revision": proof.profile_revision,
                    "instance_id": proof.instance_id,
                    "result": receipt.result,
                },
            }
        ),
    }
    await session.execute(
        text("""INSERT INTO orbit_material_audit
        (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
        VALUES(:event,:tenant_id,0,'MATERIAL_SCAN_RUNTIME_BOUND',:asset_id,:revision,:request,:change)"""),
        audit,
    )
    await session.execute(
        text("""INSERT INTO orbit_material_outbox(event_id,tenant_id,resource_id,revision)
        VALUES(:event,:tenant_id,:asset_id,:revision)"""),
        audit,
    )
    await session.execute(
        text("UPDATE orbit_material_clock SET revision=revision+1 WHERE tenant_id=:tenant_id"),
        values,
    )
    if selection is not None:
        selection.registry.verify(selection.binding, source=False)
    return StoredRuntimeScan(identifier, event, False)
