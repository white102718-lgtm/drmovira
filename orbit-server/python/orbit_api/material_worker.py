"""真实素材Worker；认领/完成复验发起身份，撤权终止旧任务且不因重新启用复活。"""

import asyncio
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ScanReceipt, UnavailableMaterialScanner
from orbit_api.material_antivirus_runtime import RuntimeScanResult, TrustedRuntimeProfile
from orbit_api.material_antivirus_sql import processing_scan_verified
from orbit_api.material_job_policy import validate_job_actor
from orbit_api.material_processing import process_material
from orbit_api.material_runtime_store import append_runtime_scan
from orbit_api.material_store import one

JOB_COLUMNS = """j.tenant_id,j.asset_id,j.actor_id,j.actor_auth_version,j.scope_digest,
 a.object_upload_id,a.mime,a.sha256,a.byte_size,a.owner_user_id,a.owner_team_id,a.revision,
 a.state AS asset_state"""


class MaterialWorker:
    def __init__(
        self,
        session_factory,
        objects,
        processor=process_material,
        scanner=None,
        runtime_profile_provider=None,
    ):
        self.sessions, self.objects, self.processor = session_factory, objects, processor
        self.scanner = scanner if scanner is not None else UnavailableMaterialScanner()
        self.runtime_profile_provider = runtime_profile_provider

    async def current_runtime_profile(self, claim):
        if self.runtime_profile_provider is None:
            return None
        value = await asyncio.to_thread(self.runtime_profile_provider, dict(claim))
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, TrustedRuntimeProfile) or value != getattr(
            self.scanner, "profile", None
        ):
            raise OrbitError(503, "ANTIVIRUS_RUNTIME_UNVERIFIED", "当前可信扫描profile不符")
        return value

    def runtime_selection(self, claim):
        """旧显式隔离fixture不伪造正式配置来源；正式子类必须提供已复核快照。"""
        return None

    async def runtime_source_current(self, session, claim):
        return True

    async def run_once(self, limit=10):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("素材单次处理数量必须1至50")
        results = []
        for _ in range(limit):
            claim = await self.claim()
            if claim is None:
                break
            if claim.get("cancelled"):
                results.append({"asset_id": claim["asset_id"], "state": "PROCESSING_FAILED"})
                continue
            receipt_asset = claim["asset_id"]
            profile = None
            try:
                profile = await self.current_runtime_profile(claim)
                receipt = await asyncio.to_thread(
                    self.scanner.scan,
                    self.objects,
                    claim["tenant_id"],
                    claim["object_upload_id"],
                    claim["sha256"],
                    claim["byte_size"],
                )
                if isinstance(receipt, RuntimeScanResult):
                    current = await self.current_runtime_profile(claim)
                    if profile is None or current != profile:
                        raise OrbitError(
                            503, "ANTIVIRUS_RUNTIME_UNVERIFIED", "扫描期间profile已变化"
                        )
            except Exception as problem:
                # 注入扫描器异常也不能回退为媒体成功；仅登记安全失败。
                now = datetime.now(UTC)
                receipt = ScanReceipt(
                    "UNVERIFIED",
                    claim["sha256"],
                    claim["byte_size"],
                    now,
                    now,
                    None,
                    None,
                    None,
                    None,
                    "ANTIVIRUS_RUNTIME_UNVERIFIED"
                    if isinstance(problem, OrbitError)
                    and problem.code == "ANTIVIRUS_RUNTIME_UNVERIFIED"
                    else "ANTIVIRUS_UNAVAILABLE",
                )
            claim, scan_state = await self.record_scan(claim, receipt, profile=profile)
            if claim is None:
                results.append({"asset_id": receipt_asset, "state": scan_state})
                continue
            try:
                result = await asyncio.to_thread(
                    self.processor,
                    self.objects,
                    claim["tenant_id"],
                    claim["object_upload_id"],
                    claim["mime"],
                )
                state, error = "READY", None
            except OrbitError as problem:
                result = None
                state = (
                    "QUARANTINED"
                    if problem.code in {"FILE_SIGNATURE_INVALID", "IMAGE_DECODE_FAILED"}
                    else "PROCESSING_FAILED"
                )
                error = problem.code
            except Exception:
                result, state, error = None, "PROCESSING_FAILED", "PROCESSING_UNAVAILABLE"
            applied, final_state = await self.finish(claim, state, error, result)
            results.append(
                {"asset_id": claim["asset_id"], "state": final_state if applied else "STALE"}
            )
        return results

    @staticmethod
    async def lock_clock(session, tenant):
        row = await one(
            session,
            """SELECT revision FROM orbit_material_clock
            WHERE tenant_id=:tenant FOR UPDATE""",
            {"tenant": tenant},
        )
        if row is None or row["revision"] >= 9007199254740991:
            raise OrbitError(409, "REVISION_EXHAUSTED", "素材目录版本不可继续处理")

    @staticmethod
    async def event(session, claim, before, after, error=None):
        params = {
            **claim,
            "event": str(uuid4()),
            "request": str(uuid4()),
            "action": "MATERIAL_" + after,
            "revision": claim["revision"] + 1,
            "change": canonical({"state": {"before": before, "after": after}, "error_code": error}),
        }
        await session.execute(
            text("""INSERT INTO orbit_material_audit
            (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
            VALUES(:event,:tenant_id,0,:action,:asset_id,:revision,:request,:change)"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_material_outbox
            (event_id,tenant_id,resource_id,revision)
            VALUES(:event,:tenant_id,:asset_id,:revision)"""),
            params,
        )
        await session.execute(
            text("""UPDATE orbit_material_clock SET revision=revision+1
            WHERE tenant_id=:tenant_id"""),
            params,
        )

    async def candidate(self, session, where, params=None):
        return await one(
            session,
            f"""SELECT {JOB_COLUMNS} FROM orbit_material_job j
            JOIN orbit_material_asset a ON a.tenant_id=j.tenant_id AND a.id=j.asset_id
            WHERE {where} ORDER BY j.created_at,j.tenant_id,j.asset_id LIMIT 1""",
            params or {},
        )

    async def claim(self):
        # 无锁候选只用于定位；先身份再clock→job→asset，统一交互/Worker锁顺序。
        async with self.sessions() as session:
            candidate = await self.candidate(session, "j.state='PENDING' AND a.state='SCANNING'")
        if candidate is None:
            return None
        async with self.sessions() as session, session.begin():
            authorized = await validate_job_actor(session, candidate)
            await self.lock_clock(session, candidate["tenant_id"])
            job = await one(
                session,
                """SELECT state FROM orbit_material_job
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id FOR UPDATE""",
                candidate,
            )
            if job is None or job["state"] != "PENDING":
                return None
            asset = await one(
                session,
                """SELECT state,revision FROM orbit_material_asset
                WHERE tenant_id=:tenant_id AND id=:asset_id FOR UPDATE""",
                candidate,
            )
            if asset is None or asset["state"] != "SCANNING":
                await session.execute(
                    text("""UPDATE orbit_material_job SET state='FAILED'
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
                    candidate,
                )
                return {**candidate, "cancelled": True}
            claim = {**candidate, "revision": asset["revision"], "claim_id": str(uuid4())}
            if not authorized:
                await self.terminate(session, claim, "SCANNING")
                return {**claim, "cancelled": True}
            if asset["revision"] >= 9007199254740990:
                raise OrbitError(409, "REVISION_EXHAUSTED", "素材版本已达上限")
            await session.execute(
                text("""UPDATE orbit_material_job SET state='RUNNING',
                claim_id=:claim_id,claimed_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
                claim,
            )
            # 真病毒扫描期间保持SCANNING，不能在媒体处理之前伪造扫描阶段已完成。
            return claim

    async def record_scan(self, claim, receipt, *, profile=None):
        if isinstance(receipt, RuntimeScanResult):
            if receipt.proof is not None and isinstance(profile, TrustedRuntimeProfile):
                try:
                    return await self.record_runtime_scan(claim, receipt, profile)
                except OrbitError as problem:
                    if problem.code in {
                        "MATERIAL_SCAN_STALE",
                        "MATERIAL_RUNTIME_SCAN_CONFLICT",
                        "MATERIAL_RUNTIME_PROOF_REQUIRED",
                    }:
                        return None, "STALE"
                    if problem.code not in {
                        "MATERIAL_RUNTIME_PROOF_INVALID",
                        "AUTHORIZATION_CHANGED",
                        "SCANNER_CONFIGURATION_CHANGED",
                        "SCANNER_CONFIGURATION_UNAVAILABLE",
                        "SCANNER_PROFILE_CHANGED",
                        "SCANNER_PROFILE_UNAVAILABLE",
                    }:
                        raise
            original = receipt.receipt
            receipt = replace(
                original,
                result="UNVERIFIED",
                error_code=(
                    original.error_code
                    if original.result == "UNVERIFIED" and original.error_code
                    else "ANTIVIRUS_RUNTIME_UNVERIFIED"
                ),
            )
        if not isinstance(receipt, ScanReceipt):
            raise ValueError("扫描器必须返回不可变扫描证据")
        valid_clean = (
            receipt.result == "CLEAN"
            and receipt.error_code is None
            and receipt.sha256 == claim["sha256"]
            and receipt.byte_size == claim["byte_size"]
            and receipt.engine_version is not None
            and receipt.database_version is not None
            and receipt.database_built_at is not None
            and receipt.policy_sha256 is not None
        )
        if receipt.result == "CLEAN":
            receipt = replace(
                receipt,
                result="UNVERIFIED",
                error_code=(
                    "ANTIVIRUS_RUNTIME_UNVERIFIED" if valid_clean else "ANTIVIRUS_EVIDENCE_INVALID"
                ),
            )
        valid_clean = False
        state = (
            "PROCESSING"
            if valid_clean
            else "QUARANTINED"
            if receipt.result == "INFECTED"
            else "PROCESSING_FAILED"
        )
        error = None if valid_clean else receipt.error_code or "ANTIVIRUS_EVIDENCE_INVALID"
        async with self.sessions() as session, session.begin():
            authorized = await validate_job_actor(session, claim)
            await self.lock_clock(session, claim["tenant_id"])
            job = await one(
                session,
                """SELECT state,claim_id FROM orbit_material_job
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id
                  AND claimed_at>=UTC_TIMESTAMP(3)-INTERVAL 5 MINUTE FOR UPDATE""",
                claim,
            )
            asset = await one(
                session,
                """SELECT state,revision,sha256,byte_size FROM orbit_material_asset
                WHERE tenant_id=:tenant_id AND id=:asset_id FOR UPDATE""",
                claim,
            )
            if (
                job is None
                or job["state"] != "RUNNING"
                or job["claim_id"] != claim["claim_id"]
                or asset is None
                or asset["state"] != "SCANNING"
                or asset["revision"] != claim["revision"]
                or asset["sha256"] != claim["sha256"]
                or asset["byte_size"] != claim["byte_size"]
            ):
                return None, "STALE"
            params = {
                **claim,
                "id": str(uuid4()),
                "scan_result": receipt.result
                if valid_clean or receipt.result in {"INFECTED", "UNVERIFIED"}
                else "UNVERIFIED",
                "engine": receipt.engine_version,
                "database": receipt.database_version,
                "built": receipt.database_built_at.astimezone(UTC).replace(tzinfo=None)
                if receipt.database_built_at
                else None,
                "policy": receipt.policy_sha256,
                "started": receipt.started_at.astimezone(UTC).replace(tzinfo=None),
                "completed": receipt.completed_at.astimezone(UTC).replace(tzinfo=None),
                "error": error,
            }
            await session.execute(
                text("""INSERT INTO orbit_material_scan_receipt
                (tenant_id,asset_id,claim_id,id,result,sha256,byte_size,engine_version,
                database_version,database_built_at,policy_sha256,started_at,completed_at,error_code)
                VALUES(:tenant_id,:asset_id,:claim_id,:id,:scan_result,:sha256,:byte_size,
                :engine,:database,:built,:policy,:started,:completed,:error)"""),
                params,
            )
            if not authorized:
                await self.terminate(session, claim, "SCANNING")
                return None, "PROCESSING_FAILED"
            await session.execute(
                text("""UPDATE orbit_material_asset SET state=:next_state,
                error_code=:error,preview_ready=0,revision=revision+1,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant_id AND id=:asset_id"""),
                {**claim, "next_state": state, "error": error},
            )
            if not valid_clean:
                await session.execute(
                    text("""UPDATE orbit_material_job SET state='FAILED'
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
                    claim,
                )
            await self.event(session, claim, "SCANNING", state, error)
            return ({**claim, "revision": claim["revision"] + 1} if valid_clean else None), state

    async def record_runtime_scan(self, claim, result, profile):
        """同事务先追加两份不可变证据，再状态CAS；任何事件失败均整体回滚。"""
        async with self.sessions() as session, session.begin():
            stored = await append_runtime_scan(
                session, claim, result, profile, selection=self.runtime_selection(claim)
            )
            if stored.replayed:
                return None, "STALE"
            clean = result.receipt.result == "CLEAN"
            state = (
                "PROCESSING"
                if clean
                else "QUARANTINED"
                if result.receipt.result == "INFECTED"
                else "PROCESSING_FAILED"
            )
            error = None if clean else result.receipt.error_code or "ANTIVIRUS_EVIDENCE_INVALID"
            changed = await session.execute(
                text("""UPDATE orbit_material_asset SET state=:state,
                error_code=:error,preview_ready=0,revision=revision+1,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant_id AND id=:asset_id
                  AND state='SCANNING' AND revision=:revision"""),
                {**claim, "state": state, "error": error},
            )
            if changed.rowcount != 1:
                raise OrbitError(409, "MATERIAL_SCAN_STALE", "扫描状态已经变化")
            if not clean:
                await session.execute(
                    text("""UPDATE orbit_material_job SET state='FAILED'
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id AND claim_id=:claim_id"""),
                    claim,
                )
            await self.event(session, claim, "SCANNING", state, error)
            return ({**claim, "revision": claim["revision"] + 1} if clean else None), state

    async def terminate(self, session, claim, before):
        await session.execute(
            text("""UPDATE orbit_material_asset SET state='PROCESSING_FAILED',
            error_code='AUTHORIZATION_CHANGED',preview_ready=0,revision=revision+1,
            updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant_id AND id=:asset_id
              AND state=:before AND revision=:revision"""),
            {**claim, "before": before},
        )
        await session.execute(
            text("""UPDATE orbit_material_job SET state='FAILED',claim_id=NULL
            WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
            claim,
        )
        await self.event(session, claim, before, "PROCESSING_FAILED", "AUTHORIZATION_CHANGED")

    async def finish(self, claim, state, error, result):
        async with self.sessions() as session, session.begin():
            authorized = await validate_job_actor(session, claim)
            source_current = await self.runtime_source_current(session, claim)
            await self.lock_clock(session, claim["tenant_id"])
            job = await one(
                session,
                """SELECT state,claim_id FROM orbit_material_job
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id
                  AND claimed_at>=UTC_TIMESTAMP(3)-INTERVAL 5 MINUTE FOR UPDATE""",
                claim,
            )
            if job is None or job["state"] != "RUNNING" or job["claim_id"] != claim["claim_id"]:
                return False, "STALE"
            if not authorized:
                await self.terminate(session, claim, "PROCESSING")
                return True, "PROCESSING_FAILED"
            if state == "READY" and (
                not source_current or not await processing_scan_verified(session, claim)
            ):
                state, error, result = "PROCESSING_FAILED", "ANTIVIRUS_RUNTIME_UNVERIFIED", None
            params = {
                **claim,
                "state": state,
                "error": error,
                "width": result.width if result else None,
                "height": result.height if result else None,
                "duration": result.duration if result else None,
                "preview": int(result is not None),
            }
            changed = await session.execute(
                text("""UPDATE orbit_material_asset SET state=:state,
                error_code=:error,width_px=:width,height_px=:height,duration_seconds=:duration,
                preview_ready=:preview,revision=revision+1,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant_id AND id=:asset_id AND state='PROCESSING'
                  AND revision=:revision"""),
                params,
            )
            await session.execute(
                text("""UPDATE orbit_material_job SET state=:state
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
                {
                    **claim,
                    "state": "DONE" if changed.rowcount == 1 and state == "READY" else "FAILED",
                },
            )
            if changed.rowcount != 1:
                return False, "STALE"
            await self.event(session, claim, "PROCESSING", state, error)
            return True, state

    async def recover(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("恢复数量必须1至50")
        async with self.sessions() as session:
            values = (
                (
                    await session.execute(
                        text(f"""SELECT {JOB_COLUMNS}
                FROM orbit_material_job j JOIN orbit_material_asset a
                  ON a.tenant_id=j.tenant_id AND a.id=j.asset_id
                WHERE j.state='RUNNING' AND j.claimed_at<UTC_TIMESTAMP(3)-INTERVAL 5 MINUTE
                ORDER BY j.claimed_at LIMIT :limit"""),
                        {"limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        recovered = 0
        for candidate in values:
            params = dict(candidate)
            async with self.sessions() as session, session.begin():
                authorized = await validate_job_actor(session, params)
                await self.lock_clock(session, params["tenant_id"])
                job = await one(
                    session,
                    """SELECT state FROM orbit_material_job
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id
                      AND claimed_at<UTC_TIMESTAMP(3)-INTERVAL 5 MINUTE FOR UPDATE""",
                    params,
                )
                if job is None or job["state"] != "RUNNING":
                    continue
                if not authorized:
                    await self.terminate(
                        session,
                        params,
                        "PROCESSING" if params.get("asset_state") == "PROCESSING" else "SCANNING",
                    )
                    continue
                changed = await session.execute(
                    text("""UPDATE orbit_material_asset
                    SET state='SCANNING',revision=revision+1,updated_at=UTC_TIMESTAMP(3)
                    WHERE tenant_id=:tenant_id AND id=:asset_id
                      AND state IN('SCANNING','PROCESSING')
                      AND revision=:revision"""),
                    params,
                )
                await session.execute(
                    text("""UPDATE orbit_material_job SET state=:state,
                    claim_id=NULL,claimed_at=NULL
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id"""),
                    {**params, "state": "PENDING" if changed.rowcount == 1 else "FAILED"},
                )
                if changed.rowcount:
                    recovered += 1
                    await self.event(
                        session, params, params["asset_state"], "SCANNING", "LEASE_EXPIRED"
                    )
        return recovered
