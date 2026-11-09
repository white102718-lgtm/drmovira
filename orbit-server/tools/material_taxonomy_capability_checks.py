"""AST-09真实HTTP专项；调用方串行启动隔离库并提供已建立的user_fixture。

不启动数据库、不绕过登录限流；SQL只建立隔离身份/素材元数据夹具和核对副作用。
"""

import re
from uuid import uuid4

from fixture_login import fixture_login

MATERIAL_TAXONOMY_CAPABILITY_CASES = [
    "pythonTaxonomyFourIndependentActionCapabilitiesWithoutAssetsRead",
    "pythonTaxonomyReadOnlyNullCsrfAndUnknownAssetCount",
    "pythonTaxonomyCreateOnlyWritesOriginalTagAndCategoryFields",
    "pythonTaxonomyEditOnlyCasAndSameKeyReplay",
    "pythonTaxonomyArchiveOnlySuccessReplayAfterStateChange",
    "pythonTaxonomyDeniedActionAndCrossSessionCsrfLeaveNoEffects",
    "pythonTaxonomyRevocationRejectsAlreadyCommittedReplay",
    "pythonTaxonomyFixedDefaultCategoryRejectsRenameAndArchive",
    "pythonTaxonomyReferencedCategoryArchiveRollsBackAllEffects",
    "pythonTaxonomyForeignTenantObjectIsNotVisible",
    "pythonTaxonomyStrictCapabilityQueryBoundary",
]


def run_material_taxonomy_capability_checks(
    client, admin, headers, fixture, password, cache, cases
):
    assert admin.host in {"127.0.0.1", "localhost"} and admin.port == 13306
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
            (tenant,),
        )
        foreign = cursor.fetchone()
        assert foreign
    prefix = "tax_actions_" + uuid4().hex[:8]
    team = fixture["users"][1]["team"]

    def checked(response, status=200):
        assert response.status_code == status, (
            response.request.method,
            response.request.url.path,
            response.status_code,
            response.text[:500],
        )
        return response.json()

    def cap(identity, operation):
        return checked(
            client.get(
                "/api/v1/material-taxonomy/capabilities",
                headers=identity,
                params={"operation": operation},
            )
        )

    actors = {}
    for index, action in enumerate(("READ", "CREATE", "EDIT", "ARCHIVE")):
        role_caps = checked(client.get("/api/v1/roles/capabilities", headers=headers))
        role = checked(
            client.post(
                "/api/v1/roles",
                headers=headers
                | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={
                    "name": prefix + action,
                    "menu_codes": ["assets"],
                    "permission_codes": ["tags." + action.lower()],
                },
            ),
            201,
        )
        native, name, identifier = 990780 + index, prefix + action, str(uuid4())
        assert len(name) <= 30, "原生用户账号与昵称均限制30字符"
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
                (tenant, role["id"]),
            )
            native_role = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,"
                "del_flag) SELECT %s,%s,%s,password,'0','0' "
                "FROM sys_user WHERE user_id=1",
                (native, name, name),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,"
                "create_time) VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (native, tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user"
                "(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
                "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
                (tenant, identifier, native, team, name),
            )
        admin.commit()
        token = checked(fixture_login(client, cache, {"username": name, "password": password}))
        identity = {"Authorization": "Bearer " + token["token"]}
        value = cap(identity, action)
        assert set(value) == {"actor_id", "tenant_id", "csrf_token"}
        assert value["actor_id"] == native and value["tenant_id"] == tenant
        assert (value["csrf_token"] is None) == (action == "READ")
        for denied in {"READ", "CREATE", "EDIT", "ARCHIVE"} - {action}:
            checked(
                client.get(
                    "/api/v1/material-taxonomy/capabilities",
                    headers=identity,
                    params={"operation": denied},
                ),
                403,
            )
        checked(client.get("/api/v1/assets/capabilities", headers=identity), 403)
        actors[action] = (identity, value, native, native_role)
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[0])

    def write_headers(action, revision=None, key=None):
        identity, value, _, _ = actors[action]
        result = identity | {
            "X-CSRF-Token": value["csrf_token"],
            "Idempotency-Key": key or str(uuid4()),
        }
        if revision is not None:
            result["If-Match"] = '"' + str(revision) + '"'
        return result

    def effects():
        with admin.cursor() as cursor:
            counts = []
            for table in (
                "orbit_material_taxonomy",
                "orbit_material_idempotency",
                "orbit_material_audit",
                "orbit_material_outbox",
            ):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s", (tenant,))
                counts.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT revision FROM orbit_material_clock WHERE tenant_id=%s", (tenant,)
            )
            counts.append(cursor.fetchone()[0])
            return counts

    tag_body = {"name": prefix + "标签", "group": "原分组信息"}
    tag = checked(client.post("/api/v1/tags", headers=write_headers("CREATE"), json=tag_body), 201)
    category = checked(
        client.post(
            "/api/v1/categories", headers=write_headers("CREATE"), json={"name": prefix + "分类"}
        ),
        201,
    )
    assert tag | tag_body == tag and tag["state"] == category["state"] == "ENABLED"
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[2])
    read = checked(client.get("/api/v1/tags/" + tag["id"], headers=actors["READ"][0]))
    assert read["visible_asset_count"] is None and read["group"] == tag_body["group"]
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[1])

    edit_headers = write_headers("EDIT", tag["revision"])
    edit_body = {"name": tag_body["name"] + "修改", "group": "修改分组"}
    edit = checked(client.put("/api/v1/tags/" + tag["id"], headers=edit_headers, json=edit_body))
    after = effects()
    assert (
        checked(client.put("/api/v1/tags/" + tag["id"], headers=edit_headers, json=edit_body))
        == edit
    )
    assert effects() == after
    checked(
        client.put(
            "/api/v1/tags/" + tag["id"],
            headers=write_headers("EDIT", tag["revision"]),
            json=edit_body,
        ),
        409,
    )
    assert effects() == after
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[3])

    archive_headers = write_headers("ARCHIVE", edit["revision"])
    archive_body = {"reason": "真实专项停用"}
    archive_path = "/api/v1/tags/" + tag["id"] + "/archive"
    archived = checked(client.post(archive_path, headers=archive_headers, json=archive_body))
    assert archived["state"] == "DISABLED"
    after = effects()
    assert (
        checked(client.post(archive_path, headers=archive_headers, json=archive_body)) == archived
    )
    assert effects() == after
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[4])
    checked(client.post("/api/v1/tags", headers=write_headers("EDIT"), json=tag_body), 403)
    stolen = write_headers("CREATE") | {"X-CSRF-Token": actors["EDIT"][1]["csrf_token"]}
    checked(client.post("/api/v1/tags", headers=stolen, json=tag_body), 403)
    assert effects() == after
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[5])
    with admin.cursor() as cursor:
        cursor.execute(
            "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", actors["ARCHIVE"][2:]
        )
    admin.commit()
    checked(client.post(archive_path, headers=archive_headers, json=archive_body), 403)
    checked(
        client.get(
            "/api/v1/material-taxonomy/capabilities",
            headers=actors["ARCHIVE"][0],
            params={"operation": "ARCHIVE"},
        ),
        403,
    )
    assert effects() == after
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[6])

    root_edit = cap(headers, "EDIT")["csrf_token"]
    root_archive = cap(headers, "ARCHIVE")["csrf_token"]

    def root_write(csrf, revision):
        return headers | {
            "X-CSRF-Token": csrf,
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + str(revision) + '"',
        }

    asset_caps = checked(client.get("/api/v1/assets/capabilities", headers=headers))
    default_id = asset_caps["default_category_id"]
    default = checked(client.get("/api/v1/categories/" + default_id, headers=headers))
    before = effects()
    rename = checked(
        client.put(
            "/api/v1/categories/" + default_id,
            headers=root_write(root_edit, default["revision"]),
            json={"name": prefix},
        ),
        409,
    )
    archive = checked(
        client.post(
            "/api/v1/categories/" + default_id + "/archive",
            headers=root_write(root_archive, default["revision"]),
            json=archive_body,
        ),
        409,
    )
    assert rename["code"] == archive["code"] == "SYSTEM_CATEGORY_FIXED"
    assert effects() == before
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[7])
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_material_asset"
            "(tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,"
            "sha256,byte_size,object_upload_id) "
            "VALUES(%s,%s,%s,%s,%s,%s,'IMAGE','image/png','INITIATED',%s,1,%s)",
            (
                tenant,
                str(uuid4()),
                fixture["users"][1]["id"],
                team,
                prefix,
                category["id"],
                uuid4().hex * 2,
                str(uuid4()),
            ),
        )
        foreign_id = str(uuid4())
        cursor.execute(
            "INSERT INTO orbit_material_taxonomy(tenant_id,id,kind,name) VALUES(%s,%s,'TAG',%s)",
            (foreign[0], foreign_id, prefix),
        )
    admin.commit()
    before = effects()
    referenced = checked(
        client.post(
            "/api/v1/categories/" + category["id"] + "/archive",
            headers=root_write(root_archive, category["revision"]),
            json=archive_body,
        ),
        409,
    )
    assert referenced["code"] == "CATEGORY_REFERENCED" and effects() == before
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[8])
    checked(client.get("/api/v1/tags/" + foreign_id, headers=actors["READ"][0]), 404)
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[9])
    for query, status in (
        ("operation=read", 422),
        ("operation=READ&unknown=1", 400),
        ("operation=READ&operation=CREATE", 400),
    ):
        checked(
            client.get("/api/v1/material-taxonomy/capabilities?" + query, headers=headers), status
        )
    cases.append(MATERIAL_TAXONOMY_CAPABILITY_CASES[10])
