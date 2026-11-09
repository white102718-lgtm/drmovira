"""独立素材生命周期系统Worker；不自动调度，未接入写fence时绝不物理删除。"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.material_store import one, rows
from orbit_api.material_worker import MaterialWorker


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


async def require_referenceable(session, tenant, asset_id):
    """引用写方已完成权限/数据范围检查后，在同一事务调用并持asset锁再插入引用。"""
    await MaterialWorker.lock_clock(session, tenant)
    asset = await one(
        session,
        "SELECT physical_cleanup_state FROM orbit_material_asset WHERE tenant_id=:tenant "
        "AND id=:asset FOR UPDATE",
        {"tenant": tenant, "asset": asset_id},
    )
    if asset is None or asset["physical_cleanup_state"] != "LIVE":
        raise OrbitError(409, "ASSET_PHYSICALLY_UNAVAILABLE", "素材已进入保留回收，不能新增引用")


class MaterialLifecycleWorker:
    def __init__(self, session_factory, objects, *, clock=utc_now):
        self.sessions, self.objects, self.clock = session_factory, objects, clock

    @staticmethod
    def bounded(limit):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("生命周期单批必须1至50")

    async def asset_lock(self, session, tenant, asset):
        await MaterialWorker.lock_clock(session, tenant)
        return await one(
            session,
            "SELECT * FROM orbit_material_asset WHERE tenant_id=:tenant AND id=:asset FOR UPDATE",
            {"tenant": tenant, "asset": asset},
        )

    @staticmethod
    async def referenced(session, tenant, asset):
        params = {"tenant": tenant, "asset": asset}
        active = await one(
            session,
            """SELECT id FROM orbit_material_reference WHERE tenant_id=:tenant
            AND asset_id=:asset AND active=1 LIMIT 1 FOR SHARE""",
            params,
        )
        if active is not None:
            return True
        historical = await one(
            session,
            """SELECT id FROM orbit_material_reference WHERE tenant_id=:tenant
            AND asset_id=:asset AND kind='HISTORICAL_EVIDENCE' LIMIT 1 FOR SHARE""",
            params,
        )
        return historical is not None

    async def event(self, session, asset, action, changes):
        params = {
            "id": str(uuid4()),
            "tenant": asset["tenant_id"],
            "asset": asset["id"],
            "revision": asset["revision"] + 1,
            "action": action,
            "request": str(uuid4()),
            "change": canonical(changes),
        }
        await session.execute(
            text("""INSERT INTO orbit_material_audit
            (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
            VALUES(:id,:tenant,0,:action,:asset,:revision,:request,:change)"""),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_material_outbox(event_id,tenant_id,resource_id,revision) "
                "VALUES(:id,:tenant,:asset,:revision)"
            ),
            params,
        )
        await session.execute(
            text("UPDATE orbit_material_clock SET revision=revision+1 WHERE tenant_id=:tenant"),
            params,
        )

    async def enqueue(self, limit=50):
        self.bounded(limit)
        now = self.clock()
        async with self.sessions() as session:
            candidates = await rows(
                session,
                """SELECT u.tenant_id,u.id AS upload_id,u.asset_id,'UPLOAD_EXPIRY' AS kind
                FROM orbit_material_upload u JOIN orbit_material_asset a
                ON a.tenant_id=u.tenant_id AND a.id=u.asset_id
                WHERE u.state IN ('INITIATED','UPLOADING') AND u.expires_at<=:now
                AND a.state IN ('INITIATED','UPLOADING')
                ORDER BY u.expires_at,u.tenant_id,u.id LIMIT :limit""",
                {"now": now, "limit": limit},
            )
            remaining = limit - len(candidates)
            if remaining:
                candidates = list(candidates) + list(
                    await rows(
                        session,
                        """SELECT a.tenant_id,a.object_upload_id AS upload_id,a.id AS asset_id,
                    'ARCHIVE_RETENTION' AS kind FROM orbit_material_asset a
                    WHERE a.state='ARCHIVED' AND a.physical_cleanup_state='LIVE'
                    AND a.archived_at<=:cutoff AND NOT EXISTS(SELECT 1
                    FROM orbit_material_lifecycle_job j WHERE j.tenant_id=a.tenant_id
                    AND j.kind='ARCHIVE_RETENTION' AND j.upload_id=a.object_upload_id)
                    ORDER BY a.archived_at,a.tenant_id,a.id LIMIT :limit""",
                        {"cutoff": now - timedelta(days=30), "limit": remaining},
                    )
                )
        accepted = 0
        for candidate in candidates:
            tenant, asset_id = candidate["tenant_id"], candidate["asset_id"]
            async with self.sessions() as session, session.begin():
                asset = await self.asset_lock(session, tenant, asset_id)
                if asset is None or asset["revision"] >= 9007199254740991:
                    continue
                params = {
                    "tenant": tenant,
                    "asset": asset_id,
                    "upload": candidate["upload_id"],
                    "kind": candidate["kind"],
                    "id": str(uuid4()),
                    "now": now,
                }
                if candidate["kind"] == "UPLOAD_EXPIRY":
                    upload = await one(
                        session,
                        "SELECT state,expires_at FROM orbit_material_upload "
                        "WHERE tenant_id=:tenant AND id=:upload FOR UPDATE",
                        params,
                    )
                    if (
                        upload is None
                        or upload["state"] not in {"INITIATED", "UPLOADING"}
                        or upload["expires_at"] > now
                        or asset["state"] not in {"INITIATED", "UPLOADING"}
                    ):
                        continue
                    await session.execute(
                        text(
                            "UPDATE orbit_material_upload SET state='EXPIRED' "
                            "WHERE tenant_id=:tenant AND id=:upload"
                        ),
                        params,
                    )
                    await session.execute(
                        text("""UPDATE orbit_material_asset SET state='UPLOAD_FAILED',
                        error_code='UPLOAD_EXPIRED',revision=revision+1,updated_at=:now
                        WHERE tenant_id=:tenant AND id=:asset"""),
                        params,
                    )
                    await self.event(
                        session,
                        asset,
                        "MATERIAL_UPLOAD_EXPIRED",
                        {
                            "state": {"before": asset["state"], "after": "UPLOAD_FAILED"},
                            "reason": "UPLOAD_EXPIRED",
                        },
                    )
                elif (
                    asset["state"] != "ARCHIVED"
                    or asset["physical_cleanup_state"] != "LIVE"
                    or asset["archived_at"] is None
                    or asset["archived_at"] > now - timedelta(days=30)
                    or await self.referenced(session, tenant, asset_id)
                ):
                    continue
                await session.execute(
                    text("""INSERT IGNORE INTO orbit_material_lifecycle_job
                    (tenant_id,id,asset_id,upload_id,kind,due_at)
                    VALUES(:tenant,:id,:asset,:upload,:kind,:now)"""),
                    params,
                )
                accepted += 1
        return accepted

    async def recover(self, limit=50):
        self.bounded(limit)
        now = self.clock()
        async with self.sessions() as session, session.begin():
            expired = await rows(
                session,
                """SELECT tenant_id,id FROM orbit_material_lifecycle_job
                WHERE state='RUNNING' AND lease_until<=:now ORDER BY lease_until,tenant_id,id
                LIMIT :limit FOR UPDATE SKIP LOCKED""",
                {"now": now, "limit": limit},
            )
            for row in expired:
                await session.execute(
                    text("""UPDATE orbit_material_lifecycle_job SET state='RETRY',
                    generation=LEAST(generation+1,9007199254740991),
                    claim_token=NULL,lease_until=NULL,due_at=:now,
                    last_error_code='LEASE_EXPIRED',updated_at=:now
                    WHERE tenant_id=:tenant AND id=:id"""),
                    {"tenant": row["tenant_id"], "id": row["id"], "now": now},
                )
            return len(expired)

    async def claim(self):
        now = self.clock()
        async with self.sessions() as session:
            candidate = await one(
                session,
                """SELECT tenant_id,id,asset_id FROM orbit_material_lifecycle_job
                WHERE state IN ('PENDING','RETRY') AND due_at<=:now
                ORDER BY due_at,tenant_id,id LIMIT 1""",
                {"now": now},
            )
        if candidate is None:
            return None
        async with self.sessions() as session, session.begin():
            tenant = candidate["tenant_id"]
            asset = await self.asset_lock(session, tenant, candidate["asset_id"])
            job = await one(
                session,
                "SELECT * FROM orbit_material_lifecycle_job WHERE tenant_id=:tenant "
                "AND id=:id FOR UPDATE",
                {"tenant": tenant, "id": candidate["id"]},
            )
            if job is None or job["state"] not in {"PENDING", "RETRY"} or job["due_at"] > now:
                return {"skipped": True}
            if not getattr(self.objects, "writers_fenced", False):
                await session.execute(
                    text("""UPDATE orbit_material_lifecycle_job SET state='RETRY',
                    due_at=:due,last_error_code='FENCE_NOT_INTEGRATED',updated_at=:now
                    WHERE tenant_id=:tenant AND id=:id"""),
                    {
                        "tenant": tenant,
                        "id": job["id"],
                        "now": now,
                        "due": now + timedelta(minutes=5),
                    },
                )
                return {"skipped": True}
            valid = (
                asset is not None
                and asset["physical_cleanup_state"] != "PURGED"
                and asset["object_upload_id"] == job["upload_id"]
                and asset["revision"] < 9007199254740991
                and (
                    asset["physical_cleanup_state"] != "LIVE"
                    or asset["revision"] < 9007199254740990
                )
                and job["generation"] < 9007199254740991
            )
            if valid and job["kind"] == "ARCHIVE_RETENTION":
                valid = (
                    asset["state"] == "ARCHIVED"
                    and asset["archived_at"] is not None
                    and asset["archived_at"] <= now - timedelta(days=30)
                    and not await self.referenced(session, tenant, asset["id"])
                )
            elif valid:
                upload = await one(
                    session,
                    "SELECT state FROM orbit_material_upload WHERE tenant_id=:tenant "
                    "AND id=:upload FOR SHARE",
                    {"tenant": tenant, "upload": job["upload_id"]},
                )
                valid = (
                    upload is not None
                    and upload["state"] == "EXPIRED"
                    and asset["state"] == "UPLOAD_FAILED"
                    and not await self.referenced(session, tenant, asset["id"])
                )
            if not valid:
                await session.execute(
                    text("""UPDATE orbit_material_lifecycle_job SET state='RETRY',
                    due_at=:due,last_error_code='LIFECYCLE_STATE_OR_REFERENCE_CONFLICT',updated_at=:now
                    WHERE tenant_id=:tenant AND id=:id"""),
                    {
                        "tenant": tenant,
                        "id": job["id"],
                        "due": now + timedelta(minutes=5),
                        "now": now,
                    },
                )
                return {"skipped": True}
            if asset["physical_cleanup_state"] == "LIVE":
                await session.execute(
                    text("""UPDATE orbit_material_asset SET physical_cleanup_state='CLEANING',
                    revision=revision+1,updated_at=:now WHERE tenant_id=:tenant AND id=:asset"""),
                    {"now": now, "tenant": tenant, "asset": asset["id"]},
                )
                await self.event(
                    session,
                    asset,
                    "MATERIAL_CLEANUP_STARTED",
                    {
                        "physical_cleanup_state": {"before": "LIVE", "after": "CLEANING"},
                        "reason": job["kind"],
                    },
                )
            token = str(uuid4())
            await session.execute(
                text("""UPDATE orbit_material_lifecycle_job SET state='RUNNING',
                generation=generation+1,claim_token=:token,lease_until=:lease,attempts=attempts+1,
                updated_at=:now WHERE tenant_id=:tenant AND id=:id"""),
                {
                    "tenant": tenant,
                    "id": job["id"],
                    "token": token,
                    "now": now,
                    "lease": now + timedelta(minutes=2),
                },
            )
            return dict(job) | {"claim_token": token, "generation": job["generation"] + 1}

    async def finish(self, claim, error=None):
        now = self.clock()
        async with self.sessions() as session, session.begin():
            tenant = claim["tenant_id"]
            asset = await self.asset_lock(session, tenant, claim["asset_id"])
            job = await one(
                session,
                "SELECT * FROM orbit_material_lifecycle_job WHERE tenant_id=:tenant "
                "AND id=:id FOR UPDATE",
                {"tenant": tenant, "id": claim["id"]},
            )
            if (
                job is None
                or job["state"] != "RUNNING"
                or job["claim_token"] != claim["claim_token"]
                or job["generation"] != claim["generation"]
                or job["lease_until"] <= now
            ):
                return "STALE"
            params = {"tenant": tenant, "id": job["id"], "asset": job["asset_id"], "now": now}
            if error:
                await session.execute(
                    text("""UPDATE orbit_material_lifecycle_job SET state='RETRY',
                    claim_token=NULL,lease_until=NULL,due_at=:due,last_error_code=:error,updated_at=:now
                    WHERE tenant_id=:tenant AND id=:id"""),
                    params | {"due": now + timedelta(seconds=60), "error": error},
                )
                return "RETRY"
            if asset is None or asset["physical_cleanup_state"] != "CLEANING":
                raise OrbitError(409, "LIFECYCLE_STATE_CONFLICT", "生命周期元数据变化，需重新核对")
            await session.execute(
                text("""UPDATE orbit_material_asset SET physical_cleanup_state='PURGED',
                physical_deleted_at=:now,revision=revision+1,updated_at=:now
                WHERE tenant_id=:tenant AND id=:asset"""),
                params,
            )
            await session.execute(
                text("""UPDATE orbit_material_lifecycle_job SET state='DONE',claim_token=NULL,
                lease_until=NULL,last_error_code=NULL,completed_at=:now,updated_at=:now
                WHERE tenant_id=:tenant AND id=:id"""),
                params,
            )
            await self.event(
                session,
                asset,
                "MATERIAL_OBJECT_PURGED",
                {
                    "physical_cleanup_state": {"before": "CLEANING", "after": "PURGED"},
                    "reason": job["kind"],
                },
            )
            return "DONE"

    async def run_once(self, limit=10):
        self.bounded(limit)
        results = []
        for _ in range(limit):
            claim = await self.claim()
            if claim is None:
                break
            if claim.get("skipped"):
                continue
            try:
                await asyncio.to_thread(
                    self.objects.purge, claim["tenant_id"], claim["upload_id"], claim["id"]
                )
                error = None
            except OrbitError as problem:
                error = problem.code
            except Exception:
                error = "LIFECYCLE_DELETE_UNAVAILABLE"
            results.append({"job_id": claim["id"], "state": await self.finish(claim, error)})
        return results
