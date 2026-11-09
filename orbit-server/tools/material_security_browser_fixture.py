"""三视口legacy安全PNG夹具：有真实原图和预览，刻意没有病毒扫描证明。"""

import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image


def prepare_material_security_browser_fixture(admin, database, object_root):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"localhost", "127.0.0.1"}
        or admin.port != 13306
    ):
        raise ValueError("legacy浏览器夹具仅接受主线当前本机UUID数据库")
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    objects = LocalMaterialObjects(Path(object_root))
    manifest = {"kind": "isolated-legacy-material-security-v1", "assets": []}
    for project, color in (
        ("desktop-1440", "orange"),
        ("wide-1920", "green"),
        ("mobile-390", "purple"),
    ):
        identifier, upload = str(uuid4()), str(uuid4())
        name = "历史安全复核-" + project + "-" + uuid4().hex[:8]
        output = BytesIO()
        Image.new("RGB", (48, 32), color).save(output, "PNG")
        content = output.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        with objects.mutation_guard(tenant, upload):
            (objects.directory(tenant, upload) / "original").write_bytes(content)
        process_material(objects, tenant, upload, "image/png")
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id,preview_ready,width_px,height_px)
                VALUES(%s,%s,%s,%s,%s,%s,'IMAGE','image/png','READY',%s,%s,%s,1,48,32)""",
                (
                    tenant,
                    identifier,
                    owner,
                    team,
                    name,
                    "00000000-0000-4000-8000-000000000001",
                    digest,
                    len(content),
                    upload,
                ),
            )
        manifest["assets"].append(
            {"project": project, "id": identifier, "name": name, "width": 48, "height": 32}
        )
    admin.commit()
    return manifest
