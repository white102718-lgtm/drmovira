"""指标源发布内部合同；原MetricProfile不加字段，不从窗口文本猜目标参数。"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_model, uuid_field
from orbit_api.launch_execution_contract import (
    AttributionSpec,
    MetricProfile,
    ResolvedMetricProfile,
)

MAX_REVISION = 9007199254740991


def unavailable():
    raise OrbitError(503, "METRIC_PROFILE_AUTHORITY_UNAVAILABLE", "指标配置权威来源尚未就绪")


@dataclass(frozen=True, repr=False)
class MetricSourceProof:
    source_sha256: str
    observed_at: datetime
    evidence_ref: str
    source_config_id: str | None
    source_config_revision: int | None
    source_connection_id: str | None = None
    source_connection_revision: int | None = None


def check_proof(proof, source):
    if (
        not isinstance(proof, MetricSourceProof)
        or not isinstance(proof.source_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", proof.source_sha256) is None
        or not isinstance(proof.observed_at, datetime)
        or proof.observed_at.tzinfo is None
        or proof.observed_at.utcoffset().total_seconds() != 0
        or not isinstance(proof.evidence_ref, str)
        or re.fullmatch(r"[A-Za-z0-9._:-]{1,255}", proof.evidence_ref) is None
    ):
        unavailable()
    if (proof.source_config_id is None) != (proof.source_config_revision is None):
        unavailable()
    if proof.source_config_id is not None:
        uuid_field(proof.source_config_id, ("source_config_id",))
        if (
            type(proof.source_config_revision) is not int
            or not 1 <= proof.source_config_revision <= MAX_REVISION
        ):
            unavailable()
    if (proof.source_connection_id is None) != (proof.source_connection_revision is None):
        unavailable()
    if proof.source_connection_id is not None:
        uuid_field(proof.source_connection_id, ("source_connection_id",))
        if (
            type(proof.source_connection_revision) is not int
            or not 1 <= proof.source_connection_revision <= MAX_REVISION
        ):
            unavailable()
    if (
        source == "META"
        and ((proof.source_config_id is not None) + (proof.source_connection_id is not None)) != 1
    ):
        unavailable()
    return proof


@dataclass(frozen=True, repr=False)
class MetricPublication:
    profile_json: bytes
    attribution_json: bytes
    adapter_version: str
    proof: MetricSourceProof

    def profile(self):
        return parse_model(self.profile_json, MetricProfile)

    @property
    def profile_hash(self):
        return hashlib.sha256(self.profile_json).hexdigest()

    @property
    def attribution_hash(self):
        return hashlib.sha256(self.attribution_json).hexdigest()


def publication(profile, adapter_version, attribution_spec, proof):
    value = parse_model(canonical(profile).encode(), MetricProfile)
    value["id"] = uuid_field(value["id"], ("id",))
    # 原version保持精确文本，不改成整数、不制造默认版本。
    if not isinstance(adapter_version, str) or not 1 <= len(adapter_version) <= 64:
        raise OrbitError(422, "FIELD_INVALID", "需要明确适配版本", "/adapter_version")
    if not isinstance(attribution_spec, list) or not 1 <= len(attribution_spec) <= 10:
        raise OrbitError(422, "FIELD_INVALID", "需要完整显式目标参数映射", "/attribution_spec")
    mapped = [parse_model(canonical(item).encode(), AttributionSpec) for item in attribution_spec]
    check_proof(proof, value["source"])
    return MetricPublication(
        canonical(value).encode(), canonical(mapped).encode(), adapter_version, proof
    )


def proof_values(proof):
    return {
        "source_sha": proof.source_sha256,
        "observed": proof.observed_at.astimezone(UTC).replace(tzinfo=None),
        "evidence": proof.evidence_ref,
        "config": proof.source_config_id,
        "config_revision": proof.source_config_revision,
        "connection": proof.source_connection_id,
        "connection_revision": proof.source_connection_revision,
    }


__all__ = [
    "MetricProfile",
    "ResolvedMetricProfile",
    "MetricSourceProof",
    "MetricPublication",
    "publication",
]


def parse_source_proof(value, source):
    """兼容历史五字段证明；连接证明须完整两字段，不接受未知字段。"""
    expected = {
        "source_sha256",
        "observed_at",
        "evidence_ref",
        "source_config_id",
        "source_config_revision",
    }
    if not isinstance(value, dict) or set(value) not in (
        expected,
        expected | {"source_connection_id", "source_connection_revision"},
    ):
        unavailable()
    try:
        proof = MetricSourceProof(
            value["source_sha256"],
            datetime.fromisoformat(value["observed_at"]),
            value["evidence_ref"],
            value["source_config_id"],
            value["source_config_revision"],
            value.get("source_connection_id"),
            value.get("source_connection_revision"),
        )
        return check_proof(proof, source)
    except (ValueError, TypeError, KeyError):
        unavailable()
