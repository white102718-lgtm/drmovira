"""独立数据库与真实双向TLS验收；真实AdsPower只在显式参数下访问。"""

import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import httpx
from environment_tls_fixture import make_environment_certificates
from fixture_login import fixture_login
from metric_fact_schema_checks import MetricFactSqlFixture

ENVIRONMENT_LIVE_CASES = [
    "environmentLiveTlsRejectsMissingCertificateAndForgedHeaders",
    "environmentLiveRealCertificateConfigurationIsDeviceScoped",
    "environmentLiveHeartbeatRequiresTwoNewSequences",
    "environmentLiveDuplicateDoesNotRenewAndChangedPayloadRejects",
    "environmentLiveRetiredBootCannotResume",
    "environmentLiveObservedTimeCannotForgeOnline",
    "environmentLiveDiagnosticsCoverageAndReplay",
    "environmentLiveProfilePagingAndCurrentAccountVisibility",
    "environmentLiveIdentityExactBindingAccountCurrencyAndFreshness",
    "environmentLiveBindingRevisionAndUnbindInvalidateIdentity",
    "environmentLiveCertificateRevocationImmediatelyRejects",
    "environmentLiveDeviceRevocationImmediatelyRejects",
    "environmentLiveActualLocalSourceOrExplicitlyDisabled",
]
ROOT = Path(__file__).resolve().parents[1]
TLS_PORT = 18443


def run_environment_live_checks(
    client,
    admin,
    headers,
    fixture,
    password,
    cache,
    database,
    values,
    cases,
    *,
    real_adspower=False,
    browser=False,
    meta_expectation_file=None,
):
    assert admin.host in {"127.0.0.1", "localhost"} and admin.port == 13306
    assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    with socket.socket() as guard:
        guard.bind(("127.0.0.1", TLS_PORT))

    def sql(statement, args=(), fetch=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, args)
            result = cursor.fetchall() if fetch else cursor.rowcount
        admin.commit()
        return result

    def checked(response, status=200):
        if response.status_code != status:
            print(
                {
                    "live_expected": status,
                    "actual": response.status_code,
                    "path": response.request.url.path,
                    "code": response.json().get("code"),
                },
                flush=True,
            )
        assert response.status_code == status
        return response.json()

    def write(revision=None, operation="ENROLL"):
        cap = checked(
            client.get(
                "/api/v1/execution-agents/capabilities",
                headers=headers,
                params={"operation": operation},
            )
        )
        return (
            headers
            | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision else {})
        )

    tenant = sql("SELECT tenant_id FROM orbit_business_user WHERE user_id=1", fetch=True)[0][0]
    agent = checked(
        client.post(
            "/api/v1/execution-agents",
            headers=write(),
            json={
                "name": "隔离mTLS监测验收",
                "endpoint": "http://127.0.0.1:50325",
                "probe_interval": 15,
            },
        ),
        201,
    )
    identifier = agent["id"]
    monitor = f"/api/v1/execution-agents/{identifier}/monitor"
    profiles = f"/api/v1/execution-agents/{identifier}/profiles"
    sql_fixture = MetricFactSqlFixture(admin, database)
    account = sql_fixture.account()
    reader = fixture["users"][1]
    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
        "WHERE tenant_id=%s AND id=%s",
        (reader["id"], reader["team"], tenant, account),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "live-reader-" + uuid4().hex[:8],
                "menu_codes": ["environments"],
                "permission_codes": ["environments.read"],
            },
        ),
        201,
    )
    native = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        True,
    )[0][0]
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (reader["native"], native))
    login = checked(
        fixture_login(client, cache, {"username": reader["name"], "password": password})
    )
    read_headers = {"Authorization": "Bearer " + login["token"]}
    account_row = sql(
        "SELECT external_id,currency,owner_user_id,owner_team_id FROM orbit_ad_account "
        "WHERE tenant_id=%s AND id=%s",
        (tenant, account),
        True,
    )[0]
    external, currency, owner, team = account_row
    profile = "isolated-profile"
    binding_value = {
        "account_id": account,
        "agent_id": identifier,
        "profile_external_id": profile,
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
    }
    binding = checked(
        client.post("/api/v1/profile-bindings", headers=write(), json=binding_value), 201
    )
    with tempfile.TemporaryDirectory(prefix="orbit-device-live-") as temporary:
        control = Path(temporary)
        certs = make_environment_certificates(control / "tls", tenant, identifier)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT / "python"), str(ROOT / "python/ruoyi_fastapi")]
        )
        launch_code = """
import asyncio,json,ssl,sys
from pathlib import Path
from config.orbit_runtime import configure_isolated_fixture
payload=json.load(sys.stdin)
configure_isolated_fixture(payload['values'])
from config.database import DataSourceRegistry
from orbit_api.agent_monitor_routes import create_device_app
from orbit_api.agent_monitor_transport import PeerCertificateH11Protocol
from orbit_api.agent_monitor_store import register_device_certificate
import uvicorn
async def run():
    async with DataSourceRegistry.session(log_sql=False) as session,session.begin():
        await register_device_certificate(session,
            Path(payload['certs']['client_cert']).read_bytes(),
                                          issuer_ca_pem=Path(payload['certs']['ca']).read_bytes(),
                                          tenant_id=payload['tenant'],agent_id=payload['agent'])
    config=uvicorn.Config(create_device_app(),host='127.0.0.1',port=18443,
        http=PeerCertificateH11Protocol,ssl_certfile=payload['certs']['server_cert'],
        ssl_keyfile=payload['certs']['server_key'],ssl_ca_certs=payload['certs']['ca'],
        ssl_cert_reqs=ssl.CERT_REQUIRED,proxy_headers=False,access_log=False,log_level='error')
    try: await uvicorn.Server(config).serve()
    finally: await DataSourceRegistry.dispose_all()
asyncio.run(run())
"""
        context = ssl.create_default_context(cafile=certs["ca"])
        context.load_cert_chain(certs["client_cert"], certs["client_key"])
        with (control / "device-server.log").open("wb") as log:
            child = subprocess.Popen(
                [sys.executable, "-c", launch_code],
                cwd=ROOT / "python/ruoyi_fastapi",
                env=environment,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=log,
            )
            child.stdin.write(
                json.dumps(
                    {"values": values, "certs": certs, "tenant": tenant, "agent": identifier}
                ).encode()
            )
            child.stdin.close()
            try:
                with httpx.Client(
                    base_url=f"https://127.0.0.1:{TLS_PORT}",
                    verify=context,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=10,
                ) as device:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if child.poll() is not None:
                            raise RuntimeError("DEVICE_LISTENER_START_FAILED")
                        try:
                            configuration = checked(device.get("/api/v1/agent-api/configuration"))
                            break
                        except httpx.HTTPError:
                            time.sleep(0.2)
                    else:
                        raise RuntimeError("DEVICE_LISTENER_NOT_READY")
                    _run_live_protocol(
                        client,
                        device,
                        headers,
                        write,
                        sql,
                        checked,
                        configuration,
                        tenant,
                        identifier,
                        monitor,
                        profiles,
                        binding,
                        binding_value,
                        external,
                        currency,
                        cases,
                        read_headers,
                    )
                    # 实际本机采集与gstack由同一仍存活的mTLS监听器接续。
                    result = _run_local_source(
                        admin,
                        client,
                        device,
                        headers,
                        write,
                        sql,
                        checked,
                        tenant,
                        identifier,
                        certs,
                        control,
                        database,
                        password,
                        real_adspower,
                        browser,
                        binding_value,
                        meta_expectation_file,
                    )
                    cases.append(ENVIRONMENT_LIVE_CASES[-1])
                    checked(
                        client.post(
                            f"/api/v1/execution-agents/{identifier}/revoke",
                            headers=write(1, "REVOKE"),
                            json={"reason": "隔离监测验收结束"},
                        )
                    )
                    checked(device.get("/api/v1/agent-api/configuration"), 403)
                    cases.append(ENVIRONMENT_LIVE_CASES[11])
                    return result
            finally:
                log.flush()
                if child.poll() not in (None, 0):
                    Path("/tmp/environment-device-server-failure.log").write_bytes(
                        (control / "device-server.log").read_bytes()
                    )
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)


def _run_live_protocol(
    client,
    device,
    headers,
    write,
    sql,
    checked,
    configuration,
    tenant,
    agent,
    monitor,
    profiles,
    binding,
    binding_value,
    external,
    currency,
    cases,
    read_headers,
):
    path = "/api/v1/agent-api/heartbeats"
    try:
        with httpx.Client(verify=False, trust_env=False, timeout=3) as anonymous:
            anonymous.post(
                f"https://127.0.0.1:{TLS_PORT}" + path,
                headers={"X-Client-Cert": "forged", "X-Agent-ID": agent},
                json={},
            )
    except httpx.HTTPError:
        pass
    else:
        raise AssertionError("无设备证书不应完成HTTP请求")
    checked(client.post(path, headers=headers, json={}), 404)
    cases.append(ENVIRONMENT_LIVE_CASES[0])
    assert configuration["agent_id"] == agent
    assert configuration["bindings"] == [
        {
            "id": binding["id"],
            "revision": 1,
            "account_id": binding["account_id"],
            "profile_external_id": binding["profile_external_id"],
            "external_account_id": external,
            "currency": currency,
        }
    ]
    cases.append(ENVIRONMENT_LIVE_CASES[1])
    boot = str(uuid4())

    def heartbeat(seq, boot_id=boot):
        observed = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return {
            "agent_id": agent,
            "boot_id": boot_id,
            "seq": seq,
            "observed_at": observed,
            "profiles": [
                {
                    "id": str(uuid5(UUID(agent), p)),
                    "agent_id": agent,
                    "external_profile_id": p,
                    "process_state": "ACTIVE",
                    "identity_state": "UNKNOWN",
                    "account_ids": [],
                    "observed_at": observed,
                }
                for p in ["isolated-profile", *[f"page-{i:02}" for i in range(20)]]
            ],
        }

    first = heartbeat(1)
    checked(device.post(path, json=first))
    assert checked(client.get(monitor, headers=headers))["machine_state"] == "SUSPECT"
    second = heartbeat(2)
    ack = checked(device.post(path, json=second))
    assert checked(client.get(monitor, headers=headers))["machine_state"] == "READY"
    current = checked(client.get(f"/api/v1/execution-agents/{agent}", headers=headers))
    assert current["revision"] == 1 and current["state"] == "READY"
    cases.append(ENVIRONMENT_LIVE_CASES[2])
    previous = sql(
        "SELECT last_seq,received_at,revision FROM orbit_agent_monitor_head "
        "WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
        True,
    )
    assert checked(device.post(path, json=second)) == ack
    assert (
        sql(
            "SELECT last_seq,received_at,revision FROM orbit_agent_monitor_head "
            "WHERE tenant_id=%s AND agent_id=%s",
            (tenant, agent),
            True,
        )
        == previous
    )
    checked(device.post(path, json=second | {"profiles": []}), 409)
    cases.append(ENVIRONMENT_LIVE_CASES[3])
    new_boot = str(uuid4())
    third = heartbeat(1, new_boot)
    checked(device.post(path, json=third))
    checked(device.post(path, json=heartbeat(3)), 409)
    checked(device.post(path, json=second), 409)
    fourth = heartbeat(2, new_boot)
    checked(device.post(path, json=fourth))
    cases.append(ENVIRONMENT_LIVE_CASES[4])
    future = heartbeat(3, new_boot) | {
        "observed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()
    }
    checked(device.post(path, json=future), 422)
    cases.append(ENVIRONMENT_LIVE_CASES[5])
    diag = {k: fourth[k] for k in ("agent_id", "boot_id", "seq", "observed_at")} | {
        "api_status": "READY",
        "inventory_coverage": "ACTIVE_ONLY",
        "error_code": "ADSPOWER_SUBSCRIPTION_REQUIRED",
    }
    dack = checked(device.post("/api/v1/agent-api/diagnostics", json=diag))
    assert checked(device.post("/api/v1/agent-api/diagnostics", json=diag)) == dack
    m = checked(client.get(monitor, headers=headers))
    assert m["inventory_coverage"] == "ACTIVE_ONLY" and m["api_status"] == "READY"
    checked(
        device.post("/api/v1/agent-api/diagnostics", json=diag | {"inventory_coverage": "FULL"}),
        409,
    )
    cases.append(ENVIRONMENT_LIVE_CASES[6])
    page = checked(client.get(profiles, headers=headers, params={"page_size": 20}))
    assert len(page["items"]) == 20 and page["next_cursor"]
    page2 = checked(
        client.get(
            profiles, headers=headers, params={"page_size": 20, "cursor": page["next_cursor"]}
        )
    )
    assert len(page2["items"]) == 1
    assert len({p["id"] for p in page["items"] + page2["items"]}) == 21
    bound = next(
        p for p in page["items"] + page2["items"] if p["external_profile_id"] == "isolated-profile"
    )
    assert bound["account_ids"] == [binding["account_id"]] and bound["identity_state"] == "UNKNOWN"
    private_page = checked(client.get(profiles, headers=read_headers))
    assert (
        len(private_page["items"]) == 1
        and private_page["items"][0]["external_profile_id"] == "isolated-profile"
    )
    assert checked(client.get(monitor, headers=read_headers))["agent_id"] == agent
    assert (
        "accounts.read" not in checked(client.get("/getInfo", headers=read_headers))["permissions"]
    )
    cases.append(ENVIRONMENT_LIVE_CASES[7])
    report = {k: fourth[k] for k in ("agent_id", "boot_id", "seq", "observed_at")} | {
        "event_id": str(uuid4()),
        "binding_id": binding["id"],
        "binding_revision": 1,
        "profile_external_id": "isolated-profile",
        "external_account_id": external,
        "currency": currency,
        "identity_state": "VALID",
        "adapter_version": "ADSPOWER_META_DOM_V2",
        "evidence_sha256": "a" * 64,
    }
    # 技术协议夹具证明核验逻辑，明确不是本机Meta正向身份验收。
    checked(
        device.post(
            "/api/v1/agent-api/identity-reports",
            json=report | {"adapter_version": "ADSPOWER_META_DOM_V1"},
        ),
        422,
    )
    iack = checked(device.post("/api/v1/agent-api/identity-reports", json=report))
    assert checked(device.post("/api/v1/agent-api/identity-reports", json=report)) == iack
    current = checked(client.get("/api/v1/profile-bindings/" + binding["id"], headers=headers))
    assert current["identity_state"] == "VALID" and current["revision"] == 1
    mismatch = report | {"event_id": str(uuid4()), "external_account_id": "999999999999999"}
    checked(device.post("/api/v1/agent-api/identity-reports", json=mismatch), 422)
    stale = report | {"event_id": str(uuid4()), "binding_revision": 2}
    checked(device.post("/api/v1/agent-api/identity-reports", json=stale), 409)
    cases.append(ENVIRONMENT_LIVE_CASES[8])
    updated = checked(
        client.put(
            "/api/v1/profile-bindings/" + binding["id"],
            headers=write(1),
            json=binding_value | {"profile_external_id": "changed-profile"},
        )
    )
    assert updated["revision"] == 2 and updated["identity_state"] == "UNKNOWN"
    checked(
        device.post("/api/v1/agent-api/identity-reports", json=report | {"event_id": str(uuid4())}),
        409,
    )
    checked(
        client.post(
            "/api/v1/profile-bindings/" + binding["id"] + "/unbind",
            headers=write(2),
            json={"reason": "isolated live check"},
        )
    )
    assert checked(device.get("/api/v1/agent-api/configuration"))["bindings"] == []
    checked(client.get(profiles, headers=read_headers), 404)
    checked(client.get(monitor, headers=read_headers), 404)
    cases.append(ENVIRONMENT_LIVE_CASES[9])
    sql(
        "UPDATE orbit_agent_certificate SET revoked_at=UTC_TIMESTAMP(6) "
        "WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
    )
    checked(device.get("/api/v1/agent-api/configuration"), 403)
    checked(device.post(path, json=fourth), 403)
    # 隔离SQL故障开关恢复，非产品撤销恢复接口；实际设备撤销在所有采集结束后验。
    sql(
        "UPDATE orbit_agent_certificate SET revoked_at=NULL WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
    )
    cases.append(ENVIRONMENT_LIVE_CASES[10])


def _run_local_source(
    admin,
    client,
    device,
    headers,
    write,
    sql,
    checked,
    tenant,
    agent,
    certs,
    control,
    database,
    password,
    real_adspower,
    browser,
    binding_value,
    meta_expectation_file,
):
    if not real_adspower:
        assert not browser, "真实浏览器专项必须显式启用本机采集"
        return {"actual_local_source": "NOT_REQUESTED", "advertising_writes": False}
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "python")
    collect_code = """
import asyncio,json
from orbit_agent.adspower_readonly import ReadonlyAdsPower
from orbit_agent.polling import collect_only
async def main():
    adapter=ReadonlyAdsPower()
    discovery=await adapter.discover()
    active={external for external,state in discovery.profiles if state=='ACTIVE'}
    # 用户已授权当前Mac只读验收；仅唯一已打开Profile，无开户或导航副作用。
    result=await collect_only(adapter,active if len(active)==1 else set())
    print(json.dumps(result | {"_active_profiles": sorted(active)}))
asyncio.run(main())
"""
    observed = subprocess.run(
        [sys.executable, "-c", collect_code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=40,
        check=True,
    )
    local = json.loads(observed.stdout)
    active = local.pop("_active_profiles")
    actual_binding = None
    if meta_expectation_file:
        expectation = _load_meta_expectation(meta_expectation_file)
        if len(active) != 1:
            raise RuntimeError("META_REQUIRES_ONE_EXPLICIT_ACTIVE_PROFILE")
        sql(
            "UPDATE orbit_ad_account SET external_id=%s,currency=%s WHERE tenant_id=%s AND id=%s",
            (
                expectation["external_account_id"],
                expectation["currency"],
                tenant,
                binding_value["account_id"],
            ),
        )
        sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
        actual_binding = checked(
            client.post(
                "/api/v1/profile-bindings",
                headers=write(),
                json=binding_value | {"profile_external_id": active[0]},
            ),
            201,
        )
    assert local["api_status"] == "READY", local.get("error_code")
    command = [
        sys.executable,
        "-m",
        "orbit_agent.polling",
        "--device-origin",
        f"https://127.0.0.1:{TLS_PORT}",
        "--agent-id",
        agent,
        "--ca-file",
        certs["ca"],
        "--certificate",
        certs["client_cert"],
        "--key-file",
        certs["client_key"],
        "--spool-dir",
        str(control / "spool"),
        "--forever",
    ]
    if actual_binding:
        command.extend(["--profile-id", active[0]])
    log_path = control / "agent-runtime.jsonl"
    with log_path.open("wb") as log:
        worker = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                if worker.poll() is not None:
                    raise RuntimeError("REAL_AGENT_EXITED")
                m = checked(
                    client.get(f"/api/v1/execution-agents/{agent}/monitor", headers=headers)
                )
                lines = log_path.read_text().splitlines()
                reports = [json.loads(x) for x in lines if x.startswith("{")]
                if (
                    len(reports) >= 2
                    and reports[-1].get("monitor_state") == "READY"
                    and m["api_status"] == "READY"
                    and (not actual_binding or reports[-1].get("identity_report_count", 0) >= 1)
                ):
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("REAL_AGENT_HEARTBEAT_NOT_READY")
            assert reports[-1]["delivery"] == "ACKNOWLEDGED"
            page = checked(
                client.get(f"/api/v1/execution-agents/{agent}/profiles", headers=headers)
            )
            assert any(p["process_state"] == "ACTIVE" for p in page["items"])
            identity = None
            if actual_binding:
                identity = checked(
                    client.get("/api/v1/profile-bindings/" + actual_binding["id"], headers=headers)
                )["identity_state"]
            result = {
                "actual_local_source": local,
                "runtime": reports[-1],
                "meta_identity_state": identity,
                "meta_positive_identity": (
                    "VERIFIED"
                    if identity == "VALID"
                    else "NOT_VERIFIED_" + identity
                    if identity
                    else "NOT_REQUESTED"
                ),
                "advertising_writes": False,
            }
            if browser:
                from rules_internal_browser_checkpoint import run_rules_internal_browser_checkpoint

                (control / "runtime-control.json").write_text(
                    json.dumps({"pid": worker.pid, "agent_id": agent, "database": database})
                )
                print(
                    json.dumps(
                        {"environment_runtime_control": str(control / "runtime-control.json")}
                    ),
                    flush=True,
                )
                result["browser"] = run_rules_internal_browser_checkpoint(
                    admin, database, password, static_dist=ROOT.parent / "orbit-web/dist"
                )
            return result
        finally:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)


def _load_meta_expectation(path):
    """预期仅来自显式私有文件；不写入源码、日志或公开验收结果。"""
    path = Path(path)
    stat = path.stat()
    if stat.st_size > 4096 or stat.st_mode & 0o077:
        raise ValueError("META_EXPECTATION_FILE_MUST_BE_PRIVATE_AND_BOUNDED")
    value = json.loads(path.read_text())
    if (
        type(value) is not dict
        or set(value) != {"external_account_id", "currency"}
        or type(value["external_account_id"]) is not str
        or not re.fullmatch(r"[0-9]{1,64}", value["external_account_id"])
        or type(value["currency"]) is not str
        or not re.fullmatch(r"[A-Z]{3}", value["currency"])
    ):
        raise ValueError("META_EXPECTATION_INVALID")
    return value
