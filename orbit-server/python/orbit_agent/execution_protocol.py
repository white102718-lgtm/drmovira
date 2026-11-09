"""租约下行精确边界；结构通过不代表业务或写动作授权。"""

import re

from orbit_agent.adspower_status import ProbeError
from orbit_agent.protocol import exact, integer, timestamp, uuid

LEASE_FIELDS = {
    "id",
    "operation_id",
    "task_id",
    "node_id",
    "attempt_id",
    "profile_binding_id",
    "expires_at",
    "fencing_token",
    "workflow_version",
    "adapter_version",
    "command_hash",
}
INSTRUCTION_FIELDS = {
    "lease_id",
    "command_hash",
    "account_id",
    "external_account_id",
    "node_key",
    "kind",
    "target",
    "plan",
    "manual",
    "policy_version",
    "submission_group_id",
    "allowed_until",
    "execution_manifest_id",
    "execution_manifest_hash",
}


def reject():
    raise ProbeError("EXECUTION_RESPONSE_INVALID")


def text(value, maximum):
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        reject()


def digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        reject()


def validate_lease(value):
    exact(value, LEASE_FIELDS)
    for key in ("id", "operation_id", "task_id", "node_id", "attempt_id", "profile_binding_id"):
        uuid(value[key])
    timestamp(value["expires_at"])
    integer(value["fencing_token"])
    for key in ("workflow_version", "adapter_version"):
        text(value[key], 64)
    digest(value["command_hash"])
    return value


def validate_instruction(value, identifier):
    exact(value, INSTRUCTION_FIELDS)
    for key in ("lease_id", "account_id"):
        uuid(value[key])
    if value["lease_id"] != identifier:
        reject()
    digest(value["command_hash"])
    text(value["external_account_id"], 64)
    if not value["external_account_id"].isdigit():
        reject()
    text(value["node_key"], 512)
    text(value["policy_version"], 64)
    timestamp(value["allowed_until"])
    if value["kind"] not in {
        "CREATE",
        "BUDGET_SET",
        "PAUSE",
        "ENABLE",
        "DELETE",
        "ARCHIVE",
        "VERIFY",
    }:
        reject()
    for key in ("submission_group_id", "execution_manifest_id"):
        if value[key] is not None:
            uuid(value[key])
    if value["execution_manifest_hash"] is not None:
        digest(value["execution_manifest_hash"])
    if (value["execution_manifest_id"] is None) != (value["execution_manifest_hash"] is None):
        reject()
    if value["kind"] == "CREATE" and value["execution_manifest_id"] is None:
        reject()
    for key in ("target", "plan", "manual"):
        if value[key] is not None and type(value[key]) is not dict:
            reject()
    return value


def validate_event_ack(value, identifiers):
    keys = {
        "accepted_event_ids",
        "duplicate_event_ids",
        "rejected_event_ids",
        "historical_event_ids",
    }
    exact(value, keys | {"request_id"})
    uuid(value["request_id"])
    for key in keys:
        rows = value[key]
        if type(rows) is not list or len(rows) > 100:
            reject()
        for identifier in rows:
            uuid(identifier)
        if len(set(rows)) != len(rows):
            reject()
    # 历史标记是已接收事件的附加分类，不能代表当前发送许可。
    groups = [
        set(value[k]) for k in ("accepted_event_ids", "duplicate_event_ids", "rejected_event_ids")
    ]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        reject()
    if set.union(*groups) != set(identifiers) or not set(value["historical_event_ids"]) <= (
        groups[0] | groups[1]
    ):
        reject()
    return value
