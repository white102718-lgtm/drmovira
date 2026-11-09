"""实际回环HTTPS服务验证TLS、流式上限和响应边界；DNS策略单独验证，不访问外网。"""

import asyncio
import ipaddress
import socket
import ssl
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpcore
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from orbit_api.errors import OrbitError
from orbit_api.oidc_http import OidcHttp, PublicNetworkBackend, public_address, secure_url


@pytest.mark.parametrize(
    "url",
    [
        "http://idp.example",
        "https://user:secret@idp.example",
        "https://idp.example/#fragment",
        "https://idp.example:8443",
        "https://idp.example\\@evil.example",
        "https://idp.example\n",
        "https://%31%32%37.0.0.1",
        "https://用户.example",
        "//idp.example",
        None,
    ],
)
def test_secure_url_rejects_ambiguous_or_non_https_targets(url):
    with pytest.raises(OrbitError):
        secure_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "192.168.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",
    ],
)
def test_private_metadata_multicast_and_mapped_loopback_are_rejected(address):
    assert not public_address(address)


@pytest.mark.asyncio
async def test_dns_is_checked_once_and_connection_uses_validated_numeric_ip(monkeypatch):
    lookup = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    backend = PublicNetworkBackend()
    connector = AsyncMock(return_value="stream-fixture")
    monkeypatch.setattr(backend.backend, "connect_tcp", connector)
    assert await backend.connect_tcp("trusted.example", 443) == "stream-fixture"
    lookup.assert_awaited_once()
    assert connector.call_args.args == ("8.8.8.8", 443)
    assert ipaddress.ip_address(connector.call_args.args[0]).is_global


@pytest.mark.asyncio
async def test_mixed_public_and_private_dns_answer_rejects_before_connection(monkeypatch):
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in ["8.8.8.8", "127.0.0.1"]
    ]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=answers))
    backend = PublicNetworkBackend()
    connector = AsyncMock()
    monkeypatch.setattr(backend.backend, "connect_tcp", connector)
    with pytest.raises(OrbitError):
        await backend.connect_tcp("trusted.example", 443)
    connector.assert_not_awaited()


@pytest_asyncio.fixture
async def tls_endpoint(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.fixture.example")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("idp.fixture.example")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(pem)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    received = []
    routes = {}

    async def serve(reader, writer):
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            line = header.split(b"\r\n", 1)[0]
            length = next(
                (
                    int(h.split(b":", 1)[1])
                    for h in header.split(b"\r\n")
                    if h.lower().startswith(b"content-length:")
                ),
                0,
            )
            body = await reader.readexactly(length) if length else b""
            received.append((line, body))
            path = line.split(b" ")[1]
            if path == b"/disconnect":
                return
            payload = {
                b"/valid": b'{"issuer":"fixture"}',
                b"/duplicate": b'{"sub":"first","sub":"second"}',
                b"/nan": b'{"exp":NaN}',
                b"/huge": b'{"value":"' + b"x" * 65536 + b'"}',
                b"/array": b"[]",
            }.get(path, b"{}")
            if path in routes:
                import json

                value = routes[path]
                payload = json.dumps(value(header, body) if callable(value) else value).encode()
            status = b"302 Found" if path == b"/redirect" else b"200 OK"
            media = b"text/html" if path == b"/html" else b"application/json"
            writer.write(
                b"HTTP/1.1 "
                + status
                + b"\r\nContent-Type: "
                + media
                + b"\r\nContent-Length: "
                + str(len(payload)).encode()
                + b"\r\nLocation: https://evil.fixture.example/\r\nConnection: close\r\n\r\n"
                + payload
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0, ssl=server_context)
    fixture_port = server.sockets[0].getsockname()[1]

    class FixtureBackend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "idp.fixture.example" and port == 443
            return await httpcore.AnyIOBackend().connect_tcp("127.0.0.1", fixture_port, **kwargs)

    context = ssl.create_default_context(cadata=pem.decode())
    async with server:
        yield (
            OidcHttp(network_backend=FixtureBackend(), ssl_context=context),
            received,
            FixtureBackend(),
            routes,
        )


@pytest.mark.asyncio
async def test_actual_tls_json_get_and_post_preserve_body(tls_endpoint):
    client, received, _, _ = tls_endpoint
    assert await client.json("GET", "https://idp.fixture.example/valid") == {"issuer": "fixture"}
    assert await client.json("POST", "https://idp.fixture.example/valid", content=b"code=fixture")
    assert received == [(b"GET /valid HTTP/1.1", b""), (b"POST /valid HTTP/1.1", b"code=fixture")]


@pytest.mark.parametrize("path", ["duplicate", "nan", "huge", "array", "html", "redirect"])
@pytest.mark.asyncio
async def test_tls_response_bounds_and_no_redirect(path, tls_endpoint):
    client, received, _, _ = tls_endpoint
    with pytest.raises(OrbitError) as failure:
        await client.json("GET", "https://idp.fixture.example/" + path)
    assert failure.value.status == 502 and len(received) == 1


@pytest.mark.asyncio
async def test_untrusted_certificate_fails_and_post_disconnect_is_unknown(tls_endpoint):
    client, received, backend, _ = tls_endpoint
    with pytest.raises(OrbitError) as untrusted:
        await OidcHttp(network_backend=backend).json("GET", "https://idp.fixture.example/valid")
    assert untrusted.value.code == "OIDC_PROVIDER_UNAVAILABLE" and received == []
    with pytest.raises(OrbitError) as unknown:
        await client.json("POST", "https://idp.fixture.example/disconnect", content=b"code=fixture")
    assert unknown.value.code == "OIDC_EXCHANGE_UNKNOWN" and len(received) == 1


@pytest.mark.asyncio
async def test_actual_https_discovery_pkce_code_exchange_and_rsa_identity(tls_endpoint):
    import base64
    import hashlib
    import json
    import time
    from urllib.parse import parse_qs, quote_plus, urlsplit

    import jwt

    from orbit_api.oidc_contract import opaque_token
    from orbit_api.oidc_provider import OidcProvider, ProviderConfiguration

    http, received, _, routes = tls_endpoint
    issuer = "https://idp.fixture.example"
    config = ProviderConfiguration(
        issuer, "fixture-client", "https://app.fixture.example/callback", "a:b +secret"
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": "fixture"}
    routes[b"/.well-known/openid-configuration"] = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/keys",
        "response_types_supported": ["code"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
    }
    routes[b"/keys"] = {"keys": [jwk]}
    provider = OidcProvider(config, http=http)
    metadata = await provider.discover()
    verifier, nonce, state = opaque_token(), opaque_token(), opaque_token()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    url = provider.authorization_url(metadata, state, nonce, challenge)
    params = parse_qs(urlsplit(url).query)
    assert params["state"] == [state] and params["nonce"] == [nonce]
    assert params["code_challenge_method"] == ["S256"] and params["code_challenge"] == [challenge]
    assert params["redirect_uri"] == [config.redirect_uri] and params["scope"] == ["openid email"]
    used = set()
    now = int(time.time())

    def exchange(header, body):
        fields = parse_qs(body.decode())
        code = fields["code"][0]
        if code in used:
            return {"error": "invalid_grant"}
        assert fields["code_verifier"] == [verifier]
        assert fields["redirect_uri"] == [config.redirect_uri]
        assert fields["grant_type"] == ["authorization_code"]
        credentials = (
            quote_plus(config.client_id) + ":" + quote_plus(config.client_secret)
        ).encode()
        assert b"Authorization: Basic " + base64.b64encode(credentials) in header
        assert "client_secret" not in fields
        used.add(code)
        token = jwt.encode(
            {
                "iss": issuer,
                "sub": "Stable-Case-Sensitive-Subject",
                "aud": config.client_id,
                "nonce": nonce,
                "iat": now,
                "exp": now + 300,
                "email": "invitee@example.org",
                "email_verified": True,
            },
            key,
            algorithm="RS256",
            headers={"kid": "fixture"},
        )
        return {
            "id_token": token,
            "access_token": "fixture-not-returned",
            "refresh_token": "fixture-not-returned",
        }

    routes[b"/token"] = exchange
    identity = await provider.exchange(
        metadata, "one-use-code", verifier, nonce=nonce, now=now, issued_after=now
    )
    assert identity.subject == "Stable-Case-Sensitive-Subject"
    assert identity.verified_email == "invitee@example.org" and identity.issuer == issuer
    assert not hasattr(identity, "access_token") and not hasattr(identity, "refresh_token")
    with pytest.raises(OrbitError) as replay:
        await provider.exchange(
            metadata, "one-use-code", verifier, nonce=nonce, now=now, issued_after=now
        )
    assert replay.value.code == "OIDC_EXCHANGE_FAILED"
    assert len(received) == 4 and len(used) == 1
