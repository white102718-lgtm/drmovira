"""预置会话的实际HTTP认证专项，不代表浏览器或OIDC回调验收。"""

from uuid import uuid4

COOKIE_HTTP_CASES = [
    "pythonCookieHttpUsesDatabaseIdentityAndRejectsBearerFallback",
    "pythonCookieHttpCapabilitiesShareCsrfAndRejectCrossOriginWrites",
    "pythonCookieHttpNativeProfileWriteKeepsCurrentUserAndRejectsDuplicateCookie",
    "pythonCookieHttpLogoutAndEpochRevocationAreImmediate",
    "pythonProductSessionExactContractAndLocalPermissionUnion",
    "pythonProductSessionDeleteCookieAndIdempotentReceipt",
]


async def run_cookie_http_checks(
    client, admin, sessions, store, issue, binding, actor, headers, cases
):
    cookie, identity = await issue()
    pair = f"adpilot_session={cookie}; __Host-orbit_browser={binding}"
    own = {"Cookie": pair}
    info = client.get("/getInfo", headers=own)
    assert info.status_code == 200 and info.json()["user"]["userId"] == actor
    conflict = client.get("/getInfo", headers=own | headers)
    assert conflict.status_code == 200 and conflict.json()["user"]["userId"] == actor
    bad = client.get("/getInfo", headers=headers | {"Cookie": "adpilot_session=malformed"})
    assert bad.status_code == 401
    cases.append(COOKIE_HTTP_CASES[0])

    caps = client.get("/api/v1/users/capabilities", headers=own)
    assert caps.status_code == 200 and caps.json()["csrf_token"] == identity.csrf_token
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT nick_name,email,phonenumber FROM sys_user WHERE user_id=%s", (actor,)
        )
        nickname, email, phone = cursor.fetchone()
    payload = {"nickName": nickname, "email": email, "phonenumber": phone}
    unsafe = own | {"X-CSRF-Token": identity.csrf_token, "Origin": "https://evil.fixture.example"}
    blocked = client.put("/system/user/profile", headers=unsafe, json=payload)
    assert blocked.status_code == 403 and blocked.json() == {"code": 403, "msg": "请求来源校验失败"}
    missing = client.put(
        "/system/user/profile",
        headers=own | {"Origin": "https://app.fixture.example"},
        json=payload,
    )
    assert missing.status_code == 403 and missing.json() == {
        "code": 403,
        "msg": "请求需要唯一的会话校验值",
    }
    cases.append(COOKIE_HTTP_CASES[1])
    accepted = client.put(
        "/system/user/profile",
        headers=own
        | {"Origin": "https://app.fixture.example", "X-CSRF-Token": identity.csrf_token},
        json=payload,
    )
    assert accepted.status_code == 200 and accepted.json()["code"] == 200
    duplicate = client.get("/getInfo", headers={"Cookie": pair + "; adpilot_session=" + cookie})
    assert duplicate.status_code == 401
    cases.append(COOKIE_HTTP_CASES[2])
    async with sessions() as db, db.begin():
        await store.logout(
            db, cookie, binding, identity.csrf_token, "http-" + uuid4().hex, str(uuid4())
        )
    assert client.get("/getInfo", headers=own).status_code == 401
    another, _ = await issue()
    with admin.cursor() as cursor:
        cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=%s", (actor,))
        epoch = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE sys_identity_subject SET auth_version=auth_version+1 WHERE user_id=%s", (actor,)
        )
    try:
        assert (
            client.get("/getInfo", headers={"Cookie": pair.replace(cookie, another)}).status_code
            == 401
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_identity_subject SET auth_version=%s WHERE user_id=%s", (epoch, actor)
            )
    cases.append(COOKIE_HTTP_CASES[3])
    cookie, principal = await issue()
    pair = f"adpilot_session={cookie}; __Host-orbit_browser={binding}"
    current = client.get("/api/v1/auth/session", headers={"Cookie": pair})
    assert current.status_code == 200
    value = current.json()
    assert set(value) == {
        "user",
        "scope_version",
        "menu_codes",
        "permission_codes",
        "csrf_token",
        "expires_at",
    }
    assert value["csrf_token"] == principal.csrf_token and value["scope_version"] >= 1
    assert value["menu_codes"] == ["system"]
    assert value["permission_codes"] == ["system.read", "system.users.manage"]
    assert value["user"]["email"] == email and len(value["user"]) == 12
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 401
    assert current.headers["referrer-policy"] == "no-referrer"
    cases.append(COOKIE_HTTP_CASES[4])
    outgoing = {
        "Cookie": pair,
        "Origin": "https://app.fixture.example",
        "X-CSRF-Token": principal.csrf_token,
        "Idempotency-Key": "http-exit-" + uuid4().hex,
    }
    first = client.delete("/api/v1/auth/session", headers=outgoing)
    replay = client.delete("/api/v1/auth/session", headers=outgoing)
    assert first.status_code == replay.status_code == 200 and first.json() == replay.json()
    assert set(first.json()) == {"id", "revision", "state", "request_id"}
    assert first.json()["state"] == "SIGNED_OUT"
    cleared = first.headers["set-cookie"]
    assert "adpilot_session=" in cleared and "Max-Age=0" in cleared
    assert "HttpOnly" in cleared and "Secure" in cleared and "SameSite=lax" in cleared
    assert client.get("/api/v1/auth/session", headers={"Cookie": pair}).status_code == 401
    cases.append(COOKIE_HTTP_CASES[5])
