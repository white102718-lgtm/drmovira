"""提供者发现约束与交换失败策略；实际TLS交换另见test_oidc_http。"""

import copy
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import pytest

from orbit_api.errors import OrbitError
from orbit_api.oidc_provider import OidcProvider, ProviderConfiguration

ISSUER = "https://trusted.fixture.example"
CONFIGURATION = ProviderConfiguration(
    ISSUER, "fixture", "https://app.fixture.example/callback", "secret"
)
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": ISSUER + "/authorize",
    "token_endpoint": ISSUER + "/token",
    "jwks_uri": ISSUER + "/keys",
    "response_types_supported": ["code"],
    "id_token_signing_alg_values_supported": ["RS256"],
    "code_challenge_methods_supported": ["S256"],
}


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", ISSUER + "/"),
        ("issuer", "https://TRUSTED.fixture.example"),
        ("authorization_endpoint", "http://trusted.fixture.example/authorize"),
        ("token_endpoint", "https://other.fixture.example/token"),
        ("jwks_uri", "https://user:secret@trusted.fixture.example/keys"),
        ("jwks_uri", ISSUER + "/keys?source=untrusted"),
        ("response_types_supported", ["token"]),
        ("response_types_supported", "code"),
        ("id_token_signing_alg_values_supported", ["HS256"]),
        ("code_challenge_methods_supported", ["plain"]),
        ("token_endpoint_auth_methods_supported", ["none"]),
        ("token_endpoint_auth_methods_supported", "client_secret_basic"),
    ],
)
@pytest.mark.asyncio
async def test_discovery_rejects_identity_mismatch_weak_flow_and_endpoint_injection(field, value):
    http = AsyncMock()
    http.json.return_value = copy.deepcopy(DISCOVERY) | {field: value}
    with pytest.raises(OrbitError) as failure:
        await OidcProvider(CONFIGURATION, http=http).discover()
    assert failure.value.code == "OIDC_DISCOVERY_INVALID"
    http.json.assert_awaited_once()


@pytest.mark.asyncio
async def test_secret_post_is_explicit_and_failed_exchange_is_not_retried():
    http = AsyncMock()
    http.json.side_effect = [
        DISCOVERY | {"token_endpoint_auth_methods_supported": ["client_secret_post"]},
        {"error": "invalid_grant", "error_description": "untrusted-sensitive-detail"},
    ]
    provider = OidcProvider(CONFIGURATION, http=http)
    metadata = await provider.discover()
    with pytest.raises(OrbitError) as failure:
        await provider.exchange(
            metadata, "code", "v" * 43, nonce="n" * 43, now=100, issued_after=100
        )
    assert failure.value.code == "OIDC_EXCHANGE_FAILED"
    assert "untrusted-sensitive-detail" not in str(failure.value)
    assert http.json.await_count == 2
    request = http.json.await_args
    assert request.args == ("POST", ISSUER + "/token")
    assert not any(name.lower() == b"authorization" for name, _ in request.kwargs["headers"])
    body = parse_qs(request.kwargs["content"].decode())
    assert body["client_id"] == ["fixture"] and body["client_secret"] == ["secret"]


@pytest.mark.parametrize(
    "code,verifier", [(None, "v" * 43), ("code\n", "v" * 43), ("code", "short")]
)
@pytest.mark.asyncio
async def test_invalid_callback_is_rejected_before_network(code, verifier):
    http = AsyncMock()
    http.json.return_value = DISCOVERY
    provider = OidcProvider(CONFIGURATION, http=http)
    metadata = await provider.discover()
    with pytest.raises(OrbitError) as failure:
        await provider.exchange(metadata, code, verifier, nonce="n" * 43, now=100, issued_after=100)
    assert failure.value.code == "OIDC_CALLBACK_INVALID" and http.json.await_count == 1
