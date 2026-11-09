"""032真实MySQL队列协议专项。ISOLATED_TEST不证明素材/平台能力，不启动服务。"""

import asyncio
import re
from dataclasses import replace
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

LAUNCH_ALLOCATION_RUNTIME_CASES = [
    "pythonAllocationRuntimeMissingProviderRejectsBeforeQueueWrite",
    "pythonAllocationRuntimeActualAtomicCaptureChunksAndOriginalIntentReplay",
    "pythonAllocationRuntimeConcurrentDuplicateAndBusyIntentSinglePlanGuard",
    "pythonAllocationRuntimeActualQueuedAuditRollbackLeavesNoPartialJob",
    "pythonAllocationRuntimeConcurrentClaimSkipLockedAndHeartbeat",
    "pythonAllocationRuntimeMissingOrCorruptChunkRejectsWholeInput",
    "pythonAllocationRuntimeExpiredClaimReclaimedWithGenerationAndOldResultRejected",
    "pythonAllocationRuntimeCompletePublicationUsesOriginalSchemaNoFakeTask",
    "pythonAllocationRuntimeChangedAuthorityAndRevokedPermissionCannotPublish",
    "pythonAllocationRuntimeReplacementAuditRollbackPreservesOriginalActiveAndWholeItems",
    "pythonAllocationRuntimeSameTenantForeignKeysAndStaleLeaseEnforced",
    "pythonAllocationRuntimeFailureAuditOutboxAndGuardAtomic",
    "pythonAllocationRuntimeTimeoutDefersOriginalHashAndSeedWithoutPartialMapping",
    "pythonAllocationRuntimeActualFiveMiBPlanTenThousandSlotsFiveHundredAssetsWholeManifestAndPublication",
    "pythonAllocationRuntimeCurrentHeadEnqueueFreezesRealLatestConfigurationVersion",
    "pythonAllocationRuntimeValidatedPublicationHeadCasAuditRollbackAndSourceNotCopied",
    "pythonAllocationRuntimeOldKeySourceRevalidatedBeforeOldCasAndRevocationStillRejects",
    "pythonAllocationRuntimeDraftPublicationPreservesHeadAndConfigurationVersion",
    "pythonAllocationRuntimeSubmittedAndArchivedRejectPublicationWithoutPartialItems",
    "pythonAllocationRuntimeChangedRealConfigurationRejectsOldPublicationAndPreservesActive",
    "pythonAllocationRuntimeOldKeyCannotRebindToChangedConfigurationSource",
    "pythonAllocationRuntimeMissingOrCorruptLatestSourceFailsClosedWithoutQueue",
]


def run_launch_allocation_runtime_checks(admin, database, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("032专项只允许主线本机UUID隔离库")
    from orbit_api.directory_tokens import canonical
    from orbit_api.errors import OrbitError
    from orbit_api.launch_access import digest
    from orbit_api.launch_allocation import build_compatibility_evidence
    from orbit_api.launch_allocation_runtime import (
        AllocationProvider,
        AllocationRuntime,
        CapturedAllocation,
        solve_packet,
    )
    from orbit_api.launch_contract import parse_plan
    from orbit_api.launch_expansion import ad_slots

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    admin.commit()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    class FixtureProvider(AllocationProvider):
        """仅隔离SQL协议，不伪造C CLEAN/真实资源认证，绝不能进入生产库。"""

        kind = "ISOLATED_TEST"
        changed = False

        async def capture(self, session, current, plan, request):
            material = {
                asset: {
                    "revision": 1,
                    "sha256": "b" * 64,
                    "kind": "IMAGE",
                    "mime": "image/png",
                    "byte_size": 100,
                    "width_px": 24,
                    "height_px": 24,
                    "duration_seconds": None,
                }
                for asset in plan["asset_ids"]
            }
            evidence = build_compatibility_evidence(
                ad_slots(plan),
                plan["asset_ids"],
                capability_version="ISOLATED-SQL-PROTOCOL-NOT-PLATFORM",
                source_hash=("d" if self.changed else "a") * 64,
                verified=True,
                complete=True,
                evaluate=lambda _slot, _asset: True,
                material_revisions={asset: 1 for asset in material},
            )
            return CapturedAllocation(evidence, material, "c" * 64, digest(plan))

        async def prepare_publication(self, session, current, packet, previous_id):
            return await self.capture(session, current, packet["plan"], packet["request"]), None

        async def publish_references(self, *args):
            # 本工具只验队列SQL事务；这里不声称已通过C病毒证明/真实素材引用发布。
            return None

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        provider = FixtureProvider()
        runtime = AllocationRuntime(provider)

        async def execute(sql, params=None):
            async with sessions() as session, session.begin():
                return await session.execute(text(sql), params or {})

        async def call(method, *args, **kwargs):
            async with sessions() as session, session.begin():
                return await method(session, *args, **kwargs)

        async def reject(method, *args, status=409, code=None, **kwargs):
            try:
                await call(method, *args, **kwargs)
            except OrbitError as error:
                assert error.status == status
                if code:
                    assert error.code == code
            else:
                raise AssertionError("应明确拒绝，不得降级成功")

        async def fixture(*, capacity=False):
            identifier, account = str(uuid4()), str(uuid4())
            assets = [str(uuid4()) for _ in range(500 if capacity else 1)]
            value = {
                "name": "032隔离SQL队列夹具",
                "ownership": {"owner_user_id": owner, "owner_team_id": team},
                "account_ids": [account],
                "asset_ids": assets,
                "channel_id": None,
                "identity_bindings": [],
                "allow_repeat": True,
                "activate_after_create": False,
                "execution_mode": "META_API",
                "campaigns": [
                    {
                        "local_id": str(uuid4()),
                        "copies": 1,
                        "adsets": [
                            {
                                "local_id": str(uuid4()),
                                "copies": 1,
                                "ads": [{"local_id": str(uuid4()), "copies": 2}],
                            }
                        ],
                    }
                ],
            }
            if capacity:
                ads = [{"local_id": str(uuid4()), "copies": 1, "body": "x"} for _ in range(10000)]
                value["campaigns"][0]["adsets"][0]["ads"] = ads
                remaining = 5 * 1024 * 1024 - len(canonical(value).encode())
                per_ad, extra = divmod(remaining, len(ads))
                assert per_ad + 2 <= 2000
                for index, ad in enumerate(ads):
                    ad["body"] += "x" * (per_ad + (index < extra))
                assert len(canonical(value).encode()) == 5 * 1024 * 1024
            value = parse_plan(canonical(value).encode())
            payload = canonical(value)
            await execute(
                """INSERT INTO orbit_launch_plan
                (tenant_id,id,owner_user_id,owner_team_id,channel_id,name,state,revision,
                payload_json,payload_hash,
                payload_bytes,account_count,asset_count,created_at,updated_at)
                VALUES(:tenant,:id,:owner,:team,NULL,'032隔离SQL队列夹具','DRAFT',1,
                :payload,:hash,:bytes,1,:asset_count,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
                {
                    "tenant": tenant,
                    "id": identifier,
                    "owner": owner,
                    "team": team,
                    "payload": payload,
                    "hash": digest(value),
                    "bytes": len(payload.encode()),
                    "asset_count": len(assets),
                },
            )
            await execute(
                """INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,
                payload_hash,dependency_json,created_at,created_by)
                SELECT tenant_id,id,1,payload_json,payload_hash,'{}',UTC_TIMESTAMP(3),1
                FROM orbit_launch_plan WHERE tenant_id=:tenant AND id=:plan""",
                {"tenant": tenant, "plan": identifier},
            )
            command = {
                "asset_ids": assets,
                "allow_repeat": True,
                "seed": 0,
                "algorithm_version": "allocation-v1",
            }
            return identifier, command

        async def enqueue(identifier, command, key=None):
            return await call(
                runtime.enqueue, 1, identifier, command, 1, key or str(uuid4()), str(uuid4())
            )

        async def solve(claim):
            _, packet, evidence = await call(runtime.load, claim)
            return solve_packet(packet, evidence)

        async def counts(identifier):
            values = {"tenant": tenant, "plan": identifier}
            async with sessions() as session, session.begin():
                allocation_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM orbit_launch_allocation WHERE "
                            "tenant_id=:tenant AND plan_id=:plan"
                        ),
                        values,
                    )
                ).scalar_one()
                guard_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM orbit_launch_allocation_guard WHERE "
                            "tenant_id=:tenant AND plan_id=:plan"
                        ),
                        values,
                    )
                ).scalar_one()
                item_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM orbit_launch_allocation_item i JOIN "
                            "orbit_launch_allocation a ON a.tenant_id=i.tenant_id AND "
                            "a.id=i.allocation_id WHERE a.tenant_id=:tenant AND "
                            "a.plan_id=:plan"
                        ),
                        values,
                    )
                ).scalar_one()
                return allocation_count, guard_count, item_count

        async def audit_counts(allocation_id):
            async with sessions() as session, session.begin():
                row = (
                    await session.execute(
                        text("""SELECT COUNT(e.id),
                    COALESCE(SUM(o.event_id IS NOT NULL),0) FROM orbit_launch_event e
                    LEFT JOIN orbit_launch_outbox o ON o.tenant_id=e.tenant_id AND o.event_id=e.id
                    WHERE e.tenant_id=:tenant AND e.resource_kind='ALLOCATION'
                    AND e.resource_id=:id"""),
                        {"tenant": tenant, "id": allocation_id},
                    )
                ).first()
                return tuple(int(item) for item in row)

        trigger = "it_alloc_" + uuid4().hex[:16]

        async def start_trigger(action):
            # 受控常量不是请求或凭据，唯一trigger只作用本隔离库。
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_launch_event "
                    f"FOR EACH ROW BEGIN IF NEW.action='{action}' THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_QUEUE_AUDIT_FAILURE'; "
                    "END IF; END"
                )
            admin.commit()

        async def drop_trigger():
            with admin.cursor() as cursor:
                cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            admin.commit()

        try:
            identifier, command = await fixture()
            await reject(
                AllocationRuntime().enqueue,
                1,
                identifier,
                command,
                1,
                str(uuid4()),
                str(uuid4()),
                status=503,
            )
            assert await counts(identifier) == (0, 0, 0)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[0])

            key = str(uuid4())
            first = await enqueue(identifier, command, key)
            assert first["state"] == "QUEUED" and first["task_id"] is None and first["items"] == []
            assert (await enqueue(identifier, command, key))["id"] == first["id"]
            assert await counts(identifier) == (1, 1, 0)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[1])

            duplicates = await asyncio.gather(
                enqueue(identifier, command), enqueue(identifier, command)
            )
            assert all(row["id"] == first["id"] for row in duplicates)
            changed = command | {"seed": 1}
            await reject(
                runtime.enqueue,
                1,
                identifier,
                changed,
                1,
                key,
                str(uuid4()),
                code="IDEMPOTENCY_CONFLICT",
            )
            await reject(
                runtime.enqueue,
                1,
                identifier,
                changed,
                1,
                str(uuid4()),
                str(uuid4()),
                code="ALLOCATION_BUSY",
            )
            assert await counts(identifier) == (1, 1, 0)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[2])

            failed_plan, failed_command = await fixture()
            await start_trigger("allocation.queued")
            try:
                try:
                    await enqueue(failed_plan, failed_command)
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("审计故障必须整体回滚")
                assert await counts(failed_plan) == (0, 0, 0)
            finally:
                await drop_trigger()
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[3])

            winners = await asyncio.gather(
                call(runtime.claim, str(uuid4())), call(runtime.claim, str(uuid4()))
            )
            assert sum(item is not None for item in winners) == 1
            claim = next(item for item in winners if item is not None)
            assert claim.allocation_id == first["id"]
            await call(runtime.heartbeat, claim)
            _, packet, _ = await call(runtime.load, claim)
            assert packet["input_hash"] == first["input_hash"]
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[4])

            async with sessions() as session:
                try:
                    async with session.begin():
                        await session.execute(
                            text(
                                "DELETE FROM orbit_launch_allocation_chunk WHERE "
                                "tenant_id=:tenant AND allocation_id=:id AND ordinal=0"
                            ),
                            {"tenant": tenant, "id": claim.allocation_id},
                        )
                        await runtime.load(session, claim)
                except OrbitError as error:
                    assert error.code == "ALLOCATION_MANIFEST_CORRUPT"
                else:
                    raise AssertionError("缺块不得恢复部分输入")
            assert (await call(runtime.load, claim))[1] == packet
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[5])

            solution = await solve(claim)
            await execute(
                "UPDATE orbit_launch_allocation_runtime SET "
                "lease_until=TIMESTAMPADD(SECOND,-1,UTC_TIMESTAMP(3)) WHERE "
                "tenant_id=:tenant AND allocation_id=:id",
                {"tenant": tenant, "id": claim.allocation_id},
            )
            renewed = await call(runtime.claim, str(uuid4()))
            assert renewed.generation == claim.generation + 1 and renewed.token != claim.token
            await reject(
                runtime.publish, claim, solution, str(uuid4()), code="ALLOCATION_CLAIM_LOST"
            )
            claim = renewed
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[6])

            complete = await call(runtime.publish, claim, solution, str(uuid4()))
            assert complete["state"] == "SUCCEEDED" and complete["task_id"] is None
            assert len(complete["items"]) == 2
            assert all(
                set(row) == {"slot_key", "account_id", "asset_id", "asset_revision"}
                for row in complete["items"]
            )
            assert await counts(identifier) == (1, 0, 2)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[7])

            new = await enqueue(identifier, command | {"seed": 1})
            claim = await call(runtime.claim, str(uuid4()))
            result = await solve(claim)
            provider.changed = True
            await reject(
                runtime.publish, claim, result, str(uuid4()), code="ALLOCATION_SOURCE_CHANGED"
            )
            provider.changed = False
            with admin.cursor() as cursor:
                cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31023")
                original_status = cursor.fetchone()[0]
                cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31023")
            admin.commit()
            try:
                await reject(runtime.publish, claim, result, str(uuid4()), status=403)
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_menu SET status=%s WHERE menu_id=31023", (original_status,)
                    )
                admin.commit()
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[8])

            await start_trigger("allocation.succeeded")
            try:
                try:
                    await call(runtime.publish, claim, result, str(uuid4()))
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("发布审计故障不得保留部分映射")
                assert await counts(identifier) == (2, 1, 2)
                old = await call(runtime.get, 1, identifier, first["id"])
                assert old["state"] == "SUCCEEDED" and len(old["items"]) == 2
            finally:
                await drop_trigger()
            second = await call(runtime.publish, claim, result, str(uuid4()))
            assert second["state"] == "SUCCEEDED" and second["id"] == new["id"]
            assert await counts(identifier) == (2, 0, 4)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[9])

            async with sessions() as session:
                try:
                    async with session.begin():
                        await session.execute(
                            text(
                                "INSERT INTO orbit_launch_allocation_chunk "
                                "(tenant_id,allocation_id,ordinal,payload,payload_hash,byte_size,created_at)"
                                " VALUES(:foreign,:id,100,'x',:hash,1,UTC_TIMESTAMP(3))"
                            ),
                            {"foreign": str(uuid4()), "id": second["id"], "hash": "a" * 64},
                        )
                except DBAPIError as error:
                    assert error.orig.args[0] == 1452
                else:
                    raise AssertionError("必须拒绝跨租户拼接分块")
            await reject(
                runtime.heartbeat,
                replace(claim, generation=claim.generation + 1),
                code="ALLOCATION_CLAIM_LOST",
            )
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[10])

            failure = await enqueue(failed_plan, failed_command)
            failure_claim = await call(runtime.claim, str(uuid4()))
            assert failure_claim.allocation_id == failure["id"]
            assert await audit_counts(failure["id"]) == (1, 1)
            await start_trigger("allocation.failed")
            try:
                try:
                    await call(runtime.fail, failure_claim, "ALLOCATION_NO_MATCH", str(uuid4()))
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("失败审计也必须同事务回滚")
                assert await counts(failed_plan) == (1, 1, 0)
                assert await audit_counts(failure["id"]) == (1, 1)
            finally:
                await drop_trigger()
            await call(runtime.fail, failure_claim, "ALLOCATION_NO_MATCH", str(uuid4()))
            assert await counts(failed_plan) == (1, 0, 0)
            assert await audit_counts(failure["id"]) == (2, 2)
            assert (await call(runtime.get, 1, failed_plan, failure["id"]))["state"] == "FAILED"
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[11])

            timeout_plan, timeout_command = await fixture()
            timeout = await enqueue(timeout_plan, timeout_command)
            timeout_claim = await call(runtime.claim, str(uuid4()))
            await call(runtime.defer_timeout, timeout_claim, str(uuid4()))
            deferred = await call(runtime.get, 1, timeout_plan, timeout["id"])
            assert deferred["state"] == "QUEUED" and deferred["input_hash"] == timeout["input_hash"]
            assert deferred["seed"] == timeout["seed"] and deferred["items"] == []
            assert await counts(timeout_plan) == (1, 1, 0)
            await reject(runtime.heartbeat, timeout_claim, code="ALLOCATION_CLAIM_LOST")
            await execute(
                "UPDATE orbit_launch_allocation_runtime SET "
                "next_attempt_at=TIMESTAMPADD(SECOND,-1,UTC_TIMESTAMP(3)) WHERE "
                "tenant_id=:tenant AND allocation_id=:id",
                {"tenant": tenant, "id": timeout["id"]},
            )
            next_claim = await call(runtime.claim, str(uuid4()))
            assert next_claim.generation == timeout_claim.generation + 1
            await call(runtime.defer_timeout, next_claim, str(uuid4()), max_attempts=1)
            assert (await call(runtime.get, 1, timeout_plan, timeout["id"]))["state"] == "FAILED"
            assert await counts(timeout_plan) == (1, 0, 0)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[12])

            capacity_plan, capacity_command = await fixture(capacity=True)
            capacity_job = await enqueue(capacity_plan, capacity_command)
            capacity_claim = await call(runtime.claim, str(uuid4()))
            head, packet, evidence = await call(runtime.load, capacity_claim)
            assert head["slot_count"] == 10000 and len(packet["material_metadata"]) == 500
            assert len(canonical(packet["plan"]).encode()) == 5 * 1024 * 1024
            assert head["byte_total"] <= 64 * 1024 * 1024 and head["chunk_count"] <= 256
            result = solve_packet(packet, evidence)
            final = await call(runtime.publish, capacity_claim, result, str(uuid4()))
            assert final["id"] == capacity_job["id"] and final["state"] == "SUCCEEDED"
            assert len(final["items"]) == 10000 and final["task_id"] is None
            assert await counts(capacity_plan) == (1, 0, 10000)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[13])

            async def plan_head(plan_id):
                async with sessions() as session, session.begin():
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT revision,state,payload_hash FROM orbit_launch_plan "
                                    "WHERE tenant_id=:tenant AND id=:plan"
                                ),
                                {"tenant": tenant, "plan": plan_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    version_count = (
                        await session.execute(
                            text(
                                "SELECT COUNT(*) FROM orbit_launch_plan_version "
                                "WHERE tenant_id=:tenant AND plan_id=:plan"
                            ),
                            {"tenant": tenant, "plan": plan_id},
                        )
                    ).scalar_one()
                    return row, version_count

            async def head_only(plan_id, revision, state):
                await execute(
                    "UPDATE orbit_launch_plan SET revision=:revision,state=:state,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:plan",
                    {"tenant": tenant, "plan": plan_id, "revision": revision, "state": state},
                )

            handoff_plan, handoff_command = await fixture()
            await head_only(handoff_plan, 4, "VALIDATED")
            handoff_key = str(uuid4())
            handoff = await call(
                runtime.enqueue, 1, handoff_plan, handoff_command, 4, handoff_key, str(uuid4())
            )
            assert handoff["plan_revision"] == 1 and handoff["task_id"] is None
            handoff_claim = await call(runtime.claim, str(uuid4()))
            assert handoff_claim.allocation_id == handoff["id"]
            _, handoff_packet, handoff_evidence = await call(runtime.load, handoff_claim)
            assert handoff_packet["plan_revision"] == 1
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[14])

            # 纯状态流转不改变配置。发布审计失败必须回滚整个head+items+终态。
            await head_only(handoff_plan, 5, "VALIDATED")
            handoff_solution = solve_packet(handoff_packet, handoff_evidence)
            await start_trigger("allocation.succeeded")
            try:
                try:
                    await call(runtime.publish, handoff_claim, handoff_solution, str(uuid4()))
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("发布审计故障不得保留状态头或部分结果")
                observed, versions = await plan_head(handoff_plan)
                assert (
                    observed["revision"] == 5 and observed["state"] == "VALIDATED" and versions == 1
                )
                assert await counts(handoff_plan) == (1, 1, 0)
                assert await audit_counts(handoff["id"]) == (1, 1)
            finally:
                await drop_trigger()
            completed_handoff = await call(
                runtime.publish, handoff_claim, handoff_solution, str(uuid4())
            )
            observed, versions = await plan_head(handoff_plan)
            assert observed["revision"] == 6 and observed["state"] == "DRAFT" and versions == 1
            assert completed_handoff["plan_revision"] == 1 and len(completed_handoff["items"]) == 2
            assert await audit_counts(handoff["id"]) == (2, 2)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[15])

            before_counts = await counts(handoff_plan)
            replayed = await call(
                runtime.enqueue, 1, handoff_plan, handoff_command, 4, handoff_key, str(uuid4())
            )
            assert replayed == completed_handoff
            await reject(
                runtime.enqueue,
                1,
                handoff_plan,
                handoff_command,
                4,
                str(uuid4()),
                str(uuid4()),
                code="REVISION_CONFLICT",
            )
            with admin.cursor() as cursor:
                cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31023")
                saved_status = cursor.fetchone()[0]
                cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31023")
            admin.commit()
            try:
                await reject(
                    runtime.enqueue,
                    1,
                    handoff_plan,
                    handoff_command,
                    4,
                    handoff_key,
                    str(uuid4()),
                    status=403,
                )
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_menu SET status=%s WHERE menu_id=31023", (saved_status,)
                    )
                admin.commit()
            assert await counts(handoff_plan) == before_counts
            assert await audit_counts(handoff["id"]) == (2, 2)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[16])

            draft_plan, draft_command = await fixture()
            await head_only(draft_plan, 7, "DRAFT")
            draft = await call(
                runtime.enqueue, 1, draft_plan, draft_command, 7, str(uuid4()), str(uuid4())
            )
            draft_claim = await call(runtime.claim, str(uuid4()))
            assert draft_claim.allocation_id == draft["id"]
            await call(runtime.publish, draft_claim, await solve(draft_claim), str(uuid4()))
            observed, versions = await plan_head(draft_plan)
            assert observed["revision"] == 7 and observed["state"] == "DRAFT" and versions == 1
            assert draft["plan_revision"] == 1
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[17])

            blocked_plan, blocked_command = await fixture()
            blocked = await enqueue(blocked_plan, blocked_command)
            blocked_claim = await call(runtime.claim, str(uuid4()))
            assert blocked_claim.allocation_id == blocked["id"]
            blocked_solution = await solve(blocked_claim)
            for forbidden in ("SUBMITTED", "ARCHIVED"):
                await head_only(blocked_plan, 2, forbidden)
                await reject(
                    runtime.publish,
                    blocked_claim,
                    blocked_solution,
                    str(uuid4()),
                    code="ALLOCATION_SOURCE_CHANGED",
                )
                assert await counts(blocked_plan) == (1, 1, 0)
                assert await audit_counts(blocked["id"]) == (1, 1)
            await head_only(blocked_plan, 3, "DRAFT")
            await call(runtime.fail, blocked_claim, "ALLOCATION_SOURCE_CHANGED", str(uuid4()))
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[18])

            replacement_key = str(uuid4())
            replacement = await call(
                runtime.enqueue,
                1,
                handoff_plan,
                handoff_command | {"seed": 1},
                6,
                replacement_key,
                str(uuid4()),
            )
            replacement_claim = await call(runtime.claim, str(uuid4()))
            assert replacement_claim.allocation_id == replacement["id"]
            replacement_solution = await solve(replacement_claim)
            async with sessions() as session, session.begin():
                old = (
                    await session.execute(
                        text(
                            "SELECT payload_json FROM orbit_launch_plan "
                            "WHERE tenant_id=:tenant AND id=:plan FOR UPDATE"
                        ),
                        {"tenant": tenant, "plan": handoff_plan},
                    )
                ).scalar_one()
                from orbit_api.configuration_store import _decode

                revised = _decode(old)
                revised["name"] += "新配置"
                revised_json, revised_hash = canonical(revised), digest(revised)
                params = {
                    "tenant": tenant,
                    "plan": handoff_plan,
                    "payload": revised_json,
                    "hash": revised_hash,
                    "bytes": len(revised_json.encode()),
                }
                await session.execute(
                    text(
                        "UPDATE orbit_launch_plan SET revision=7,payload_json=:payload,"
                        "payload_hash=:hash,payload_bytes=:bytes,updated_at=UTC_TIMESTAMP(3) "
                        "WHERE tenant_id=:tenant AND id=:plan"
                    ),
                    params,
                )
                await session.execute(
                    text(
                        "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,"
                        "payload_json,payload_hash,dependency_json,created_at,created_by) "
                        "VALUES(:tenant,:plan,7,:payload,:hash,'{}',UTC_TIMESTAMP(3),1)"
                    ),
                    params,
                )
            await reject(
                runtime.publish,
                replacement_claim,
                replacement_solution,
                str(uuid4()),
                code="ALLOCATION_SOURCE_CHANGED",
            )
            assert await counts(handoff_plan) == (2, 1, 2)
            assert (await call(runtime.get, 1, handoff_plan, handoff["id"])) == completed_handoff
            assert await audit_counts(replacement["id"]) == (1, 1)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[19])

            await reject(
                runtime.enqueue,
                1,
                handoff_plan,
                handoff_command,
                4,
                handoff_key,
                str(uuid4()),
                code="ALLOCATION_SOURCE_CHANGED",
            )
            assert await counts(handoff_plan) == (2, 1, 2)
            assert await audit_counts(handoff["id"]) == (2, 2)
            await call(runtime.fail, replacement_claim, "ALLOCATION_SOURCE_CHANGED", str(uuid4()))
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[20])

            missing_plan, missing_command = await fixture()
            await execute(
                "DELETE FROM orbit_launch_plan_version WHERE tenant_id=:tenant AND plan_id=:plan",
                {"tenant": tenant, "plan": missing_plan},
            )
            await reject(
                runtime.enqueue,
                1,
                missing_plan,
                missing_command,
                1,
                str(uuid4()),
                str(uuid4()),
                status=503,
                code="LAUNCH_SOURCE_STATE_UNAVAILABLE",
            )
            assert await counts(missing_plan) == (0, 0, 0)
            corrupt_plan, corrupt_command = await fixture()
            await execute(
                "UPDATE orbit_launch_plan_version SET payload_hash=:hash "
                "WHERE tenant_id=:tenant AND plan_id=:plan",
                {"tenant": tenant, "plan": corrupt_plan, "hash": "f" * 64},
            )
            await reject(
                runtime.enqueue,
                1,
                corrupt_plan,
                corrupt_command,
                1,
                str(uuid4()),
                str(uuid4()),
                status=503,
                code="LAUNCH_SOURCE_STATE_UNAVAILABLE",
            )
            assert await counts(corrupt_plan) == (0, 0, 0)
            cases.append(LAUNCH_ALLOCATION_RUNTIME_CASES[21])
            return {
                "producer_kind": "ISOLATED_TEST",
                "real_platform_verified": False,
                "plan_bytes": len(canonical(packet["plan"]).encode()),
                "manifest_bytes": head["byte_total"],
                "chunk_count": head["chunk_count"],
                "slot_count": head["slot_count"],
                "asset_count": len(packet["material_metadata"]),
                "published_items": len(final["items"]),
            }
        finally:
            await drop_trigger()
            await engine.dispose()

    return asyncio.run(run())
