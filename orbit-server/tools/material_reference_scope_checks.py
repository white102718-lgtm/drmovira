"""引用双方真实授权交集专项；使用既有user_fixture，非HTTP分配或杀毒证明。"""

import asyncio
import re
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_REFERENCE_SCOPE_CASES = [
    "pythonMaterialReferenceExplicitManagerAndTargetOwnerIntersection",
    "pythonMaterialReferenceSameTeamUserCannotReadAnotherOwnersAsset",
    "pythonMaterialReferenceTargetOwnerCannotBorrowCallersAdminScope",
    "pythonMaterialReferenceActorAssetReadRevocationRejectsFrozenContext",
    "pythonMaterialReferenceTargetAssetReadRevocationRejectsFrozenContext",
]


def run_material_reference_scope_checks(client, admin, database, headers, fixture, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("素材交集专项只能使用主线当前本机UUID库")
    from orbit_api.authorization import require_business_access
    from orbit_api.errors import OrbitError
    from orbit_api.material_references import require_allocation_assets

    manager, user, _, peer = fixture["users"][:4]
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    capabilities = client.get("/api/v1/roles/capabilities", headers=headers)
    assert capabilities.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {"X-CSRF-Token": capabilities.json()["csrf_token"], "Idempotency-Key": str(uuid4())},
        json={
            "name": "内部素材交集" + uuid4().hex[:8],
            "menu_codes": ["assets"],
            "permission_codes": ["assets.read"],
        },
    )
    assert role.status_code == 201
    asset = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        native_role = cursor.fetchone()[0]
        for actor in (manager, user, peer):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], native_role),
            )
        cursor.execute(
            """INSERT INTO orbit_material_asset
            (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
            sha256,byte_size,object_upload_id)
            VALUES(%s,%s,%s,%s,'双方交集元数据夹具',%s,'IMAGE','image/png','READY',%s,100,%s)""",
            (
                tenant,
                asset,
                user["id"],
                user["team"],
                "00000000-0000-4000-8000-000000000001",
                "a" * 64,
                str(uuid4()),
            ),
        )
    admin.commit()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def revoke(actor):
        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT ur.role_id FROM sys_user_role ur
                JOIN sys_role_menu rm ON rm.role_id=ur.role_id
                WHERE ur.user_id=%s AND rm.menu_id=31051""",
                (actor["native"],),
            )
            roles = [row[0] for row in cursor.fetchall()]
            assert roles
            for identifier in roles:
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor["native"], identifier),
                )
        admin.commit()
        return roles

    def restore(actor, roles):
        with admin.cursor() as cursor:
            for identifier in roles:
                cursor.execute(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                    (actor["native"], identifier),
                )
        admin.commit()

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
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def ctx(actor):
            async with sessions() as session, session.begin():
                return await require_business_access(session, actor, "assets", "assets.read")

        async def fetch(context, target, expected=None):
            async with sessions() as session, session.begin():
                try:
                    result = await require_allocation_assets(
                        session, context, target["id"], target["team"], [asset]
                    )
                except OrbitError as error:
                    assert expected == error.status, (expected, error.status, error.code)
                    return
                assert expected is None
                assert list(result) == [asset]

        try:
            manager_ctx, user_ctx, peer_ctx, root_ctx = [
                await ctx(actor) for actor in (manager["native"], user["native"], peer["native"], 1)
            ]
            await fetch(manager_ctx, user)
            await fetch(user_ctx, user)
            cases.append(MATERIAL_REFERENCE_SCOPE_CASES[0])
            await fetch(peer_ctx, user, 404)
            cases.append(MATERIAL_REFERENCE_SCOPE_CASES[1])
            # root可读但目标peer不能借管理员范围读取user素材。
            await fetch(root_ctx, peer, 404)
            cases.append(MATERIAL_REFERENCE_SCOPE_CASES[2])
            removed = revoke(manager)
            try:
                await fetch(manager_ctx, user, 403)
            finally:
                restore(manager, removed)
            cases.append(MATERIAL_REFERENCE_SCOPE_CASES[3])
            removed = revoke(user)
            try:
                await fetch(root_ctx, user, 404)
            finally:
                restore(user, removed)
            cases.append(MATERIAL_REFERENCE_SCOPE_CASES[4])
        finally:
            await engine.dispose()

    asyncio.run(run())
