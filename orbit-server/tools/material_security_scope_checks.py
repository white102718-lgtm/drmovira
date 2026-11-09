"""安全扩展多身份真实HTTP专项；复用主线USER夹具，不改OIDC或角色管理合同。"""

import asyncio
import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fixture_login import fixture_login
from PIL import Image
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_SECURITY_SCOPE_CASES = [
    "pythonMaterialSecurityReadOnlyOwnerSeesUnverifiedButCannotRequestRescan",
    "pythonMaterialSecuritySameTeamUserCannotReadOrRescanAnotherOwnersObject",
    "pythonMaterialSecurityGrantedUploadQueuesOwnObjectWithoutOwnershipTransfer",
    "pythonMaterialSecurityUploadRevokedAfterQueueCancelsActualWorkerWithoutCleanProof",
]


def run_material_security_scope_checks(
    client, admin, database, headers, object_root, scanner, fixture, password, cache, cases
):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("安全scope专项只能使用主线本机UUID库")
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_worker import MaterialWorker

    _, user, _, peer = fixture["users"][:4]
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    assert user["team"] == peer["team"], "必须用同团队不同普通用户验证隔离"
    caps = client.get("/api/v1/roles/capabilities", headers=headers)
    assert caps.status_code == 200

    def role(permissions):
        result = client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": caps.json()["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "扫描权限" + uuid4().hex[:8],
                "menu_codes": ["assets"],
                "permission_codes": permissions,
            },
        )
        assert result.status_code == 201
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
                (tenant, result.json()["id"]),
            )
            return cursor.fetchone()[0]

    read_role = role(["assets.read", "assets.edit"])
    upload_role = role(["assets.read", "assets.upload"])
    with admin.cursor() as cursor:
        # peer原USER夹具只有目录/读取角色，本专项不继承其他fixture的上传能力。
        cursor.execute(
            """SELECT DISTINCT ur.role_id FROM sys_user_role ur
            JOIN sys_role_menu rm ON rm.role_id=ur.role_id
            WHERE ur.user_id=%s AND rm.menu_id=31052""",
            (peer["native"],),
        )
        previous_upload = [row[0] for row in cursor.fetchall()]
        for identifier in previous_upload:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                (peer["native"], identifier),
            )
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (peer["native"], read_role)
        )
    admin.commit()
    objects = LocalMaterialObjects(Path(object_root))

    def legacy(owner):
        identifier, upload = str(uuid4()), str(uuid4())
        output = BytesIO()
        Image.new("RGB", (12, 12), "orange").save(output, "PNG")
        content = output.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        (objects.directory(tenant, upload) / "original").write_bytes(content)
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id)
                VALUES(%s,%s,%s,%s,'安全scope未扫描PNG',%s,'IMAGE','image/png','READY',%s,%s,%s)""",
                (
                    tenant,
                    identifier,
                    owner["id"],
                    owner["team"],
                    "00000000-0000-4000-8000-000000000001",
                    digest,
                    len(content),
                    upload,
                ),
            )
        admin.commit()
        return identifier

    own, other = legacy(peer), legacy(user)
    try:
        login = fixture_login(client, cache, {"username": peer["name"], "password": password})
        assert login.status_code == 200 and login.json().get("token")
        actor_headers = {"Authorization": "Bearer " + login.json()["token"]}
        actor_caps = client.get("/api/v1/assets/capabilities", headers=actor_headers)
        assert actor_caps.status_code == 200
        csrf = actor_caps.json()["csrf_token"]

        def rescan(identifier):
            return client.post(
                "/api/v1/assets/" + identifier + "/rescan",
                headers=actor_headers
                | {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4()), "If-Match": '"1"'},
                json={"reason": "本人素材安全复核"},
            )

        inspection = client.get("/api/v1/assets/" + own + "/security", headers=actor_headers)
        assert inspection.status_code == 200 and inspection.json()["scan_status"] == "UNVERIFIED"
        assert inspection.json()["rescan_allowed"] is False
        assert inspection.json()["rescan_reason"] == "PERMISSION_REQUIRED"
        assert rescan(own).status_code == 403
        cases.append(MATERIAL_SECURITY_SCOPE_CASES[0])
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (peer["native"], upload_role),
            )
        admin.commit()
        assert (
            client.get("/api/v1/assets/" + other + "/security", headers=actor_headers).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/assets/security",
                headers=actor_headers,
                params={"asset_ids": own + "," + other},
            ).status_code
            == 404
        )
        assert rescan(other).status_code == 404
        cases.append(MATERIAL_SECURITY_SCOPE_CASES[1])
        accepted = rescan(own)
        assert accepted.status_code == 202 and accepted.json()["state"] == "SCANNING"
        assert accepted.json()["ownership"] == {
            "owner_user_id": peer["id"],
            "owner_team_id": peer["team"],
        }
        cases.append(MATERIAL_SECURITY_SCOPE_CASES[2])
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                (peer["native"], upload_role),
            )
            cursor.execute(
                "UPDATE orbit_material_job SET created_at='2000-01-01' "
                "WHERE tenant_id=%s AND asset_id=%s",
                (tenant, own),
            )
        admin.commit()

        def decoded(value):
            return value.decode() if isinstance(value, bytes) else value

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
            try:
                result = await MaterialWorker(
                    async_sessionmaker(engine, expire_on_commit=False),
                    objects,
                    scanner=scanner,
                    runtime_profile_provider=lambda claim: scanner.profile,
                ).run_once(1)
                assert result == [{"asset_id": own, "state": "PROCESSING_FAILED"}]
            finally:
                await engine.dispose()

        asyncio.run(run())
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,error_code,preview_ready FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, own),
            )
            assert cursor.fetchone() == ("PROCESSING_FAILED", "AUTHORIZATION_CHANGED", 0)
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_material_scan_receipt "
                "WHERE tenant_id=%s AND asset_id=%s",
                (tenant, own),
            )
            assert cursor.fetchone()[0] == 0
        admin.commit()
        cases.append(MATERIAL_SECURITY_SCOPE_CASES[3])
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id IN(%s,%s)",
                (peer["native"], read_role, upload_role),
            )
            for identifier in previous_upload:
                cursor.execute(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                    (peer["native"], identifier),
                )
        admin.commit()
