"""实际HTTP后台及HTTPS IdP往返；预置既有身份绑定，首次邀请激活另行验收。"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

OIDC_CALLBACK_CASES = [
    "pythonOidcHttpAuthorizationStartAndActualHttpsCallback",
    "pythonOidcHttpCallbackOnceAndBrowserBinding",
    "pythonOidcHttpNonceMismatchAndNoIdentityByEmail",
    "pythonOidcHttpCallbackFinalAuditRollback",
    "pythonOidcHttpInFlightConfigurationChangeRejectsCookie",
]


def run_oidc_callback_checks(client, admin, cipher, provider, actor, idp, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT email FROM sys_user WHERE user_id=%s", (actor,))
        idp.email = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE orbit_system_configuration SET settings_json=%s,secrets_json=%s WHERE id=%s",
            (
                json.dumps(
                    {
                        "issuer": idp.issuer,
                        "clientId": idp.client_id,
                        "redirectUri": idp.redirect_uri,
                    }
                ),
                json.dumps(
                    {
                        "clientSecret": cipher.encrypt(
                            idp.client_secret,
                            "00000000-0000-0000-0000-000000000001",
                            provider,
                            "clientSecret",
                        )
                    }
                ),
                provider,
            ),
        )
        cursor.execute(
            "UPDATE orbit_external_identity SET issuer=%s,issuer_digest=%s,"
            "subject=%s,subject_digest=%s "
            "WHERE user_id=%s",
            (
                idp.issuer,
                hashlib.sha256(idp.issuer.encode()).digest(),
                idp.subject,
                hashlib.sha256(idp.subject.encode()).digest(),
                actor,
            ),
        )

    def start():
        response = client.post(
            "/api/v1/auth/authorization-sessions",
            headers={"Origin": "https://app.fixture.example"},
            json={"return_to": "/orbit/users"},
        )
        assert response.status_code == 200 and set(response.json()) == {
            "authorize_url",
            "expires_at",
        }
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        binding = cookie["__Host-orbit_browser"].value
        return response.json()["authorize_url"], binding

    def callback(location, binding):
        return client.get(
            "/api/v1/auth/callback?" + urlsplit(location).query,
            headers={"Cookie": "__Host-orbit_browser=" + binding},
        )

    def count_sessions():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_browser_session WHERE provider_id=%s", (provider,)
            )
            return cursor.fetchone()[0]

    url, binding = start()
    location = idp.authorize(url)
    response = callback(location, binding)
    assert response.status_code == 200 and response.json()["user"]["email"] == idp.email
    assert response.json()["user"]["identity_status"] == "OIDC_VERIFIED"
    assert response.headers["x-orbit-return-to"] == "%2Forbit%2Fusers"
    assert "id_token" not in response.text and "access_token" not in response.text
    issued = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        issued.load(header)
        assert "HttpOnly" in header and "Secure" in header and "SameSite=lax" in header
        assert "Domain=" not in header and "Path=/" in header
    pair = (
        "adpilot_session=" + issued["adpilot_session"].value + "; __Host-orbit_browser=" + binding
    )
    session = client.get("/api/v1/auth/session", headers={"Cookie": pair})
    assert session.status_code == 200 and session.json()["user"] == response.json()["user"]
    assert client.get("/getInfo", headers={"Cookie": pair}).json()["user"]["userId"] == actor
    cases.append(OIDC_CALLBACK_CASES[0])
    exchanges = idp.exchanges
    assert callback(location, binding).status_code == 401 and idp.exchanges == exchanges
    url, binding = start()
    location = idp.authorize(url)
    assert callback(location, "x" * 43).status_code == 401 and idp.exchanges == exchanges
    assert callback(location, binding).status_code == 200 and idp.exchanges == exchanges + 1
    cases.append(OIDC_CALLBACK_CASES[1])
    before = count_sessions()
    url, binding = start()
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    query["nonce"] = ["n" * 43]
    wrong_nonce = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
    assert callback(idp.authorize(wrong_nonce), binding).status_code == 401
    original_subject = idp.subject
    try:
        idp.subject = "Unbound-Subject-Same-Email"
        url, binding = start()
        rejected = callback(idp.authorize(url), binding)
        assert rejected.status_code == 403 and rejected.json()["code"] == "OIDC_INVITATION_REQUIRED"
    finally:
        idp.subject = original_subject
    assert count_sessions() == before
    cases.append(OIDC_CALLBACK_CASES[2])
    url, binding = start()
    location = idp.authorize(url)
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER oidc_session_audit_fail BEFORE INSERT ON orbit_auth_audit "
            "FOR EACH ROW BEGIN IF NEW.action='SESSION_CREATED' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture OIDC audit failure'; END IF; END"
        )
    try:
        failed = callback(location, binding)
        assert failed.status_code == 503 and "set-cookie" not in failed.headers
        assert count_sessions() == before
        exchanges = idp.exchanges
        assert callback(location, binding).status_code == 401 and idp.exchanges == exchanges
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS oidc_session_audit_fail")
    cases.append(OIDC_CALLBACK_CASES[3])
    url, binding = start()
    location = idp.authorize(url)
    idp.entered.clear()
    idp.release.clear()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(callback, location, binding)
            assert idp.entered.wait(4)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=2 WHERE id=%s", (provider,)
                )
            idp.release.set()
            changed = future.result(timeout=8)
            assert changed.status_code == 409 and "set-cookie" not in changed.headers
            assert count_sessions() == before
    finally:
        idp.release.set()
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_system_configuration SET revision=1 WHERE id=%s", (provider,)
            )
    cases.append(OIDC_CALLBACK_CASES[4])
