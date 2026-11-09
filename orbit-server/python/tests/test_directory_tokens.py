"""篡改、分域、过期和会话绑定验证，不将签名单测当作团队业务验收。"""

import base64
import json

import pytest

from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError


@pytest.fixture
def tokens():
    return DirectoryTokens(
        CredentialCipher("fixture", {"fixture": base64.b64encode(b"x" * 32).decode()})
    )


def test_csrf_fits_header_without_containing_bearer(tokens):
    binding = tokens.session_binding("Bearer private-fixture", 1, "tenant")
    value = tokens.issue("DIRECTORY_CSRF_V1", {"binding": binding})
    assert len(value) <= 255 and "private-fixture" not in value
    assert tokens.verify("DIRECTORY_CSRF_V1", value)["binding"] == binding
    assert binding != tokens.session_binding("Bearer other-session", 1, "tenant")
    assert binding != tokens.session_binding("Bearer private-fixture", 2, "tenant")
    assert binding != tokens.session_binding("Bearer private-fixture", 1, "other")


@pytest.mark.parametrize("mutation", ["signature", "payload", "domain", "expired"])
def test_token_cannot_be_repurposed_or_forged(tokens, mutation):
    value = tokens.issue(
        "DIRECTORY_CURSOR_V1", {"after": "a"}, ttl=-1 if mutation == "expired" else 60
    )
    if mutation == "signature":
        value = value[:-1] + ("A" if value[-1] != "A" else "B")
    elif mutation == "payload":
        body, signature = value.split(".")
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        claims["after"] = "b"
        value = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            + "."
            + signature
        )
    with pytest.raises(OrbitError) as error:
        tokens.verify("DIRECTORY_CSRF_V1" if mutation == "domain" else "DIRECTORY_CURSOR_V1", value)
    assert error.value.code == "TOKEN_INVALID"


@pytest.mark.parametrize("value", ["", "a.b.c", "a" * 2049, "☃.x", "W10.x"])
def test_untrusted_token_structure_is_safe(tokens, value):
    with pytest.raises(OrbitError) as error:
        tokens.verify("DIRECTORY_CURSOR_V1", value)
    assert error.value.status == 400


def test_signing_purpose_must_be_whitelisted(tokens):
    with pytest.raises(ValueError):
        tokens.cipher.application_mac("JWT", b"untrusted")


@pytest.mark.parametrize(
    "purpose", ["TASK_LIST_CURSOR_V1", "TASK_NODE_CURSOR_V1", "TASK_EVENT_CHECKPOINT_V1"]
)
def test_task_cursor_purposes_are_distinct_from_each_other_and_launch(tokens, purpose):
    """任务游标只能回到同一用途，不能借任务签名跨到计划或另一种分页。"""
    value = tokens.issue(purpose, {"after": "fixture", "tenant": "tenant-a"})
    assert tokens.verify(purpose, value)["after"] == "fixture"
    others = {
        "TASK_LIST_CURSOR_V1",
        "TASK_NODE_CURSOR_V1",
        "TASK_EVENT_CHECKPOINT_V1",
        "LAUNCH_CURSOR_V1",
    } - {purpose}
    for other in others:
        with pytest.raises(OrbitError) as error:
            tokens.verify(other, value)
        assert error.value.code == "TOKEN_INVALID"
