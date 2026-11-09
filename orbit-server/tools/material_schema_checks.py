"""从原始OpenAPI读取素材响应字段约束；不以产品自己的类型定义替代合同。"""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

SPEC_PATH = (
    Path(__file__).resolve().parents[2] / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
)
MATERIAL_SCHEMA_CASES = [
    "pythonMaterialOriginalAssetSchemaTypesAndDecimalDuration",
    "pythonMaterialOriginalTagSchemaAndRegisteredVisibleCountExtension",
    "pythonMaterialOriginalCategorySchemaAndRegisteredVisibleCountExtension",
]


def validate_original_schema(value, definition, specification):
    """仅使用本组原schema实际出现的JSON Schema关键字；陌生关键字明确失败。"""
    supported = {
        "$ref",
        "anyOf",
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
        "description",
        "title",
        "default",
    }
    if set(definition) - supported:
        raise NotImplementedError("原素材schema出现新关键字，必须补校验而不是忽略")
    if "$ref" in definition:
        resolved = specification
        for token in definition["$ref"].removeprefix("#/").split("/"):
            resolved = resolved[token]
        validate_original_schema(value, resolved, specification)
        return
    if "anyOf" in definition:
        for option in definition["anyOf"]:
            try:
                validate_original_schema(value, option, specification)
                break
            except (AssertionError, ValueError, TypeError):
                continue
        else:
            raise AssertionError("值不符合原schema任何分支")
        return
    kind = definition.get("type")
    if kind == "null":
        assert value is None
    elif kind == "boolean":
        # MetricProfile等原合同使用布尔值，不能让Python的bool/int继承关系接受0或1。
        assert type(value) is bool
    elif kind == "integer":
        assert type(value) is int
        assert definition.get("minimum", value) <= value <= definition.get("maximum", value)
    elif kind == "string":
        assert isinstance(value, str)
        assert (
            definition.get("minLength", 0) <= len(value) <= definition.get("maxLength", len(value))
        )
        if "pattern" in definition:
            assert re.search(definition["pattern"], value)
        format = definition.get("format")
        if format == "uuid":
            UUID(value)
        elif format == "uri":
            parsed = urlsplit(value)
            assert parsed.scheme in {"http", "https"} and parsed.netloc
        elif format == "date-time":
            assert datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
        elif format is not None:
            raise NotImplementedError("原素材schema出现未处理format")
    elif kind == "array":
        assert isinstance(value, list)
        assert definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", len(value))
        for item in value:
            validate_original_schema(item, definition["items"], specification)
    elif kind == "object":
        assert isinstance(value, dict)
        assert set(definition.get("required", [])) <= set(value)
        properties = definition.get("properties", {})
        if definition.get("additionalProperties") is False:
            assert set(value) <= set(properties)
        for name, item in value.items():
            if name in properties:
                validate_original_schema(item, properties[name], specification)
    else:
        raise NotImplementedError("原素材schema出现未处理type")
    if "enum" in definition:
        assert value in definition["enum"]


def run_material_schema_checks(client, headers, cases):
    """必须排在真实素材HTTP与视频组后；验证真实响应，不能注入模拟成功数据。"""
    specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    schemas = specification["components"]["schemas"]
    response = client.get("/api/v1/assets", headers=headers, params={"page_size": 200})
    assert response.status_code == 200
    page = response.json()
    validate_original_schema(page, schemas["AssetPage"], specification)
    assert {item["kind"] for item in page["items"]} >= {"IMAGE", "VIDEO"}
    video = [item for item in page["items"] if item["kind"] == "VIDEO" and item["state"] == "READY"]
    assert video and all(isinstance(item["duration_seconds"], str) for item in video)
    assert "width_px" not in schemas["Asset"]["properties"]
    assert "height_px" not in schemas["Asset"]["properties"]
    cases.append(MATERIAL_SCHEMA_CASES[0])
    for path, schema_name, case in (
        ("tags", "Tag", MATERIAL_SCHEMA_CASES[1]),
        ("categories", "Category", MATERIAL_SCHEMA_CASES[2]),
    ):
        response = client.get("/api/v1/" + path, headers=headers, params={"page_size": 200})
        assert response.status_code == 200
        page = response.json()
        assert page["items"]
        # 唯一技术扩展显式拆分校验；不改原schema、不顺带放过其他额外字段。
        originals = []
        for item in page["items"]:
            assert "visible_asset_count" in item
            count = item["visible_asset_count"]
            assert count is None or type(count) is int and 0 <= count <= 9007199254740991
            originals.append(
                {key: value for key, value in item.items() if key != "visible_asset_count"}
            )
        validate_original_schema(
            page | {"items": originals}, schemas[schema_name + "Page"], specification
        )
        cases.append(case)
