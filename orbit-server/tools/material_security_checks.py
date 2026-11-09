"""legacy消费者真实HTTP门禁和受控重扫；安全PNG，不生成或上传病毒样本。"""

import asyncio
import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_SECURITY_CASES = [
    "pythonMaterialLegacyReadyReadAndCollectionExplicitlyRemainUnverified",
    "pythonMaterialLegacyReadyPreviewAndEditAreActuallyRejected",
    "pythonMaterialLegacySameHashCannotDeduplicateAndNewUploadActuallyScans",
    "pythonMaterialLegacyCachedDedupCompleteAndEditCannotBypassCurrentProof",
    "pythonMaterialLegacyRescanIsIdempotentAndActualWorkerRestoresVerifiedReady",
    "pythonMaterialLegacyMissingOrChangedOriginalNeverQueuesOrFillsClean",
    "pythonMaterialLegacyRescanRequiresVersionCsrfAndAllowedUnreferencedState",
    "pythonMaterialSecurityCollectionRejectsDuplicatesAndForeignScopeAsWholeBatch",
]


def run_material_security_checks(client, admin, database, headers, object_root, scanner, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("legacy专项仅使用主线本机UUID库")
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material
    from orbit_api.material_worker import MaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    objects = LocalMaterialObjects(Path(object_root))
    caps = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps.status_code == 200
    csrf, category = caps.json()["csrf_token"], caps.json()["default_category_id"]

    def send(path, body, *, key=None, revision=None, method="POST", extra=None):
        request_headers = headers | {"X-CSRF-Token": csrf, "Idempotency-Key": key or str(uuid4())}
        if revision is not None:
            request_headers["If-Match"] = f'"{revision}"'
        return client.request(
            method, "/api/v1/" + path, headers=request_headers | (extra or {}), json=body
        )

    def legacy(*, missing=False):
        identifier, upload = str(uuid4()), str(uuid4())
        output = BytesIO()
        Image.new("RGB", (18, 18), "green").save(output, "PNG")
        content = output.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        if not missing:
            (objects.directory(tenant, upload) / "original").write_bytes(content)
            process_material(objects, tenant, upload, "image/png")
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id,preview_ready,width_px,height_px)
                VALUES(%s,%s,%s,%s,'legacy未扫描安全PNG',%s,'IMAGE','image/png','READY',
                 %s,%s,%s,1,18,18)""",
                (tenant, identifier, owner, team, category, digest, len(content), upload),
            )
        admin.commit()
        return identifier, upload, content, digest

    def get(identifier):
        result = client.get("/api/v1/assets/" + identifier, headers=headers)
        assert result.status_code == 200
        return result.json()

    def security(identifier):
        result = client.get("/api/v1/assets/" + identifier + "/security", headers=headers)
        assert result.status_code == 200
        return result.json()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def process(identifier):
        # 只优先本轮对象，不用该夹具证明队列公平性。
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_material_job SET created_at='2000-01-01' "
                "WHERE tenant_id=%s AND asset_id=%s",
                (tenant, identifier),
            )
        admin.commit()
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
        try:
            result = await MaterialWorker(
                async_sessionmaker(engine, expire_on_commit=False),
                objects,
                scanner=scanner,
                runtime_profile_provider=lambda claim: scanner.profile,
            ).run_once(1)
            assert result == [{"asset_id": identifier, "state": "READY"}]
        finally:
            await engine.dispose()

    identifier, upload, content, digest = legacy()
    assert get(identifier)["state"] == "READY" and get(identifier)["preview_url"] is None
    listing = client.get("/api/v1/assets", headers=headers, params={"q": "legacy未扫描安全PNG"})
    assert listing.status_code == 200
    listed = next(item for item in listing.json()["items"] if item["id"] == identifier)
    assert listed["state"] == "READY" and listed["preview_url"] is None
    inspection = security(identifier)
    assert inspection["scan_status"] == "UNVERIFIED" and inspection["receipt_at"] is None
    assert inspection["rescan_allowed"] is True and inspection["hash_matches"] is False
    batch = client.get("/api/v1/assets/security", headers=headers, params={"asset_ids": identifier})
    assert batch.status_code == 200 and batch.json() == {"items": [inspection]}
    assert set(inspection) == {
        "asset_id",
        "revision",
        "scan_status",
        "hash_matches",
        "engine_version",
        "database_version",
        "receipt_at",
        "rescan_allowed",
        "rescan_reason",
    }
    cases.append(MATERIAL_SECURITY_CASES[0])
    preview = client.get("/api/v1/assets/" + identifier + "/preview", headers=headers)
    assert preview.status_code == 409 and preview.json()["code"] == "ANTIVIRUS_UNVERIFIED"
    metadata = {"name": "不得修改未扫描文件", "category_id": category, "tag_ids": []}
    edit = send("assets/" + identifier, metadata, revision=1, method="PUT")
    assert edit.status_code == 409 and edit.json()["code"] == "ANTIVIRUS_UNVERIFIED"
    assert get(identifier)["revision"] == 1
    cases.append(MATERIAL_SECURITY_CASES[1])
    intent = {"metadata": metadata, "mime": "image/png", "size": len(content), "sha256": digest}
    created = send("assets/upload-sessions", intent)
    assert created.status_code == 201
    new = created.json()
    assert new["asset_id"] != identifier and new["part_size"] > 0
    part = client.put(
        f"/api/v1/assets/upload-sessions/{new['id']}/parts/1",
        headers=headers
        | {
            "X-CSRF-Token": csrf,
            "Idempotency-Key": str(uuid4()),
            "Content-Type": "application/octet-stream",
        },
        content=content,
    )
    assert part.status_code == 200
    completed_body = {"size": len(content), "sha256": digest, "parts": [part.json()]}
    completed = send(f"assets/upload-sessions/{new['id']}/complete", completed_body)
    assert completed.status_code == 202 and completed.json()["state"] == "SCANNING"
    asyncio.run(process(new["asset_id"]))
    assert security(new["asset_id"])["scan_status"] == "CLEAN"
    cases.append(MATERIAL_SECURITY_CASES[2])
    duplicate_key, complete_key, edit_key = [str(uuid4()) for _ in range(3)]
    duplicate = send("assets/upload-sessions", intent, key=duplicate_key)
    assert duplicate.status_code == 201 and duplicate.json()["part_size"] == 0
    duplicate_upload = duplicate.json()["id"]
    complete_path = f"assets/upload-sessions/{duplicate_upload}/complete"
    assert send(complete_path, completed_body, key=complete_key).status_code == 202
    current = get(new["asset_id"])
    edit_path = "assets/" + current["id"]
    assert (
        send(
            edit_path, metadata, key=edit_key, revision=current["revision"], method="PUT"
        ).status_code
        == 200
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_job SET state='FAILED' WHERE tenant_id=%s AND asset_id=%s",
            (tenant, current["id"]),
        )
    admin.commit()
    for result in (
        send("assets/upload-sessions", intent, key=duplicate_key),
        send(complete_path, completed_body, key=complete_key),
        send(edit_path, metadata, key=edit_key, revision=current["revision"], method="PUT"),
    ):
        assert result.status_code == 409 and result.json()["code"] == "ANTIVIRUS_UNVERIFIED"
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_job SET state='DONE' WHERE tenant_id=%s AND asset_id=%s",
            (tenant, current["id"]),
        )
    admin.commit()
    cases.append(MATERIAL_SECURITY_CASES[3])
    reason, rescan_key = {"reason": "复核历史安全PNG"}, str(uuid4())
    route = "assets/" + identifier + "/rescan"
    accepted = send(route, reason, key=rescan_key, revision=1)
    assert accepted.status_code == 202 and accepted.json()["state"] == "SCANNING"
    assert send(route, reason, key=rescan_key, revision=1).json() == accepted.json()
    assert security(identifier)["scan_status"] == "SCANNING"
    asyncio.run(process(identifier))
    assert get(identifier)["preview_url"] and security(identifier)["scan_status"] == "CLEAN"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_material_audit WHERE tenant_id=%s AND resource_id=%s "
            "AND action='MATERIAL_RESCAN_REQUESTED'",
            (tenant, identifier),
        )
        assert cursor.fetchone()[0] == 1
    admin.commit()
    cases.append(MATERIAL_SECURITY_CASES[4])
    absent, _, _, _ = legacy(missing=True)
    denied = send("assets/" + absent + "/rescan", reason, revision=1)
    assert denied.status_code == 409 and denied.json()["code"] == "ORIGINAL_OBJECT_UNAVAILABLE"
    changed, changed_upload, _, _ = legacy()
    with objects.mutation_guard(tenant, changed_upload):
        objects.original(tenant, changed_upload).write_bytes(b"changed-safe-original")
    denied = send("assets/" + changed + "/rescan", reason, revision=1)
    assert denied.status_code == 409 and denied.json()["code"] == "ORIGINAL_OBJECT_CHANGED"
    assert get(absent)["revision"] == get(changed)["revision"] == 1
    cases.append(MATERIAL_SECURITY_CASES[5])
    bounded, _, _, _ = legacy()
    bounded_route = "assets/" + bounded + "/rescan"
    assert send(bounded_route, reason).status_code == 400
    assert send(bounded_route, reason, revision=99).status_code == 409
    assert (
        send(
            bounded_route, reason, revision=1, extra={"X-CSRF-Token": "invalid-session-token"}
        ).status_code
        == 403
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_material_reference(tenant_id,asset_id,id,kind,resource_id,active) "
            "VALUES(%s,%s,%s,'ALLOCATION',%s,1)",
            (tenant, bounded, str(uuid4()), str(uuid4())),
        )
    admin.commit()
    assert security(bounded)["rescan_reason"] == "ACTIVE_REFERENCE"
    refused = send(bounded_route, reason, revision=1)
    assert refused.status_code == 409 and refused.json()["code"] == "ASSET_REFERENCED"
    assert get(bounded)["revision"] == 1
    forbidden_state, _, _, _ = legacy()
    state_route = "assets/" + forbidden_state + "/rescan"
    for field, state, reason_code in (
        ("state", "ARCHIVED", "ARCHIVED"),
        ("physical_cleanup_state", "CLEANING", "OBJECT_UNAVAILABLE"),
    ):
        with admin.cursor() as cursor:
            cursor.execute(
                f"UPDATE orbit_material_asset SET {field}=%s WHERE tenant_id=%s AND id=%s",
                (state, tenant, forbidden_state),
            )
        admin.commit()
        assert security(forbidden_state)["rescan_reason"] == reason_code
        refused = send(state_route, reason, revision=1)
        assert refused.status_code == 409 and refused.json()["code"] == "RESCAN_STATE_CONFLICT"
        with admin.cursor() as cursor:
            cursor.execute(
                f"UPDATE orbit_material_asset SET {field}=%s WHERE tenant_id=%s AND id=%s",
                ("READY" if field == "state" else "LIVE", tenant, forbidden_state),
            )
        admin.commit()
    with admin.cursor() as cursor:
        cursor.execute(
            """INSERT INTO orbit_material_job
            (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,claim_id,claimed_at)
            VALUES(%s,%s,1,1,%s,'RUNNING',%s,UTC_TIMESTAMP(3))""",
            (tenant, forbidden_state, "a" * 64, str(uuid4())),
        )
    admin.commit()
    assert security(forbidden_state)["rescan_reason"] == "SCAN_IN_PROGRESS"
    refused = send(state_route, reason, revision=1)
    assert refused.status_code == 409 and refused.json()["code"] == "RESCAN_STATE_CONFLICT"
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_job SET state='FAILED' WHERE tenant_id=%s AND asset_id=%s",
            (tenant, forbidden_state),
        )
    admin.commit()
    cases.append(MATERIAL_SECURITY_CASES[6])
    for ids in (identifier + "," + identifier, identifier + ",", "not-uuid"):
        assert (
            client.get(
                "/api/v1/assets/security", headers=headers, params={"asset_ids": ids}
            ).status_code
            == 422
        )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
            (tenant,),
        )
        foreign = cursor.fetchone()
        assert foreign, "集合隔离专项要求主线USER夹具"
        foreign_id = str(uuid4())
        cursor.execute(
            """INSERT INTO orbit_material_asset
            (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
             sha256,byte_size,object_upload_id)
            VALUES(%s,%s,%s,%s,'异租户元数据夹具',%s,'IMAGE','image/png','READY',%s,1,%s)""",
            (foreign[0], foreign_id, foreign[1], foreign[2], category, "a" * 64, str(uuid4())),
        )
    admin.commit()
    refused = client.get(
        "/api/v1/assets/security",
        headers=headers,
        params={"asset_ids": identifier + "," + foreign_id},
    )
    assert refused.status_code == 404
    cases.append(MATERIAL_SECURITY_CASES[7])
