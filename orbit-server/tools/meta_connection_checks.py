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
    "metaSqlNativeSessionAndMultiApplicationIsolation",
]


def run_meta_connection_checks(admin, database, cases, client, values, *, browser=False, bearer_headers=None):
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
        # 原生Bearer必须能建立真实浏览器会话，不创建虚构OIDC提供商。
        native_response = client.post('/api/v1/auth/native-session',
            headers=(bearer_headers or {}) | {'Origin':'https://app.fixture.example'})
        assert native_response.status_code == 200, native_response.status_code
        native_cookies = native_response.cookies
        native_header = SESSION_COOKIE + '=' + native_cookies[SESSION_COOKIE] + '; ' + BINDING_COOKIE + '=' + native_cookies[BINDING_COOKIE]
        native_headers = {'Cookie':native_header}
        cap = client.get('/api/v1/integrations/meta/capabilities',headers=native_headers)
        assert cap.status_code == 200
        async with sessions() as db, db.begin():
            native_identity = await browser.resolve(db, native_cookies[SESSION_COOKIE], native_cookies[BINDING_COOKIE])
        bind_verified_cookie(native_identity)
        from orbit_api.meta_application_registry import load_application, resolve_application
        app_ids = [str(uuid4()), str(uuid4())]
        async with sessions() as db, db.begin():
            for index, app_id in enumerate(app_ids):
                await db.execute(text("INSERT INTO orbit_system_configuration(id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,verification_status,updated_at) VALUES(:id,:tenant,'META_APP',:name,1,1,:settings,:secrets,'UNTESTED',UTC_TIMESTAMP(3))"),
                    {'id':app_id,'tenant':tenant,'name':'多应用隔离'+app_id,
                     'settings':json.dumps({'appId':str(123+index),'graphVersion':'v24.0','loginConfigId':str(456+index)}),
                     'secrets':json.dumps({'appSecret':cipher.encrypt('isolated-secret',tenant,app_id,'appSecret'),
                                          'marketingToken':cipher.encrypt('isolated-marketing-token',tenant,app_id,'marketingToken')})})
            app_a = await load_application(db,cipher,tenant,app_ids[0])
            app_b = await load_application(db,cipher,tenant,app_ids[1])
        service_a = MetaConnectionService(sessions,cipher,app_a,TestTransport())
        service_b = MetaConnectionService(sessions,cipher,app_b,TestTransport())
        request_key = str(uuid4())
        started = await service_a.start(1,'/orbit/accounts',request_key,str(uuid4()))
        assert parse_qs(urlsplit(started['authorize_url']).query)['client_id'] == ['123']
        try:
            await service_b.start(1,'/orbit/accounts',request_key,str(uuid4()))
        except OrbitError as exc:
            assert exc.code == 'IDEMPOTENCY_CONFLICT'
        else:
            raise AssertionError('同幂等键换应用未拒绝')
        resolved = await resolve_application(sessions,cipher,1,state=state(started))
        assert resolved.configuration_id == app_ids[0]
        async with sessions() as db, db.begin():
            await db.execute(text('UPDATE orbit_system_configuration SET revision=2 WHERE id=:id'),{'id':app_ids[0]})
        try:
            await service_a.callback(1,state(started),'isolated-code',str(uuid4()))
        except OrbitError as exc:
            assert exc.code == 'META_APP_CHANGED'
        else:
            raise AssertionError('应用版本改变后仍交换授权码')
        assert service_a.transport.calls == 0
        # 租户绑定的同名App ID签名不得撤销历史平台来源或其他应用配置。
        import base64, hmac
        payload = base64.urlsafe_b64encode(json.dumps({'algorithm':'HMAC-SHA256','user_id':'12345',
            'issued_at':int(datetime.now(UTC).timestamp())}).encode()).decode().rstrip('=')
        signature = base64.urlsafe_b64encode(hmac.new(b'isolated-secret',payload.encode(),hashlib.sha256).digest()).decode().rstrip('=')
        await service_a.provider_callback(signature+'.'+payload,'DEAUTHORIZE')
        async with sessions() as db, db.begin():
            legacy = (await db.execute(text('SELECT revision FROM orbit_meta_connection WHERE id=:id'),{'id':identifier})).scalar_one()
            assert legacy == 3
            revoked = (await db.execute(text('SELECT last_revoked_at FROM orbit_meta_principal_lock WHERE app_id=:id AND principal_id=:principal'),{'id':'123','principal':'12345'})).scalar_one()
            assert revoked is None
        # 来源Bearer转换后立即失效，旧令牌不能在Cookie退出后继续访问。
        assert client.get('/getInfo',headers=bearer_headers).json().get('code') == 401
        cap = client.get('/api/v1/integrations/meta/capabilities',headers=native_headers)
        assert cap.status_code == 200 and len(cap.json()['applications']) == 2
        assert 'isolated-secret' not in cap.text and 'isolated-marketing-token' not in cap.text
        async with sessions() as db, db.begin():
            await browser.logout(db,native_cookies[SESSION_COOKIE],native_cookies[BINDING_COOKIE],
                native_identity.csrf_token,str(uuid4()),str(uuid4()))
        assert client.get('/api/v1/integrations/meta/capabilities',headers=native_headers).status_code == 401
        bind_verified_cookie(identity)
        cases.append(CASES[5])
        if browser_requested:
            from pathlib import Path

            path = Path("/tmp/orbit-meta-browser-cookie.json")
            path.write_text(json.dumps({"cookie_header": cookie_header}), encoding="utf-8")
            path.chmod(0o600)
        await engine.dispose()

    asyncio.run(checks())
    return {"result": "PASS", "external_meta": "NOT_RUN_APP_UNAVAILABLE"}
