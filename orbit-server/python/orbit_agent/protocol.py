"""设备监听器精确安全载荷；不接受DOM、URL、Cookie、任意文本诊断。"""

import re
from datetime import datetime
from uuid import UUID

from orbit_agent.adspower_status import ProbeError

MAX_SEQUENCE = 9007199254740991
ADAPTER_VERSION = "ADSPOWER_META_DOM_V2"
ERRORS = {
    None,
    "ADSPOWER_UNREACHABLE",
    "ADSPOWER_AUTH_FAILED",
    "ADSPOWER_RESPONSE_INVALID",
    "ADSPOWER_TIMEOUT",
    "PROFILE_DISCOVERY_FAILED",
    "ADSPOWER_SUBSCRIPTION_REQUIRED",
    "CDP_UNAVAILABLE",
    "IDENTITY_PROBE_FAILED",
}
PATHS = {
    "heartbeat": "/api/v1/agent-api/heartbeats",
    "diagnostics": "/api/v1/agent-api/diagnostics",
    "identity": "/api/v1/agent-api/identity-reports",
}


def fail():
    raise ProbeError("AGENT_PROTOCOL_INVALID")


def uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            fail()
    except (ValueError, AttributeError):
        fail()
    return value


def timestamp(value):
    try:
        if (
            type(value) is not str
            or len(value) > 40
            or datetime.fromisoformat(value).tzinfo is None
        ):
            fail()
    except ValueError:
        fail()
    return value


def integer(value):
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        fail()
    return value


def profile_id(value):
    if type(value) is not str or not 1 <= len(value) <= 128 or any(ord(c) < 33 for c in value):
        fail()
    return value


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        fail()


def validate_payload(kind, value):
    base = {"agent_id", "boot_id", "observed_at"}
    extra = {
        "heartbeat": {"seq", "profiles"},
        "diagnostics": {"seq", "api_status", "inventory_coverage", "error_code"},
        "identity": {
            "event_id",
            "seq",
            "binding_id",
            "binding_revision",
            "profile_external_id",
            "external_account_id",
            "currency",
            "identity_state",
            "adapter_version",
            "evidence_sha256",
        },
    }
    if kind not in extra:
        fail()
    exact(value, base | extra[kind])
    uuid(value["agent_id"])
    uuid(value["boot_id"])
    timestamp(value["observed_at"])
    integer(value["seq"])
    if kind == "heartbeat":
        profiles = value["profiles"]
        if type(profiles) is not list or len(profiles) > 5000:
            fail()
        seen = set()
        for p in profiles:
            exact(
                p,
                {
                    "id",
                    "agent_id",
                    "external_profile_id",
                    "process_state",
                    "identity_state",
                    "account_ids",
                    "observed_at",
                },
            )
            uuid(p["id"])
            uuid(p["agent_id"])
            profile_id(p["external_profile_id"])
            timestamp(p["observed_at"])
            if (
                p["agent_id"] != value["agent_id"]
                or p["identity_state"] != "UNKNOWN"
                or p["account_ids"] != []
                or p["process_state"] not in {"ACTIVE", "INACTIVE", "UNKNOWN"}
                or p["external_profile_id"] in seen
            ):
                fail()
            seen.add(p["external_profile_id"])
    elif kind == "diagnostics":
        if (
            value["api_status"] not in {"READY", "UNREACHABLE", "AUTH_FAILED", "UNKNOWN"}
            or value["inventory_coverage"] not in {"FULL", "ACTIVE_ONLY", "UNAVAILABLE"}
            or value["error_code"] not in ERRORS
        ):
            fail()
    else:
        for key in ("event_id", "binding_id"):
            uuid(value[key])
        integer(value["binding_revision"])
        profile_id(value["profile_external_id"])
        external, currency = value["external_account_id"], value["currency"]
        if external is not None and (
            type(external) is not str or re.fullmatch(r"[0-9]{1,64}", external) is None
        ):
            fail()
        if currency is not None and (
            type(currency) is not str or re.fullmatch(r"[A-Z]{3}", currency) is None
        ):
            fail()
        if (
            value["identity_state"]
            not in {"VALID", "LOGIN_REQUIRED", "CHALLENGE", "IDENTITY_MISMATCH", "UNKNOWN"}
            or value["adapter_version"] != ADAPTER_VERSION
            or type(value["evidence_sha256"]) is not str
            or re.fullmatch(r"[a-f0-9]{64}", value["evidence_sha256"]) is None
            or (value["identity_state"] == "VALID" and (external is None or currency is None))
        ):
            fail()
    return value
