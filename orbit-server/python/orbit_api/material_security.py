"""所有素材消费者共用当前对象扫描证据门禁，不把旧READY或缓存响应当扫描证明。"""

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError
from orbit_api.material_antivirus_sql import scan_evidence_predicate


def clean_scan_predicate(alias="a"):
    return scan_evidence_predicate(alias)


async def clean_scan_ids(session, tenant, identifiers):
    if not identifiers:
        return frozenset()
    if len(identifiers) > 200:
        raise ValueError("一次扫描证明查询最多200个素材")
    query = text(
        "SELECT a.id AS asset_id FROM orbit_material_asset a "
        "WHERE a.tenant_id=:tenant AND a.id IN :ids AND a.state='READY' "
        "AND a.physical_cleanup_state='LIVE' AND " + clean_scan_predicate()
    ).bindparams(bindparam("ids", expanding=True))
    return frozenset(
        row["asset_id"]
        for row in (await session.execute(query, {"tenant": tenant, "ids": list(identifiers)}))
        .mappings()
        .all()
    )


async def require_clean_scan(session, tenant, asset):
    if asset["id"] not in await clean_scan_ids(session, tenant, [asset["id"]]):
        raise OrbitError(
            409, "ANTIVIRUS_UNVERIFIED", "素材缺少当前对象完整病毒扫描证据，请申请安全复核"
        )


async def safe_asset_rows(session, tenant, values):
    verified = await clean_scan_ids(session, tenant, [row["id"] for row in values])
    return [dict(row) | {"_scan_verified": row["id"] in verified} for row in values]


def security_ids(csv):
    from orbit_api.identity_contract import _uuid

    if not isinstance(csv, str) or not 1 <= len(csv) <= 7399:
        raise OrbitError(422, "FIELD_INVALID", "安全查询要求1至200个UUID", "/asset_ids")
    parts = csv.split(",")
    if not 1 <= len(parts) <= 200 or len(set(parts)) != len(parts):
        raise OrbitError(422, "FIELD_INVALID", "安全查询不得重复且最多200项", "/asset_ids")
    return sorted(_uuid(value, "/asset_ids") for value in parts)


async def read_security(service, session, actor, identifiers):
    context = await service.context(session, actor)
    can_upload = True
    try:
        await service.context(session, actor, "assets.upload")
    except OrbitError as error:
        if error.status != 403:
            raise
        can_upload = False
    statement = text("""SELECT a.id,a.revision,a.owner_user_id,a.owner_team_id,a.state,
        a.sha256,a.byte_size,a.physical_cleanup_state,j.state AS job_state,
        r.result,r.sha256 AS receipt_sha,r.byte_size AS receipt_size,r.engine_version,
        r.database_version,r.database_built_at,r.policy_sha256,r.completed_at,r.error_code,
        EXISTS(SELECT 1 FROM orbit_material_reference mr
          WHERE mr.tenant_id=a.tenant_id AND mr.asset_id=a.id AND mr.active=1
            AND mr.kind IN('ALLOCATION','EXECUTION')) AS active_reference
        FROM orbit_material_asset a LEFT JOIN orbit_material_job j
          ON j.tenant_id=a.tenant_id AND j.asset_id=a.id
        LEFT JOIN orbit_material_scan_receipt r ON r.tenant_id=j.tenant_id
          AND r.asset_id=j.asset_id AND r.claim_id=j.claim_id
        WHERE a.tenant_id=:tenant AND a.id IN :ids ORDER BY a.id""").bindparams(
        bindparam("ids", expanding=True)
    )
    values = (
        (await session.execute(statement, {"tenant": context.tenant_id, "ids": identifiers}))
        .mappings()
        .all()
    )
    managed = set()
    if context.data_role == "TEAM_ADMIN":
        query = text("""SELECT m.team_id FROM orbit_business_team_manager m
            JOIN orbit_business_team t ON t.tenant_id=m.tenant_id AND t.id=m.team_id AND t.enabled=1
            WHERE m.tenant_id=:tenant AND m.manager_user_id=:actor AND m.enabled=1""")
        managed = {
            row["team_id"]
            for row in (await session.execute(query, {"tenant": context.tenant_id, "actor": actor}))
            .mappings()
            .all()
        }
    if len(values) != len(identifiers) or any(
        context.data_role != "SUPER_ADMIN"
        and row["owner_user_id"] != context.subject_id
        and row["owner_team_id"] not in managed
        for row in values
    ):
        raise OrbitError(404, "NOT_FOUND", "素材集合包含不存在或不可见项")
    result = []
    verified = await clean_scan_ids(session, context.tenant_id, identifiers)
    for row in values:
        matched = row["receipt_sha"] == row["sha256"] and row["receipt_size"] == row["byte_size"]
        clean = row["id"] in verified
        reason = (
            "PERMISSION_REQUIRED"
            if not can_upload
            else "ARCHIVED"
            if row["state"] == "ARCHIVED"
            else "OBJECT_UNAVAILABLE"
            if row["physical_cleanup_state"] != "LIVE"
            else "SCAN_IN_PROGRESS"
            if row["state"] in {"SCANNING", "PROCESSING"} or row["job_state"] == "RUNNING"
            else "UPLOAD_INCOMPLETE"
            if row["state"] in {"INITIATED", "UPLOADING", "UPLOAD_FAILED"}
            else "ACTIVE_REFERENCE"
            if row["active_reference"]
            else "RECHECK_AVAILABLE"
        )
        status = (
            "CLEAN"
            if clean
            else "SCANNING"
            if row["state"] in {"SCANNING", "PROCESSING"}
            else ("INFECTED" if row["result"] == "INFECTED" and matched else "UNVERIFIED")
        )
        result.append(
            {
                "asset_id": row["id"],
                "revision": row["revision"],
                "scan_status": status,
                "hash_matches": matched,
                "engine_version": row["engine_version"],
                "database_version": row["database_version"],
                "receipt_at": row["completed_at"].isoformat(timespec="milliseconds") + "Z"
                if row["completed_at"]
                else None,
                "rescan_allowed": reason == "RECHECK_AVAILABLE",
                "rescan_reason": reason,
            }
        )
    return {"items": result}


def verify_rescan_source(objects, tenant, asset):
    import hashlib

    try:
        with objects.mutation_guard(tenant, asset["object_upload_id"]):
            source = objects.original(tenant, asset["object_upload_id"])
            digest, size = hashlib.sha256(), 0
            with source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > asset["byte_size"] or size > 500 * 1024**2:
                        raise OrbitError(
                            409, "ORIGINAL_OBJECT_CHANGED", "原文件尺寸变化，不能申请复核"
                        )
                    digest.update(chunk)
            if size != asset["byte_size"] or digest.hexdigest() != asset["sha256"]:
                raise OrbitError(409, "ORIGINAL_OBJECT_CHANGED", "原文件摘要或尺寸不符")
    except FileNotFoundError:
        raise OrbitError(409, "ORIGINAL_OBJECT_UNAVAILABLE", "原文件缺失，不能申请复核") from None


async def rescan_asset(
    service, session, actor, authorization, csrf, key, expected, snapshot, value, request_id
):
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_store import MAX_REVISION, one

    context, digest, replay = await service.begin_write(
        session,
        actor,
        authorization,
        csrf,
        key,
        "assets.upload",
        [snapshot["id"], "rescan", expected, value.model_dump()],
    )
    if replay is not None:
        return replay
    asset = await service.asset(session, context, snapshot["id"], lock=True)
    if asset["revision"] != expected or any(
        asset[field] != snapshot[field]
        for field in ("sha256", "byte_size", "object_upload_id", "owner_user_id", "owner_team_id")
    ):
        raise OrbitError(409, "REVISION_CONFLICT", "复核前素材已变化，请重新加载")
    if expected >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "素材版本不可继续变更")
    if asset["physical_cleanup_state"] != "LIVE" or asset["state"] not in {
        "READY",
        "QUARANTINED",
        "PROCESSING_FAILED",
    }:
        raise OrbitError(409, "RESCAN_STATE_CONFLICT", "当前素材状态不允许重新扫描")
    job = await one(
        session,
        """SELECT state FROM orbit_material_job
        WHERE tenant_id=:tenant AND asset_id=:id FOR UPDATE""",
        {"tenant": context.tenant_id, "id": asset["id"]},
    )
    if job and job["state"] == "RUNNING":
        raise OrbitError(409, "RESCAN_STATE_CONFLICT", "当前扫描任务尚未结束")
    active = await one(
        session,
        """SELECT id FROM orbit_material_reference
        WHERE tenant_id=:tenant AND asset_id=:id AND active=1
        AND kind IN('ALLOCATION','EXECUTION') LIMIT 1 FOR UPDATE""",
        {"tenant": context.tenant_id, "id": asset["id"]},
    )
    if active:
        raise OrbitError(409, "ASSET_REFERENCED", "先解除活跃分配或执行引用，再申请重新扫描")
    version = await actor_auth_version(session, actor)
    await session.execute(
        text("""INSERT INTO orbit_material_job
        (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state)
        VALUES(:tenant,:id,:actor,:version,:scope,'PENDING')
        ON DUPLICATE KEY UPDATE actor_id=:actor,actor_auth_version=:version,
        scope_digest=:scope,state='PENDING',claim_id=NULL,claimed_at=NULL,created_at=UTC_TIMESTAMP(3)"""),
        {
            "tenant": context.tenant_id,
            "id": asset["id"],
            "actor": actor,
            "version": version,
            "scope": material_job_scope(context, asset),
        },
    )
    await session.execute(
        text("""UPDATE orbit_material_asset SET state='SCANNING',preview_ready=0,
        error_code=NULL,revision=revision+1,updated_at=UTC_TIMESTAMP(3)
        WHERE tenant_id=:tenant AND id=:id"""),
        {"tenant": context.tenant_id, "id": asset["id"]},
    )
    await service.changed(
        session,
        context,
        "MATERIAL_RESCAN_REQUESTED",
        asset["id"],
        expected + 1,
        request_id,
        {"reason": value.reason, "state": {"before": asset["state"], "after": "SCANNING"}},
    )
    tags = (await service.tags(session, context.tenant_id, [asset["id"]]))[asset["id"]]
    response = service.public_asset(
        dict(asset) | {"state": "SCANNING", "preview_ready": 0, "revision": expected + 1}, tags
    )
    return await service.finish(session, context, key, digest, response)
