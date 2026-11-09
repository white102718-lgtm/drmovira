"""真实Python/HTTP/MySQL引用资料与渠道专项，由唯一隔离运行器排队调用。"""

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

REFERENCE_CHANNEL_CASES = [
    "pythonReferencePreviewRowIssuesAndNoCatalogMutation",
    "pythonReferenceAtomicCommitReplayAndSourceIdentity",
    "pythonReferenceProductAgentVisibilityAndCandidateSelection",
    "pythonReferenceConcurrentCatalogRevisionHasOneCommit",
    "pythonReferenceExpiryAndCurrentOwnerRevalidation",
    "pythonReferenceAuditFailureRollsBackWholeBatch",
    "pythonChannelCreateAllFieldsReplayUniqueAndHttps",
    "pythonChannelEditCasHistoricalBindingAndReferences",
    "pythonChannelAssignmentAndArchivePreserveHistory",
    "pythonChannelAuditFailureRollsBackVersionAndIdempotency",
    "pythonReferenceAndChannelKeysetScopeAndWatermark",
    "pythonReferenceChannelCurrentPermissionRevocation",
    "pythonChannelReactivationRechecksAvailabilityAndProductAgent",
    "pythonChannelOwnKeysetWatermarkAndBatchDisplayLabels",
    "pythonReferenceChannelStructureTypesUnknownFieldsAndJsonPointers",
    "pythonReferenceRowValueIssuesRemainRejectedAndAtomic",
]


def run_reference_channel_checks(client, admin, headers, user_fixture, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        database = cursor.fetchone()[0]
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database), "只允许专属临时数据库"
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    caps = client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers)
    assert caps.status_code == 200, "引用目录权限或迁移未接通"
    csrf = caps.json()["csrf_token"]
    write = headers | {"X-CSRF-Token": csrf}

    def head(key=None, revision=None):
        return (
            write
            | {"Idempotency-Key": key or str(uuid.uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision else {})
        )

    def item(kind="BUSINESS_AGENT", **changes):
        identifier = str(uuid.uuid4())
        return {
            "kind": kind,
            "id": identifier,
            "name": "引用夹具" + identifier[-6:],
            "availability": "AVAILABLE",
            "owner_team_id": team,
            "data_owner_user_ids": [owner],
            "source_key": "fixture-" + identifier,
            **changes,
        }

    def preview(rows, key=None):
        current = client.get(
            "/api/v1/reference-catalog-imports/capabilities", headers=headers
        ).json()
        value = {
            "kind": rows[0]["kind"],
            "source": "隔离HTTP验收",
            "reason": "验证原子导入",
            "base_catalog_revision": current["catalog_revision"],
            "items": rows,
        }
        response = client.post("/api/v1/reference-catalog-imports", headers=head(key), json=value)
        assert response.status_code == 201, "引用资料预检HTTP失败"
        return response.json(), value

    def commit(value, key=None):
        return client.post(
            f"/api/v1/reference-catalog-imports/{value['id']}/commit",
            headers=head(key, value["revision"]),
        )

    agent = item()
    rejected, _ = preview(
        [agent, agent, item(name=""), item(data_owner_user_ids=[str(uuid.uuid4())])]
    )
    assert rejected["state"] == "REJECTED" and {issue["row"] for issue in rejected["issues"]} == {
        1,
        2,
        3,
    }
    assert commit(rejected).status_code == 409
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_reference_record WHERE tenant_id=%s AND id=%s",
            (tenant, agent["id"]),
        )
        assert cursor.fetchone()[0] == 0
    assert (
        client.post(
            "/api/v1/reference-catalog-imports", headers=head(), json={"tenant_id": tenant}
        ).status_code
        == 400
    )
    cases.append(REFERENCE_CHANNEL_CASES[0])

    valid, input_value = preview([agent])
    assert valid["state"] == "VALIDATED" and valid["created_count"] == 1
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_record WHERE id=%s", (agent["id"],))
        assert cursor.fetchone()[0] == 0
    key = str(uuid.uuid4())
    committed = commit(valid, key)
    assert committed.status_code == 200 and committed.json()["state"] == "COMMITTED"
    assert commit(valid, key).json() == committed.json()
    assert commit(valid).status_code == 409
    conflict, _ = preview([item(source_key=agent["source_key"])])
    assert conflict["state"] == "REJECTED" and conflict["issues"][0]["code"] == "SOURCE_CONFLICT"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_reference_event WHERE resource_id=%s", (valid["id"],)
        )
        assert cursor.fetchone()[0] == 1
    cases.append(REFERENCE_CHANNEL_CASES[1])

    product = item("PRODUCT", allowed_agent_ids=[agent["id"]])
    product_preview, _ = preview([product])
    assert product_preview["state"] == "VALIDATED"
    assert commit(product_preview).status_code == 200
    candidates = client.get(
        "/api/v1/reference-catalogs/BUSINESS_AGENT",
        params={"product_id": product["id"]},
        headers=headers,
    )
    assert candidates.status_code == 200 and [
        row["value"]["id"] for row in candidates.json()["items"]
    ] == [agent["id"]]
    assert (
        client.get("/api/v1/reference-catalogs/BUSINESS_AGENT", headers=headers).status_code == 422
    )
    assert (
        client.get(
            "/api/v1/reference-catalogs/BUSINESS_AGENT",
            params={"product_id": str(uuid.uuid4())},
            headers=headers,
        ).status_code
        == 404
    )
    invalid, _ = preview([item("PRODUCT", allowed_agent_ids=[str(uuid.uuid4())])])
    assert invalid["state"] == "REJECTED"
    cases.append(REFERENCE_CHANNEL_CASES[2])

    first, _ = preview([item("VENDOR")])
    second, _ = preview([item("VENDOR")])
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [first, second]))
    assert sorted(response.status_code for response in outcomes) == [200, 409]
    cases.append(REFERENCE_CHANNEL_CASES[3])

    expired, _ = preview([item("VENDOR")])
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_reference_import SET expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
            "WHERE id=%s",
            (expired["id"],),
        )
    assert commit(expired).status_code == 410
    assert (
        client.get(f"/api/v1/reference-catalog-imports/{expired['id']}", headers=headers).json()[
            "state"
        ]
        == "EXPIRED"
    )
    # 新预览依赖总代有效状态；在不变目录水位下模拟资料失效，提交仍必须逐行复验。
    revalidate, _ = preview([item("PRODUCT", allowed_agent_ids=[agent["id"]])])
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT value_json FROM orbit_reference_record WHERE tenant_id=%s AND id=%s",
            (tenant, agent["id"]),
        )
        original_json = cursor.fetchone()[0]
        changed = json.loads(original_json)
        changed["availability"] = "UNAVAILABLE"
        cursor.execute(
            "UPDATE orbit_reference_record SET availability='UNAVAILABLE',value_json=%s "
            "WHERE tenant_id=%s AND id=%s",
            (json.dumps(changed), tenant, agent["id"]),
        )
    try:
        assert commit(revalidate).status_code == 422
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_reference_record SET availability='AVAILABLE',value_json=%s "
                "WHERE tenant_id=%s AND id=%s",
                (original_json, tenant, agent["id"]),
            )
    cases.append(REFERENCE_CHANNEL_CASES[4])

    atomic_rows = [item("VENDOR"), item("VENDOR")]
    atomic, _ = preview(atomic_rows)
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER fixture_reference_failure BEFORE INSERT ON orbit_reference_event "
            + "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
        )
    try:
        assert commit(atomic).status_code == 503
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_reference_record WHERE tenant_id=%s AND id IN (%s,%s)",
                (tenant, atomic_rows[0]["id"], atomic_rows[1]["id"]),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT state,revision FROM orbit_reference_import WHERE id=%s", (atomic["id"],)
            )
            assert cursor.fetchone() == ("VALIDATED", 1)
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_reference_failure")
    assert commit(atomic).status_code == 200
    cases.append(REFERENCE_CHANNEL_CASES[5])

    value = {
        "ownership": {"owner_team_id": team, "data_owner_user_ids": [owner]},
        "code": "CH_" + uuid.uuid4().hex,
        "name": "渠道全部字段",
        "product_id": product["id"],
        "agent_id": agent["id"],
        "type": "WEBSITE",
        "media": "META",
        "url": "https://example.com/landing?existing=1",
        "status": "ENABLED",
    }
    key = str(uuid.uuid4())
    response = client.post("/api/v1/channels", headers=head(key), json=value)
    assert response.status_code == 201, "渠道真实创建失败"
    channel = response.json()
    path = "/api/v1/channels/" + channel["id"]
    assert {key: channel[key] for key in value} == value and channel["revision"] == 1
    assert client.post("/api/v1/channels", headers=head(key), json=value).json() == channel
    assert client.post("/api/v1/channels", headers=head(), json=value).status_code == 409
    assert (
        client.post(
            "/api/v1/channels",
            headers=head(),
            json=value | {"code": uuid.uuid4().hex, "url": "http://example.com"},
        ).status_code
        == 422
    )
    assert client.get(path, headers=headers).json() == channel
    cases.append(REFERENCE_CHANNEL_CASES[6])

    updated = client.put(path, headers=head(revision=1), json=value | {"name": "编辑后名称"})
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert client.put(path, headers=head(revision=1), json=value).status_code == 409
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_channel SET product_locked=1 WHERE tenant_id=%s AND id=%s",
            (tenant, channel["id"]),
        )
    bound = client.put(
        path, headers=head(revision=2), json=value | {"product_id": str(uuid.uuid4())}
    )
    assert bound.status_code == 422 and bound.json()["code"] == "PRODUCT_BOUND"
    assert client.get(path + "/edit-context", headers=headers).json()["product_locked"] is True
    assert (
        client.put(
            path, headers=head(revision=2), json=value | {"agent_id": str(uuid.uuid4())}
        ).status_code
        == 422
    )
    cases.append(REFERENCE_CHANNEL_CASES[7])

    assigned = client.put(
        path + "/owners",
        headers=head(revision=2),
        json={"ownership": value["ownership"], "reason": "确认当前归属"},
    )
    assert assigned.status_code == 200 and assigned.json()["revision"] == 3
    archive_key = str(uuid.uuid4())
    archived = client.post(
        path + "/archive", headers=head(archive_key, 3), json={"reason": "停止新增投放"}
    )
    assert archived.status_code == 200 and archived.json()["status"] == "DISABLED"
    assert archived.json()["url"] == value["url"] and archived.json()["product_id"] == product["id"]
    assert (
        client.post(
            path + "/archive", headers=head(archive_key, 3), json={"reason": "停止新增投放"}
        ).json()
        == archived.json()
    )
    assert (
        client.post(
            path + "/archive", headers=head(revision=4), json={"reason": "重复停用"}
        ).status_code
        == 409
    )
    cases.append(REFERENCE_CHANNEL_CASES[8])

    failure_key = str(uuid.uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER fixture_channel_failure BEFORE INSERT ON orbit_reference_event "
            + "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
        )
    try:
        failed = client.put(
            path,
            headers=head(failure_key, 4),
            json=value | {"name": "必须回滚", "status": "DISABLED"},
        )
        assert failed.status_code == 503 and "fixture rejection" not in failed.text
        assert client.get(path, headers=headers).json() == archived.json()
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_reference_idempotency WHERE request_key=%s",
                (failure_key,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_channel_failure")
    cases.append(REFERENCE_CHANNEL_CASES[9])

    page_rows = [item("VENDOR", name=f"分页户商{index}") for index in range(21)]
    page_preview, _ = preview(page_rows)
    assert commit(page_preview).status_code == 200
    first_page = client.get(
        "/api/v1/reference-catalogs/VENDOR?page_size=20", headers=headers
    ).json()
    assert len(first_page["items"]) == 20 and first_page["next_cursor"]
    page_two = client.get(
        "/api/v1/reference-catalogs/VENDOR",
        params={"page_size": 20, "cursor": first_page["next_cursor"]},
        headers=headers,
    ).json()
    assert not {row["value"]["id"] for row in first_page["items"]} & {
        row["value"]["id"] for row in page_two["items"]
    }
    assert (
        client.get(
            "/api/v1/reference-catalogs/PRODUCT",
            params={"page_size": 20, "cursor": first_page["next_cursor"]},
            headers=headers,
        ).status_code
        == 409
    )
    newer, _ = preview([item("VENDOR")])
    assert commit(newer).status_code == 200
    assert (
        client.get(
            "/api/v1/reference-catalogs/VENDOR",
            params={"page_size": 20, "cursor": first_page["next_cursor"]},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.get("/api/v1/channels?product_id=" + product["id"], headers=headers).json()[
        "items"
    ]
    assert client.get("/api/v1/channels?q=a&q=b", headers=headers).status_code == 400
    assert (
        client.get(
            "/api/v1/channels", headers=headers | {"X-Target-Tenant": str(uuid.uuid4())}
        ).status_code
        == 403
    )
    cases.append(REFERENCE_CHANNEL_CASES[10])

    # 原管理员权限也必须实时来自菜单；短暂关闭渠道read动作后同Token立即失败。
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31071")
        old_status = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31071")
    try:
        assert client.get(path, headers=headers).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status=%s WHERE menu_id=31071", (old_status,))
    assert client.get(path, headers=headers).status_code == 200
    cases.append(REFERENCE_CHANNEL_CASES[11])
    unavailable, _ = preview([product | {"availability": "UNAVAILABLE"}])
    assert commit(unavailable).status_code == 200
    assert client.put(path, headers=head(revision=4), json=value).status_code == 422
    assert client.get(path, headers=headers).json()["status"] == "DISABLED"
    alternate_agent = item()
    ready, _ = preview([alternate_agent])
    assert commit(ready).status_code == 200
    changed_product = product | {"allowed_agent_ids": [alternate_agent["id"]]}
    ready, _ = preview([changed_product])
    assert commit(ready).status_code == 200
    assert client.put(path, headers=head(revision=4), json=value).status_code == 422
    ready, _ = preview([product])
    assert commit(ready).status_code == 200
    enabled = client.put(path, headers=head(revision=4), json=value)
    assert enabled.status_code == 200 and enabled.json()["status"] == "ENABLED"
    url_value = value | {
        "code": uuid.uuid4().hex,
        "name": "",
        "url": "https://example.com:8443/landing?original=1#/welcome",
    }
    url_response = client.post("/api/v1/channels", headers=head(), json=url_value)
    assert url_response.status_code == 201 and url_response.json()["url"] == url_value["url"]
    assert url_response.json()["name"] == ""
    cases.append(REFERENCE_CHANNEL_CASES[12])

    prefix = "渠道键集" + uuid.uuid4().hex[:8]
    for index in range(21):
        response = client.post(
            "/api/v1/channels",
            headers=head(),
            json=value | {"code": uuid.uuid4().hex, "name": f"{prefix}-{index}"},
        )
        assert response.status_code == 201
    query = {"q": prefix, "page_size": 20}
    first_channels = client.get("/api/v1/channels", headers=headers, params=query).json()
    assert len(first_channels["items"]) == 20 and first_channels["next_cursor"]
    second_channels = client.get(
        "/api/v1/channels",
        headers=headers,
        params=query | {"cursor": first_channels["next_cursor"]},
    ).json()
    assert len(second_channels["items"]) == 1 and second_channels["next_cursor"] is None
    assert first_channels["data_as_of"] == second_channels["data_as_of"]
    identifiers = [row["id"] for row in first_channels["items"] + second_channels["items"]]
    assert len(set(identifiers)) == 21
    labels = client.get(
        "/api/v1/channels/display-labels",
        headers=headers,
        params={"ids": ",".join(identifiers + [str(uuid.uuid4())])},
    )
    assert labels.status_code == 200 and len(labels.json()["items"]) == 21
    for label in labels.json()["items"]:
        assert set(label) == {"id", "product_name", "agent_name", "team_name", "owners"}
        assert label["product_name"] == product["name"] and label["agent_name"] == agent["name"]
        assert [entry["id"] for entry in label["owners"]] == [owner]
    assert (
        client.get(
            "/api/v1/channels/display-labels",
            headers=headers,
            params={"ids": identifiers[0] + "," + identifiers[0]},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/channels",
            headers=headers,
            params=query | {"q": "另一筛选", "cursor": first_channels["next_cursor"]},
        ).status_code
        == 409
    )
    changed = first_channels["items"][0]
    assert (
        client.put(
            "/api/v1/channels/" + changed["id"],
            headers=head(revision=1),
            json=value | {"code": changed["code"], "name": prefix + "变更"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/channels",
            headers=headers,
            params=query | {"cursor": first_channels["next_cursor"]},
        ).status_code
        == 409
    )
    cases.append(REFERENCE_CHANNEL_CASES[13])
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_import WHERE tenant_id=%s", (tenant,))
        before_previews = cursor.fetchone()[0]
    channel_errors = [
        (value | {"name": 42}, 400, "INVALID_STRUCTURE", "/name"),
        (value | {"ownership": []}, 400, "INVALID_STRUCTURE", "/ownership"),
        (
            value | {"ownership": value["ownership"] | {"owner_team_id": 1}},
            400,
            "INVALID_STRUCTURE",
            "/ownership/owner_team_id",
        ),
        (
            value | {"ownership": value["ownership"] | {"data_owner_user_ids": "wrong"}},
            400,
            "INVALID_STRUCTURE",
            "/ownership/data_owner_user_ids",
        ),
        (
            value | {"ownership": value["ownership"] | {"data_owner_user_ids": [1]}},
            400,
            "INVALID_STRUCTURE",
            "/ownership/data_owner_user_ids/0",
        ),
        (value | {"bad/~field": 1}, 400, "UNKNOWN_FIELD", "/bad~1~0field"),
        (
            value | {"ownership": value["ownership"] | {"bad/~field": 1}},
            400,
            "UNKNOWN_FIELD",
            "/ownership/bad~1~0field",
        ),
        (value | {"code": "bad code"}, 422, "FIELD_INVALID", "/code"),
        (value | {"product_id": "not-uuid"}, 422, "FIELD_INVALID", "/product_id"),
    ]
    for invalid, status, code, pointer in channel_errors:
        error = client.post("/api/v1/channels", headers=head(), json=invalid)
        assert error.status_code == status and error.json()["code"] == code
        assert error.json()["field_errors"][0]["path"] == pointer
        assert set(error.json()) == {"code", "message", "request_id", "retryable", "field_errors"}
    current = client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers).json()
    clean = {
        "kind": "BUSINESS_AGENT",
        "source": "结构断言",
        "reason": "错误不建预览",
        "base_catalog_revision": current["catalog_revision"],
        "items": [item()],
    }
    missing_name = item()
    del missing_name["name"]
    reference_errors = [
        (clean | {"source": 42}, 400, "INVALID_STRUCTURE", "/source"),
        (clean | {"kind": 42}, 400, "INVALID_STRUCTURE", "/kind"),
        (
            clean | {"base_catalog_revision": True},
            400,
            "INVALID_STRUCTURE",
            "/base_catalog_revision",
        ),
        (clean | {"items": {}}, 400, "INVALID_STRUCTURE", "/items"),
        (clean | {"items": ["not-object"]}, 400, "INVALID_STRUCTURE", "/items/0"),
        (clean | {"items": [item(name=42)]}, 400, "INVALID_STRUCTURE", "/items/0/name"),
        (clean | {"items": [missing_name]}, 400, "INVALID_STRUCTURE", "/items/0/name"),
        (
            clean | {"items": [item(data_owner_user_ids=[42])]},
            400,
            "INVALID_STRUCTURE",
            "/items/0/data_owner_user_ids/0",
        ),
        (
            clean | {"items": [item(**{"bad/~field": 1})]},
            400,
            "UNKNOWN_FIELD",
            "/items/0/bad~1~0field",
        ),
        (clean | {"items": []}, 422, "FIELD_INVALID", "/items"),
        (clean | {"items": clean["items"] * 501}, 422, "FIELD_INVALID", "/items"),
        (clean | {"base_catalog_revision": -1}, 422, "FIELD_INVALID", "/base_catalog_revision"),
    ]
    for invalid, status, code, pointer in reference_errors:
        error = client.post("/api/v1/reference-catalog-imports", headers=head(), json=invalid)
        assert error.status_code == status and error.json()["code"] == code
        assert error.json()["field_errors"][0]["path"] == pointer
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_import WHERE tenant_id=%s", (tenant,))
        assert cursor.fetchone()[0] == before_previews
    cases.append(REFERENCE_CHANNEL_CASES[14])

    seed = item()
    business_rows = [
        seed,
        seed,
        item(name=""),
        item(availability="INVALID"),
        item(data_owner_user_ids=[str(uuid.uuid4())]),
        item(source_key=""),
    ]
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_record WHERE tenant_id=%s", (tenant,))
        before_records = cursor.fetchone()[0]
    errors, _ = preview(business_rows)
    assert errors["state"] == "REJECTED" and {issue["row"] for issue in errors["issues"]} == {
        1,
        2,
        3,
        4,
        5,
    }
    assert all(set(issue) == {"row", "code", "message"} for issue in errors["issues"])
    assert commit(errors).status_code == 409
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_record WHERE tenant_id=%s", (tenant,))
        assert cursor.fetchone()[0] == before_records
        cursor.execute("SELECT COUNT(*) FROM orbit_reference_import WHERE tenant_id=%s", (tenant,))
        assert cursor.fetchone()[0] == before_previews + 1
    cases.append(REFERENCE_CHANNEL_CASES[15])
    return {"product_id": product["id"], "agent_id": agent["id"], "channel_id": channel["id"]}
