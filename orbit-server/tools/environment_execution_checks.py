"""受控环境验收包装：原HTTP受理任务，真实SQL租约，合成身份绝非真实广告授权。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from agent_execution_checks import create_accepted_source
from environment_tls_fixture import make_environment_certificates

ROOT = Path(__file__).resolve().parents[1]
HELPER = """
import asyncio,json,sys
from pathlib import Path
from uuid import uuid4,uuid5,UUID
from datetime import datetime,UTC,timedelta
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from config.orbit_runtime import configure_isolated_fixture
p=json.load(sys.stdin);configure_isolated_fixture(p['values'])
from config.database import DataSourceRegistry
from orbit_api.agent_monitor_store import AgentMonitorStore,register_device_certificate
from orbit_api.agent_capability_store import AgentCapabilityStore
from orbit_api.agent_capability_contract import AcceptanceEvidence,VERSIONS
from agent_execution_checks import run_agent_execution_checks
async def main():
    cases=[];sessions=lambda:DataSourceRegistry.session(log_sql=False)
    der=x509.load_pem_x509_certificate(Path(p['certs']['client_cert']).read_bytes()).public_bytes(Encoding.DER)
    boot=str(uuid4()); agent=p['grant']['agent_id'];binding=p['grant']['profile_binding_id']
    profile='isolated-execution-profile'; monitor=AgentMonitorStore()
    try:
        async with sessions() as s,s.begin():
            await register_device_certificate(s,Path(p['certs']['client_cert']).read_bytes(),
                issuer_ca_pem=Path(p['certs']['ca']).read_bytes(),tenant_id=p['grant']['tenant_id'],agent_id=agent)
        for seq in (1,2):
            now=datetime.now(UTC).isoformat()
            report=dict(agent_id=agent,boot_id=boot,seq=seq,observed_at=now,
                profiles=[dict(id=str(uuid5(UUID(agent),profile)),agent_id=agent,
                external_profile_id=profile,process_state='INACTIVE',identity_state='UNKNOWN',
                account_ids=[p['grant']['instruction']['account_id']],observed_at=now)])
            async with sessions() as s,s.begin():
                await monitor.heartbeat(s,der,report,str(uuid4()))
        async with sessions() as s,s.begin():
            await monitor.identity_report(s,der,dict(agent_id=agent,boot_id=boot,seq=2,
                observed_at=datetime.now(UTC).isoformat(),event_id=str(uuid4()),binding_id=binding,
                binding_revision=1,profile_external_id=profile,
                external_account_id=p['grant']['instruction']['external_account_id'],currency='USD',
                identity_state='VALID',adapter_version='ADSPOWER_META_DOM_V2',evidence_sha256='a'*64),str(uuid4()))
            now=datetime.now(UTC)
            evidence=AcceptanceEvidence('a'*64,{k:'b'*64 for k in
                ('success_readback','explicit_failure','unknown','challenge')},now,now+timedelta(hours=1))
            await AgentCapabilityStore().publish(s,p['grant']['actor_id'],
                profile_binding_id=binding,
                operation_kind='CREATE',entity_type='CAMPAIGN',versions=p['grant']['versions'],
                evidence=evidence,request_id=str(uuid4()))
        await run_agent_execution_checks(sessions,p['database'],der,p['grant'],cases)
        print(json.dumps({'cases':cases}))
    finally: await DataSourceRegistry.dispose_all()
asyncio.run(main())
"""


def run_environment_execution_checks(client, admin, headers, values, database, sql, checked, cases):
    task = create_accepted_source(client, admin, headers)
    source = sql(
        "SELECT c.tenant_id,c.node_id,c.node_key,c.account_id,p.id,p.manifest_hash,"
        "t.owner_user_id,t.owner_team_id FROM orbit_launch_execution_command c JOIN "
        "orbit_launch_execution_preparation p ON p.tenant_id=c.tenant_id AND "
        "p.id=c.preparation_id JOIN orbit_task t ON t.tenant_id=c.tenant_id AND "
        "t.id=c.task_id WHERE c.task_id=%s AND c.kind='CAMPAIGN' ORDER BY c.ordinal "
        "LIMIT 1",
        (task["id"],),
        True,
    )[0]
    tenant, node, key, account, manifest, manifest_hash, owner, team = source
    external = str(uuid4().int)
    sql(
        "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
        "owner_user_id,owner_team_id,currency,timezone_id,auth_status,"
        "account_status,value_json,details_json,bound_at,created_at) VALUES(%s,%s,"
        "%s,'ISOLATED_EXECUTION','ISOLATED',%s,%s,'USD','Asia/Shanghai',"
        "'AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
        (tenant, account, external, owner, team),
    )
    caps = checked(
        client.get(
            "/api/v1/execution-agents/capabilities", headers=headers, params={"operation": "ENROLL"}
        )
    )

    def write():
        return headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid4())}

    agent = checked(
        client.post(
            "/api/v1/execution-agents",
            headers=write(),
            json={
                "name": "隔离执行租约验收",
                "endpoint": "http://127.0.0.1:50325",
                "probe_interval": 15,
            },
        ),
        201,
    )["id"]
    binding = checked(
        client.post(
            "/api/v1/profile-bindings",
            headers=write(),
            json={
                "account_id": account,
                "agent_id": agent,
                "profile_external_id": "isolated-execution-profile",
                "ownership": {"owner_user_id": owner, "owner_team_id": team},
            },
        ),
        201,
    )
    versions = {
        k: "isolated-fixture-v1"
        for k in (
            "workflow_version",
            "adapter_version",
            "client_version",
            "browser_version",
            "page_language",
        )
    }
    grant = dict(
        tenant_id=tenant,
        id=str(uuid4()),
        task_id=task["id"],
        node_id=node,
        operation_id=str(uuid4()),
        agent_id=agent,
        profile_binding_id=binding["id"],
        binding_revision=1,
        actor_id=1,
        entity_type="CAMPAIGN",
        versions=versions,
        instruction=dict(
            account_id=account,
            external_account_id=external,
            node_key=key,
            kind="CREATE",
            target=None,
            plan=None,
            manual=None,
            policy_version="isolated-policy-v1",
            submission_group_id=None,
            execution_manifest_id=manifest,
            execution_manifest_hash=manifest_hash,
        ),
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "python"), str(ROOT / "python/ruoyi_fastapi"), str(ROOT / "tools")]
    )
    with tempfile.TemporaryDirectory(prefix="orbit-execution-sql-") as folder:
        certs = make_environment_certificates(Path(folder), tenant, agent)
        result = subprocess.run(
            [sys.executable, "-c", HELPER],
            input=json.dumps(dict(values=values, database=database, grant=grant, certs=certs)),
            text=True,
            capture_output=True,
            cwd=ROOT / "python/ruoyi_fastapi",
            env=env,
            timeout=80,
        )
        if result.returncode:
            Path("/tmp/orbit-execution-sql-error.log").write_text(result.stderr)
            raise AssertionError(
                "EXECUTION_SQL_HELPER_FAILED; local /tmp/orbit-execution-sql-error.log"
            )
        cases.extend(json.loads(result.stdout.strip().splitlines()[-1])["cases"])
