"""排队运行的真实HTTP/MySQL/磁盘素材专项；不启动服务、不访问云、不伪造处理成功。"""

import asyncio
import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_CASES = [
    "pythonMaterialTaxonomyOriginalFieldsAndFixedUncategorized",
    "pythonMaterialUploadStrictFieldsHashAndPartConflict",
    "pythonMaterialActualPngUploadProcessingAndAuthenticatedPreview",
    "pythonMaterialOwnerReadyDedupNeverCreatesAnotherAsset",
    "pythonMaterialMetadataCasAndDisabledTagRetention",
    "pythonMaterialAnyAllFiltersAndUnknownMetricsRemainUnknown",
    "pythonMaterialActiveReferencesBlockAtomicArchive",
    "pythonMaterialArchiveAuditFailureRollsBackWholeBatch",
    "pythonMaterialCorruptSignatureOnlyPngQuarantines",
    "pythonMaterialRevokedPendingJobFailsAndReenableNeverRevives",
    "pythonMaterialRevokedAfterRealDecodeCannotPublishReady",
    "pythonMaterialDisabledTenantQueueDoesNotStarveValidJob",
]


def run_material_checks(client, admin, database, headers, object_root, cases, *, scanner):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("素材检查只能连接本轮独立测试库")
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_worker import MaterialWorker

    objects = LocalMaterialObjects(Path(object_root))
    caps = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps.status_code == 200
    csrf = caps.json()["csrf_token"]

    def send(path, value, *, revision=None, method="POST", key=None):
        extra = {"X-CSRF-Token": csrf, "Idempotency-Key": key or "material-" + uuid4().hex}
        if revision is not None:
            extra["If-Match"] = f'"{revision}"'
        return client.request(method, "/api/v1/" + path, headers=headers | extra, json=value)

    category = send("categories", {"name": "素材验收分类"})
    tag = send("tags", {"name": "素材验收标签", "group": "自动专项"})
    assert category.status_code == tag.status_code == 201
    category, tag = category.json(), tag.json()
    for path in [
        "assets/not-a-uuid",
        "categories/not-a-uuid",
        "tags/not-a-uuid",
        "assets?category_id=not-a-uuid",
        "assets?tag_ids=not-a-uuid",
    ]:
        rejected = client.get("/api/v1/" + path, headers=headers)
        assert rejected.status_code == 422 and rejected.json()["code"] == "FIELD_INVALID", (
            path,
            rejected.status_code,
            rejected.json().get("code"),
            rejected.json().get("message"),
        )
    invalid_archive = send("categories/not-a-uuid/archive", {"reason": "标识边界"}, revision=1)
    assert (
        invalid_archive.status_code == 422
        and invalid_archive.json()["field_errors"][0]["path"] == "/id"
    )
    fixed_get = client.get(
        "/api/v1/categories/" + caps.json()["default_category_id"], headers=headers
    )
    assert fixed_get.status_code == 200 and fixed_get.json()["name"] == "未分类"
    fixed = send(
        "categories/" + caps.json()["default_category_id"] + "/archive",
        {"reason": "固定分类不能停用"},
        revision=1,
    )
    assert fixed.status_code == 409 and fixed.json()["code"] == "SYSTEM_CATEGORY_FIXED", (
        fixed.status_code,
        fixed.json().get("code"),
        fixed.json().get("message"),
    )
    for path, original in (("tags", tag), ("categories", category)):
        read = client.get("/api/v1/" + path + "/" + original["id"], headers=headers)
        assert read.status_code == 200
        body = read.json()
        # 只拆出已登记MAT-TAXONOMY-COUNT-V1，原字段仍须逐值严格相等。
        count = body.pop("visible_asset_count")
        assert type(count) is int and count == 0
        assert body == original
    cases.append(MATERIAL_CASES[0])
    output = BytesIO()
    Image.new("RGB", (128, 96), "blue").save(output, "PNG")
    data = output.getvalue()

    def create(data, name="素材PNG验收"):
        response = send(
            "assets/upload-sessions",
            {
                "metadata": {"name": name, "category_id": category["id"], "tag_ids": [tag["id"]]},
                "mime": "image/png",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        assert response.status_code == 201
        return response.json()

    upload = create(data)
    bad = send(
        "assets/upload-sessions",
        {
            "metadata": {"name": "不允许路径", "category_id": category["id"], "tag_ids": []},
            "mime": "image/png",
            "size": 20 * 1024 * 1024 + 1,
            "sha256": "a" * 64,
        },
    )
    assert bad.status_code == 422

    def part(upload, content):
        return client.put(
            "/api/v1/assets/upload-sessions/" + upload["id"] + "/parts/1",
            headers=headers
            | {
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "part-" + uuid4().hex,
                "Content-Type": "application/octet-stream",
            },
            content=content,
        )

    uploaded = part(upload, data)
    assert (
        uploaded.status_code == 200 and uploaded.json()["etag"] == hashlib.sha256(data).hexdigest()
    )
    conflict = part(upload, b"x" * len(data))
    assert conflict.status_code == 409
    cases.append(MATERIAL_CASES[1])

    def complete(upload, data):
        return send(
            "assets/upload-sessions/" + upload["id"] + "/complete",
            {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "parts": [{"part_number": 1, "etag": hashlib.sha256(data).hexdigest()}],
            },
        )

    completed = complete(upload, data)
    assert completed.status_code == 202 and completed.json()["state"] == "SCANNING"
    row = completed.json()
    assert (
        send(
            "assets/" + row["id"],
            {"name": "还未READY", "category_id": category["id"], "tag_ids": []},
            revision=row["revision"],
            method="PUT",
        ).status_code
        == 409
    )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def worker():
        engine = create_async_engine(url, echo=False)
        try:
            return await MaterialWorker(
                async_sessionmaker(engine, expire_on_commit=False),
                objects,
                scanner=scanner,
                runtime_profile_provider=lambda claim: scanner.profile,
            ).run_once(50)
        finally:
            await engine.dispose()

    results = asyncio.run(worker())
    assert any(r["asset_id"] == row["id"] and r["state"] == "READY" for r in results)
    asset = client.get("/api/v1/assets/" + row["id"], headers=headers).json()
    assert asset["state"] == "READY" and asset["duration_seconds"] is None
    preview = client.get("/api/v1/assets/" + row["id"] + "/preview", headers=headers)
    assert preview.status_code == 200 and preview.headers["content-type"].startswith("image/jpeg")
    with Image.open(BytesIO(preview.content)) as image:
        assert image.size == (128, 96)
    cases.append(MATERIAL_CASES[2])
    duplicate = create(data, "重复文件应该复用")
    assert duplicate["asset_id"] == asset["id"] and duplicate["part_size"] == 0
    cases.append(MATERIAL_CASES[3])

    other_png = BytesIO()
    Image.new("RGB", (128, 97), "green").save(other_png, "PNG")
    other_data = other_png.getvalue()
    other_upload = create(other_data, "批量事务对照素材")
    assert part(other_upload, other_data).status_code == 200
    assert complete(other_upload, other_data).status_code == 202
    asyncio.run(worker())
    other_asset = client.get("/api/v1/assets/" + other_upload["asset_id"], headers=headers).json()
    assert other_asset["state"] == "READY"

    disabled = send(
        "tags/" + tag["id"] + "/archive", {"reason": "保留旧关联"}, revision=tag["revision"]
    )
    assert disabled.status_code == 200
    changed = send(
        "assets/" + asset["id"],
        {"name": "已编辑可用素材", "category_id": category["id"], "tag_ids": [tag["id"]]},
        revision=asset["revision"],
        method="PUT",
    )
    assert changed.status_code == 200 and changed.json()["tag_ids"] == [tag["id"]]
    stale = send(
        "assets/" + asset["id"],
        {"name": "冲突修改", "category_id": category["id"], "tag_ids": []},
        revision=asset["revision"],
        method="PUT",
    )
    assert stale.status_code == 409
    asset = changed.json()
    cases.append(MATERIAL_CASES[4])
    for mode in ["ALL", "ANY"]:
        response = client.get(
            "/api/v1/assets",
            headers=headers,
            params={
                "sort": "name",
                "direction": "ASC",
                "tag_ids": tag["id"],
                "tag_match": mode,
                "q": "已编辑",
            },
        )
        assert response.status_code == 200 and [a["id"] for a in response.json()["items"]] == [
            asset["id"]
        ]
    assert client.get("/api/v1/assets?sort=spend", headers=headers).status_code == 503
    cases.append(MATERIAL_CASES[5])

    tenant = "00000000-0000-0000-0000-000000000001"
    reference = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_material_reference(tenant_id,asset_id,id,kind,resource_id,active) "
            "VALUES(%s,%s,%s,'ALLOCATION',%s,1)",
            (tenant, asset["id"], reference, str(uuid4())),
        )
    selected = {
        "assets": [
            {"id": asset["id"], "revision": asset["revision"]},
            {"id": other_asset["id"], "revision": other_asset["revision"]},
        ],
        "reason": "引用应阻止",
    }
    blocked = send("assets/bulk-delete", selected)
    assert blocked.status_code == 409 and blocked.json()["code"] == "ASSET_REFERENCED"
    assert client.get("/api/v1/assets/" + asset["id"] + "/references", headers=headers).json()[
        "items"
    ][0]["active"]
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_material_reference SET active=0 WHERE id=%s", (reference,))
    cases.append(MATERIAL_CASES[6])
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER material_audit_failure BEFORE INSERT ON orbit_material_audit "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
        )
    try:
        failed = send("assets/bulk-delete", selected)
        assert failed.status_code == 503
        unchanged = client.get("/api/v1/assets/" + asset["id"], headers=headers).json()
        assert unchanged["state"] == "READY" and unchanged["revision"] == asset["revision"]
        unchanged_other = client.get("/api/v1/assets/" + other_asset["id"], headers=headers).json()
        assert unchanged_other["state"] == "READY"
        assert unchanged_other["revision"] == other_asset["revision"]
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER material_audit_failure")
    accepted = send("assets/bulk-delete", selected)
    assert accepted.status_code == 200 and accepted.json()["state"] == "ARCHIVED"
    assert objects.original(tenant, upload["id"]).is_file()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(change_json,'$.reason')) "
            "FROM orbit_material_audit WHERE action='ASSET_ARCHIVED' AND resource_id=%s",
            (asset["id"],),
        )
        assert cursor.fetchone()[0] == selected["reason"]
    cases.append(MATERIAL_CASES[7])
    # 重新启用夹具标签仅为创建损坏文件场景，不冒充产品存在恢复标签接口。
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_taxonomy SET state='ENABLED' WHERE id=%s", (tag["id"],)
        )
    bad_data = b"\x89PNG\r\n\x1a\n" + b"broken" * 100
    bad_upload = create(bad_data, "损坏PNG")
    assert part(bad_upload, bad_data).status_code == 200
    assert complete(bad_upload, bad_data).status_code == 202
    asyncio.run(worker())
    assert (
        client.get("/api/v1/assets/" + bad_upload["asset_id"], headers=headers).json()["state"]
        == "QUARANTINED"
    )
    cases.append(MATERIAL_CASES[8])

    def queued(name, color):
        buffer = BytesIO()
        Image.new("RGB", (17, 19), color).save(buffer, "PNG")
        content = buffer.getvalue()
        pending = create(content, name)
        assert part(pending, content).status_code == 200
        assert complete(pending, content).status_code == 202
        return pending

    def revoke(enabled):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_menu SET status=%s WHERE menu_id=31052", ("0" if enabled else "1",)
            )

    revoked = queued("撤权前未开始", "orange")
    revoke(False)
    try:
        result = asyncio.run(worker())
        assert any(
            r["asset_id"] == revoked["asset_id"] and r["state"] == "PROCESSING_FAILED"
            for r in result
        )
    finally:
        revoke(True)
    assert not asyncio.run(worker())
    assert (
        client.get("/api/v1/assets/" + revoked["asset_id"], headers=headers).json()["state"]
        == "PROCESSING_FAILED"
    )
    cases.append(MATERIAL_CASES[9])

    running = queued("处理后撤权", "yellow")

    async def late_revoke():
        from orbit_api.material_processing import process_material

        engine = create_async_engine(url, echo=False)
        try:
            real_worker = MaterialWorker(
                async_sessionmaker(engine, expire_on_commit=False),
                objects,
                scanner=scanner,
                runtime_profile_provider=lambda claim: scanner.profile,
            )
            claim = await real_worker.claim()
            assert claim["asset_id"] == running["asset_id"]
            receipt = await asyncio.to_thread(
                scanner.scan, objects, tenant, running["id"], claim["sha256"], claim["byte_size"]
            )
            claim, state = await real_worker.record_scan(claim, receipt, profile=scanner.profile)
            assert claim is not None and state == "PROCESSING"
            actual = await asyncio.to_thread(
                process_material, objects, tenant, running["id"], "image/png"
            )
            revoke(False)
            try:
                applied, final = await real_worker.finish(claim, "READY", None, actual)
                assert applied and final == "PROCESSING_FAILED"
            finally:
                revoke(True)
        finally:
            await engine.dispose()

    asyncio.run(late_revoke())
    assert not asyncio.run(worker())
    assert (
        client.get("/api/v1/assets/" + running["asset_id"], headers=headers).json()["preview_url"]
        is None
    )
    cases.append(MATERIAL_CASES[10])

    valid = queued("停用队列后仍可完成", "purple")
    disabled_tenant, disabled_asset = str(uuid4()), str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_tenant(id,name,enabled) VALUES(%s,'停用素材租户夹具',0)",
            (disabled_tenant,),
        )
        cursor.execute(
            "INSERT INTO orbit_material_clock(tenant_id,revision) VALUES(%s,1)", (disabled_tenant,)
        )
        cursor.execute(
            "INSERT INTO orbit_material_asset "
            "(tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,"
            "byte_size,object_upload_id) SELECT %s,%s,owner_user_id,owner_team_id,name,category_id,"
            "kind,mime,'SCANNING',sha256,byte_size,object_upload_id FROM orbit_material_asset "
            "WHERE tenant_id=%s AND id=%s",
            (disabled_tenant, disabled_asset, tenant, valid["asset_id"]),
        )
        cursor.execute(
            "INSERT INTO orbit_material_job "
            "(tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,created_at) "
            "SELECT %s,%s,actor_id,actor_auth_version,scope_digest,'PENDING',"
            "UTC_TIMESTAMP(3)-INTERVAL 1 DAY FROM orbit_material_job "
            "WHERE tenant_id=%s AND asset_id=%s",
            (disabled_tenant, disabled_asset, tenant, valid["asset_id"]),
        )
        # 无关目录更新不应取消素材处理；发起人身份和该素材范围没有变化。
        cursor.execute(
            "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )
    result = asyncio.run(worker())
    assert any(
        r["asset_id"] == disabled_asset and r["state"] == "PROCESSING_FAILED" for r in result
    )
    assert any(r["asset_id"] == valid["asset_id"] and r["state"] == "READY" for r in result)
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_tenant SET enabled=1 WHERE id=%s", (disabled_tenant,))
    assert not asyncio.run(worker())
    cases.append(MATERIAL_CASES[11])
