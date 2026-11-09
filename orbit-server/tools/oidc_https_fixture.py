"""仅隔离验收的本机HTTPS IdP；真实签名、PKCE和一次性码，不引入生产身份切换。"""

import base64
import hashlib
import http.client
import json
import secrets
import ssl
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlencode, urlsplit

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from tls_fixture_server import ThreadedTlsFixtureServer


class LocalOidcFixture:
    issuer = "https://orbit-idp.fixture.example"
    client_id = "orbit-https-fixture"
    redirect_uri = "https://app.fixture.example/auth/callback"
    subject = "Stable-Fixture-Subject"
    email = "verified-fixture@example.org"
    email_verified = True

    def __enter__(self):
        self.client_secret = secrets.token_urlsafe(32)
        self.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.codes = {}
        self.lock = threading.Lock()
        self.exchanges = 0
        self.notifications = []
        self.notification_mode = "accepted"
        self.browser_accounts = {}
        self.entered, self.release = threading.Event(), threading.Event()
        self.release.set()
        self.directory = tempfile.TemporaryDirectory(prefix="orbit-local-oidc-")
        tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "orbit-idp.fixture.example")])
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(tls_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("orbit-idp.fixture.example"),
                        x509.DNSName("app.fixture.example"),
                        x509.IPAddress(ip_address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .sign(tls_key, hashes.SHA256())
        )
        self.ca_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
        cert_path, key_path = (
            Path(self.directory.name) / "cert.pem",
            Path(self.directory.name) / "key.pem",
        )
        cert_path.write_text(self.ca_pem, encoding="ascii")
        key_path.write_bytes(
            tls_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        self.server_ssl_context = context
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def send_json(self, value, status=200):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                target = urlsplit(self.path)
                if target.path == "/.well-known/openid-configuration":
                    self.send_json(
                        {
                            "issuer": fixture.issuer,
                            "authorization_endpoint": fixture.issuer + "/authorize",
                            "token_endpoint": fixture.issuer + "/token",
                            "jwks_uri": fixture.issuer + "/keys",
                            "response_types_supported": ["code"],
                            "id_token_signing_alg_values_supported": ["RS256"],
                            "code_challenge_methods_supported": ["S256"],
                        }
                    )
                elif target.path == "/keys":
                    self.send_json(
                        {
                            "keys": [
                                json.loads(
                                    jwt.algorithms.RSAAlgorithm.to_jwk(
                                        fixture.signing_key.public_key()
                                    )
                                )
                                | {"kid": "fixture-signing"}
                            ]
                        }
                    )
                elif target.path == "/authorize":
                    values = parse_qs(target.query)
                    if (
                        values.get("client_id") != [fixture.client_id]
                        or values.get("redirect_uri") != [fixture.redirect_uri]
                        or values.get("response_type") != ["code"]
                        or values.get("code_challenge_method") != ["S256"]
                    ):
                        self.send_json({"error": "invalid_request"}, 400)
                        return
                    code = secrets.token_urlsafe(32)
                    with fixture.lock:
                        cookies = SimpleCookie()
                        cookies.load(self.headers.get("Cookie", ""))
                        project = cookies.get("fixture_project")
                        account = fixture.browser_accounts.get(project.value) if project else None
                        fixture.codes[code] = (
                            values["code_challenge"][0],
                            values["nonce"][0],
                            time.time(),
                            dict(account) if account else None,
                        )
                    self.send_response(302)
                    self.send_header(
                        "Location",
                        fixture.redirect_uri
                        + "?"
                        + urlencode(
                            {
                                "code": code,
                                "state": values["state"][0],
                            }
                        ),
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self.send_json({"error": "not_found"}, 404)

            def do_POST(self):
                if self.path == "/notifications":
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 16384:
                        self.send_json({"error": "invalid_payload"}, 400)
                        return
                    content = self.rfile.read(length)
                    with fixture.lock:
                        fixture.notifications.append((content, dict(self.headers)))
                    mode = fixture.notification_mode
                    if mode == "disconnect":
                        self.close_connection = True
                        return
                    if mode == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "https://other.fixture.example/notifications")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if mode == "server-error":
                        self.send_json({"error": "untrusted-sensitive-detail"}, 503)
                        return
                    if mode == "invalid-json":
                        self.send_json({"accepted": "true"})
                        return
                    self.send_json(
                        {
                            "delivery_id": "wrong"
                            if mode == "wrong-id"
                            else json.loads(content)["delivery_id"],
                            "accepted": mode != "rejected",
                        }
                    )
                    return
                if self.path != "/token":
                    self.send_json({"error": "not_found"}, 404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 16384:
                        raise ValueError
                    values = parse_qs(self.rfile.read(length).decode())
                    scheme, encoded = self.headers.get("Authorization", "").split(" ", 1)
                    client, secret = base64.b64decode(encoded, validate=True).decode().split(":", 1)
                    if (
                        scheme != "Basic"
                        or unquote_plus(client) != fixture.client_id
                        or unquote_plus(secret) != fixture.client_secret
                        or values.get("redirect_uri") != [fixture.redirect_uri]
                        or values.get("grant_type") != ["authorization_code"]
                    ):
                        raise ValueError
                    with fixture.lock:
                        fixture.exchanges += 1
                        grant = fixture.codes.pop(values.get("code", [""])[0], None)
                    challenge = (
                        base64.urlsafe_b64encode(
                            hashlib.sha256(values.get("code_verifier", [""])[0].encode()).digest()
                        )
                        .rstrip(b"=")
                        .decode()
                    )
                    if grant is None or grant[0] != challenge or time.time() - grant[2] >= 300:
                        raise ValueError
                    fixture.entered.set()
                    if not fixture.release.wait(10):
                        raise ValueError
                    now = int(time.time())
                    token = jwt.encode(
                        {
                            "iss": fixture.issuer,
                            "sub": grant[3]["subject"] if grant[3] else fixture.subject,
                            "aud": fixture.client_id,
                            "nonce": grant[1],
                            "iat": now,
                            "exp": now + 300,
                            "email": grant[3]["email"] if grant[3] else fixture.email,
                            "email_verified": fixture.email_verified,
                        },
                        fixture.signing_key,
                        algorithm="RS256",
                        headers={"kid": "fixture-signing"},
                    )
                    self.send_json({"id_token": token, "access_token": "fixture-not-retained"})
                except (ValueError, UnicodeError):
                    self.send_json({"error": "invalid_grant"}, 400)

        self.server = ThreadedTlsFixtureServer(("127.0.0.1", 0), Handler, context)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def authorize(self, url):
        target = urlsplit(url)
        if target.scheme != "https" or target.netloc != "orbit-idp.fixture.example":
            raise ValueError("只能访问本次隔离IdP")
        connection = http.client.HTTPSConnection(
            "127.0.0.1",
            self.port,
            timeout=5,
            context=ssl.create_default_context(cadata=self.ca_pem),
        )
        try:
            connection.request("GET", target.path + "?" + target.query)
            response = connection.getresponse()
            assert response.status == 302
            return response.getheader("Location")
        finally:
            connection.close()

    def __exit__(self, *_args):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()
