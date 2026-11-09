"""从隔离加密队列取得测试凭据，实际HTTPS验证首次绑定；通知投递另行验收。"""

import json
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from uuid import uuid4

INVITATION_ACTIVATION_CASES = [
    "pythonInvitationStartRejectsRevokedExpiredAndChangedSnapshots",
    "pythonInvitationRequiresVerifiedMatchingEmailBeforeBinding",
    "pythonInvitationActivationAuditFailureRollsBackBindingUserAndSession",
    "pythonInvitationAtomicOidcBindingClearsPasswordAndConsumesOnce",
    "pythonInvitationOidcAccountCannotGainNativePassword",
]


def run_invitation_activation_checks(
    client, admin, headers, user, caps, send, current, provider, cipher, idp, cases
):
    def payload(active=True):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT d.id,d.protected_json,i.id,i.expires_at FROM orbit_invitation_delivery d "
                "JOIN orbit_user_invitation i ON i.id=d.invitation_id WHERE i.provider_id=%s "
                "AND i.status=%s ORDER BY i.created_at DESC,i.id DESC LIMIT 1",
                (provider, "ACTIVE" if active else "REVOKED"),
            )
            delivery, encrypted, invitation, expires = cursor.fetchone()
        body = json.loads(
            cipher.decrypt_internal(
                json.loads(encrypted)["envelope"],
                "00000000-0000-0000-0000-000000000001",
                delivery,
                "invitation_delivery",
            )
        )
        return body["invitation_token"], invitation, expires

    def start(token):
        return client.post(
            "/api/v1/auth/invitation-authorization-sessions",
            headers={"Origin": "https://app.fixture.example"},
            json={"invitation_token": token, "return_to": "/index"},
        )

    def authorization(token):
        response = start(token)
        assert response.status_code == 200
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        return idp.authorize(response.json()["authorize_url"]), cookie["__Host-orbit_browser"].value

    def callback(location, binding):
        return client.get(
            "/api/v1/auth/callback?" + urlsplit(location).query,
            headers={"Cookie": "__Host-orbit_browser=" + binding},
        )

    def business_snapshot():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT b.user_id,u.status,u.password,b.revision,b.invited,s.auth_version "
                "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
                "JOIN sys_identity_subject s ON s.user_id=u.user_id WHERE b.id=%s",
                (user["id"],),
            )
            person = cursor.fetchone()
            cursor.execute(
                "SELECT id,status,revision FROM orbit_user_invitation "
                "WHERE provider_id=%s ORDER BY id",
                (provider,),
            )
            invitations = cursor.fetchall()
            counts = []
            for table, column in [
                ("orbit_external_identity", "user_id"),
                ("orbit_browser_session", "user_id"),
                ("orbit_directory_audit", "resource_id"),
                ("orbit_directory_outbox", "resource_id"),
            ]:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column}=%s",
                    (person[0] if column == "user_id" else user["id"],),
                )
                counts.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s",
                ("00000000-0000-0000-0000-000000000001",),
            )
            return person, invitations, tuple(counts), cursor.fetchone()[0]

    token, invitation, expires = payload()
    assert start("x" * 43).status_code == 401
    assert start(payload(False)[0]).status_code == 401
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_user_invitation SET expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
            "WHERE id=%s",
            (invitation,),
        )
    try:
        assert start(token).status_code == 401
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_user_invitation SET expires_at=%s WHERE id=%s", (expires, invitation)
            )
    before_user = current()
    changed = client.put(
        "/api/v1/users/" + user["id"],
        headers=headers
        | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": "invite-profile-" + uuid4().hex,
            "If-Match": f'"{before_user["revision"]}"',
        },
        json={
            **{
                k: v
                for k, v in before_user.items()
                if k not in {"id", "revision", "identity_status"}
            },
            "nickname": "邀请后资料变更",
        },
    )
    assert changed.status_code == 200 and start(token).status_code == 401
    assert send(changed.json()["revision"], "after-profile-" + uuid4().hex).status_code == 200
    token, invitation, _ = payload()
    cases.append(INVITATION_ACTIVATION_CASES[0])
    original_email, original_subject = idp.email, idp.subject
    idp.subject = "invitation-" + uuid4().hex
    before = business_snapshot()
    try:
        idp.email = "wrong-receiver@example.org"
        location, binding = authorization(token)
        assert callback(location, binding).status_code == 401 and business_snapshot() == before
        idp.email = user["email"]
        idp.email_verified = False
        location, binding = authorization(token)
        assert callback(location, binding).status_code == 401 and business_snapshot() == before
        idp.email_verified = True
        cases.append(INVITATION_ACTIVATION_CASES[1])
        location, binding = authorization(token)
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER invite_consume_fail BEFORE INSERT ON orbit_auth_audit "
                "FOR EACH ROW BEGIN IF NEW.action='INVITATION_CONSUMED' THEN "
                "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture consume failure'; END IF; END"
            )
        try:
            failed = callback(location, binding)
            assert failed.status_code == 503 and "set-cookie" not in failed.headers
            assert business_snapshot() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER IF EXISTS invite_consume_fail")
        exchanges = idp.exchanges
        assert callback(location, binding).status_code == 401 and idp.exchanges == exchanges
        cases.append(INVITATION_ACTIVATION_CASES[2])
        location, binding = authorization(token)
        activated = callback(location, binding)
        assert activated.status_code == 200
        person = activated.json()["user"]
        assert person["id"] == user["id"] and person["status"] == "ENABLED"
        assert (
            person["identity_status"] == "OIDC_VERIFIED" and person["revision"] == before[0][3] + 1
        )
        after = business_snapshot()
        assert after[0][1:3] == ("0", None) and after[0][4] == 0
        assert after[0][5] == before[0][5] + 1
        assert after[2][0] == before[2][0] + 1 and after[2][1] == before[2][1] + 1
        assert start(token).status_code == 401 and callback(location, binding).status_code == 401
        assert business_snapshot() == after
        issued = SimpleCookie()
        for value in activated.headers.get_list("set-cookie"):
            issued.load(value)
        cookie_pair = (
            "adpilot_session="
            + issued["adpilot_session"].value
            + "; __Host-orbit_browser="
            + binding
        )
        assert client.get("/getRouters", headers={"Cookie": cookie_pair}).status_code == 200
        assert (
            client.get("/api/v1/auth/session", headers={"Cookie": cookie_pair}).json()["user"]
            == person
        )
        cases.append(INVITATION_ACTIVATION_CASES[3])
        forbidden = client.put(
            "/system/user/resetPwd",
            headers=headers,
            json={
                "userId": after[0][0],
                "password": "OrbitFixt7!pw",
            },
        )
        assert forbidden.status_code == 200 and forbidden.json()["code"] != 200
        assert "OIDC" in forbidden.json()["msg"] and business_snapshot() == after
        cases.append(INVITATION_ACTIVATION_CASES[4])
    finally:
        idp.email, idp.subject, idp.email_verified = original_email, original_subject, True
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS invite_consume_fail")
