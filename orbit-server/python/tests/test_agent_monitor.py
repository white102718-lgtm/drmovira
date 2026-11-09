"""设备监测协议纯测；真实mTLS/MySQL验收由主线独立执行。"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError


def uid(n):
    return str(UUID(int=n))


def heartbeat(**changes):
    return {
        "agent_id": uid(1),
        "boot_id": uid(2),
        "seq": 1,
        "profiles": [],
        "observed_at": "2026-11-09T00:00:00Z",
    } | changes


def test_original_heartbeat_shape_and_no_claimed_identity():
    from orbit_api.agent_monitor_contract import parse_heartbeat

    assert parse_heartbeat(json.dumps(heartbeat()).encode())["seq"] == 1
    profile = {
        "id": uid(3),
        "agent_id": uid(1),
        "external_profile_id": "p1",
        "process_state": "ACTIVE",
        "identity_state": "VALID",
        "account_ids": [],
        "observed_at": "2026-11-09T00:00:00Z",
    }
    with pytest.raises(OrbitError):
        parse_heartbeat(json.dumps(heartbeat(profiles=[profile])).encode())


@pytest.mark.parametrize(
    "change",
    [{"seq": True}, {"seq": 0}, {"token": "secret"}, {"observed_at": "2026-11-09T00:00:00"}],
)
def test_heartbeat_rejects_unsafe_or_untyped_fields(change):
    from orbit_api.agent_monitor_contract import parse_heartbeat

    with pytest.raises(OrbitError):
        parse_heartbeat(json.dumps(heartbeat(**change)).encode())


@pytest.mark.parametrize(
    "previous,seq,elapsed,streak,expected",
    [(None, 1, 0, 0, 1), (1, 2, 15, 1, 2), (1, 3, 15, 1, 1), (2, 3, 91, 2, 1)],
)
def test_recovery_requires_two_contiguous_fresh_sequences(previous, seq, elapsed, streak, expected):
    from orbit_api.agent_monitor_contract import recovery_streak

    assert recovery_streak(previous, seq, elapsed, streak) == expected


def test_tls_peer_cannot_come_from_headers():
    from orbit_api.agent_monitor_transport import peer_certificate

    scope = {
        "type": "http",
        "scheme": "https",
        "headers": [(b"x-client-cert", b"fake"), (b"x-agent-id", uid(1).encode())],
    }
    with pytest.raises(OrbitError) as error:
        peer_certificate(scope)
    assert error.value.status == 401


@pytest.fixture
def certificates(tmp_path):
    from datetime import timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "isolated-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None), critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )

    def leaf(cn, server=False):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        san = (
            [x509.DNSName("localhost")]
            if server
            else [x509.UniformResourceIdentifier("urn:orbit:tenant:" + uid(9))]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(minutes=30))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
            )
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        return key, cert

    server_key, server = leaf("localhost", True)
    client_key, client = leaf(uid(1))
    for name, value in (("ca", ca), ("server", server), ("client", client)):
        (tmp_path / (name + ".pem")).write_bytes(value.public_bytes(serialization.Encoding.PEM))
    for name, key in (("server", server_key), ("client", client_key)):
        path = tmp_path / (name + ".key")
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        path.chmod(0o600)
    return tmp_path, client.public_bytes(serialization.Encoding.DER)


def test_registration_verifies_real_signed_leaf_binding(certificates):
    from orbit_api.agent_monitor_store import certificate_metadata

    path, der = certificates
    result = certificate_metadata(
        (path / "client.pem").read_bytes(), (path / "ca.pem").read_bytes(), uid(9), uid(1)
    )
    import hashlib

    assert result["fingerprint_sha256"] == hashlib.sha256(der).hexdigest()
    for tenant, agent in ((uid(8), uid(1)), (uid(9), uid(2))):
        with pytest.raises(OrbitError):
            certificate_metadata(
                (path / "client.pem").read_bytes(), (path / "ca.pem").read_bytes(), tenant, agent
            )
    with pytest.raises(OrbitError):
        certificate_metadata(
            (path / "server.pem").read_bytes(), (path / "ca.pem").read_bytes(), uid(9), uid(1)
        )


def tls_pair(path, with_client_certificate=True):
    import ssl

    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(path / "server.pem", path / "server.key")
    server.verify_mode = ssl.CERT_REQUIRED
    server.load_verify_locations(path / "ca.pem")
    client = ssl.create_default_context(cafile=str(path / "ca.pem"))
    if with_client_certificate:
        client.load_cert_chain(path / "client.pem", path / "client.key")
    si, so, ci, co = (ssl.MemoryBIO() for _ in range(4))
    ss = server.wrap_bio(si, so, server_side=True)
    cs = client.wrap_bio(ci, co, server_side=False, server_hostname="localhost")
    done = set()
    for _ in range(30):
        for name, obj in (("client", cs), ("server", ss)):
            try:
                obj.do_handshake()
                done.add(name)
            except ssl.SSLWantReadError:
                pass
        for output, target in ((co, si), (so, ci)):
            packet = output.read()
            if packet:
                target.write(packet)
        if len(done) == 2:
            return ss
    raise AssertionError("TLS handshake did not complete")


async def test_real_mutual_tls_peer_der_is_injected_by_protocol(certificates):
    import uvicorn
    from uvicorn.server import ServerState

    from orbit_api.agent_monitor_transport import PeerCertificateH11Protocol, peer_certificate

    path, der = certificates
    ssl_object = tls_pair(path)
    recorded = []

    async def app(scope, receive, send):
        recorded.append(peer_certificate(scope))

    config = uvicorn.Config(app, proxy_headers=False, lifespan="off", access_log=False)
    config.load()
    protocol = PeerCertificateH11Protocol(config, ServerState(), {})

    class Transport:
        def get_extra_info(self, name):
            return (
                ssl_object
                if name == "ssl_object"
                else ("127.0.0.1", 12345)
                if name in {"sockname", "peername"}
                else None
            )

    protocol.connection_made(Transport())
    await protocol.app(
        {"type": "http", "scheme": "https", "headers": [(b"x-client-cert", b"fake")]}, None, None
    )
    assert recorded == [der]


def test_real_tls_handshake_rejects_missing_client_cert(certificates):
    import ssl

    with pytest.raises(ssl.SSLError):
        tls_pair(certificates[0], False)


async def test_duplicate_heartbeat_returns_original_ack_without_refresh(monkeypatch):
    from unittest.mock import AsyncMock

    from orbit_api import agent_monitor_store as module

    now = datetime.now(UTC)
    value = heartbeat()
    p = {"tenant": uid(9), "agent": uid(1)}
    ack = {"id": uid(1), "revision": 1, "state": "SUSPECT", "request_id": uid(11)}
    store = module.AgentMonitorStore()
    store.authenticate = AsyncMock(return_value=(p, now))
    store.head = AsyncMock(return_value={"boot_id": uid(2), "last_seq": 1})

    async def one(session, sql, params):
        if "orbit_agent_boot" in sql:
            return {"retired_at": None}
        return {"payload_hash": module.access.digest(value), "ack_json": ack}

    monkeypatch.setattr(module, "one", one)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=AssertionError("duplicate cannot refresh"))
    )
    assert await store.heartbeat(session, b"der", value, uid(12)) == ack


async def test_retired_boot_rejected_before_receipt_replay(monkeypatch):
    from unittest.mock import AsyncMock

    from orbit_api import agent_monitor_store as module

    now = datetime.now(UTC)
    store = module.AgentMonitorStore()
    store.authenticate = AsyncMock(return_value=({"tenant": uid(9), "agent": uid(1)}, now))
    store.head = AsyncMock(return_value={"boot_id": uid(3), "last_seq": 1})
    monkeypatch.setattr(module, "one", AsyncMock(return_value={"retired_at": now}))
    with pytest.raises(OrbitError) as error:
        await store.heartbeat(object(), b"der", heartbeat(), uid(12))
    assert error.value.code == "AGENT_BOOT_RETIRED"


@pytest.mark.parametrize(
    "sequence,seconds,code", [(1, 0, "AGENT_SEQUENCE_STALE"), (2, 91, "AGENT_SEQUENCE_STALE")]
)
def test_old_report_never_refreshes_identity(sequence, seconds, code):
    from datetime import timedelta

    from orbit_api.agent_monitor_store import AgentMonitorStore

    now = datetime.now(UTC)
    head = {"boot_id": uid(2), "last_seq": 2, "received_at": now - timedelta(seconds=seconds)}
    with pytest.raises(OrbitError) as caught:
        AgentMonitorStore().current_report(head, heartbeat(seq=sequence), now)
    assert caught.value.code == code


async def test_device_database_failure_is_safe_503_without_exception_text(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    import httpx

    from orbit_api import agent_monitor_routes as module
    from orbit_api.agent_monitor_transport import DevicePeer

    @asynccontextmanager
    async def session(_):
        yield object()

    monkeypatch.setattr(module, "device_session", session)
    monkeypatch.setattr(
        module.AgentMonitorStore,
        "configuration",
        AsyncMock(side_effect=RuntimeError("secret-db-value")),
    )
    app = module.create_device_app()

    async def trusted_fixture(scope, receive, send):
        scope["orbit.device_peer"] = DevicePeer(b"fixture-der")
        await app(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted_fixture, raise_app_exceptions=False),
        base_url="https://localhost",
    ) as client:
        response = await client.get("/api/v1/agent-api/configuration")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "secret-db-value" not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_identity_replay_uses_current_lock_read_and_never_rewrites(monkeypatch):
    from unittest.mock import AsyncMock

    from orbit_api import agent_monitor_store as module

    now = datetime.now(UTC)
    value = heartbeat(seq=2, observed_at=now.isoformat())
    value.pop("profiles")
    value.update(
        event_id=uid(12),
        binding_id=uid(13),
        binding_revision=1,
        profile_external_id="profile",
        identity_state="UNKNOWN",
        external_account_id=None,
        currency=None,
        evidence_sha256="a" * 64,
        adapter_version="ADSPOWER_META_DOM_V1",
    )
    p = {"tenant": uid(9), "agent": uid(1)}
    head = {"boot_id": uid(2), "last_seq": 2, "received_at": now, "recovery_streak": 2}
    binding = {
        "agent_id": uid(1),
        "unbound_at": None,
        "account_unbound": None,
        "owner_user_id": uid(4),
        "current_owner": uid(4),
        "owner_team_id": uid(5),
        "current_team": uid(5),
        "revision": 1,
        "profile_external_id": "profile",
    }
    ack = {"id": uid(1), "revision": 2, "state": "IDENTITY_RECORDED", "request_id": uid(14)}
    store = module.AgentMonitorStore()
    store.authenticate = AsyncMock(return_value=(p, now))
    store.head = AsyncMock(return_value=head)
    monkeypatch.setattr(module, "many", AsyncMock(return_value=[binding]))

    async def receipt(session, sql, params):
        assert "orbit_agent_identity_report" in sql and "FOR SHARE" in sql
        return {"payload_hash": module.access.digest(value), "ack_json": ack}

    monkeypatch.setattr(module, "one", receipt)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=AssertionError("replay must not write"))
    )
    assert await store.identity_report(session, b"der", value, uid(15)) == ack


@pytest.mark.parametrize("elapsed,expected", [(44.99, 2), (45, 1), (80, 1)])
def test_two_heartbeat_recovery_must_be_within_suspect_threshold(elapsed, expected):
    from orbit_api.agent_monitor_contract import recovery_streak

    assert recovery_streak(1, 2, elapsed, 1) == expected


@pytest.mark.parametrize(
    "adapter,accepted", [("ADSPOWER_META_DOM_V1", False), ("ADSPOWER_META_DOM_V2", True)]
)
def test_valid_identity_requires_current_same_page_adapter(adapter, accepted):
    from orbit_api.agent_monitor_contract import parse_identity

    value = heartbeat()
    value.pop("profiles")
    value.update(
        event_id=uid(12),
        binding_id=uid(13),
        binding_revision=1,
        profile_external_id="profile",
        identity_state="VALID",
        external_account_id="123",
        currency="USD",
        evidence_sha256="a" * 64,
        adapter_version=adapter,
    )
    raw = json.dumps(value).encode()
    if accepted:
        assert parse_identity(raw)["adapter_version"] == adapter
    else:
        with pytest.raises(OrbitError) as error:
            parse_identity(raw)
        assert error.value.code == "IDENTITY_ADAPTER_UNSUPPORTED"


async def test_binding_identity_read_rejects_legacy_valid_adapter():
    from orbit_api.agent_monitor_store import batch_binding_identities

    class Session:
        async def execute(self, query, parameters):
            assert "r.adapter_version='ADSPOWER_META_DOM_V2'" in str(query)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))

    result = await batch_binding_identities(Session(), uid(1), [{"id": uid(2)}])
    assert result == {uid(2): {"identity_state": "UNKNOWN", "verified_at": None}}


async def test_profile_binding_read_is_bounded_before_identity_resolution(monkeypatch):
    from unittest.mock import AsyncMock

    from orbit_api import agent_monitor_store as module
    from orbit_api.execution_agent_store import ExecutionAgentStore

    current = SimpleNamespace(
        tenant_id=uid(9), actor_id=1, subject_id=uid(4), data_role="SUPER_ADMIN"
    )
    monkeypatch.setattr(module.access, "context", AsyncMock(return_value=current))
    monkeypatch.setattr(module.access, "clock", AsyncMock(return_value=1))
    monkeypatch.setattr(ExecutionAgentStore, "row", AsyncMock(return_value={}))
    monkeypatch.setattr(
        "orbit_api.profile_binding_access.fingerprint", AsyncMock(return_value="scope")
    )
    monkeypatch.setattr(module, "now_utc", AsyncMock(return_value=datetime.now(UTC)))
    monkeypatch.setattr(
        module, "many", AsyncMock(return_value=[{"id": uid(7), "external_profile_id": "p"}])
    )
    identities = AsyncMock(
        side_effect=AssertionError("over-capacity must fail before identity lookup")
    )
    monkeypatch.setattr(module, "batch_binding_identities", identities)
    bindings = [{"id": uid(i + 100), "profile_external_id": "p"} for i in range(501)]
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: bindings))
        )
    )
    with pytest.raises(OrbitError) as caught:
        await module.list_profiles(session, 1, uid(1), {"q": "", "page_size": 200}, None, None)
    assert caught.value.code == "PROFILE_ACCOUNT_LIMIT"
    assert "LIMIT :binding_limit" in str(session.execute.await_args.args[0])
    assert session.execute.await_args.args[1]["binding_limit"] == 501
    identities.assert_not_awaited()


async def test_certificate_repeat_revoke_preserves_original_time(monkeypatch):
    from unittest.mock import AsyncMock

    from orbit_api import agent_monitor_store as module

    at = datetime.now(UTC)
    monkeypatch.setattr(module.access, "clock", AsyncMock(return_value=1))
    monkeypatch.setattr(module, "one", AsyncMock(return_value={"revoked_at": at}))
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=AssertionError("duplicate revoke must not write"))
    )
    result = await module.revoke_device_certificate(
        session, tenant_id=uid(9), agent_id=uid(1), fingerprint_sha256="a" * 64
    )
    assert result == {"fingerprint_sha256": "a" * 64, "revoked_at": module.stamp(at)}
