"""039原execute隔离协议：真实SQL清单/引用，不是平台或CLEAN权威证明。

仅127.0.0.1:13306及orbit_py_it_UUID库；没有HTTP写后门或外部平台调用。
素材/身份/能力/归因均明确ISOLATED_TEST样本，生产Provider不得复用。
"""

import hashlib
import json
from dataclasses import replace
from uuid import UUID, uuid4

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import build_compatibility_evidence, solve_allocation
from orbit_api.launch_execution_contract import prepare_execution
from orbit_api.launch_execution_store import (
    ExecutionAuthorityProvider,
    ExecutionEvidence,
    database_now,
)
from orbit_api.launch_expansion import ad_slots
from orbit_api.launch_validation_store import ObservationReference, ValidationInput
from orbit_api.reference_access import scope_version

if __package__:
    from .launch_validation_fixture import PREFIX, IsolatedValidationProvider, first, guard
else:
    from launch_validation_fixture import PREFIX, IsolatedValidationProvider, first, guard

EXECUTION_MARKER = "_EXECUTE_"


def create_protocol_plan(admin, tenant, owner, team, *, mode="SUCCESS", activate=False, copies=2):
    """实际021/032行的显式SQL样本，不声称生产来源、引用或CLEAN已核验。"""
    if __package__:
        from .task_core_fixture import plan as skeleton
    else:
        from task_core_fixture import plan as skeleton

    from orbit_api.launch_expansion import campaign_slots

    if type(copies) is not int or copies < 1:
        raise ValueError("隔离协议副本数须为正整数")
    plan = skeleton(owner, team, copies=copies)
    plan["name"] = PREFIX + "EXECUTE_" + mode + "_" + uuid4().hex[:10]
    plan["activate_after_create"] = activate
    campaign = plan["campaigns"][0]
    campaign.update(
        objective="OUTCOME_SALES",
        buying_type="AUCTION",
        special_ad_categories=[],
        bid_strategy="LOWEST_COST_WITHOUT_CAP",
        budget={
            "owner": "CAMPAIGN",
            "type": "DAILY",
            "amount": "12.34",
            "currency": "USD",
            "spend_cap": None,
        },
    )
    group = campaign["adsets"][0]
    group.update(
        name="隔离完整广告组",
        country_codes=["US"],
        age_min=18,
        age_max=65,
        placements="AUTO",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        metric_profile_id=str(UUID(int=93903)),
        start_time="2026-11-09T00:00:00.000Z",
    )
    for ad in group["ads"]:
        ad.update(
            name="隔离完整广告",
            title="实际协议标题",
            body="实际协议正文",
            cta="LEARN_MORE",
            asset_type="IMAGE",
            url="https://example.org/isolated-execution",
        )
    plan["identity_bindings"] = [
        {
            "account_id": plan["account_ids"][0],
            "page_id": "123456",
            "groups": [
                {
                    "adset_local_id": group["local_id"],
                    "pixel_id": "234567",
                    "conversion_event": "PURCHASE",
                    "application_id": None,
                    "object_store_url": None,
                }
            ],
            "ad_overrides": [],
        }
    ]
    identifier, allocation, names = str(uuid4()), str(uuid4()), str(uuid4())
    payload = canonical(plan)
    revisions = {asset: 1 for asset in plan["asset_ids"]}
    compatibility = build_compatibility_evidence(
        ad_slots(plan),
        plan["asset_ids"],
        capability_version="ISOLATED_PROTOCOL_NOT_PLATFORM",
        source_hash=digest([digest(plan), "ISOLATED_COMPATIBILITY"]),
        verified=True,
        complete=True,
        evaluate=lambda _slot, _asset: True,
        material_revisions=revisions,
    )
    solution = solve_allocation(
        ad_slots(plan),
        plan["asset_ids"],
        compatibility,
        allow_repeat=True,
        seed=0,
        material_revisions=revisions,
    )
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATE(UTC_TIMESTAMP(3)+INTERVAL 8 HOUR)")
        day = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,owner_team_id,name,state,"
            "revision,payload_json,payload_hash,payload_bytes,account_count,asset_count,"
            "created_at,updated_at) "
            "VALUES(%s,%s,%s,%s,%s,'DRAFT',1,%s,%s,%s,1,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (
                tenant,
                identifier,
                owner,
                team,
                plan["name"],
                payload,
                digest(plan),
                len(payload.encode()),
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,"
            "payload_hash,dependency_json,created_at,created_by) "
            "VALUES(%s,%s,1,%s,%s,'{}',UTC_TIMESTAMP(3),1)",
            (tenant, identifier, payload, digest(plan)),
        )
        cursor.execute(
            "INSERT INTO orbit_launch_allocation(tenant_id,id,plan_id,plan_revision,state,task_id,"
            "algorithm_version,seed,input_hash,warnings_json,active,created_at,updated_at) "
            "VALUES(%s,%s,%s,1,'SUCCEEDED',NULL,'allocation-v1',0,%s,'[]',1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, allocation, identifier, solution.input_hash),
        )
        cursor.executemany(
            "INSERT INTO orbit_launch_allocation_item(tenant_id,allocation_id,ordinal,slot_key,"
            "account_id,asset_id,asset_revision,asset_sha256) VALUES(%s,%s,%s,%s,%s,%s,1,%s)",
            [
                (tenant, allocation, n, slot.key, slot.account_id, plan["asset_ids"][0], "a" * 64)
                for n, slot in enumerate(ad_slots(plan))
            ],
        )
        cursor.execute(
            "INSERT INTO orbit_launch_name_reservation(tenant_id,id,plan_id,plan_revision,"
            "naming_date,"
            "source_hash,created_at) VALUES(%s,%s,%s,1,%s,%s,UTC_TIMESTAMP(3))",
            (tenant, names, identifier, day, digest([identifier, "isolated-names"])),
        )
        cursor.executemany(
            "INSERT INTO orbit_launch_name_item(tenant_id,reservation_id,ordinal,"
            "slot_key,name,sequence) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            [
                (
                    tenant,
                    names,
                    n,
                    "/".join(map(str, slot)),
                    f"隔离系列_{day:%Y%m%d}_{n + 1:04d}",
                    n + 1,
                )
                for n, slot in enumerate(campaign_slots(plan))
            ],
        )
    admin.commit()
    return {
        "id": identifier,
        "value": plan,
        "body": {"allocation_id": allocation, "name_reservation_id": names},
    }


class IsolatedExecutionValidationProvider(IsolatedValidationProvider):
    """仅专属计划在首次原validate捕获时声明网站，绝不事后改038冻结hash。"""

    async def capture(self, value):
        evidence = await super().capture(value)
        if EXECUTION_MARKER not in value.source.payload()["name"] or evidence.errors:
            return evidence
        arguments = json.loads(evidence.freeze_arguments_json)
        arguments["channel_snapshot"]["type"] = "WEBSITE"
        return replace(
            evidence,
            fingerprint=digest([evidence.fingerprint, "ISOLATED_WEBSITE"]),
            freeze_arguments_json=canonical(arguments).encode(),
        )


def profile(identifier):
    """显示原FIXTURE来源；不冒充META registry或外部平台适配验收。"""
    original = {
        "id": identifier,
        "version": "isolated-execution-profile-v1",
        "source": "FIXTURE",
        "register_action_type": None,
        "purchase_action_type": "fixture_purchase",
        "value_action_type": "fixture_value",
        "attribution_windows": ["explicit-isolated-window"],
        "action_report_time": "conversion",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 7,
        "verified": True,
    }
    return {
        "profile": original,
        "profile_source_hash": digest(original),
        "adapter_version": "isolated-explicit-attribution-v1",
        "bound_profile_version": original["version"],
        "registry_revision": 1,
        "attribution_spec": [{"event_type": "CLICK_THROUGH", "window_days": 7}],
    }


class IsolatedExecutionProvider(ExecutionAuthorityProvider):
    kind = "ISOLATED_TEST"

    def __init__(self, session_factory, control_dir=None):
        self.session_factory = session_factory
        self.control_dir = control_dir

    async def capture(self, value):
        plan = value.source.payload()
        if not plan["name"].startswith(PREFIX) or EXECUTION_MARKER not in plan["name"]:
            raise OrbitError(503, "LAUNCH_EXECUTION_AUTHORITY_UNAVAILABLE", "仅隔离执行协议计划")
        async with self.session_factory() as session, session.begin():
            await guard(session)
            row = await first(
                session,
                "SELECT allocation_id,name_reservation_id FROM orbit_launch_validation "
                "WHERE tenant_id=:tenant AND id=:id",
                {"tenant": value.current.tenant_id, "id": value.validation_id},
            )
            if row is None:
                raise OrbitError(409, "STALE_PREVIEW", "实际038来源已不存在")
            now = await database_now(session)
        observed = await IsolatedExecutionValidationProvider(
            self.session_factory, self.control_dir
        ).capture(
            ValidationInput(
                value.current,
                value.source,
                canonical(dict(row)).encode(),
            )
        )
        arguments = json.loads(observed.freeze_arguments_json)
        arguments.pop("total_dag_node_count")
        revisions = {asset: 1 for asset in plan["asset_ids"]}
        compatibility = build_compatibility_evidence(
            ad_slots(plan),
            plan["asset_ids"],
            capability_version=arguments["capability_version"],
            source_hash=digest([value.source.payload_hash, "ISOLATED_COMPATIBILITY"]),
            verified=True,
            complete=True,
            evaluate=lambda _slot, _asset: True,
            material_revisions=revisions,
        )
        # 这些描述为显式SQL协议样本，不是实扫文件；此档不计C CLEAN/双主体权限验收。
        materials = {
            asset: {
                "id": asset,
                "revision": 1,
                "sha256": "a" * 64,
                "mime": "image/png",
                "size": 1234,
                "width": 1080,
                "height": 1080,
                "duration": None,
                "state": "READY",
                "physical_cleanup_state": "LIVE",
                "antivirus_status": "CLEAN",
                "execution_eligible": True,
                **plan["ownership"],
            }
            for asset in plan["asset_ids"]
        }
        identifiers = {
            group["metric_profile_id"]
            for campaign in plan["campaigns"]
            for group in campaign["adsets"]
        }
        references = tuple(observed.observations) + (
            ObservationReference("CAPABILITY", str(UUID(int=93901)), 1),
            ObservationReference("POLICY", str(UUID(int=93902)), 1),
        )
        references += tuple(
            ObservationReference("ACCOUNT", item, 1) for item in plan["account_ids"]
        )
        references += tuple(ObservationReference("MATERIAL", item, 1) for item in revisions)
        references += tuple(ObservationReference("CONFIGURATION", item, 1) for item in identifiers)
        prepared = prepare_execution(
            value.source,
            value.validation,
            validated_head_revision=value.source.head_revision,
            **arguments,
            compatibility=compatibility,
            material_revisions=revisions,
            material_metadata=materials,
            resolved_metric_profiles={item: profile(item) for item in identifiers},
            observation_refs=references,
            request=json.loads(value.request_json),
            now=now,
        )
        return ExecutionEvidence(
            value.current,
            value.validation_id,
            hashlib.sha256(prepared.observations_json).hexdigest(),
            prepared,
        )

    async def revalidate(self, session, current, source, evidence):
        await guard(session)
        if current != evidence.current or source != evidence.prepared.source:
            raise OrbitError(409, "STALE_PREVIEW", "隔离来源上下文已变化")
        expected = json.loads(evidence.prepared.inputs_json)["scope_version"]
        if await scope_version(session, current) != expected:
            raise OrbitError(409, "STALE_PREVIEW", "当前真实授权版本已变化")
        return evidence

    async def publish_references(self, session, current, evidence, task_id, request_id):
        await guard(session)
        # 真SQL登记完整集合，而非noop；无文件扫描来源，不能当真实C执行引用桥通过。
        for asset in json.loads(evidence.prepared.materials_json):
            await session.execute(
                text(
                    "INSERT INTO orbit_material_reference"
                    "(tenant_id,asset_id,id,kind,resource_id,active,created_at) "
                    "VALUES(:tenant,:asset,:id,'EXECUTION',:task,1,UTC_TIMESTAMP(3))"
                ),
                {"tenant": current.tenant_id, "asset": asset, "id": str(uuid4()), "task": task_id},
            )
