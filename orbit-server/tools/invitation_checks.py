"""邀请排队的实际MySQL/HTTP专项；不把排队或解密夹具凭据当作真实通知送达。"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fixture_login import fixture_login
from invitation_activation_checks import run_invitation_activation_checks
from invitation_delivery_checks import run_invitation_delivery_checks

INVITATION_CASES = [
    "pythonInvitationMissingChannelDoesNotChangeUserOrIdempotency",
    "pythonInvitationAckEncryptedQueueAndOneDayExpiry",
    "pythonInvitationResendRevokesOldAndEnforcesCas",
    "pythonInvitationHeadersBodyScopeAndSuperAdminBoundary",
    "pythonInvitationAuditAndBothOutboxesRollbackAndRetry",
    "pythonInvitationConcurrentKeysHaveSingleCommit",
]


def run_invitation_checks(
    client, admin, headers, fixture, cases, keys, idp, database, password, cache, values
):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("邀请专项只允许当前独立夹具数据库")
    from orbit_api.credentials import CredentialCipher

    cipher = CredentialCipher("fixture", keys)
    tenant = "00000000-0000-0000-0000-000000000001"
    provider, notification = str(uuid4()), str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_system_configuration "
            "(id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,"
            "verification_status,updated_at) "
            "VALUES(%s,%s,'OIDC',%s,1,1,%s,%s,'UNTESTED',UTC_TIMESTAMP(3))",
            (
                provider,
                tenant,
                "邀请OIDC夹具" + provider,
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
                            idp.client_secret, tenant, provider, "clientSecret"
                        )
                    }
                ),
            ),
        )
        cursor.execute(
            "SELECT id FROM orbit_system_configuration WHERE tenant_id=%s "
            "AND section='NOTIFICATIONS' AND enabled=1 "
            "AND JSON_UNQUOTE(JSON_EXTRACT(settings_json,'$.channel'))='WEBHOOK'",
            (tenant,),
        )
        prior_channels = [row[0] for row in cursor.fetchall()]
        for identifier in prior_channels:
            cursor.execute(
                "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (identifier,)
            )
    caps = client.get("/api/v1/users/capabilities", headers=headers).json()
    created = client.post(
        "/api/v1/users",
        headers=headers
        | {
            "Idempotency-Key": "invite-person-" + uuid4().hex,
            "X-CSRF-Token": caps["csrf_token"],
        },
        json={
            "display_name": "邀请验证专项" + uuid4().hex[:8],
            "nickname": "",
            "phone": "",
            "email": "invite-" + uuid4().hex + "@example.org",
            "team_id": fixture["users"][0]["team"],
            "role_ids": [fixture["role_id"]],
            "data_role": "USER",
            "managed_team_ids": [],
            "status": "INVITED",
        },
    )
    assert created.status_code == 201
    user = created.json()
    path = "/api/v1/users/" + user["id"] + "/invitation"

    def current():
        response = client.get("/api/v1/users/" + user["id"], headers=headers)
        assert response.status_code == 200
        return response.json()

    def send(revision, key, *, custom_headers=None, content=None):
        request_headers = headers | {
            "Idempotency-Key": key,
            "If-Match": f'"{revision}"',
            "X-CSRF-Token": caps["csrf_token"],
        }
        return client.post(path, headers=custom_headers or request_headers, content=content)

    def snapshot():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT b.revision FROM orbit_business_user b WHERE b.id=%s", (user["id"],)
            )
            revision = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id,status,revision FROM orbit_user_invitation WHERE tenant_id=%s "
                "AND user_id=(SELECT user_id FROM orbit_business_user WHERE id=%s) ORDER BY id",
                (tenant, user["id"]),
            )
            invitations = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM orbit_invitation_delivery")
            queue = cursor.fetchone()[0]
            counts = []
            for table in (
                "orbit_auth_audit",
                "orbit_directory_audit",
                "orbit_directory_outbox",
                "orbit_directory_idempotency",
            ):
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts.append(cursor.fetchone()[0])
            return revision, invitations, queue, tuple(counts)

    try:
        before = snapshot()
        blocked = send(user["revision"], "no-channel-" + uuid4().hex)
        assert (
            blocked.status_code == 409 and blocked.json()["code"] == "INVITATION_CHANNEL_REQUIRED"
        )
        assert snapshot() == before
        status = client.get(path, headers=headers)
        assert status.status_code == 200 and status.json()["can_invite"] is False
        assert status.json()["invitation"] is None
        cases.append(INVITATION_CASES[0])
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_system_configuration "
                "(id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,"
                "verification_status,updated_at) "
                "VALUES(%s,%s,'NOTIFICATIONS',%s,1,1,%s,'{}','UNTESTED',UTC_TIMESTAMP(3))",
                (
                    notification,
                    tenant,
                    "邀请通知夹具" + notification,
                    json.dumps({"channel": "WEBHOOK", "webhookUrl": idp.issuer + "/notifications"}),
                ),
            )
        key = "first-invite-" + uuid4().hex
        first = send(user["revision"], key)
        assert first.status_code == 200 and set(first.json()) == {
            "id",
            "revision",
            "state",
            "request_id",
        }
        assert first.json()["state"] == "INVITATION_QUEUED" and first.json()["id"] == user["id"]
        committed = snapshot()
        assert send(user["revision"], key).json() == first.json() and snapshot() == committed
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT token_digest,TIMESTAMPDIFF(SECOND,i.created_at,i.expires_at),"
                "d.id,d.protected_json,i.user_revision,i.created_by_auth_version "
                "FROM orbit_user_invitation i "
                "JOIN orbit_invitation_delivery d ON d.invitation_id=i.id "
                "WHERE i.provider_id=%s AND i.status='ACTIVE'",
                (provider,),
            )
            digest, ttl, delivery, encrypted, user_revision, actor_version = cursor.fetchone()
            assert len(digest) == 32 and ttl == 86400 and actor_version >= 1
            assert user_revision == first.json()["revision"]
            protected = json.loads(encrypted)
            payload = json.loads(
                cipher.decrypt_internal(
                    protected["envelope"], tenant, delivery, "invitation_delivery"
                )
            )
            assert (
                payload["recipient_email"] == user["email"]
                and len(payload["invitation_token"]) == 43
            )
            assert (
                payload["invitation_token"] not in encrypted
                and payload["invitation_token"] not in first.text
            )
        cases.append(INVITATION_CASES[1])
        assert send(user["revision"], "stale-invite-" + uuid4().hex).status_code == 409
        assert send(first.json()["revision"], key).status_code == 409
        second = send(first.json()["revision"], "resend-invite-" + uuid4().hex)
        assert (
            second.status_code == 200 and second.json()["revision"] == first.json()["revision"] + 1
        )
        states = snapshot()[1]
        assert sum(row[1] == "ACTIVE" for row in states) == 1
        assert sum(row[1:] == ("REVOKED", 2) for row in states) == 1
        cases.append(INVITATION_CASES[2])
        before = snapshot()
        base = headers | {
            "Idempotency-Key": "bad-header-" + uuid4().hex,
            "If-Match": f'"{current()["revision"]}"',
            "X-CSRF-Token": caps["csrf_token"],
        }
        for removed, expected in [
            ("Idempotency-Key", 400),
            ("If-Match", 400),
            ("X-CSRF-Token", 403),
        ]:
            assert (
                client.post(
                    path, headers={k: v for k, v in base.items() if k != removed}
                ).status_code
                == expected
            )
        assert client.post(path, headers=base, json={"actor_id": 1}).status_code == 400
        assert client.post(path, headers=base | {"X-Target-Tenant": tenant}).status_code == 403
        login = fixture_login(
            client,
            cache,
            {
                "username": fixture["users"][1]["name"],
                "password": password,
            },
        )
        assert login.status_code == 200 and login.json().get("token")
        actor_headers = {"Authorization": "Bearer " + login.json()["token"]}
        actor_response = client.get("/api/v1/users/capabilities", headers=actor_headers)
        assert actor_response.status_code == 200
        actor_caps = actor_response.json()
        assert (
            client.post(
                path,
                headers=actor_headers
                | {
                    "Idempotency-Key": "scope-invite-" + uuid4().hex,
                    "If-Match": base["If-Match"],
                    "X-CSRF-Token": actor_caps["csrf_token"],
                },
            ).status_code
            == 403
        )
        assert snapshot() == before
        cases.append(INVITATION_CASES[3])
        for table in ["orbit_auth_audit", "orbit_invitation_delivery", "orbit_directory_outbox"]:
            revision = current()["revision"]
            before = snapshot()
            key = "rollback-invite-" + uuid4().hex
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE TRIGGER invite_write_fail BEFORE INSERT ON {table} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT='fixture invitation failure'"
                )
            try:
                assert send(revision, key).status_code == 503 and snapshot() == before
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS invite_write_fail")
            assert send(revision, key).status_code == 200
        cases.append(INVITATION_CASES[4])
        revision = current()["revision"]
        key = "parallel-invite-" + uuid4().hex
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: send(revision, key), range(2)))
        assert (
            all(r.status_code == 200 for r in outcomes) and outcomes[0].json() == outcomes[1].json()
        )
        assert current()["revision"] == revision + 1
        revision = current()["revision"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(lambda _: send(revision, "cas-invite-" + uuid4().hex), range(2))
            )
        assert sorted(r.status_code for r in outcomes) == [200, 409]
        assert current()["revision"] == revision + 1
        assert sum(row[1] == "ACTIVE" for row in snapshot()[1]) == 1
        cases.append(INVITATION_CASES[5])
        run_invitation_delivery_checks(admin, database, send, current, cipher, idp, cases, values)
        run_invitation_activation_checks(
            client, admin, headers, user, caps, send, current, provider, cipher, idp, cases
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS invite_write_fail")
            for identifier in prior_channels:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (identifier,)
                )
