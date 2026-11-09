"""隔离Graph协议夹具；仅显式测试使用，不挂入生产应用或读取真实Token。"""

import json
import ssl
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpcore
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from orbit_api.account_platform import (
    MetaAccountPlatform,
    MetaReadConfiguration,
)


@contextmanager
def local_graph(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "graph.facebook.com")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("graph.facebook.com")]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert = certificate.public_bytes(serialization.Encoding.PEM)
    cert_path, key_path = tmp_path / "fixture-cert.pem", tmp_path / "fixture-key.pem"
    cert_path.write_bytes(cert)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    state = SimpleNamespace(mode="normal", requests=[], external_id="001")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state.requests.append((self.command, self.path, dict(self.headers)))
            path, params = urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)
            if state.mode == "disconnect":
                self.connection.close()
                return
            status, body = 200, None
            if state.mode == "redirect":
                status, body = 302, {}
            elif state.mode == "rate":
                status, body = 429, {"error": {"message": "fixture-secret-token"}}
            elif state.mode == "forbidden":
                status, body = 403, {"error": {"message": "fixture-secret-token"}}
            elif state.mode == "graph-error":
                body = {"error": {"code": 190, "message": "fixture-secret-token"}}
            elif state.mode == "graph-rate":
                status, body = 400, {"error": {"code": 4, "message": "fixture-secret-token"}}
            elif state.mode == "graph-transient":
                status, body = 400, {"error": {"code": 2, "is_transient": True}}
            elif state.mode == "server-error":
                status, body = 503, {"message": "fixture-secret-token"}
            elif path.endswith("/owned_ad_accounts"):
                body = {
                    "data": []
                    if state.mode in {"missing", "client"}
                    else [{"id": "act_" + state.external_id, "account_id": state.external_id}]
                }
                if state.mode == "scope-incomplete":
                    body = {
                        "data": [],
                        "paging": {
                            "next": "https://evil.example/?access_token=secret",
                            "cursors": {"after": "same"},
                        },
                    }
                elif state.mode == "paged" and "after" not in params:
                    body = {
                        "data": [],
                        "paging": {
                            "next": "https://evil.example/?access_token=secret",
                            "cursors": {"after": "cursor-two"},
                        },
                    }
            elif path.endswith("/client_ad_accounts"):
                body = {
                    "data": [{"id": "act_" + state.external_id, "account_id": state.external_id}]
                    if state.mode == "client"
                    else []
                }
            else:
                body = {
                    "id": "act_" + state.external_id,
                    "account_id": state.external_id,
                    "name": "平台账户原名",
                    "currency": "USD",
                    "timezone_name": "America/New_York",
                    "account_status": 1,
                }
                if state.mode == "wrong-id":
                    body["account_id"] = "999"
                elif state.mode == "missing-field":
                    del body["timezone_name"]
                elif state.mode == "invalid-name":
                    body["name"] = "\ud800"
                elif state.mode == "long-name":
                    body["name"] = "名" * 10000
                elif state.mode == "bad-request-metadata":
                    status = 400
            content = json.dumps(body).encode()
            if state.mode == "duplicate-json":
                content = b'{"data":[],"data":[]}'
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "https://evil.example")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class Network(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "graph.facebook.com" and port == 443
            return await httpcore.AnyIOBackend().connect_tcp(
                "127.0.0.1", server.server_port, **kwargs
            )

    state.reader = MetaAccountPlatform(
        MetaReadConfiguration("42", "v25.0", "fixture-secret-token"),
        network_backend=Network(),
        ssl_context=ssl.create_default_context(cadata=cert.decode()),
    )

    def factory(configuration):
        return MetaAccountPlatform(
            configuration,
            network_backend=Network(),
            ssl_context=ssl.create_default_context(cadata=cert.decode()),
        )

    state.factory = factory
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
