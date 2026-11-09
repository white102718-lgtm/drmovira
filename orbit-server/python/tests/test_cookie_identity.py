"""Cookie身份上下文隔离与CSRF兼容边界，不能用旧Bearer校验绕过Cookie失败。"""

import asyncio
import base64
import os
from datetime import datetime

import pytest

from orbit_api.cookie_identity import (
    CookieIdentity,
    CookieIdentityBoundary,
    current_cookie_identity,
    effective_csrf,
    verify_cookie_csrf,
)
from orbit_api.credentials import CredentialCipher
from orbit_api.errors import OrbitError


def identity(actor):
    return CookieIdentity(actor, "tenant", 1, "session", f"csrf-{actor}", datetime(2030, 1, 1))


@pytest.mark.asyncio
async def test_concurrent_contexts_and_exception_are_cleared():
    from orbit_api.cookie_identity import _identity

    entered = asyncio.Event()
    results = []

    async def app(scope, receive, send):
        assert current_cookie_identity() is None
        _identity.set(identity(scope["actor"]))
        entered.set()
        await asyncio.sleep(0)
        results.append(current_cookie_identity().actor_id)
        if scope["actor"] == 2:
            raise RuntimeError("fixture")

    boundary = CookieIdentityBoundary(app)
    outcomes = await asyncio.gather(
        boundary({"actor": 1}, None, None),
        boundary({"actor": 2}, None, None),
        return_exceptions=True,
    )
    assert entered.is_set() and sorted(results) == [1, 2]
    assert outcomes[0] is None and isinstance(outcomes[1], RuntimeError)
    assert current_cookie_identity() is None


@pytest.mark.asyncio
async def test_cookie_csrf_failure_cannot_fall_back_to_legacy():
    from orbit_api.cookie_identity import _identity

    assert effective_csrf(1, "legacy") == "legacy"
    assert verify_cookie_csrf(1, "legacy") is False
    token = _identity.set(identity(1))
    try:
        assert effective_csrf(1, "legacy") == "csrf-1"
        assert verify_cookie_csrf(1, "csrf-1") is True
        for actor, value in [(1, "legacy"), (2, "csrf-1"), (1, "非ASCII"), (1, None)]:
            with pytest.raises(OrbitError) as failure:
                verify_cookie_csrf(actor, value)
            assert failure.value.status == 403
        with pytest.raises(OrbitError):
            effective_csrf(2, "legacy")
    finally:
        _identity.reset(token)


def test_cookie_mac_is_domain_separated_and_retains_original_key_during_rotation():
    old = base64.b64encode(os.urandom(32)).decode()
    new = base64.b64encode(os.urandom(32)).decode()
    original = CredentialCipher("old", {"old": old})
    rotated = CredentialCipher("new", {"old": old, "new": new})
    body = b"fixture-session-context"
    purposes = ["DIRECTORY_CURSOR_V1", "DIRECTORY_CSRF_V1", "BROWSER_SESSION_CSRF_V1"]
    values = [original.application_mac(purpose, body) for purpose in purposes]
    assert len(set(values)) == 3
    assert rotated.application_mac(purposes[-1], body, "old") == values[-1]
    assert rotated.application_mac(purposes[-1], body) != values[-1]
    with pytest.raises(OrbitError):
        CredentialCipher("new", {"new": new}).application_mac(purposes[-1], body, "old")
    with pytest.raises(ValueError):
        original.application_mac("UNTRUSTED_PURPOSE", body)


def test_directory_capabilities_and_writes_share_cookie_csrf_without_bearer_fallback():
    from orbit_api.cookie_identity import _identity
    from orbit_api.directory_tokens import DirectoryTokens

    tokens = DirectoryTokens(CredentialCipher(None, {}))
    token = _identity.set(identity(1))
    try:
        binding = tokens.session_binding("ignored-bearer", 1, "tenant")
        assert binding == tokens.session_binding("", 1, "tenant")
        csrf = tokens.issue("DIRECTORY_CSRF_V1", {"binding": binding})
        assert csrf == "csrf-1"
        assert tokens.verify("DIRECTORY_CSRF_V1", csrf) == {"binding": binding}
        with pytest.raises(OrbitError):
            tokens.verify("DIRECTORY_CSRF_V1", "legacy-token")
        with pytest.raises(OrbitError):
            tokens.session_binding("", 1, "foreign-tenant")
        with pytest.raises(OrbitError):
            tokens.session_binding("", 2, "tenant")
    finally:
        _identity.reset(token)
