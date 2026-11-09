"""账户专属短认证的Cookie真实HTTP补充；仅当前UUID夹具，不代表平台数据。"""

import re
from uuid import uuid4

ACCOUNT_READ_COOKIE_CASES = (
    "pythonAccountReadCookieOwnScopeAndImmediateActionRevocation",
    "pythonAccountReadCookieRejectsMalformedDuplicateAndSignedOutWithoutBearerFallback",
)
ACCOUNT_KEYS = {
    "id",
    "external_id",
    "name",
    "ownership",
    "vendor_id",
    "currency",
    "auth_status",
    "account_status",
    "revision",
    "timezone",
    "synced_at",
    "vendor_alias",
    "spend",
    "balance",
}
PAGE_KEYS = {
    "items",
    "next_cursor",
    "data_as_of",
    "scope_version",
    "account_version",
    "metric_snapshot_id",
}


def guard_account_cookie_fixture(admin, database, actor):
    """先核真实当前库与原users[22]身份；拒绝任何非目标写入。"""
    if (
        not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) is None
        or admin.host != "127.0.0.1"
        or admin.port != 13306
        or type(actor) is not int
        or actor != 980022
    ):
        raise ValueError("ACCOUNT_COOKIE_FIXTURE_BOUNDARY")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone() != (database,):
            raise ValueError("ACCOUNT_COOKIE_DATABASE_MISMATCH")
        cursor.execute(
            "SELECT b.tenant_id,b.id,b.team_id,s.data_role,u.user_name,u.status,u.del_flag,"
            "b.enabled,b.invited FROM orbit_business_user b "
            "JOIN sys_user u ON u.user_id=b.user_id "
            "JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id "
            "AND s.enabled=1 WHERE b.user_id=%s",
            (actor,),
        )
        own = cursor.fetchone()
        if own is None or own[3:] != ("USER", "user_directory_22", "0", "0", 1, 0):
            raise ValueError("ACCOUNT_COOKIE_ACTOR_MISMATCH")
        cursor.execute(
            "SELECT b.id,b.team_id FROM orbit_business_user b "
            "JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0' "
            "WHERE b.tenant_id=%s AND b.user_id=980021 AND b.enabled=1 AND b.invited=0",
            (own[0],),
        )
        foreign = cursor.fetchone()
        if foreign is None or foreign[0] == own[1]:
            raise ValueError("ACCOUNT_COOKIE_PEER_MISMATCH")
    return own[0], own[1], own[2], foreign[0], foreign[1]


def check_cookie_account_payload(value, identifier, owner, team):
    assert set(value) == {"account", "details"}, "ACCOUNT_COOKIE_DETAIL_FIELDS"
    account, details = value["account"], value["details"]
    assert set(account) == ACCOUNT_KEYS, "ACCOUNT_COOKIE_CORE_FIELDS"
    assert account["id"] == details["account_id"] == identifier, "ACCOUNT_COOKIE_IDENTITY"
    assert account["ownership"] == {"owner_user_id": owner, "owner_team_id": team}
    assert account["auth_status"] == account["account_status"] == "UNKNOWN"
    assert account["currency"] == "USD" and account["vendor_id"] is None
    assert account["synced_at"] is None
    assert account["spend"]["amount"] is None and account["balance"]["amount"] is None
    assert details["identity_status"] == "UNSYNCED" and details["identity_count"] is None


async def run_account_read_cookie_checks(
    client, admin, sessions, store, issue, binding, actor, headers, cases, *, database
):
    """在原六Cookie组之后调用；复用原issue/store，不创建HTTP会话后门。"""
    tenant, owner, team, foreign_owner, foreign_team = guard_account_cookie_fixture(
        admin, database, actor
    )
    ids = [str(uuid4()), str(uuid4())]
    marker = "CookieRead-" + uuid4().hex
    native_role, seeded = None, False
    caps = client.get("/api/v1/roles/capabilities", headers=headers)
    assert caps.status_code == 200, "ACCOUNT_COOKIE_ROLE_CAPABILITY"
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": caps.json()["csrf_token"],
            "Idempotency-Key": "account-cookie-role-" + uuid4().hex,
        },
        json={
            "name": "账户Cookie只读夹具-" + uuid4().hex,
            "menu_codes": ["accounts"],
            "permission_codes": ["accounts.read"],
        },
    )
    assert role.status_code == 201, "ACCOUNT_COOKIE_ROLE_CREATED"
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
                (tenant, role.json()["id"]),
            )
            row = cursor.fetchone()
            assert row is not None, "ACCOUNT_COOKIE_ROLE_MAPPING"
            native_role = row[0]
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, native_role)
            )
            for identifier, person, person_team in (
                (ids[0], owner, team),
                (ids[1], foreign_owner, foreign_team),
            ):
                cursor.execute(
                    "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                    "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
                    "value_json,details_json,bound_at,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','UTC','UNKNOWN','UNKNOWN','{}','{}',"
                    "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                    (
                        tenant,
                        identifier,
                        str(10**20 + uuid4().int % 10**20),
                        marker,
                        marker,
                        person,
                        person_team,
                    ),
                )
                seeded = True
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
            assert cursor.rowcount == 1, "ACCOUNT_COOKIE_CLOCK"
        cookie, principal = await issue()
        pair = f"adpilot_session={cookie}; __Host-orbit_browser={binding}"
        own_headers = {"Cookie": pair}
        extended = "/api/v1/accounts/extended"
        detail = "/api/v1/accounts/" + ids[0] + "/details"
        paths = (extended, detail)
        for request_headers in (own_headers, headers | own_headers):
            page = client.get(
                extended, headers=request_headers, params={"q": marker, "page_size": "20"}
            )
            assert page.status_code == 200, "ACCOUNT_COOKIE_LIST_200"
            value = page.json()
            assert set(value) == PAGE_KEYS and value["next_cursor"] is None
            assert len(value["items"]) == 1, "ACCOUNT_COOKIE_OWN_ONLY"
            check_cookie_account_payload(value["items"][0], ids[0], owner, team)
            single = client.get(detail, headers=request_headers)
            assert single.status_code == 200, "ACCOUNT_COOKIE_DETAIL_200"
            check_cookie_account_payload(single.json(), ids[0], owner, team)
            peer = client.get("/api/v1/accounts/" + ids[1] + "/details", headers=request_headers)
            assert peer.status_code == 404, "ACCOUNT_COOKIE_PEER_404"
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (actor, native_role)
            )
            assert cursor.rowcount == 1
        for path in paths:
            for request_headers in (own_headers, headers | own_headers):
                assert client.get(path, headers=request_headers).status_code == 403, (
                    "ACCOUNT_COOKIE_REVOKED_ACTION_403"
                )
        cases.append(ACCOUNT_READ_COOKIE_CASES[0])
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, native_role)
            )
        for path in paths:
            assert client.get(path, headers=own_headers).status_code == 200, (
                "ACCOUNT_COOKIE_RESTORED_200"
            )
            assert (
                client.get(
                    path, headers=headers | {"Cookie": "adpilot_session=malformed"}
                ).status_code
                == 401
            ), "ACCOUNT_COOKIE_MALFORMED_401"
            assert (
                client.get(
                    path, headers=headers | {"Cookie": pair + "; adpilot_session=" + cookie}
                ).status_code
                == 401
            ), "ACCOUNT_COOKIE_DUPLICATE_VALUE_401"
            assert (
                client.get(
                    path, headers=list(headers.items()) + [("Cookie", pair), ("Cookie", pair)]
                ).status_code
                == 401
            ), "ACCOUNT_COOKIE_DUPLICATE_HEADER_401"
        async with sessions() as db, db.begin():
            await store.logout(
                db,
                cookie,
                binding,
                principal.csrf_token,
                "account-cookie-exit-" + uuid4().hex,
                str(uuid4()),
            )
        for path in paths:
            for request_headers in (own_headers, headers | own_headers):
                assert client.get(path, headers=request_headers).status_code == 401, (
                    "ACCOUNT_COOKIE_SIGNED_OUT_401"
                )
        cases.append(ACCOUNT_READ_COOKIE_CASES[1])
    finally:
        with admin.cursor() as cursor:
            if native_role is not None:
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor, native_role),
                )
            if seeded:
                cursor.execute(
                    "DELETE FROM orbit_ad_account WHERE tenant_id=%s AND id IN(%s,%s)",
                    (tenant, *ids),
                )
                cursor.execute(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
