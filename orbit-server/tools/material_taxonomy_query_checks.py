"""待排队的标签分类原合同查询专项；需要新生产查询能力后才可执行。"""

from uuid import uuid4

MATERIAL_TAXONOMY_QUERY_CASES = [
    "pythonMaterialTagOriginalNameStatePageSizeQueryAndGroupRemain",
    "pythonMaterialCategoryOriginalNameStatePageSizeQueryRemains",
    "pythonMaterialTaxonomyRejectsInvalidAndUnsupportedQueryWithoutIgnoring",
    "pythonMaterialTaxonomyNameCannotBypassUniquenessByChangingGroup",
    "pythonMaterialTaxonomyVisibleAssetCountIsExplicitAndNotPlatformUsage",
]


def run_material_taxonomy_query_checks(client, headers, cases):
    """只使用主线隔离HTTP实例；不启动服务，不写云存储，不以响应模拟替代业务。"""
    prefix = "目录验收" + uuid4().hex[:8]
    caps = client.get("/api/v1/assets/capabilities", headers=headers)
    assert caps.status_code == 200
    csrf = caps.json()["csrf_token"]

    def create(kind, name, group=None):
        value = {"name": name}
        if group is not None:
            value["group"] = group
        return client.post(
            "/api/v1/" + kind,
            headers=headers | {"X-CSRF-Token": csrf, "Idempotency-Key": "taxonomy-" + uuid4().hex},
            json=value,
        )

    tag_ids = []
    for suffix, group in (("甲", "测试甲组"), ("乙", "测试乙组")):
        result = create("tags", prefix + suffix, group)
        assert result.status_code == 201
        tag_ids.append(result.json()["id"])
    category = create("categories", prefix + "分类")
    assert category.status_code == 201
    for path, expected_ids, case in (
        ("tags", set(tag_ids), MATERIAL_TAXONOMY_QUERY_CASES[0]),
        ("categories", {category.json()["id"]}, MATERIAL_TAXONOMY_QUERY_CASES[1]),
    ):
        response = client.get(
            "/api/v1/" + path,
            headers=headers,
            params={"q": prefix, "status": "ENABLED", "page_size": 20},
        )
        assert response.status_code == 200
        body = response.json()
        assert {item["id"] for item in body["items"]} == expected_ids
        assert body["next_cursor"] is None and body["scope_version"] >= 1
        assert body["data_as_of"].endswith("Z")
        if path == "tags":
            assert {item["group"] for item in body["items"]} == {"测试甲组", "测试乙组"}
        disabled = client.get(
            "/api/v1/" + path,
            headers=headers,
            params={"q": prefix, "status": "DISABLED", "page_size": 20},
        )
        assert disabled.status_code == 200 and disabled.json()["items"] == []
        cases.append(case)

    for path in ("tags", "categories"):
        for params in (
            {"status": "NOT_A_TAXONOMY_STATE"},
            {"page_size": 1},
            {"page_size": 201},
            {"q": "字" * 101},
            {"cursor": ""},
            {"cursor": "x" * 2049},
            {"date_from": "not-a-date"},
            {"metric_profile_id": "invalid-uuid"},
        ):
            response = client.get("/api/v1/" + path, headers=headers, params=params)
            assert response.status_code == 422, (path, tuple(params), response.status_code)
        unknown = client.get(
            "/api/v1/" + path, headers=headers, params={"unsupported_field": "must-not-ignore"}
        )
        assert unknown.status_code == 400 and unknown.json()["code"] == "UNKNOWN_FIELD"
    cases.append(MATERIAL_TAXONOMY_QUERY_CASES[2])

    duplicate = create("tags", prefix + "甲", "另一个分组")
    assert duplicate.status_code == 409
    cases.append(MATERIAL_TAXONOMY_QUERY_CASES[3])

    # 本专项未给新目录关联任何素材，真实关联数为0；与广告使用次数含义不同。
    for path, resource_id in (("tags", tag_ids[0]), ("categories", category.json()["id"])):
        response = client.get(f"/api/v1/{path}/{resource_id}", headers=headers)
        assert response.status_code == 200
        count = response.json()["visible_asset_count"]
        assert type(count) is int and count == 0
    cases.append(MATERIAL_TAXONOMY_QUERY_CASES[4])
