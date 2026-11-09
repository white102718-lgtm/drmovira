"""隔离数据库实际能力发行/撤销及HTTP列表，所有凭证均为测试专用合成回执。"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_CASES = [
    "environmentCapabilityExactPageAndStrictQueries",
    "environmentCapabilityControlledPublicationAndVersionGate",
    "environmentCapabilityAccountScopeAndChangedBindingFailClosed",
    "environmentCapabilityRevokeDoesNotFallBackToOlderReceipt",
    "environmentCapabilityAuditFailureRollsBackPublication",
]

HELPER = """
import asyncio,json,sys
from datetime import timedelta
from config.orbit_runtime import configure_isolated_fixture
p=json.load(sys.stdin)
configure_isolated_fixture(p['values'])
from config.database import DataSourceRegistry
from orbit_api.agent_capability_store import AgentCapabilityStore,require_verified
from orbit_api.agent_capability_contract import AcceptanceEvidence,VERSIONS
from orbit_api.agent_monitor_store import now_utc
from orbit_api.errors import OrbitError
from orbit_api import execution_agent_access as access
async def main():
    try:
        async with DataSourceRegistry.session(log_sql=False) as s,s.begin():
            store=AgentCapabilityStore()
            versions={k:'isolated-fixture-v1' for k in VERSIONS}
            if p['action'] in ('publish','rollback'):
                now=await now_utc(s)
                evidence=AcceptanceEvidence('a'*64,
                    {k:'b'*64 for k in (
                        'success_readback','explicit_failure','unknown','challenge')},
                    now,now+timedelta(hours=1))
                if p['action']=='rollback':
                    async def fail(*args,**kwargs): raise RuntimeError('FIXTURE_AUDIT_FAILURE')
                    access.event=fail
                result=await store.publish(s,p['actor'],profile_binding_id=p['binding'],
                    operation_kind='PAUSE',entity_type='CAMPAIGN',versions=versions,
                    evidence=evidence,request_id=p['request'])
            elif p['action']=='revoke':
                await store.revoke(s,p['actor'],p['capability'],p['request']);result='REVOKED'
            else:
                if p['action']=='wrong_version': versions['adapter_version']='other'
                row=await require_verified(s,tenant_id=p['tenant'],agent_id=p['agent'],
                    profile_binding_id=p['binding'],operation_kind='PAUSE',
                    entity_type='CAMPAIGN',versions=versions)
                result=row['id']
        print(json.dumps({'result':result}))
    except OrbitError as e: print(json.dumps({'code':e.code}))
    except RuntimeError as e:
        if str(e)!='FIXTURE_AUDIT_FAILURE': raise
        print(json.dumps({'code':'FIXTURE_AUDIT_FAILURE'}))
    finally: await DataSourceRegistry.dispose_all()
asyncio.run(main())
"""


def run_capability_checks(
    client, headers, read_headers, values, database, tenant, agent, binding, sql, checked, cases
):
    assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    root = "/api/v1/environment-capabilities"
    actor = checked(client.get("/api/v1/execution-agents/capabilities", headers=headers))[
        "actor_id"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "python"), str(ROOT / "python/ruoyi_fastapi")])

    def operation(action, capability=None):
        p = dict(
            values=values,
            actor=actor,
            tenant=tenant,
            agent=agent,
            binding=binding["id"],
            request=str(uuid4()),
            action=action,
            capability=capability,
        )
        done = subprocess.run(
            [sys.executable, "-c", HELPER],
            input=json.dumps(p),
            text=True,
            capture_output=True,
            cwd=ROOT / "python/ruoyi_fastapi",
            env=env,
            timeout=40,
        )
        assert done.returncode == 0, "CAPABILITY_FIXTURE_HELPER_FAILED"
        return json.loads(done.stdout.strip().splitlines()[-1])

    def page(identity=headers):
        return checked(client.get(root, headers=identity))

    assert set(page()) == {"items", "next_cursor", "data_as_of", "scope_version"}
    checked(client.get(root + "?agent_id=" + agent, headers=headers), 400)
    checked(client.get(root + "?page_size=201", headers=headers), 422)
    checked(client.get(root, headers=headers | {"X-Target-Tenant": str(uuid4())}), 403)
    cases.append(CAPABILITY_CASES[0])
    first = operation("publish")["result"]
    second = operation("publish")["result"]
    assert operation("require")["result"] == second
    assert operation("wrong_version")["code"] == "CAPABILITY_UNVERIFIED"
    assert any(r["id"] == second and r["state"] == "VERIFIED" for r in page()["items"])
    cases.append(CAPABILITY_CASES[1])
    assert any(r["id"] == second for r in page(read_headers)["items"])
    sql(
        "UPDATE orbit_profile_binding SET revision=revision+1 WHERE tenant_id=%s AND id=%s",
        (tenant, binding["id"]),
    )
    assert operation("require")["code"] == "CAPABILITY_UNVERIFIED"
    assert next(r for r in page()["items"] if r["id"] == second)["state"] == "UNVERIFIED"
    sql(
        "UPDATE orbit_profile_binding SET revision=revision-1 WHERE tenant_id=%s AND id=%s",
        (tenant, binding["id"]),
    )
    original = binding["ownership"]["owner_user_id"]
    sql(
        "UPDATE orbit_profile_binding SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
        (str(uuid4()), tenant, binding["id"]),
    )
    assert all(r["id"] not in (first, second) for r in page(read_headers)["items"])
    sql(
        "UPDATE orbit_profile_binding SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
        (original, tenant, binding["id"]),
    )
    cases.append(CAPABILITY_CASES[2])
    assert operation("revoke", second)["result"] == "REVOKED"
    assert operation("require")["code"] == "CAPABILITY_UNVERIFIED"
    cases.append(CAPABILITY_CASES[3])
    count = len(page()["items"])
    assert operation("rollback")["code"] == "FIXTURE_AUDIT_FAILURE"
    assert len(page()["items"]) == count
    cases.append(CAPABILITY_CASES[4])
