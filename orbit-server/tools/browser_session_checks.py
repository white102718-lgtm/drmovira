"""隔离MySQL的会话存储专项；预置验证映射，不冒充OIDC授权往返验收。"""

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

from authorization_store_checks import run_authorization_store_checks
from cookie_http_checks import run_cookie_http_checks
from oidc_callback_checks import run_oidc_callback_checks
from sqlalchemy import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BROWSER_SESSION_CASES = [
    "pythonCookieSessionStoresOnlyHashesAndIndependentCsrf",
    "pythonCookieSessionIdleAbsoluteAndIdentityRevocation",
    "pythonCookieSessionLogoutIdempotencyAndNoResurrection",
    "pythonCookieSessionAuditFailureRollsBackWholeIssueAndLogout",
]


def run_browser_session_checks(
    admin,
    database,
    fixture,
    cases,
    client,
    headers,
    keys,
    idp,
    *,
    include_account_read_cookie=False,
):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from orbit_api.browser_session_store import BrowserSessionStore
    from orbit_api.credentials import CredentialCipher
    from orbit_api.errors import OrbitError
    from orbit_api.oidc_contract import opaque_token

    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("会话专项只能使用当前隔离夹具数据库")
    tenant = "00000000-0000-0000-0000-000000000001"
    actor = fixture["users"][22]["native"]
    provider, identity_id = str(uuid4()), str(uuid4())
    issuer, subject = "https://session-storage.fixture.example", "storage-only-subject"
    cipher = CredentialCipher("fixture", keys)
    with admin.cursor() as cursor:
        cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=%s", (actor,))
        original_version = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orbit_system_configuration "
            "(id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,"
            "verification_status,updated_at) "
            "VALUES(%s,%s,'OIDC',%s,1,1,%s,%s,'UNTESTED',UTC_TIMESTAMP(3))",
            (
                provider,
                tenant,
                "会话存储夹具" + provider,
                json.dumps(
                    {
                        "issuer": issuer,
                        "clientId": "storage-client",
                        "redirectUri": "https://app.fixture.example/auth/callback",
                    }
                ),
                json.dumps(
                    {
                        "clientSecret": cipher.encrypt(
                            "fixture-client-secret", tenant, provider, "clientSecret"
                        )
                    }
                ),
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_external_identity "
            "(id,tenant_id,user_id,issuer,issuer_digest,subject,subject_digest,"
            "provider_id,verified_email,verified_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(3))",
            (
                identity_id,
                tenant,
                actor,
                issuer,
                hashlib.sha256(issuer.encode()).digest(),
                subject,
                hashlib.sha256(subject.encode()).digest(),
                provider,
                "storage-user@fixture.example.org",
            ),
        )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def checks():
        engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = BrowserSessionStore(cipher)
        binding = opaque_token()

        async def issue():
            async with sessions() as db, db.begin():
                return await store.issue(db, tenant, actor, provider, 1, binding, str(uuid4()))

        async def resolve(cookie):
            async with sessions() as db, db.begin():
                return await store.resolve(db, cookie, binding)

        async def rejected(cookie, *, alternate_binding=None):
            try:
                async with sessions() as db, db.begin():
                    await store.resolve(db, cookie, alternate_binding or binding)
            except OrbitError as error:
                assert error.status == 401
            else:
                raise AssertionError("无效会话不应通过存储认证")

        try:
            cookie, principal = await issue()
            assert (await resolve(cookie)).session_id == principal.session_id
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT token_digest,binding_digest,"
                    "TIMESTAMPDIFF(SECOND,created_at,idle_expires_at),"
                    "TIMESTAMPDIFF(SECOND,created_at,absolute_expires_at) "
                    "FROM orbit_browser_session WHERE id=%s",
                    (principal.session_id,),
                )
                digest, bound, idle, absolute = cursor.fetchone()
                assert len(digest) == len(bound) == 32 and idle == 1800 and absolute == 43200
                assert cookie.encode() != digest and binding.encode() != bound
            await rejected(cookie, alternate_binding=opaque_token())
            another_cookie, another = await issue()
            assert another.csrf_token != principal.csrf_token
            cases.append(BROWSER_SESSION_CASES[0])
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_browser_session "
                    "SET last_seen_at=UTC_TIMESTAMP(3)-INTERVAL 90 SECOND "
                    "WHERE id=%s",
                    (principal.session_id,),
                )
                cursor.execute(
                    "SELECT absolute_expires_at FROM orbit_browser_session WHERE id=%s",
                    (principal.session_id,),
                )
                fixed_expiry = cursor.fetchone()[0]
            await resolve(cookie)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT absolute_expires_at,TIMESTAMPDIFF(SECOND,last_seen_at,idle_expires_at) "
                    "FROM orbit_browser_session WHERE id=%s",
                    (principal.session_id,),
                )
                assert cursor.fetchone() == (fixed_expiry, 1800)
                cursor.execute(
                    "UPDATE orbit_browser_session "
                    "SET idle_expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
                    "WHERE id=%s",
                    (principal.session_id,),
                )
            await rejected(cookie)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_browser_session "
                    "SET absolute_expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
                    "WHERE id=%s",
                    (another.session_id,),
                )
            await rejected(another_cookie)
            epoch_cookie, _ = await issue()
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_identity_subject SET auth_version=auth_version+1 WHERE user_id=%s",
                    (actor,),
                )
            await rejected(epoch_cookie)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_identity_subject SET auth_version=%s WHERE user_id=%s",
                    (original_version, actor),
                )
            cases.append(BROWSER_SESSION_CASES[1])
            logout_cookie, logout_identity = await issue()
            key, request_id = "sign-out-" + uuid4().hex, str(uuid4())
            async with sessions() as db, db.begin():
                first = await store.logout(
                    db, logout_cookie, binding, logout_identity.csrf_token, key, request_id
                )
            async with sessions() as db, db.begin():
                replay = await store.logout(
                    db, logout_cookie, binding, logout_identity.csrf_token, key, str(uuid4())
                )
            assert first == replay and first["revision"] == 2 and first["state"] == "SIGNED_OUT"
            await rejected(logout_cookie)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_auth_audit "
                    "WHERE resource_id=%s AND action='SIGNED_OUT'",
                    (first["id"],),
                )
                assert cursor.fetchone()[0] == 1
            cases.append(BROWSER_SESSION_CASES[2])
            rollback_cookie, rollback_identity = await issue()
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_browser_session WHERE provider_id=%s", (provider,)
                )
                count = cursor.fetchone()[0]
                cursor.execute(
                    "CREATE TRIGGER auth_session_audit_fail BEFORE INSERT ON orbit_auth_audit "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT='fixture auth audit failure'"
                )
            try:
                try:
                    await issue()
                except SQLAlchemyError:
                    pass
                else:
                    raise AssertionError("审计失败不应发放会话")
                try:
                    async with sessions() as db, db.begin():
                        await store.logout(
                            db,
                            rollback_cookie,
                            binding,
                            rollback_identity.csrf_token,
                            "rollback-" + uuid4().hex,
                            str(uuid4()),
                        )
                except SQLAlchemyError:
                    pass
                else:
                    raise AssertionError("审计失败不应提交退出状态")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_browser_session WHERE provider_id=%s",
                        (provider,),
                    )
                    assert cursor.fetchone()[0] == count
                assert (await resolve(rollback_cookie)).session_id == rollback_identity.session_id
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS auth_session_audit_fail")
            cases.append(BROWSER_SESSION_CASES[3])
            await run_authorization_store_checks(
                admin, sessions, cipher, tenant, provider, binding, cases
            )
            await run_cookie_http_checks(
                client, admin, sessions, store, issue, binding, actor, headers, cases
            )
            if include_account_read_cookie:
                from account_read_cookie_checks import run_account_read_cookie_checks

                await run_account_read_cookie_checks(
                    client,
                    admin,
                    sessions,
                    store,
                    issue,
                    binding,
                    actor,
                    headers,
                    cases,
                    database=database,
                )
            run_oidc_callback_checks(client, admin, cipher, provider, actor, idp, cases)
        finally:
            await engine.dispose()

    try:
        asyncio.run(checks())
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS auth_session_audit_fail")
            cursor.execute(
                "UPDATE sys_identity_subject SET auth_version=%s WHERE user_id=%s",
                (original_version, actor),
            )
            cursor.execute(
                "DELETE FROM orbit_auth_audit WHERE resource_id IN "
                "(SELECT id FROM orbit_browser_session WHERE provider_id=%s)",
                (provider,),
            )
            cursor.execute(
                "DELETE FROM orbit_auth_idempotency WHERE session_id IN "
                "(SELECT id FROM orbit_browser_session WHERE provider_id=%s)",
                (provider,),
            )
            cursor.execute(
                "DELETE FROM orbit_auth_audit WHERE resource_id IN "
                "(SELECT id FROM orbit_oidc_authorization WHERE provider_id=%s)",
                (provider,),
            )
            cursor.execute("DELETE FROM orbit_oidc_authorization WHERE provider_id=%s", (provider,))
            cursor.execute("DELETE FROM orbit_browser_session WHERE provider_id=%s", (provider,))
            cursor.execute("DELETE FROM orbit_external_identity WHERE id=%s", (identity_id,))
            cursor.execute("DELETE FROM orbit_system_configuration WHERE id=%s", (provider,))
