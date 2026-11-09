"""S2持久协议纯合同；结构/摘要合法不代表来源、授权或成功模拟已发行。"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from orbit_api.configuration import _parse_json
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_conditions import compile_conditions
from orbit_api.rule_contract import (
    MAX_SAFE,
    RuleWrite,
    Simulation,
    _text,
    parse_rule_response,
    parse_rule_write,
)
from orbit_api.rule_simulation_evaluator import ALGORITHM_VERSION, EvaluationSummary

MAX_SCANNED = 2147483647


def uuid_value(value):
    if type(value) is not str:
        raise ValueError("SIMULATION_UUID_INVALID")
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ValueError("SIMULATION_UUID_INVALID")


def hash_value(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("SIMULATION_HASH_INVALID")
    return value


def integer(value, minimum=0, maximum=MAX_SAFE):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("SIMULATION_INTEGER_INVALID")
    return value


def utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("SIMULATION_UTC_REQUIRED")
    return value.astimezone(UTC)


def utc_text(value):
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SimulationIntent:
    actor_id: int
    rule_id: str
    revision: int
    key_hash: str
    request_id: str

    def __post_init__(self):
        integer(self.actor_id, 1)
        uuid_value(self.rule_id)
        integer(self.revision, 1)
        hash_value(self.key_hash)
        uuid_value(self.request_id)

    @property
    def intent_hash(self):
        # request_id是审计身份，不改变同一次原模拟业务意图。
        return digest(["SIMULATE", self.rule_id, self.revision])


@dataclass(frozen=True, slots=True)
class SimulationQuality:
    missing_unit_count: int
    stale_unit_count: int
    immature_unit_count: int
    invalid_unit_count: int
    sparse_entity_count: int
    oldest_observed_at: datetime | None

    def __post_init__(self):
        for key in (
            "missing_unit_count",
            "stale_unit_count",
            "immature_unit_count",
            "invalid_unit_count",
            "sparse_entity_count",
        ):
            integer(getattr(self, key), maximum=MAX_SCANNED)
        if self.oldest_observed_at is not None:
            utc(self.oldest_observed_at)

    def public_internal(self):
        return {
            key: utc_text(value) if isinstance(value, datetime) else value
            for key, value in (
                ("missing_unit_count", self.missing_unit_count),
                ("stale_unit_count", self.stale_unit_count),
                ("immature_unit_count", self.immature_unit_count),
                ("invalid_unit_count", self.invalid_unit_count),
                ("sparse_entity_count", self.sparse_entity_count),
                ("oldest_observed_at", self.oldest_observed_at),
            )
        }


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    tenant_id: str
    actor_id: int
    rule_id: str
    revision: int
    rule_json: str
    manifest_id: str
    member_hash: str
    auth_fingerprint: str
    owner_auth_fingerprint: str
    account_count: int
    account_root: str
    unit_root: str
    entity_count: int
    entity_ids_root: str
    profile_version: str
    profile_hash: str
    profile_proof_hash: str
    source_publication_id: str
    source_generation: int
    capture_sequence_max: int
    source_selection_root: str
    evaluated_at: datetime
    quality: SimulationQuality

    def __post_init__(self):
        for key in ("tenant_id", "rule_id", "manifest_id", "source_publication_id"):
            uuid_value(getattr(self, key))
        integer(self.actor_id, 1)
        integer(self.revision, 1)
        integer(self.account_count, 1, 50000)
        integer(self.entity_count, 0, MAX_SCANNED)
        integer(self.source_generation, 1)
        integer(self.capture_sequence_max, 1)
        for key in (
            "member_hash",
            "auth_fingerprint",
            "owner_auth_fingerprint",
            "account_root",
            "unit_root",
            "entity_ids_root",
            "profile_hash",
            "profile_proof_hash",
            "source_selection_root",
        ):
            hash_value(getattr(self, key))
        if type(self.profile_version) is not str or not 1 <= len(self.profile_version) <= 64:
            raise ValueError("SIMULATION_PROFILE_VERSION_INVALID")
        if _text(self.profile_version, "/profile_version", 64) != self.profile_version:
            raise ValueError("SIMULATION_PROFILE_VERSION_INVALID")
        utc(self.evaluated_at)
        if type(self.quality) is not SimulationQuality:
            raise ValueError("SIMULATION_QUALITY_CONTRACT_REQUIRED")
        if (
            self.quality.oldest_observed_at is not None
            and self.quality.oldest_observed_at > self.evaluated_at
        ):
            raise ValueError("SIMULATION_FUTURE_OBSERVATION")
        if type(self.rule_json) is not str:
            raise ValueError("SIMULATION_RULE_CANONICAL_REQUIRED")
        # raw bytes受现严格parser约束，随后只保留规范不可变字符串。
        parsed = parse_rule_write(self.rule_json.encode("utf-8"))
        if canonical(parsed.model_dump()) != self.rule_json:
            raise ValueError("SIMULATION_RULE_CANONICAL_REQUIRED")
        unit_count = self.unit_count
        if (
            any(
                getattr(self.quality, key) > unit_count
                for key in (
                    "missing_unit_count",
                    "stale_unit_count",
                    "immature_unit_count",
                    "invalid_unit_count",
                )
            )
            or self.quality.sparse_entity_count > self.entity_count
        ):
            raise ValueError("SIMULATION_QUALITY_COUNT_INVALID")

    def rule(self) -> RuleWrite:
        return parse_rule_write(self.rule_json.encode())

    @property
    def leaf_count(self):
        return sum(len(group.conditions) for group in compile_conditions(self.rule()).groups)

    @property
    def unit_count(self):
        return (
            self.account_count
            * {"TODAY": 1, "YESTERDAY": 1, "LAST_3D": 3, "LAST_7D": 7}[self.rule().window]
        )

    def payload(self):
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "rule_id": self.rule_id,
            "revision": self.revision,
            "rule": json.loads(self.rule_json),
            "manifest_id": self.manifest_id,
            "member_hash": self.member_hash,
            "auth_fingerprint": self.auth_fingerprint,
            "owner_auth_fingerprint": self.owner_auth_fingerprint,
            "account_count": self.account_count,
            "account_root": self.account_root,
            "unit_count": self.unit_count,
            "unit_root": self.unit_root,
            "entity_count": self.entity_count,
            "entity_ids_root": self.entity_ids_root,
            "profile_version": self.profile_version,
            "profile_hash": self.profile_hash,
            "profile_proof_hash": self.profile_proof_hash,
            "source_publication_id": self.source_publication_id,
            "source_generation": self.source_generation,
            "capture_sequence_max": self.capture_sequence_max,
            "source_selection_root": self.source_selection_root,
            "evaluated_at": utc_text(self.evaluated_at),
            "quality": self.quality.public_internal(),
            "algorithm": ALGORITHM_VERSION,
        }

    @property
    def input_hash(self):
        return digest(self.payload())


def validate_summary(snapshot, summary):
    if type(snapshot) is not SimulationSnapshot or type(summary) is not EvaluationSummary:
        raise ValueError("SIMULATION_COMPLETE_SUMMARY_REQUIRED")
    if summary.algorithm != ALGORITHM_VERSION or summary.rule_hash != digest(
        snapshot.rule().model_dump()
    ):
        raise ValueError("SIMULATION_SUMMARY_RULE_CHANGED")
    for key in ("scanned_count", "hit_count", "unknown_count", "false_count"):
        integer(getattr(summary, key), maximum=MAX_SCANNED)
    if (
        summary.scanned_count != snapshot.entity_count
        or summary.scanned_count != summary.hit_count + summary.unknown_count + summary.false_count
        or type(summary.condition_count) is not int
        or summary.condition_count != summary.scanned_count * snapshot.leaf_count
        or summary.entity_ids_root != snapshot.entity_ids_root
    ):
        raise ValueError("SIMULATION_SUMMARY_INCOMPLETE")
    hash_value(summary.results_root)


def simulation_response(
    snapshot, summary, *, simulation_id, snapshot_id, sealed_at, conditions, next_cursor
):
    """仅首次POST原DTO投影；不是来源证明/SQL封存，也不是GET分页实现。"""
    validate_summary(snapshot, summary)
    uuid_value(simulation_id)
    uuid_value(snapshot_id)
    if snapshot_id in {
        simulation_id,
        snapshot.manifest_id,
        snapshot.source_publication_id,
        snapshot.rule().scope_snapshot_id,
    }:
        raise ValueError("SIMULATION_INDEPENDENT_SNAPSHOT_REQUIRED")
    sealed_at = utc(sealed_at)
    if sealed_at < snapshot.evaluated_at:
        raise ValueError("SIMULATION_SEAL_BEFORE_EVALUATION")
    if type(conditions) is not list or len(conditions) != min(200, summary.condition_count):
        raise ValueError("SIMULATION_FIRST_PAGE_INCOMPLETE")
    if (summary.condition_count > 200) != (next_cursor is not None):
        raise ValueError("SIMULATION_FIRST_PAGE_CURSOR_INVALID")
    business_hash = digest(["ORBIT_RULE_SIMULATION_V1", snapshot.input_hash, summary.results_root])
    return parse_rule_response(
        Simulation,
        {
            "id": simulation_id,
            "rule_id": snapshot.rule_id,
            "revision": snapshot.revision,
            "snapshot_id": snapshot_id,
            "hash": business_hash,
            "account_count": snapshot.account_count,
            "scanned_count": summary.scanned_count,
            "hit_count": summary.hit_count,
            "unknown_count": summary.unknown_count,
            "false_count": summary.false_count,
            "conditions": conditions,
            "expires_at": utc_text(sealed_at + timedelta(minutes=15)),
            "next_cursor": next_cursor,
        },
    ).model_dump()


def confirmation_unexpired(expires_at, now):
    """仅时间必要条件，不是enable/分析/广告许可。"""
    return utc(now) < utc(expires_at)


@dataclass(frozen=True, slots=True)
class OriginalSimulationReceipt:
    """原字节与存储JSON、可信头/首批叶投影三方绑定，不签发来源证明。

    expected_response_json必须由publisher/replay从精确SQL头及有序首批叶构造，
    不接受HTTP提供的“预期”。字符串字段保留深不可变；不重排response_bytes。
    """

    response_bytes: bytes
    response_json: str
    expected_response_json: str

    def __post_init__(self):
        if type(self.response_bytes) is not bytes or len(self.response_bytes) > 1048576:
            raise ValueError("SIMULATION_RECEIPT_BYTES_INVALID")
        documents = [_parse_json(self.response_bytes)]
        for value in (self.response_json, self.expected_response_json):
            if type(value) is not str or len(value.encode("utf-8")) > 1048576:
                raise ValueError("SIMULATION_RECEIPT_BINDING_INVALID")
            documents.append(_parse_json(value.encode("utf-8")))
        for document in documents:
            if parse_rule_response(Simulation, document).model_dump() != document:
                raise ValueError("SIMULATION_RECEIPT_NONCANONICAL_FIELDS")
        # 规范语义比较：对象键序/空白无关，数组顺序和重复叶仍有意义。
        if len({canonical(document) for document in documents}) != 1:
            raise ValueError("SIMULATION_RECEIPT_BINDING_MISMATCH")

    @classmethod
    def bind(cls, response_bytes, *, response_json, header, first_conditions, next_cursor):
        """header为原13字段除conditions/next_cursor的精确SQL投影。"""
        fields = {
            "id",
            "rule_id",
            "revision",
            "snapshot_id",
            "hash",
            "account_count",
            "scanned_count",
            "hit_count",
            "unknown_count",
            "false_count",
            "expires_at",
        }
        if type(header) is not dict or set(header) != fields or type(first_conditions) is not list:
            raise ValueError("SIMULATION_RECEIPT_BINDING_INVALID")
        if len(first_conditions) > 200:
            raise ValueError("SIMULATION_RECEIPT_BINDING_INVALID")
        expected = {**header, "conditions": first_conditions, "next_cursor": next_cursor}
        return cls(response_bytes, response_json, canonical(expected))

    @property
    def response_hash(self):
        return hashlib.sha256(self.response_bytes).hexdigest()

    def document(self):
        return _parse_json(self.response_bytes)


def unavailable():
    raise OrbitError(
        503, "RULE_SIMULATION_SOURCE_UNAVAILABLE", "完整规则授权与指标预期来源尚未接入"
    )
