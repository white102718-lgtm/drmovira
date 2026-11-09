"""标签分类真实多身份计数/游标专项；只使用主线UUID库与现有user_fixture。"""

import re
from uuid import uuid4

from fixture_login import fixture_login

MATERIAL_TAXONOMY_SCOPE_CASES = [
    "pythonMaterialTaxonomyNonzeroCountsFollowOwnAndExplicitManagedScope",
    "pythonMaterialTaxonomyCountExcludesArchivedAndForeignTenantAssets",
    "pythonMaterialTaxonomyTagsOnlyActorSeesUnknownCountWithoutAssetRead",
    "pythonMaterialTaxonomyCursorCannotBeReusedByAnotherActor",
    "pythonMaterialTaxonomyTwentyOneEntitiesUseStrictKeysetWithoutDuplicates",
    "pythonMaterialTaxonomyFilterChangeRejectsPreviouslySignedCursor",
    "pythonMaterialTaxonomyAssetReadRevocationImmediatelyMakesCountUnknown",
]


def run_material_taxonomy_scope_checks(client, admin, headers, fixture, password, cache, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        assert admin.host in {"127.0.0.1", "localhost"} and admin.port == 13306
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
            (tenant,),
        )
        foreign = cursor.fetchone()
        assert foreign, "真实跨租户计数矩阵需要主线user_fixture的异租户记录"
    manager, user, unmanaged, peer = fixture["users"][:4]
    prefix = "标签范围" + uuid4().hex[:8]

    def create_role(name, permissions):
        capabilities = client.get("/api/v1/roles/capabilities", headers=headers)
        assert capabilities.status_code == 200
        result = client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": capabilities.json()["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"name": name, "menu_codes": ["assets"], "permission_codes": permissions},
        )
        assert result.status_code == 201
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE id=%s AND tenant_id=%s",
                (result.json()["id"], tenant),
            )
            return cursor.fetchone()[0]

    tags_role = create_role(prefix + "标签读", ["tags.read"])
    assets_role = create_role(prefix + "素材读", ["assets.read"])
    with admin.cursor() as cursor:
        for actor in (manager, user, peer):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], tags_role),
            )
        for actor in (manager, user):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], assets_role),
            )
    admin.commit()

    def login(actor):
        result = fixture_login(client, cache, {"username": actor["name"], "password": password})
        assert result.status_code == 200 and result.json().get("token")
        return {"Authorization": "Bearer " + result.json()["token"]}

    manager_headers, user_headers, peer_headers = login(manager), login(user), login(peer)
    caps = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps.status_code == 200
    csrf = caps.json()["csrf_token"]
    tags = []
    for index in range(21):
        result = client.post(
            "/api/v1/tags",
            headers=headers | {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json={"name": prefix + f"{index:02d}", "group": "范围专项"},
        )
        assert result.status_code == 201
        tags.append(result.json())
    tag = tags[0]
    # 明确元数据计数夹具：INITIATED无文件/无任务，不能把它们称为上传或处理成功。
    with admin.cursor() as cursor:
        for actor in (manager, user, unmanaged, peer):
            identifier = str(uuid4())
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id)
                VALUES(%s,%s,%s,%s,%s,%s,'IMAGE','image/png','INITIATED',%s,1,%s)""",
                (
                    tenant,
                    identifier,
                    actor["id"],
                    actor["team"],
                    prefix,
                    caps.json()["default_category_id"],
                    uuid4().hex * 2,
                    str(uuid4()),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_material_asset_tag(tenant_id,asset_id,tag_id) VALUES(%s,%s,%s)",
                (tenant, identifier, tag["id"]),
            )
        archived = str(uuid4())
        cursor.execute(
            """INSERT INTO orbit_material_asset
            (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
             sha256,byte_size,object_upload_id,archived_at)
            VALUES(%s,%s,%s,%s,%s,%s,'IMAGE','image/png','ARCHIVED',%s,1,%s,UTC_TIMESTAMP(3))""",
            (
                tenant,
                archived,
                user["id"],
                user["team"],
                prefix,
                caps.json()["default_category_id"],
                uuid4().hex * 2,
                str(uuid4()),
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_material_asset_tag(tenant_id,asset_id,tag_id) VALUES(%s,%s,%s)",
            (tenant, archived, tag["id"]),
        )
        foreign_tenant, foreign_owner, foreign_team = foreign
        cursor.execute(
            "INSERT IGNORE INTO orbit_material_taxonomy(tenant_id,id,kind,name,is_system) "
            "VALUES(%s,%s,'CATEGORY','未分类',1)",
            (foreign_tenant, caps.json()["default_category_id"]),
        )
        foreign_asset = str(uuid4())
        cursor.execute(
            "INSERT INTO orbit_material_taxonomy(tenant_id,id,kind,name) VALUES(%s,%s,'TAG',%s)",
            (foreign_tenant, tag["id"], prefix),
        )
        cursor.execute(
            """INSERT INTO orbit_material_asset
            (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
             sha256,byte_size,object_upload_id)
            VALUES(%s,%s,%s,%s,%s,%s,'IMAGE','image/png','INITIATED',%s,1,%s)""",
            (
                foreign_tenant,
                foreign_asset,
                foreign_owner,
                foreign_team,
                prefix,
                caps.json()["default_category_id"],
                uuid4().hex * 2,
                str(uuid4()),
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_material_asset_tag(tenant_id,asset_id,tag_id) VALUES(%s,%s,%s)",
            (foreign_tenant, foreign_asset, tag["id"]),
        )
        cursor.execute(
            "UPDATE orbit_material_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )
    admin.commit()

    def count(identity):
        result = client.get("/api/v1/tags/" + tag["id"], headers=identity)
        assert result.status_code == 200
        return result.json()["visible_asset_count"]

    assert type(count(user_headers)) is int and count(user_headers) == 1
    assert count(manager_headers) == 3
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[0])
    assert count(headers) == 4
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[1])
    assert count(peer_headers) is None
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[2])
    query = {"q": prefix, "page_size": 20, "status": "ENABLED"}
    first = client.get("/api/v1/tags", headers=user_headers, params=query)
    assert first.status_code == 200
    first = first.json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    replay = client.get(
        "/api/v1/tags", headers=manager_headers, params=query | {"cursor": first["next_cursor"]}
    )
    assert replay.status_code == 409 and replay.json()["code"] == "CURSOR_STALE"
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[3])
    second = client.get(
        "/api/v1/tags", headers=user_headers, params=query | {"cursor": first["next_cursor"]}
    )
    assert second.status_code == 200
    second = second.json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert ids == sorted(ids) and len(set(ids)) == 21 and set(ids) == {item["id"] for item in tags}
    assert first["data_as_of"] == second["data_as_of"]
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[4])
    changed = client.get(
        "/api/v1/tags",
        headers=user_headers,
        params=query | {"q": prefix + "0", "cursor": first["next_cursor"]},
    )
    assert changed.status_code == 409 and changed.json()["code"] == "CURSOR_STALE"
    cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[5])
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                (user["native"], assets_role),
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
        assert count(user_headers) is None
        cases.append(MATERIAL_TAXONOMY_SCOPE_CASES[6])
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (user["native"], assets_role),
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
