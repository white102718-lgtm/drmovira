"""从原OpenAPI读取渠道合同的真实HTTP专项；不修改受测产品或既有工具。"""

import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from channel_scope_matrix_checks import snapshot

CHANNEL_FIELD_CONTRACT_CASES = [
    "pythonChannelOriginalSchemaStrictAcrossEveryLifecycleResponse",
    "pythonChannelOriginalPositiveCodeNameUrlBoundaries",
    "pythonChannelOriginalEveryTypeMediaStatusCombination",
    "pythonChannelOriginalInvalidFieldBoundariesAreAtomic",
    "pythonChannelOriginalOwnershipAndReasonBoundariesAreAtomic",
    "pythonChannelOriginalLiteralSearchProductStatusDatesAndPageSizes",
]


def assert_original_schema(value, schema, schemas):
    """只支持本次Channel引用树实际使用的断言，未知合同关键字必须失败而非忽略。"""
    supported = {
        "$ref",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "enum",
        "anyOf",
        "description",
    }
    assert not schema.keys() - supported, "原合同出现未支持约束，禁止静默跳过"
    if "$ref" in schema:
        assert schema["$ref"].startswith("#/components/schemas/")
        return assert_original_schema(value, schemas[schema["$ref"].split("/")[-1]], schemas)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                assert_original_schema(value, alternative, schemas)
                return
            except AssertionError:
                continue
        raise AssertionError("返回值不符合原anyOf合同")
    expected = schema.get("type")
    assert {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "null": lambda: value is None,
        "boolean": lambda: type(value) is bool,
    }[expected]()
    if "enum" in schema:
        assert value in schema["enum"]
    if expected == "object":
        assert set(schema.get("required", [])) <= value.keys(), "缺少原响应必填字段"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert not value.keys() - properties.keys(), "返回了原schema未允许的额外字段"
        for key in value.keys() & properties.keys():
            assert_original_schema(value[key], properties[key], schemas)
    if expected in {"array", "string"}:
        assert len(value) >= schema.get("minItems" if expected == "array" else "minLength", 0)
        maximum = schema.get("maxItems" if expected == "array" else "maxLength")
        assert maximum is None or len(value) <= maximum
    if expected == "array":
        for item in value:
            assert_original_schema(item, schema["items"], schemas)
    if expected == "integer":
        assert schema.get("minimum", value) <= value <= schema.get("maximum", value)
    if expected == "string":
        if "pattern" in schema:
            assert re.search(schema["pattern"], value)
        if schema.get("format") == "uuid":
            uuid.UUID(value)
        elif schema.get("format") == "date-time":
            assert datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
        elif schema.get("format") == "uri":
            assert urlsplit(value).scheme and urlsplit(value).netloc


def run_channel_field_contract_checks(
    client, admin, headers, reference_fixture, cases, contract_path=None
):
    snapshot(admin)
    contract_path = (
        contract_path
        or Path(__file__).resolve().parents[2]
        / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
    )
    schemas = json.loads(Path(contract_path).read_text(encoding="utf-8"))["components"]["schemas"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT id,team_id FROM orbit_business_user WHERE user_id=1")
        owner, team = cursor.fetchone()
    caps = client.get("/api/v1/channels/capabilities", headers=headers)
    assert caps.status_code == 200
    prefix = "字段合同" + uuid.uuid4().hex[:8]
    base = {
        "ownership": {"owner_team_id": team, "data_owner_user_ids": [owner]},
        "code": "contract_" + uuid.uuid4().hex,
        "name": prefix,
        "product_id": reference_fixture["product_id"],
        "agent_id": reference_fixture["agent_id"],
        "type": "APP",
        "media": "META",
        "url": "https://example.com/landing?x=1#keep",
        "status": "ENABLED",
    }

    def head(revision=None):
        return (
            headers
            | {"X-CSRF-Token": caps.json()["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision is not None else {})
        )

    def check(response, schema="Channel", status=200):
        assert response.status_code == status
        result = response.json()
        assert_original_schema(result, schemas[schema], schemas)
        return result

    def create(**changes):
        body = deepcopy(base) | {"code": uuid.uuid4().hex} | changes
        return check(client.post("/api/v1/channels", headers=head(), json=body), status=201)

    value = create()
    path = "/api/v1/channels/" + value["id"]
    assert check(client.get(path, headers=headers)) == value
    editable = {key: value[key] for key in schemas["ChannelWrite"]["properties"]}
    edited = check(client.put(path, headers=head(1), json=editable | {"name": prefix + "编辑"}))
    assert edited["revision"] == 2
    assigned = check(
        client.put(
            path + "/owners",
            headers=head(2),
            json={"ownership": base["ownership"], "reason": "完整响应合同"},
        )
    )
    assert assigned["revision"] == 3
    archived = check(
        client.post(path + "/archive", headers=head(3), json={"reason": "完整响应合同"})
    )
    assert archived["revision"] == 4 and archived["status"] == "DISABLED"
    check(client.get("/api/v1/channels", headers=headers, params={"q": prefix}), "ChannelPage")
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[0])

    url = "https://example.com/" + "x" * (2048 - len("https://example.com/"))
    boundary = create(code="A" * 64, name="😀" * 100, url=url)
    assert (
        boundary["code"] == "A" * 64 and boundary["name"] == "😀" * 100 and boundary["url"] == url
    )
    assert create(name="")["name"] == ""
    assert create(name="e\u0301" * 100)["name"] == "é" * 100
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[1])

    for channel_type in ("APP", "WEBSITE", "OTHER"):
        for media in ("META", "GOOGLE", "TIKTOK", "OTHER"):
            for status in ("ENABLED", "DISABLED"):
                result = create(type=channel_type, media=media, status=status)
                assert (result["type"], result["media"], result["status"]) == (
                    channel_type,
                    media,
                    status,
                )
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[2])

    invalids = [
        ({"code": ""}, 422),
        ({"code": "A" * 65}, 422),
        ({"code": "汉字"}, 422),
        ({"code": "a b"}, 422),
        ({"code": "a\n"}, 422),
        ({"name": "😀" * 101}, 422),
        ({"name": "a\u200b"}, 422),
        ({"url": url + "x"}, 422),
        ({"url": "http://example.com"}, 422),
        ({"url": "https://user:pass@example.com"}, 422),
        ({"url": "https://127.0.0.1"}, 422),
        ({"url": "https://example.com/%xy"}, 422),
        ({"product_id": "bad"}, 422),
        ({"agent_id": "bad"}, 422),
        ({"type": "INVALID"}, 422),
        ({"media": "INVALID"}, 422),
        ({"status": "INVALID"}, 422),
        ({"name": None}, 400),
        ({"status": True}, 400),
        ({"unexpected": "拒绝"}, 400),
    ]
    for changes, expected in invalids:
        before = snapshot(admin)
        response = client.post("/api/v1/channels", headers=head(), json=deepcopy(base) | changes)
        assert response.status_code == expected
        assert snapshot(admin) == before
    for field in schemas["ChannelWrite"]["required"]:
        missing = deepcopy(base)
        del missing[field]
        before = snapshot(admin)
        assert client.post("/api/v1/channels", headers=head(), json=missing).status_code == 400
        assert snapshot(admin) == before
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[3])

    for ownership, expected in (
        ({}, 400),
        ({"owner_team_id": team, "data_owner_user_ids": []}, 422),
        ({"owner_team_id": team, "data_owner_user_ids": [owner] * 501}, 422),
        ({"owner_team_id": team, "data_owner_user_ids": [owner, owner]}, 422),
        ({"owner_team_id": team, "data_owner_user_ids": [3]}, 400),
    ):
        before = snapshot(admin)
        assert (
            client.put(
                path + "/owners", headers=head(4), json={"ownership": ownership, "reason": "边界"}
            ).status_code
            == expected
        )
        assert snapshot(admin) == before
    for reason in ("", " ", "原" * 1001, "原因\n"):
        before = snapshot(admin)
        assert (
            client.put(
                path + "/owners",
                headers=head(4),
                json={"ownership": base["ownership"], "reason": reason},
            ).status_code
            == 422
        )
        assert snapshot(admin) == before
    accepted = check(
        client.put(
            path + "/owners",
            headers=head(4),
            json={"ownership": base["ownership"], "reason": "原" * 1000},
        )
    )
    assert accepted["revision"] == 5
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[4])

    literal = create(name=prefix + "%_needle")
    create(name=prefix + "XXneedle")
    exact = check(
        client.get("/api/v1/channels", headers=headers, params={"q": "%_needle"}), "ChannelPage"
    )
    assert {row["id"] for row in exact["items"]} == {literal["id"]}
    for size in (20, 50, 100, 200):
        result = check(
            client.get(
                "/api/v1/channels",
                headers=headers,
                params={
                    "q": prefix,
                    "page_size": size,
                    "product_id": base["product_id"],
                    "status": "ENABLED",
                },
            ),
            "ChannelPage",
        )
        assert len(result["items"]) <= size
        assert all(
            row["product_id"] == base["product_id"] and row["status"] == "ENABLED"
            for row in result["items"]
        )
    day = literal["created_at"][:10]
    result = check(
        client.get(
            "/api/v1/channels",
            headers=headers,
            params={"q": "%_needle", "date_from": day, "date_to": day},
        ),
        "ChannelPage",
    )
    assert [row["id"] for row in result["items"]] == [literal["id"]]
    tomorrow = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
    assert not check(
        client.get(
            "/api/v1/channels", headers=headers, params={"q": "%_needle", "date_from": tomorrow}
        ),
        "ChannelPage",
    )["items"]
    for query in (
        {"page_size": 201},
        {"status": "INVALID"},
        {"date_from": "2026-02-30"},
        {"date_from": "2026-02-02", "date_to": "2026-02-01"},
        {"product_id": "bad"},
        {"cursor": ""},
    ):
        assert client.get("/api/v1/channels", headers=headers, params=query).status_code == 422
    cases.append(CHANNEL_FIELD_CONTRACT_CASES[5])
