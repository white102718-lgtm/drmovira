"""通知传输边界；真实TLS、DNS限制和未知结果不自动重发。"""

import hashlib
import hmac
import json
import ssl
from pathlib import Path
from uuid import uuid4

import httpcore
import pytest

from orbit_api.notification_http import NotificationHttp


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://notify.example",
        "https://notify.example?token=x",
        "https://user:secret@notify.example",
        "https://notify.example:8443",
    ],
)
@pytest.mark.asyncio
async def test_invalid_webhook_target_is_rejected_before_connect(endpoint):
    outcome = await NotificationHttp().send(endpoint, str(uuid4()), b"{}")
    assert (outcome.status, outcome.failure_code) == ("FAILED", "WEBHOOK_CONFIGURATION_INVALID")


@pytest.mark.asyncio
async def test_header_injection_and_oversized_payload_are_rejected_before_connect():
    client = NotificationHttp()
    for identifier, body in [("bad\r\nInjected: secret", b"{}"), (str(uuid4()), b"x" * 16385)]:
        assert (await client.send("https://notify.example", identifier, body)).status == "FAILED"


@pytest.mark.parametrize(
    "mode,expected,code",
    [
        ("accepted", "ACCEPTED", None),
        ("rejected", "FAILED", "WEBHOOK_DELIVERY_REJECTED"),
        ("wrong-id", "UNKNOWN", "WEBHOOK_RECEIPT_INVALID"),
        ("invalid-json", "UNKNOWN", "WEBHOOK_RECEIPT_INVALID"),
        ("server-error", "UNKNOWN", "WEBHOOK_SERVER_RESULT_UNKNOWN"),
        ("redirect", "FAILED", "WEBHOOK_REQUEST_REJECTED"),
        ("disconnect", "UNKNOWN", "WEBHOOK_TRANSPORT_RESULT_UNKNOWN"),
    ],
)
@pytest.mark.asyncio
async def test_actual_https_receipt_signature_and_no_retry(mode, expected, code):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from oidc_https_fixture import LocalOidcFixture

    with LocalOidcFixture() as fixture:
        fixture.notification_mode = mode

        class LoopbackFixtureBackend(httpcore.AsyncNetworkBackend):
            async def connect_tcp(self, host, port, **kwargs):
                assert host == "orbit-idp.fixture.example" and port == 443
                return await httpcore.AnyIOBackend().connect_tcp(
                    "127.0.0.1", fixture.port, **kwargs
                )

        client = NotificationHttp(
            network_backend=LoopbackFixtureBackend(),
            ssl_context=ssl.create_default_context(cadata=fixture.ca_pem),
        )
        identifier = str(uuid4())
        body = json.dumps({"delivery_id": identifier, "recipient": "fixture@example.org"}).encode()
        outcome = await client.send(
            fixture.issuer + "/notifications", identifier, body, "test-signing-secret"
        )
        assert (outcome.status, outcome.failure_code) == (expected, code)
        assert len(fixture.notifications) == 1
        received, headers = fixture.notifications[0]
        assert received == body and headers["Idempotency-Key"] == identifier
        expected_signature = hmac.new(
            b"test-signing-secret",
            headers["X-ORBIT-Timestamp"].encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-ORBIT-Signature"] == "sha256=" + expected_signature
        assert "test-signing-secret" not in repr(headers)
