"""规则原MetricProfile只读桥；不要求投放适配器或授予平台执行能力。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_model
from orbit_api.metric_profile_contract import MetricProfile, MetricSourceProof, check_proof
from orbit_api.metric_profile_query import mysql_millisecond_instant
from orbit_api.metric_profile_store import fixture_boundary
from orbit_api.rule_access import assert_owner, revalidate_owner
from orbit_api.rule_contract import MAX_SAFE, identifier


@dataclass(frozen=True, repr=False)
class RuleProfileBinding:
    profile_id: str
    version: str
    head_revision: int
    directory_revision: int
    profile_json: bytes
    profile_hash: str
    source: str
    source_config_id: str | None
    source_config_revision: int | None
    source_proof_json: bytes

    def profile(self):
        return json.loads(self.profile_json)


def unavailable():
    raise OrbitError(503, "RULE_METRIC_PROFILE_UNAVAILABLE", "规则指标配置来源或完整性尚未就绪")


async def _one(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().first()


async def lock_rule_profile(session, access, owner, profile_id, *, expected_version=None):
    """auth双方→普通probe→实际source→metric clock→当前head/version。

    必须在账户clock、规则clock/head之前调用。probe只定位来源；最终当前读发现
    source/版本漂移即拒绝，不在已持clock后补首次source锁。无网络或数据库写入。
    """
    assert_owner(session, access, owner)
    await revalidate_owner(session, access, owner)
    profile_id = identifier(profile_id, "/metric_profile_id")
    values = {"tenant": access.current.tenant_id, "id": profile_id}
    probe = await _one(
        session,
        "SELECT h.current_version,v.source,v.authority_kind,v.source_config_id,"
        "v.source_config_revision FROM orbit_metric_profile_head h "
        "JOIN orbit_metric_profile_version v ON v.tenant_id=h.tenant_id "
        "AND v.profile_id=h.id AND v.version=h.current_version "
        "WHERE h.tenant_id=:tenant AND h.id=:id",
        values,
    )
    if probe is None:
        raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "指标配置不存在或不可见")
    if expected_version is not None and probe["current_version"] != expected_version:
        # 精确版本已变化时先拒绝，不能为新版本首次锁入未预声明的配置来源。
        # 后面的当前锁读仍再次核版本，覆盖probe之后发生的并发换版。
        raise OrbitError(409, "METRIC_PROFILE_VERSION_CHANGED", "规则冻结的指标版本已变化")
    if probe["source"] == "FIXTURE" and probe["authority_kind"] == "ISOLATED_TEST":
        await fixture_boundary(session)
    elif probe["source"] == "META" and probe["authority_kind"] == "TRUSTED":
        if probe["source_config_id"] is None:
            unavailable()
        source = await _one(
            session,
            "SELECT id,revision,enabled,section FROM orbit_system_configuration "
            "WHERE tenant_id=:tenant AND id=:source FOR SHARE",
            values | {"source": probe["source_config_id"]},
        )
        if (
            source is None
            or not source["enabled"]
            or source["section"] != "META_BM"
            or source["revision"] != probe["source_config_revision"]
        ):
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标来源版本已变化或被停用")
    else:
        unavailable()
    clock = await _one(
        session,
        "SELECT revision,UTC_TIMESTAMP(3) AS now FROM orbit_metric_profile_clock "
        "WHERE tenant_id=:tenant FOR SHARE",
        values,
    )
    if clock is None:
        unavailable()
    row = await _one(
        session,
        "SELECT h.current_version,h.revision AS head_revision,h.state,v.* "
        "FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v "
        "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
        "WHERE h.tenant_id=:tenant AND h.id=:id FOR SHARE",
        values,
    )
    if row is None or row["state"] != "ENABLED":
        raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "指标配置当前不可用")
    if any(
        row[key] != probe[key]
        for key in (
            "current_version",
            "source",
            "authority_kind",
            "source_config_id",
            "source_config_revision",
        )
    ):
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标当前版本与预选来源不一致")
    if expected_version is not None and row["current_version"] != expected_version:
        raise OrbitError(409, "METRIC_PROFILE_VERSION_CHANGED", "规则冻结的指标版本已变化")
    if any(
        type(value) is not int or not 1 <= value <= MAX_SAFE
        for value in (row["head_revision"], clock["revision"])
    ):
        unavailable()
    try:
        profile = (
            json.loads(row["payload_json"])
            if isinstance(row["payload_json"], str)
            else row["payload_json"]
        )
        parsed = parse_model(canonical(profile).encode(), MetricProfile)
        proof_value = (
            json.loads(row["source_proof_json"])
            if isinstance(row["source_proof_json"], str)
            else row["source_proof_json"]
        )
        if set(proof_value) != {
            "source_sha256",
            "observed_at",
            "evidence_ref",
            "source_config_id",
            "source_config_revision",
        }:
            unavailable()
        proof = MetricSourceProof(
            proof_value["source_sha256"],
            datetime.fromisoformat(proof_value["observed_at"]),
            proof_value["evidence_ref"],
            proof_value["source_config_id"],
            proof_value["source_config_revision"],
        )
        check_proof(proof, row["source"])
        observed, now = row["observed_at"], clock["now"]
        if (
            not isinstance(observed, datetime)
            or not isinstance(now, datetime)
            or observed.microsecond % 1000
            or now.microsecond % 1000
        ):
            unavailable()
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        if (
            observed.utcoffset().total_seconds() != 0
            or now.utcoffset().total_seconds() != 0
            or observed != mysql_millisecond_instant(proof.observed_at)
            or observed > now
        ):
            unavailable()
        digest = hashlib.sha256(canonical(parsed).encode()).hexdigest()
        if (
            parsed != profile
            or parsed["id"] != profile_id
            or parsed["version"] != row["current_version"]
            or parsed["source"] != row["source"]
            or parsed["verified"] is not True
            or digest != row["payload_hash"]
            or proof.source_sha256 != row["source_sha256"]
            or proof.evidence_ref != row["evidence_ref"]
            or proof.source_config_id != row["source_config_id"]
            or proof.source_config_revision != row["source_config_revision"]
        ):
            unavailable()
    except (KeyError, TypeError, ValueError, UnicodeError, OrbitError):
        unavailable()
    return RuleProfileBinding(
        profile_id,
        row["current_version"],
        row["head_revision"],
        clock["revision"],
        canonical(parsed).encode(),
        digest,
        row["source"],
        row["source_config_id"],
        row["source_config_revision"],
        canonical(proof_value).encode(),
    )
