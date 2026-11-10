"""真实隔离MySQL授权事务验收，Meta网络使用明确测试替身，不证明外部授权。"""

import asyncio
import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "metaSqlSingleUseAndEncryptedGrant",
    "metaSqlReauthorizationAndDisconnectVersion",
    "metaSqlExpiredAndCrossBrowserState",
    "metaSqlAuditRollback",
    "metaHttpCookiePermissionAndUnconfiguredApplication",
]


def run_meta_connection_checks(admin, database, cases, client, values, *, browser=False):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("仅允许本轮隔离数据库")
    from orbit_api.browser_session_store import BrowserSessionStore
    from orbit_api.cookie_identity import bind_verified_cookie
    from orbit_api.credentials import CredentialCipher
    from orbit_api.errors import OrbitError
    from orbit_api.meta_connection_contract import MetaApplication, ValidatedGrant
    from orbit_api.meta_connection_service import MetaConnectionService

    tenant = "00000000-0000-0000-0000-000000000001"
    provider, identity_id = str(uuid4()), str(uuid4())
    issuer = "https://meta-session.fixture.example"
    cipher = CredentialCipher(
        values["ORBIT_PYTHON_SECRETS_ACTIVE_KEY_ID"], values["ORBIT_PYTHON_SECRETS_KEYS"]
    )
    with admin.cursor() as c:
        c.execute(
            "INSERT INTO orbit_system_configuration (id,tenant_id,section,name,enabled,revision"
            ",settings_json,secrets_json,verification_status,updated_at) "
            "VALUES(%s,%s,'OIDC',%s,1,1,%s,'{}','UNTESTED',UTC_TIMESTAMP(3))",
            (provider, tenant, "Meta隔离会话" + provider, json.dumps({"issuer": issuer})),
        )
        c.execute(
            "INSERT INTO orbit_external_identity (id,tenant_id,user_id,issuer,issuer_digest,sub"
            "ject,subject_digest,provider_id,verified_email,verified_at) "
            "VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(3))",
            (
                identity_id,
                tenant,
                issuer,
                hashlib.sha256(issuer.encode()).digest(),
                "meta-isolated-user",
                hashlib.sha256(b"meta-isolated-user").digest(),
                provider,
                "meta@fixture.example",
            ),
        )
    admin.commit()

    def decode(v):
        return v.decode() if isinstance(v, bytes) else v

    url = URL.create(
        "mysql+asyncmy",
        username=decode(admin.user),
        password=decode(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    class TestTransport:
        calls = 0

        async def exchange(self, code):
            assert code == "isolated-code"
            self.calls += 1
            return "isolated-meta-token", ValidatedGrant(
                "12345",
                ("ads_read",),
                datetime.now(UTC) + timedelta(hours=1),
                datetime.now(UTC) + timedelta(days=1),
            )

    browser_requested = browser

    async def checks():
        engine = create_async_engine(url, echo=False, isolation_level="READ COMMITTED")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        browser = BrowserSessionStore(cipher)
        binding = secrets.token_urlsafe(32)
        async with sessions() as db, db.begin():
            cookie, identity = await browser.issue(
                db, tenant, 1, provider, 1, binding, str(uuid4())
            )
        bind_verified_cookie(identity)
        transport = TestTransport()
        service = MetaConnectionService(
            sessions, cipher, MetaApplication("123", "isolated-secret", "v24.0", "456"), transport
        )

        def state(value):
            return parse_qs(urlsplit(value["authorize_url"]).query)["state"][0]

        key = str(uuid4())
        start = await service.start(1, "/orbit/accounts", key, str(uuid4()))
        assert await service.start(1, "/orbit/accounts", key, str(uuid4())) == start
        assert await service.callback(1, state(start), "isolated-code", str(uuid4())) == (
            "/orbit/accounts",
            "connected",
        )
        try:
            await service.callback(1, state(start), "isolated-code", str(uuid4()))
        except OrbitError as e:
            assert e.code == "META_STATE_INVALID"
        else:
            raise AssertionError("state复用通过")
        assert transport.calls == 1
        async with sessions() as db, db.begin():
            row = (
                (
                    await db.execute(
                        text("SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant"),
                        {"tenant": tenant},
                    )
                )
                .mappings()
                .one()
            )
            assert "isolated-meta-token" not in row["token_envelope"]
            assert (
                cipher.decrypt_internal(row["token_envelope"], tenant, row["id"], "meta_token")
                == "isolated-meta-token"
            )
            identifier = row["id"]
        cases.append(CASES[0])
        start = await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()), identifier)
        await service.callback(1, state(start), "isolated-code", str(uuid4()))
        rows = await service.list_connections(1)
        assert rows["items"][0]["revision"] == 2
        key = str(uuid4())
        result = await service.disconnect(1, identifier, 2, "隔离验收", key, str(uuid4()))
        assert await service.disconnect(1, identifier, 2, "隔离验收", key, str(uuid4())) == result
        assert result["revision"] == 3 and result["status"] == "DISCONNECTED"
        async with sessions() as db, db.begin():
            assert (
                await db.execute(
                    text("SELECT token_envelope FROM orbit_meta_connection WHERE id=:id"),
                    {"id": identifier},
                )
            ).scalar_one() is None
        cases.append(CASES[1])
        start = await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()))
        async with sessions() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE orbit_meta_authorization_session SET expires_at=UTC_TIMESTAMP(3) "
                    "WHERE state_digest=:digest"
                ),
                {"digest": hashlib.sha256(state(start).encode()).digest()},
            )
        try:
            await service.callback(1, state(start), "isolated-code", str(uuid4()))
        except OrbitError as e:
            assert e.code == "META_STATE_INVALID"
        else:
            raise AssertionError("过期state通过")
        start = await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()))
        async with sessions() as db, db.begin():
            _, other = await browser.issue(
                db, tenant, 1, provider, 1, secrets.token_urlsafe(32), str(uuid4())
            )
        bind_verified_cookie(other)
        try:
            await service.callback(1, state(start), "isolated-code", str(uuid4()))
        except OrbitError as e:
            assert e.code == "META_STATE_INVALID"
        else:
            raise AssertionError("跨浏览器state通过")
        bind_verified_cookie(identity)
        cases.append(CASES[2])
        async with sessions() as db, db.begin():
            before = (
                await db.execute(text("SELECT COUNT(*) FROM orbit_meta_authorization_session"))
            ).scalar_one()
            await db.execute(
                text(
                    "CREATE TRIGGER isolated_meta_audit_failure BEFORE INSERT ON "
                    "orbit_account_event FOR EACH ROW SIGNAL SQLSTATE '45000' SET "
                    "MESSAGE_TEXT='isolated rollback'"
                )
            )
        try:
            try:
                await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()))
            except Exception:
                pass
            else:
                raise AssertionError("审计失败未回滚")
        finally:
            async with sessions() as db, db.begin():
                await db.execute(text("DROP TRIGGER isolated_meta_audit_failure"))
                assert (
                    await db.execute(text("SELECT COUNT(*) FROM orbit_meta_authorization_session"))
                ).scalar_one() == before
        cases.append(CASES[3])
        from orbit_api.cookie_auth import BINDING_COOKIE
        from orbit_api.oidc_contract import SESSION_COOKIE

        cookie_header = SESSION_COOKIE + "=" + cookie + "; " + BINDING_COOKIE + "=" + binding
        headers = {"Cookie": cookie_header}
        response = client.get("/api/v1/integrations/meta/capabilities", headers=headers)
        assert response.status_code == 200, response.status_code
        capability = response.json()
        assert capability["configured"] is False
        listing = client.get("/api/v1/integrations/meta/connections", headers=headers)
        assert listing.status_code == 200
        assert listing.json()["items"][0]["status"] == "DISCONNECTED"
        rejected = client.post(
            "/api/v1/integrations/meta/authorization-sessions",
            headers=headers
            | {
                "Origin": "https://app.fixture.example",
                "X-CSRF-Token": capability["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            },
            json={"return_to": "/orbit/accounts"},
        )
        assert rejected.status_code == 503 and rejected.json()["code"] == "META_APP_NOT_CONFIGURED"
        cases.append(CASES[4])
        if browser_requested:
            from pathlib import Path

            path = Path("/tmp/orbit-meta-browser-cookie.json")
            path.write_text(json.dumps({"cookie_header": cookie_header}), encoding="utf-8")
            path.chmod(0o600)
        await engine.dispose()

    asyncio.run(checks())
    return {"result": "PASS", "external_meta": "NOT_RUN_APP_UNAVAILABLE"}
