"""真实HTTP 100-continue屏障：应用已读取授权快照后再过期并回收。"""

import asyncio
import hashlib
import http.client
import json
import re
import socket
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_LIFECYCLE_HTTP_RACE_CASES = [
    "pythonMaterialHttpPartSnapshotThenExpiryAndPurgeRejectsLateBodyWithoutOrphan",
    "pythonMaterialHttpCompletedUploadIsNotReclaimedByLateExpiryCandidate",
    "pythonMaterialHistoricalEvidenceGateInsertAfterQueueBeforeClaimBlocksPurge",
]


def run_material_lifecycle_http_race_checks(client, admin, database, headers, object_root, cases):
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("HTTP生命周期竞争只能使用当前隔离测试库")
    if admin.host not in {"127.0.0.1", "localhost"} or admin.port != 13306:
        raise ValueError("HTTP生命周期竞争只能使用本机隔离MySQL")
    if (
        client.base_url.scheme != "http"
        or client.base_url.host != "127.0.0.1"
        or client.base_url.port != 18083
    ):
        raise ValueError("HTTP快照竞争只允许直连主线本机隔离18083")
    from orbit_api.material_lifecycle import MaterialLifecycleWorker, require_referenceable
    from orbit_api.material_lifecycle_objects import LifecycleObjectFence

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    caps = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps.status_code == 200
    csrf = caps.json()["csrf_token"]
    stream = BytesIO()
    Image.new("RGB", (17, 13), "green").save(stream, "PNG")
    data = stream.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    root = Path(object_root)

    def write_headers():
        return headers | {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}

    def create(name):
        result = client.post(
            "/api/v1/assets/upload-sessions",
            headers=write_headers(),
            json={
                "metadata": {
                    "name": name + uuid4().hex[:8],
                    "category_id": caps.json()["default_category_id"],
                    "tag_ids": [],
                },
                "mime": "image/png",
                "size": len(data),
                "sha256": digest,
            },
        )
        assert result.status_code == 201 and result.json()["part_size"] != 0
        return result.json()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def maintain():
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
            worker = MaterialLifecycleWorker(
                async_sessionmaker(engine, expire_on_commit=False),
                LifecycleObjectFence(root, writers_fenced=True),
            )
            await worker.enqueue()
            await worker.run_once(50)
        finally:
            await engine.dispose()

    upload = create("HTTP快照后过期")
    path = "/api/v1/assets/upload-sessions/" + upload["id"] + "/parts/1"
    head = write_headers() | {
        "Host": "127.0.0.1:18083",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(data)),
        "Expect": "100-continue",
        "Connection": "close",
    }
    for key, value in head.items():
        assert "\r" not in key + value and "\n" not in key + value
    with socket.create_connection(("127.0.0.1", 18083), timeout=15) as connection:
        wire = (
            "PUT "
            + path
            + " HTTP/1.1\r\n"
            + "".join(key + ": " + value + "\r\n" for key, value in head.items())
            + "\r\n"
        )
        connection.sendall(wire.encode("ascii"))
        interim = bytearray()
        while not interim.endswith(b"\r\n\r\n") and len(interim) < 8192:
            block = connection.recv(1)
            assert block, "原生HTTP未到达100-continue快照屏障"
            interim.extend(block)
        assert bytes(interim).split(b"\r\n", 1)[0] == b"HTTP/1.1 100 Continue", (
            "原生HTTP未确认应用读body"
        )
        # 此路由在snapshot事务完成后才读body；仅加速当前测试上传deadline，不修改其他会话。
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_material_upload SET expires_at=%s WHERE tenant_id=%s AND id=%s",
                (
                    datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
                    tenant,
                    upload["id"],
                ),
            )
        admin.commit()
        asyncio.run(maintain())
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,physical_cleanup_state FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, upload["asset_id"]),
            )
            assert cursor.fetchone() == ("UPLOAD_FAILED", "PURGED")
        connection.sendall(data)
        response = http.client.HTTPResponse(connection)
        response.begin()
        body = response.read(65537)
        assert len(body) <= 65536 and response.status == 409
        assert json.loads(body)["code"] == "OBJECT_EXPIRED"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_material_upload_part WHERE tenant_id=%s AND upload_id=%s",
            (tenant, upload["id"]),
        )
        assert cursor.fetchone()[0] == 0
    assert not (root / tenant / upload["id"]).exists()
    cases.append(MATERIAL_LIFECYCLE_HTTP_RACE_CASES[0])

    # 另一真实HTTP上传先提交COMPLETE/SCANNING，再把旧expires_at置过去，维护不能误取消。
    upload = create("HTTP完成先赢")
    part = client.put(
        "/api/v1/assets/upload-sessions/" + upload["id"] + "/parts/1",
        headers=write_headers() | {"Content-Type": "application/octet-stream"},
        content=data,
    )
    assert part.status_code == 200
    complete = client.post(
        "/api/v1/assets/upload-sessions/" + upload["id"] + "/complete",
        headers=write_headers(),
        json={"size": len(data), "sha256": digest, "parts": [part.json()]},
    )
    assert complete.status_code == 202 and complete.json()["state"] == "SCANNING"
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_upload SET expires_at=%s WHERE tenant_id=%s AND id=%s",
            (datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1), tenant, upload["id"]),
        )
    admin.commit()
    asyncio.run(maintain())
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT state,physical_cleanup_state FROM orbit_material_asset "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, upload["asset_id"]),
        )
        assert cursor.fetchone() == ("SCANNING", "LIVE")
        cursor.execute(
            "SELECT state FROM orbit_material_upload WHERE tenant_id=%s AND id=%s",
            (tenant, upload["id"]),
        )
        assert cursor.fetchone()[0] == "COMPLETE"
    assert (root / tenant / upload["id"] / "original").is_file()
    cases.append(MATERIAL_LIFECYCLE_HTTP_RACE_CASES[1])

    archived = client.post(
        "/api/v1/assets/bulk-delete",
        headers=write_headers(),
        json={
            "assets": [{"id": upload["asset_id"], "revision": complete.json()["revision"]}],
            "reason": "历史引用竞争专项",
        },
    )
    assert archived.status_code == 200
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_material_asset SET archived_at=%s WHERE tenant_id=%s AND id=%s",
            (
                datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31),
                tenant,
                upload["asset_id"],
            ),
        )
    admin.commit()

    async def history_wins():
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
        worker = MaterialLifecycleWorker(sessions, LifecycleObjectFence(root, writers_fenced=True))
        try:
            await worker.enqueue()
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT state FROM orbit_material_lifecycle_job WHERE tenant_id=%s "
                    "AND asset_id=%s AND kind='ARCHIVE_RETENTION'",
                    (tenant, upload["asset_id"]),
                )
                assert cursor.fetchone()[0] == "PENDING"
            async with sessions() as session, session.begin():
                await require_referenceable(session, tenant, upload["asset_id"])
                await session.execute(
                    text("""INSERT INTO orbit_material_reference
                    (tenant_id,asset_id,id,kind,resource_id,active)
                    VALUES(:tenant,:asset,:id,'HISTORICAL_EVIDENCE',:resource,0)"""),
                    {
                        "tenant": tenant,
                        "asset": upload["asset_id"],
                        "id": str(uuid4()),
                        "resource": str(uuid4()),
                    },
                )
            await worker.run_once(50)
        finally:
            await engine.dispose()

    asyncio.run(history_wins())
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT state,physical_cleanup_state FROM orbit_material_asset "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, upload["asset_id"]),
        )
        assert cursor.fetchone() == ("ARCHIVED", "LIVE")
    assert (root / tenant / upload["id"] / "original").is_file()
    cases.append(MATERIAL_LIFECYCLE_HTTP_RACE_CASES[2])
