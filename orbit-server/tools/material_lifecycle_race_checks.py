"""已接入真实对象写方的跨进程回收竞争；独占文件，不模拟处理成功。"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from functools import partial
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MATERIAL_LIFECYCLE_RACE_CASES = [
    "pythonMaterialActualPartWriterGuardSerializesPurgeAndRejectsLateWrite",
    "pythonMaterialActualAssemblyGuardSerializesPurgeAndRejectsLateWrite",
    "pythonMaterialActualPillowPreviewGuardSerializesPurgeAndRejectsLateWrite",
]
_CHILD = r"""
import base64,json,sys,time
from pathlib import Path
try:
    value=json.loads(sys.stdin.buffer.read())
    sys.path[:0]=[str(Path(value['server'])/'python')]
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_processing import process_material
    class PausingObjects(LocalMaterialObjects):
        paused=False
        def directory(self,tenant,upload):
            actual=super().directory(tenant,upload)
            if not self.paused:
                self.paused=True
                Path(value['ready']).write_text('GUARDED',encoding='ascii')
                end=time.monotonic()+20
                while not Path(value['release']).exists():
                    if time.monotonic()>end:raise ValueError('controlled race timeout')
                    time.sleep(0.01)
            return actual
    objects=PausingObjects(Path(value['root']))
    data=base64.b64decode(value['data'])
    tenant,upload=value['tenant'],value['upload']
    if value['mode']=='part':
        objects.put_part(tenant,upload,1,data,len(data))
    elif value['mode']=='assembly':
        objects.assemble(tenant,upload,[CompletedPart(part_number=1,etag=value['sha'])],
                         len(data),value['sha'],'image/png')
    elif value['mode']=='preview':
        result=process_material(objects,tenant,upload,'image/png')
        assert (result.width,result.height)==(16,12)
    else:raise ValueError('unsupported fixture mode')
    print(json.dumps({'status':'PASS'}))
except Exception as error:
    print(json.dumps({'status':'FAIL','code':getattr(error,'code','MATERIAL_RACE_CHILD_FAILED')}))
    sys.exit(1)
"""


def run_material_lifecycle_race_checks(object_root, cases):
    from orbit_api.errors import OrbitError
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_lifecycle_objects import LifecycleObjectFence
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material

    root = LocalMaterialObjects(Path(object_root)).root
    objects = LocalMaterialObjects(root)
    fence = LifecycleObjectFence(root, writers_fenced=True)
    output = BytesIO()
    Image.new("RGB", (16, 12), "blue").save(output, "PNG")
    data = output.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    parts = [CompletedPart(part_number=1, etag=digest)]
    system = os.environ.get("SystemRoot", "C:/Windows")
    env = {
        "SystemRoot": system,
        "WINDIR": system,
        "PYTHONIOENCODING": "utf-8",
        "PATH": str(Path(system) / "System32"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for mode, case in zip(
        ("part", "assembly", "preview"), MATERIAL_LIFECYCLE_RACE_CASES, strict=True
    ):
        tenant, upload = str(uuid4()), str(uuid4())
        directory = objects.directory(tenant, upload)
        if mode != "part":
            objects.put_part(tenant, upload, 1, data, len(data))
        if mode == "preview":
            objects.assemble(tenant, upload, parts, len(data), digest, "image/png")
        ipc = Path(tempfile.mkdtemp(prefix="material-race-", dir=root)).absolute()
        ready, release = ipc / "ready", ipc / "release"
        value = {
            "server": str(ROOT),
            "root": str(root),
            "tenant": tenant,
            "upload": upload,
            "ready": str(ready),
            "release": str(release),
            "mode": mode,
            "data": base64.b64encode(data).decode(),
            "sha": digest,
        }
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            child.stdin.write(json.dumps(value).encode())
            child.stdin.close()
            child.stdin = None
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "真实写方未到达受控guard区，不能跳过竞争"
            try:
                fence.purge(tenant, upload, str(uuid4()))
            except OrbitError as error:
                assert error.code == "OBJECT_BUSY"
            else:
                raise AssertionError("真实写方持guard时物理回收不能穿过")
            release.write_text("CONTINUE", encoding="ascii")
            stdout, _ = child.communicate(timeout=10)
            assert child.returncode == 0 and json.loads(stdout)["status"] == "PASS"
            assert fence.purge(tenant, upload, str(uuid4())) >= 1
            assert not directory.exists()
            for late in (
                partial(objects.put_part, tenant, upload, 1, data, len(data)),
                partial(objects.assemble, tenant, upload, parts, len(data), digest, "image/png"),
                partial(process_material, objects, tenant, upload, "image/png"),
            ):
                try:
                    late()
                except OrbitError as error:
                    assert error.code == "OBJECT_EXPIRED"
                else:
                    raise AssertionError("墓碑后真实对象写方不得恢复旧UUID")
                assert not directory.exists()
            cases.append(case)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)
            if ipc.parent != root or not ipc.name.startswith("material-race-"):
                raise ValueError("只允许清理本次独占IPC目录")
            ready.unlink(missing_ok=True)
            release.unlink(missing_ok=True)
            ipc.rmdir()
