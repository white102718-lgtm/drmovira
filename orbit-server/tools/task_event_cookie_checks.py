"""真实本地HTTPS IdP→Cookie→SSE撤销；不代表生产IdP或平台执行。"""

import asyncio
import hashlib
import re
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TASK_EVENT_COOKIE_CASES = [
    "pythonTaskEventCookieActualHttpsCallbackTaskCheckpointAndSse",
    "pythonTaskEventCookieActualDeleteCsrfIdempotencyAndInFlightRevocation",
    "pythonTaskEventCookieActualProviderDisableRevokesIdleObserver",
    "pythonTaskEventCookieActualProviderRevisionRevokesIdleObserver",
    "pythonTaskEventCookieOldSessionAndStreamCannotReviveAfterProviderRestored",
]


def issued_pair(response, binding):
    """仅内存解析Secure Cookie；异常不带响应正文或Cookie。"""
    issued = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        issued.load(header)
        if header.startswith("adpilot_session="):
            assert all(flag in header for flag in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"))
            assert "Domain=" not in header
    assert "adpilot_session" in issued, "真实回调没有签发会话"
    return (
        "adpilot_session=" + issued["adpilot_session"].value + "; __Host-orbit_browser=" + binding
    )


def consume_revocation(lines, started):
    """仅返回无凭据观测指标；拒绝撤权后出现任何带id的旧业务帧。"""
    observed = []
    for line in lines:
        if line:
            observed.append(line)
        if line.startswith("data:"):
            break
    elapsed = time.monotonic() - started
    assert observed == ["event: SCOPE_REVOKED", 'data: {"code":"SCOPE_REVOKED"}']
    assert elapsed < 2, {"revocation_seconds": elapsed}
    return elapsed


def run_task_event_cookie_checks(client, admin, headers, database, idp, cases, *, provider_id=None):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("Cookie事件专项仅允许13306当前UUID隔离库")
    native = 990383
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,))
        assert cursor.fetchone()[0] == 0, "Cookie事件专用身份ID占用，拒绝覆盖"
        cursor.execute("SELECT tenant_id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, team = cursor.fetchone()
        cursor.execute(
            "SELECT id FROM orbit_system_configuration WHERE tenant_id=%s "
            "AND section='OIDC' AND enabled=1",
            (tenant,),
        )
        enabled = [row[0] for row in cursor.fetchall()]
    # 只有显式指定的本地夹具提供者可复用，不能任意停用其他来源解决唯一性冲突。
    assert enabled == ([] if provider_id is None else [provider_id]), "存在非本专项启用OIDC来源"
    owner, role_name = str(uuid4()), "Cookie事件只读-" + uuid4().hex[:12]
    cap = client.get("/api/v1/roles/capabilities", headers=headers)
    assert cap.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": cap.json()["csrf_token"],
            "Idempotency-Key": "event-cookie-role-" + uuid4().hex,
        },
        json={"name": role_name, "menu_codes": ["launch"], "permission_codes": ["tasks.read"]},
    )
    assert role.status_code == 201
    username = "event_cookie_" + uuid4().hex[:12]
    email = username + "@fixture.example.org"
    old_subject, old_email = idp.subject, idp.email
    subject = "Task-Event-Cookie-" + uuid4().hex
    idp.subject, idp.email = subject, email
    configuration = {
        "section": "OIDC",
        "name": "事件Cookie独占来源-" + uuid4().hex[:12],
        "enabled": True,
        "settings": {
            "issuer": idp.issuer,
            "clientId": idp.client_id,
            "redirectUri": idp.redirect_uri,
        },
        "secrets": {"clientSecret": {"operation": "REPLACE", "value": idp.client_secret}},
        "reason": "隔离UUID库真实Cookie事件专项配置",
    }
    provider = None
    restore = None
    reused = provider_id is not None
    metrics = {}
    try:
        if provider_id is None:
            created = client.post(
                "/api/v1/system-configurations",
                headers=headers
                | {
                    "Idempotency-Key": "event-cookie-provider-" + uuid4().hex,
                },
                json=configuration,
            )
            assert created.status_code == 200
            provider = created.json()
        else:
            response = client.get("/api/v1/system-configurations/" + provider_id, headers=headers)
            assert response.status_code == 200
            provider = response.json()
            assert (
                provider["section"] == "OIDC" and provider["settings"] == configuration["settings"]
            )
            configuration["name"] = provider["name"]
        provider_id = provider["id"]
        original_name, original_enabled = provider["name"], provider["enabled"]
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
                (tenant, role.json()["id"]),
            )
            native_role = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,'Cookie事件夹具',%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (native, username, email),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (native, tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
                "invited,created_at) VALUES(%s,%s,%s,%s,'Cookie事件夹具',0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team),
            )
            cursor.execute(
                "INSERT INTO orbit_external_identity(id,tenant_id,user_id,issuer,issuer_digest,"
                "subject,subject_digest,provider_id,verified_email,verified_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(3))",
                (
                    str(uuid4()),
                    tenant,
                    native,
                    idp.issuer,
                    hashlib.sha256(idp.issuer.encode()).digest(),
                    subject,
                    hashlib.sha256(subject.encode()).digest(),
                    provider_id,
                    email,
                ),
            )
        admin.commit()

        def decode(value):
            return value.decode() if isinstance(value, bytes) else value

        async def prepare_task():
            from task_core_fixture import compile_dag, insert_plan, plan

            from orbit_api.task_contract import validate_dag
            from orbit_api.task_manifest import TaskManifestStore

            engine = create_async_engine(
                URL.create(
                    "mysql+asyncmy",
                    username=decode(admin.user),
                    password=decode(admin.password),
                    host=admin.host,
                    port=admin.port,
                    database=database,
                ),
                echo=False,
            )
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            manifest = TaskManifestStore()

            async def call(operation):
                async with sessions() as session, session.begin():
                    return await operation(session)

            try:
                value = plan(owner, team, copies=1)
                graph = compile_dag(value)
                source = await call(lambda s: insert_plan(s, tenant, value))
                task = await call(
                    lambda s: manifest.begin(
                        s, 1, source, 1, graph, str(uuid4()), producer="ISOLATED_TEST"
                    )
                )
                await call(lambda s: manifest.append(s, 1, task, 0, validate_dag(graph)))
                await call(lambda s: manifest.finalize(s, 1, task))
                return task
            finally:
                await engine.dispose()

        task = asyncio.run(prepare_task())

        def issue():
            start = client.post(
                "/api/v1/auth/authorization-sessions",
                headers={"Origin": "https://app.fixture.example"},
                json={"return_to": "/orbit/launch"},
            )
            assert start.status_code == 200
            binding_cookie = SimpleCookie()
            binding_cookie.load(start.headers["set-cookie"])
            binding = binding_cookie["__Host-orbit_browser"].value
            location = idp.authorize(start.json()["authorize_url"])
            callback = client.get(
                "/api/v1/auth/callback?" + urlsplit(location).query,
                headers={"Cookie": "__Host-orbit_browser=" + binding},
            )
            assert callback.status_code == 200
            assert callback.json()["user"]["email"] == email
            pair = issued_pair(callback, binding)
            own = {"Cookie": pair}
            session = client.get("/api/v1/auth/session", headers=own)
            assert session.status_code == 200
            assert session.json()["menu_codes"] == ["launch"]
            assert session.json()["permission_codes"] == ["tasks.read"]
            detail = client.get("/api/v1/tasks/" + task, headers=own)
            assert detail.status_code == 200 and detail.headers.get("x-task-event-checkpoint")
            return own, session.json()["csrf_token"], detail.json()["latest_event_id"]

        def mutate(*, enabled, name):
            nonlocal provider
            updated = client.put(
                "/api/v1/system-configurations/" + provider_id,
                headers=headers
                | {
                    "If-Match": '"' + str(provider["revision"]) + '"',
                    "Idempotency-Key": "cookie-revoke-" + uuid4().hex,
                },
                json=configuration
                | {
                    "enabled": enabled,
                    "name": name,
                    "secrets": {"clientSecret": {"operation": "KEEP"}},
                },
            )
            assert updated.status_code == 200
            assert updated.json()["revision"] == provider["revision"] + 1
            provider = updated.json()

        restore = mutate

        def live_revoke(own, event_id, action, metric, expected_code):
            with client.stream(
                "GET", f"/api/v1/tasks/{task}/events", headers=own | {"Last-Event-ID": event_id}
            ) as stream:
                assert stream.status_code == 200
                lines = stream.iter_lines()
                assert next(lines) == ": keepalive"
                started = time.monotonic()
                action()
                metrics[metric] = consume_revocation(lines, started)
            denied = client.get("/api/v1/tasks/" + task, headers=own)
            assert denied.status_code == 401
            assert denied.json()["code"] == expected_code

        own, csrf, event_id = issue()
        with client.stream(
            "GET", f"/api/v1/tasks/{task}/events", headers=own | {"Last-Event-ID": event_id}
        ) as stream:
            assert stream.status_code == 200 and next(stream.iter_lines()) == ": keepalive"
        cases.append(TASK_EVENT_COOKIE_CASES[0])
        receipt = []
        outgoing = own | {
            "Origin": "https://app.fixture.example",
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "task-event-logout-" + uuid4().hex,
        }

        def logout():
            invalid = client.delete(
                "/api/v1/auth/session", headers=outgoing | {"X-CSRF-Token": "bad"}
            )
            assert invalid.status_code == 403 and invalid.json()["code"] == "CSRF_INVALID"
            first = client.delete("/api/v1/auth/session", headers=outgoing)
            assert first.status_code == 200 and first.json()["state"] == "SIGNED_OUT"
            replay = client.delete("/api/v1/auth/session", headers=outgoing)
            assert replay.status_code == 200 and replay.json() == first.json()
            receipt.append(first.json())

        live_revoke(own, event_id, logout, "logout_seconds", "SESSION_REQUIRED")
        assert len(receipt) == 1
        cases.append(TASK_EVENT_COOKIE_CASES[1])
        disabled_cookie, _, event_id = issue()
        live_revoke(
            disabled_cookie,
            event_id,
            lambda: mutate(enabled=False, name=original_name),
            "provider_disable_seconds",
            "SESSION_REAUTH_REQUIRED",
        )
        cases.append(TASK_EVENT_COOKIE_CASES[2])
        mutate(enabled=True, name=original_name)
        revised_cookie, _, event_id = issue()
        live_revoke(
            revised_cookie,
            event_id,
            lambda: mutate(enabled=True, name=original_name + "-修订"),
            "provider_revision_seconds",
            "SESSION_REAUTH_REQUIRED",
        )
        cases.append(TASK_EVENT_COOKIE_CASES[3])
        mutate(enabled=original_enabled, name=original_name)
        for stale, expected_code in (
            (own, "SESSION_REQUIRED"),
            (disabled_cookie, "SESSION_REAUTH_REQUIRED"),
            (revised_cookie, "SESSION_REAUTH_REQUIRED"),
        ):
            with client.stream("GET", f"/api/v1/tasks/{task}/events", headers=stale) as stream:
                assert stream.status_code == 401
                stream.read()
                assert stream.json()["code"] == expected_code
        cases.append(TASK_EVENT_COOKIE_CASES[4])
        return metrics
    finally:
        idp.subject, idp.email = old_subject, old_email
        # 所有数据属主线UUID库；保留真实审计供主线整体drop。新建来源留禁用，复用来源恢复其启用状态。
        if provider is not None and provider_id is not None and restore is not None:
            desired = original_enabled if reused else False
            if provider["enabled"] != desired or provider["name"] != original_name:
                restore(enabled=desired, name=original_name)
