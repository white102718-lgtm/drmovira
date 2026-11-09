"""设备租约合同；动态租约字段不改变冻结指令摘要。"""

from typing import Literal

from pydantic import Field, ValidationError

from orbit_api.agent_monitor_contract import observed_time
from orbit_api.configuration import _parse_json
from orbit_api.errors import OrbitError
from orbit_api.execution_agent_access import digest
from orbit_api.reference_contract import StrictInput, schema_error, uuid_value

MAX_FENCE = 9007199254740991
LEASE_SECONDS = 120
RENEW_SECONDS = 20


class LeaseRenewInput(StrictInput):
    agent_id: str
    boot_id: str
    fencing_token: int = Field(ge=1, le=MAX_FENCE)


def parse_renew(raw):
    try:
        value = LeaseRenewInput.model_validate(_parse_json(raw)).model_dump()
    except ValidationError as error:
        raise schema_error(error) from None
    for key in ("agent_id", "boot_id"):
        value[key] = uuid_value(value[key], "/" + key)
    return value


def instruction_hash(instruction):
    """原指令稳定字段的规范SHA256；租约续期不能改变业务意图。"""
    return digest(
        {
            k: v
            for k, v in instruction.items()
            if k not in {"lease_id", "command_hash", "allowed_until"}
        }
    )


class AgentEventInput(StrictInput):
    event_id: str
    sequence: int = Field(ge=1, le=MAX_FENCE)
    operation_id: str
    task_id: str
    node_id: str
    attempt_id: str
    agent_id: str
    boot_id: str
    profile_binding_id: str
    workflow_version: str = Field(min_length=1, max_length=64)
    adapter_version: str = Field(min_length=1, max_length=64)
    phase: Literal[
        "PREFLIGHT", "FILLING", "WRITE_INTENT", "SUBMITTED", "READBACK", "RECOVERY", "CLEANUP"
    ]
    state: Literal[
        "DRAFT",
        "VALIDATED",
        "QUEUED",
        "RUNNING",
        "ACCEPTED",
        "VERIFYING",
        "SUCCEEDED",
        "FAILED",
        "UNKNOWN",
        "RETRY_WAIT",
        "CANCELLED",
        "EXPIRED",
        "BLOCKED_AUTH",
        "NEEDS_HUMAN",
    ]
    error_code: str | None = Field(min_length=1, max_length=64)
    retryable: bool
    evidence_refs: list[str] = Field(max_length=20)
    occurred_at: str
    fencing_token: int = Field(ge=1, le=MAX_FENCE)


class AgentEventBatchInput(StrictInput):
    events: list[AgentEventInput] = Field(min_length=1, max_length=100)


def parse_events(raw):
    try:
        value = AgentEventBatchInput.model_validate(_parse_json(raw)).model_dump()
    except ValidationError as error:
        raise schema_error(error) from None
    if len({event["event_id"] for event in value["events"]}) != len(value["events"]):
        raise OrbitError(422, "EVENT_DUPLICATE_IN_BATCH", "批次事件标识不能重复", "/events")
    for event in value["events"]:
        for key in (
            "event_id",
            "operation_id",
            "task_id",
            "node_id",
            "attempt_id",
            "agent_id",
            "boot_id",
            "profile_binding_id",
        ):
            uuid_value(event[key], "/events/" + key)
        observed_time(event["occurred_at"])
        if any(
            not isinstance(ref, str) or not 1 <= len(ref) <= 255 for ref in event["evidence_refs"]
        ):
            raise OrbitError(422, "FIELD_INVALID", "证据引用长度无效", "/events/evidence_refs")
    return value
