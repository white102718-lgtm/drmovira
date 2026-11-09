"""排队的真实素材视频/跨8MiB分片HTTP专项；只在独立子进程PATH注入固定工具。"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PINNED_EXECUTABLES = {
    "ffmpeg.exe": "3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec",
    "ffprobe.exe": "f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52",
}
MATERIAL_VIDEO_CASES = [
    "pythonMaterialActualMp4HttpWorkerDurationAndAuthenticatedPreview",
    "pythonMaterialTruncatedMp4WorkerNeverPublishesReady",
    "pythonMaterialMediaSizeLimitsRejectBeforeObjectCreation",
    "pythonMaterialAbsentProcessorFailsWithoutFakeReadyOrAutomaticRevival",
    "pythonMaterialActualPngOverEightMiBTwoHttpPartsAndWorker",
]

_CHILD = r"""
import asyncio,hashlib,json,shutil,subprocess,sys
from pathlib import Path
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
try:
    value=json.loads(sys.stdin.buffer.read())
    root=Path(value["server_root"])
    sys.path[:0]=[str(root/"python"),str(root/"python/ruoyi_fastapi")]
    if value["tools_enabled"]:
        for name,expected in value["pinned_tools"].items():
            actual=shutil.which(name)
            if not actual or Path(actual).resolve()!=Path(value["tool_bin"],name).resolve():
                raise ValueError("tool resolution mismatch")
            if hashlib.sha256(Path(actual).read_bytes()).hexdigest()!=expected:
                raise ValueError("tool checksum mismatch")
    elif shutil.which("ffmpeg") or shutil.which("ffprobe"):
        raise ValueError("negative fixture unexpectedly resolves processor")
    if value["action"]=="generate":
        target=Path(value["target"]).resolve()
        if not target.is_relative_to(Path(value["object_root"]).resolve()):
            raise ValueError("generated fixture escapes root")
        source=("testsrc=size=160x120:rate=12" if value["variant"]==1
                else "testsrc2=size=128x96:rate=12")
        duration="2" if value["variant"]==1 else "1"
        command=[shutil.which("ffmpeg"),"-v","error","-nostdin","-f","lavfi","-i",source,
                 "-t",duration,"-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",str(target)]
        result=subprocess.run(command,capture_output=True,timeout=30)
        if result.returncode!=0:raise ValueError("fixture encoding failed")
        print(json.dumps({"status":"PASS","byte_size":target.stat().st_size}))
    elif value["action"]=="worker":
        from orbit_api.material_antivirus_runtime import PROFILE_KEY,ProcessBoundMaterialScanner
        from orbit_api.material_objects import LocalMaterialObjects
        from orbit_api.material_worker import MaterialWorker
        profile=value["runtime_profile"]
        if not isinstance(profile,dict) or set(profile)!={"profile_id","profiles"}:
            raise ValueError("complete trusted runtime profile required")
        encoded_profiles=json.dumps(profile["profiles"])
        scanner=ProcessBoundMaterialScanner(profile["profile_id"],
            values_provider=lambda:{PROFILE_KEY:encoded_profiles})
        async def run():
            engine=create_async_engine(URL.create("mysql+asyncmy",**value["database"]),echo=False)
            try:
                worker=MaterialWorker(async_sessionmaker(engine,expire_on_commit=False),
                    LocalMaterialObjects(Path(value["object_root"])),scanner=scanner,
                    runtime_profile_provider=lambda claim:scanner.profile)
                return await worker.run_once(50)
            finally:
                await engine.dispose()
        print(json.dumps({"status":"PASS","results":asyncio.run(run())}))
    else:
        raise ValueError("unsupported action")
except Exception:
    print(json.dumps({"status":"FAIL","error_code":"MATERIAL_MEDIA_CHILD_FAILED"}))
    sys.exit(1)
"""


def _file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _validate_tools(directory):
    directory = Path(directory).resolve()
    allowed = (ROOT.parent / ".runtime/tools").resolve()
    if not directory.is_relative_to(allowed):
        raise ValueError("素材测试工具必须位于本项目独立工具缓存")
    for filename, expected in PINNED_EXECUTABLES.items():
        path = directory / filename
        if not path.is_file() or path.is_symlink() or _file_sha(path) != expected:
            raise ValueError("素材视频工具缺失或固定SHA256不符，不能跳过标通过")
    return directory


def run_material_video_checks(
    client, admin, database, headers, object_root, cases, ffmpeg_bin, *, runtime_profile
):
    """调用方负责排队服务/当前UUID库及对象根；本函数不启动API、不更改全局环境。"""
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("素材媒体专项只能使用当前独立测试库")
    if admin.host not in {"localhost", "127.0.0.1"} or admin.port != 13306:
        raise ValueError("素材媒体专项只能使用本机隔离MySQL")
    from orbit_api.material_contract import PART_SIZE
    from orbit_api.material_objects import LocalMaterialObjects

    object_root = Path(object_root).resolve()
    LocalMaterialObjects(object_root)
    tool_bin = _validate_tools(ffmpeg_bin)

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    connection = {
        "username": decoded(admin.user),
        "password": decoded(admin.password),
        "host": admin.host,
        "port": admin.port,
        "database": database,
    }

    def child(action, *, tools=True, **extra):
        # 只给新子进程设置PATH；不写os.environ、注册表或运行中的预览进程。
        system = os.environ.get("SystemRoot", "C:/Windows")
        environment = {
            "SystemRoot": system,
            "WINDIR": os.environ.get("WINDIR", system),
            "PATH": str(tool_bin) + os.pathsep + str(Path(system) / "System32")
            if tools
            else str(Path(system) / "System32"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        value = {
            "server_root": str(ROOT),
            "object_root": str(object_root),
            "database": connection,
            "tools_enabled": tools,
            "tool_bin": str(tool_bin),
            "pinned_tools": PINNED_EXECUTABLES,
            "action": action,
            "runtime_profile": runtime_profile,
            **extra,
        }
        process = subprocess.Popen(
            [sys.executable, "-c", _CHILD],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            output, _ = process.communicate(json.dumps(value).encode(), timeout=240)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
            raise AssertionError("素材媒体专项子进程超时，未标通过") from None
        try:
            result = json.loads(output)
        except (ValueError, UnicodeError):
            raise AssertionError("素材媒体专项子进程未返回安全结果") from None
        assert process.returncode == 0 and result.get("status") == "PASS", (
            process.returncode,
            result.get("error_code", "MATERIAL_MEDIA_CHILD_FAILED"),
        )
        return result

    caps_response = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps_response.status_code == 200
    caps = caps_response.json()
    csrf = caps["csrf_token"]
    metadata = {"name": "真实媒体专项", "category_id": caps["default_category_id"], "tag_ids": []}

    def send(path, value):
        return client.post(
            "/api/v1/" + path,
            headers=headers | {"X-CSRF-Token": csrf, "Idempotency-Key": "media-" + uuid4().hex},
            json=value,
        )

    def upload(content, mime, name):
        digest = hashlib.sha256(content).hexdigest()
        response = send(
            "assets/upload-sessions",
            {
                "metadata": metadata | {"name": name},
                "mime": mime,
                "size": len(content),
                "sha256": digest,
            },
        )
        assert response.status_code == 201
        upload = response.json()
        assert upload["part_size"] == PART_SIZE, "本专项必须传真实不同内容，不能以READY去重替代上传"
        parts = []
        for offset in range(0, len(content), PART_SIZE):
            number, block = offset // PART_SIZE + 1, content[offset : offset + PART_SIZE]
            response = client.put(
                f"/api/v1/assets/upload-sessions/{upload['id']}/parts/{number}",
                headers=headers
                | {
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": "media-part-" + uuid4().hex,
                    "Content-Type": "application/octet-stream",
                },
                content=block,
            )
            assert response.status_code == 200
            assert response.json() == {
                "part_number": number,
                "etag": hashlib.sha256(block).hexdigest(),
            }
            parts.append(response.json())
        completed = send(
            f"assets/upload-sessions/{upload['id']}/complete",
            {"size": len(content), "sha256": digest, "parts": parts},
        )
        assert completed.status_code == 202 and completed.json()["state"] == "SCANNING"
        return upload["asset_id"], len(parts)

    def get(asset_id):
        response = client.get("/api/v1/assets/" + asset_id, headers=headers)
        assert response.status_code == 200
        return response.json()

    fixture_dir = Path(tempfile.mkdtemp(prefix="material-media-", dir=object_root)).resolve()
    try:
        source = fixture_dir / "generated.mp4"
        child("generate", target=str(source), variant=1)
        video = source.read_bytes()
        asset_id, part_count = upload(video, "video/mp4", "真实H264视频")
        assert part_count == 1
        child("worker")
        asset = get(asset_id)
        assert asset["kind"] == "VIDEO" and asset["state"] == "READY"
        assert asset["duration_seconds"] == "2.000000" and asset["preview_url"] is not None
        preview = client.get(f"/api/v1/assets/{asset_id}/preview", headers=headers)
        assert preview.status_code == 200
        with Image.open(BytesIO(preview.content)) as image:
            assert image.format == "JPEG" and image.size == (1024, 768)
        assert client.get(f"/api/v1/assets/{asset_id}/preview").status_code == 401
        cases.append(MATERIAL_VIDEO_CASES[0])

        invalid_id, _ = upload(video[:64], "video/mp4", "截断MP4不得可用")
        child("worker")
        invalid = get(invalid_id)
        assert invalid["state"] == "PROCESSING_FAILED" and invalid["preview_url"] is None
        assert invalid["duration_seconds"] is None
        assert (
            client.get(f"/api/v1/assets/{invalid_id}/preview", headers=headers).status_code == 404
        )
        cases.append(MATERIAL_VIDEO_CASES[1])

        def counts():
            with admin.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM orbit_material_asset")
                assets = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM orbit_material_upload")
                return assets, cursor.fetchone()[0]

        before = counts()
        for mime, size in [
            ("image/png", 20 * 1024 * 1024 + 1),
            ("video/mp4", 500 * 1024 * 1024 + 1),
        ]:
            rejected = send(
                "assets/upload-sessions",
                {"metadata": metadata, "mime": mime, "size": size, "sha256": "a" * 64},
            )
            assert rejected.status_code == 422
        assert counts() == before
        cases.append(MATERIAL_VIDEO_CASES[2])

        alternate = fixture_dir / "alternate.mp4"
        child("generate", target=str(alternate), variant=2)
        unavailable_id, _ = upload(alternate.read_bytes(), "video/mp4", "缺工具不得假成功")
        child("worker", tools=False)
        unavailable = get(unavailable_id)
        assert unavailable["state"] == "PROCESSING_FAILED" and unavailable["preview_url"] is None
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT error_code FROM orbit_material_asset WHERE id=%s", (unavailable_id,)
            )
            assert cursor.fetchone()[0] == "VIDEO_PROCESSOR_UNAVAILABLE"
        assert not child("worker")["results"]
        assert get(unavailable_id)["state"] == "PROCESSING_FAILED"
        cases.append(MATERIAL_VIDEO_CASES[3])

        buffer = BytesIO()
        Image.new("RGB", (2048, 1536), "purple").save(buffer, "PNG", compress_level=0)
        image_bytes = buffer.getvalue()
        assert PART_SIZE < len(image_bytes) < 20 * 1024 * 1024
        image_id, part_count = upload(image_bytes, "image/png", "真实双分片PNG")
        assert part_count == 2
        child("worker")
        assert get(image_id)["state"] == "READY"
        preview = client.get(f"/api/v1/assets/{image_id}/preview", headers=headers)
        assert preview.status_code == 200
        with Image.open(BytesIO(preview.content)) as image:
            assert image.format == "JPEG" and image.size == (1024, 768)
        cases.append(MATERIAL_VIDEO_CASES[4])
    finally:
        # 子进程均已退出或被kill/join，核验最终绝对目标后只删本函数创建的目录。
        assert fixture_dir.resolve().parent == object_root
        assert fixture_dir.name.startswith("material-media-")
        shutil.rmtree(fixture_dir)
