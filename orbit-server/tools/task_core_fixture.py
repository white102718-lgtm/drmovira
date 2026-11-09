"""T1隔离协议专用合法配置→真实B编译DAG，不提供生产能力/预检证据。"""

from uuid import UUID, uuid4

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import build_compatibility_evidence, solve_allocation
from orbit_api.launch_contract import parse_plan
from orbit_api.launch_dag import build_launch_dag
from orbit_api.launch_expansion import ad_slots


def plan(owner, team, *, branches=None, copies=300):
    campaigns = [
        {
            "local_id": str(uuid4()),
            "copies": 1,
            "adsets": [
                {
                    "local_id": str(uuid4()),
                    "copies": 1,
                    "ads": [
                        {"local_id": str(uuid4()), "copies": min(50, copies - offset)}
                        for offset in range(0, copies, 50)
                    ]
                    if branches is None
                    else [{"local_id": str(uuid4()), "copies": 1}],
                }
            ],
        }
        for _ in range(branches or 1)
    ]
    value = {
        "name": "真实Task隔离协议夹具",
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
        "account_ids": [str(uuid4())],
        "campaigns": campaigns,
        "asset_ids": [str(UUID(int=800000 + index)) for index in range(6 if branches else 1)],
        "identity_bindings": [],
        "allow_repeat": True,
        "activate_after_create": branches is not None,
        "execution_mode": "META_API",
    }
    return parse_plan(canonical(value).encode())


def compile_dag(value):
    slots = ad_slots(value)
    versions = {asset: 1 for asset in value["asset_ids"]}
    evidence = build_compatibility_evidence(
        slots,
        value["asset_ids"],
        capability_version="ISOLATED-TASK-PROTOCOL-NOT-PLATFORM",
        source_hash="a" * 64,
        verified=True,
        complete=True,
        evaluate=lambda _slot, _asset: True,
        material_revisions=versions,
    )
    allocation = solve_allocation(
        slots, value["asset_ids"], evidence, allow_repeat=True, seed=0, material_revisions=versions
    )
    return build_launch_dag(
        value,
        plan_revision=1,
        allocation=allocation,
        compatibility=evidence,
        material_revisions=versions,
    )


async def insert_plan(session, tenant, payload):
    """真实同租户021主表/版本；仅SQL夹具，不冒充已通过真实引用/平台预检。"""
    identifier = str(uuid4())
    values = {
        "tenant": tenant,
        "id": identifier,
        "owner": payload["ownership"]["owner_user_id"],
        "team": payload["ownership"]["owner_team_id"],
        "name": payload["name"],
        "json": canonical(payload),
        "hash": digest(payload),
        "bytes": len(canonical(payload).encode()),
        "accounts": len(payload["account_ids"]),
        "assets": len(payload["asset_ids"]),
    }
    await session.execute(
        text(
            "INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,owner_team_id,name,"
            "state,revision,payload_json,payload_hash,payload_bytes,account_count,asset_count,"
            "created_at,updated_at) "
            "VALUES(:tenant,:id,:owner,:team,:name,'DRAFT',1,:json,:hash,:bytes,:accounts,:assets,"
            "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
        ),
        values,
    )
    await session.execute(
        text(
            "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,"
            "payload_hash,dependency_json,created_at,created_by) "
            "VALUES(:tenant,:id,1,:json,:hash,'{}',UTC_TIMESTAMP(3),1)"
        ),
        values,
    )
    await session.execute(
        text("UPDATE orbit_launch_clock SET plan_revision=plan_revision+1 WHERE tenant_id=:tenant"),
        values,
    )
    return identifier
