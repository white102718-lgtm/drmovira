"""Agent主动mTLS设备监听器连接；固定CA/证书、hostname验证、无代理/重定向。"""

import asyncio
import json
import os
import re
import ssl
import stat
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from orbit_agent.adspower_status import ProbeError, _unique_object
from orbit_agent.protocol import (
    PATHS,
    exact,
    integer,
    profile_id,
    timestamp,
    uuid,
    validate_payload,
)

REJECTIONS = {
    "AGENT_BOOT_RETIRED",
    "AGENT_BOOT_MISMATCH",
    "AGENT_BOOT_SEQUENCE_REQUIRED",
    "AGENT_SEQUENCE_STALE",
    "AGENT_SEQUENCE_CONFLICT",
    "AGENT_REVOKED",
    "AGENT_NOT_READY",
    "IDENTITY_REPORT_EXPIRED",
    "PROFILE_BINDING_STALE",
}


class DeviceRejected(ProbeError):
    def __init__(self, code, status):
        self.status = status
        super().__init__(code)


def device_origin(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.hostname is None
            or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
            or parsed.port is not None
            and not 1 <= parsed.port <= 65535
        ):
            raise ValueError
        return value.rstrip("/")
    except (ValueError, TypeError):
        raise ProbeError("DEVICE_ORIGIN_REJECTED") from None


def certificate_file(value, *, private=False):
    descriptor = None
    try:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_size > 1024 * 1024
            or private
            and info.st_mode & 0o077
        ):
            raise ValueError
        return str(path)
    except (OSError, ValueError, TypeError):
        raise ProbeError("DEVICE_CERTIFICATE_REJECTED") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def validate_ack(kind, value, agent):
    exact(value, {"id", "revision", "state", "request_id"})
    uuid(value["id"])
    uuid(value["request_id"])
    integer(value["revision"])
    states = {
        "heartbeat": {"READY", "SUSPECT"},
        "diagnostics": {"DIAGNOSTICS_ACCEPTED"},
        "identity": {"IDENTITY_RECORDED"},
    }
    if value["id"] != agent or value["state"] not in states[kind]:
        raise ProbeError("DEVICE_ACK_INVALID")
    return value


def validate_configuration(value, agent):
    exact(value, {"agent_id", "bindings"})
    if (
        value["agent_id"] != agent
        or type(value["bindings"]) is not list
        or len(value["bindings"]) > 5000
    ):
        raise ProbeError("DEVICE_CONFIGURATION_INVALID")
    seen = set()
    for item in value["bindings"]:
        exact(
            item,
            {
                "id",
                "revision",
                "account_id",
                "profile_external_id",
                "external_account_id",
                "currency",
            },
        )
        for key in ("id", "account_id"):
            uuid(item[key])
        integer(item["revision"])
        profile_id(item["profile_external_id"])
        if (
            item["id"] in seen
            or type(item["external_account_id"]) is not str
            or re.fullmatch(r"[0-9]{1,64}", item["external_account_id"]) is None
            or type(item["currency"]) is not str
            or re.fullmatch(r"[A-Z]{3}", item["currency"]) is None
        ):
            raise ProbeError("DEVICE_CONFIGURATION_INVALID")
        seen.add(item["id"])
    return value


class DeviceClient:
    def __init__(self, origin, agent_id, *, ca_file, certificate, key_file):
        self.origin = device_origin(origin)
        self.agent_id = uuid(agent_id)
        try:
            context = ssl.create_default_context(cafile=certificate_file(ca_file))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(
                certificate_file(certificate),
                certificate_file(key_file, private=True),
                password=lambda: "",
            )
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise ValueError
            self.context = context
        except (ssl.SSLError, OSError, ValueError):
            raise ProbeError("DEVICE_CERTIFICATE_REJECTED") from None

    async def request(self, method, path, value=None):
        try:
            async with asyncio.timeout(10):
                async with httpx.AsyncClient(
                    verify=self.context,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=8,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                ) as client:
                    async with client.stream(
                        method,
                        self.origin + path,
                        json=value,
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    ) as response:
                        if (
                            sum(len(k) + len(v) for k, v in response.headers.raw) > 8192
                            or response.headers.get("content-encoding", "identity") != "identity"
                        ):
                            raise ProbeError("DEVICE_RESPONSE_INVALID")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if len(raw) + len(chunk) > 2 * 1024 * 1024:
                                raise ProbeError("DEVICE_RESPONSE_INVALID")
                            raw.extend(chunk)
                        body = json.loads(raw, object_pairs_hook=_unique_object)
                        if response.status_code != 200:
                            code = body.get("code") if type(body) is dict else None
                            raise DeviceRejected(
                                code if code in REJECTIONS else "DEVICE_REQUEST_REJECTED",
                                response.status_code,
                            )
                        return body
        except (TimeoutError, httpx.HTTPError):
            raise ProbeError("DEVICE_CONNECTION_FAILED") from None
        except (ValueError, UnicodeError, RecursionError):
            raise ProbeError("DEVICE_RESPONSE_INVALID") from None

    async def configuration(self):
        return validate_configuration(
            await self.request("GET", "/api/v1/agent-api/configuration"), self.agent_id
        )

    async def send(self, kind, payload):
        validate_payload(kind, payload)
        if payload["agent_id"] != self.agent_id:
            raise ProbeError("DEVICE_AGENT_MISMATCH")
        return validate_ack(kind, await self.request("POST", PATHS[kind], payload), self.agent_id)

    async def probe_requests(self):
        """只读取本设备的新观察请求，拒绝任意命令或URL扩展。"""
        from datetime import datetime

        value = await self.request("GET", "/api/v1/agent-api/probe-requests")
        exact(value, {"agent_id", "request"})
        if value["agent_id"] != self.agent_id:
            raise ProbeError("DEVICE_AGENT_MISMATCH")
        item = value["request"]
        if item is not None:
            exact(item, {"id", "created_at", "expires_at"})
            uuid(item["id"])
            duration = (
                datetime.fromisoformat(timestamp(item["expires_at"]))
                - datetime.fromisoformat(timestamp(item["created_at"]))
            ).total_seconds()
            if not 0 < duration <= 120:
                raise ProbeError("DEVICE_RESPONSE_INVALID")
        return value

    async def complete_probe(self, identifier, payload):
        """完成只表示已交付新观察，不宣称广告账户可写。"""
        uuid(identifier)
        exact(payload, {"agent_id", "boot_id", "seq", "observed_at"})
        uuid(payload["agent_id"])
        uuid(payload["boot_id"])
        integer(payload["seq"])
        timestamp(payload["observed_at"])
        if payload["agent_id"] != self.agent_id:
            raise ProbeError("DEVICE_AGENT_MISMATCH")
        value = await self.request(
            "POST", f"/api/v1/agent-api/probe-requests/{identifier}/complete", payload
        )
        exact(value, {"id", "revision", "state", "request_id"})
        uuid(value["request_id"])
        if (
            value["id"] != identifier
            or type(value["revision"]) is not int
            or value["revision"] != 1
            or value["state"] not in {"COMPLETED", "FAILED"}
        ):
            raise ProbeError("DEVICE_ACK_INVALID")
        return value
