"""最小引用资料的严格输入：结构错误拒绝请求，行错误保留为可审查的预检结果。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError

KINDS = {"PRODUCT", "BUSINESS_AGENT", "VENDOR"}


def pointer(parts):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def schema_error(error):
    """只读取错误类型和位置，不读取或回显Pydantic的原始输入。"""
    first = error.errors(include_input=False, include_context=False)[0]
    path = pointer(first["loc"])
    if first["type"] == "extra_forbidden":
        return OrbitError(400, "UNKNOWN_FIELD", "请求包含未知字段", path)
    if first["type"] in {
        "literal_error",
        "value_error",
        "greater_than_equal",
        "greater_than",
        "less_than_equal",
        "less_than",
        "too_short",
        "too_long",
        "string_too_short",
        "string_too_long",
    }:
        return OrbitError(422, "FIELD_INVALID", "字段值或数量边界不符合要求", path)
    return OrbitError(400, "INVALID_STRUCTURE", "请求字段缺失或类型无效", path)


def row_structure(row, index, import_kind):
    """先验证整包JSON结构，再逐行做字段值/关联预检；不能创建结构非法的预览。"""
    kind = row.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        kind = import_kind
    required = {
        "id",
        "kind",
        "name",
        "availability",
        "owner_team_id",
        "data_owner_user_ids",
        "source_key",
    }
    if kind == "PRODUCT":
        required.add("allowed_agent_ids")
    for field in row:
        if field not in required:
            raise OrbitError(
                400, "UNKNOWN_FIELD", "资料行包含未知字段", pointer(("items", index, field))
            )
    for field in sorted(required - row.keys()):
        raise OrbitError(
            400, "INVALID_STRUCTURE", "资料行缺少必填字段", pointer(("items", index, field))
        )
    for field in required - {"data_owner_user_ids", "allowed_agent_ids"}:
        if not isinstance(row[field], str):
            raise OrbitError(
                400, "INVALID_STRUCTURE", "资料行文本字段类型无效", pointer(("items", index, field))
            )
    for field in required & {"data_owner_user_ids", "allowed_agent_ids"}:
        if not isinstance(row[field], list):
            raise OrbitError(
                400,
                "INVALID_STRUCTURE",
                "资料行关联字段必须为数组",
                pointer(("items", index, field)),
            )
        for item_index, value in enumerate(row[field]):
            if not isinstance(value, str):
                raise OrbitError(
                    400,
                    "INVALID_STRUCTURE",
                    "资料行关联UUID必须为字符串",
                    pointer(("items", index, field, item_index)),
                )


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Ownership(StrictInput):
    owner_team_id: str
    data_owner_user_ids: list[str] = Field(min_length=1, max_length=500)


class ReferenceImport(StrictInput):
    kind: Literal["PRODUCT", "BUSINESS_AGENT", "VENDOR"]
    source: str
    reason: str
    base_catalog_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    items: list[dict] = Field(min_length=1, max_length=500)


def uuid_value(value, pointer):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            raise ValueError
        return value.lower()
    except (ValueError, AttributeError):
        raise OrbitError(422, "FIELD_INVALID", "请输入完整业务UUID", pointer) from None


def ids(values, pointer):
    if not isinstance(values, list):
        raise OrbitError(400, "INVALID_STRUCTURE", "关联字段必须为数组", pointer)
    if not 1 <= len(values) <= 500:
        raise OrbitError(422, "FIELD_INVALID", "必须选择1至500个拥有者或关联资料", pointer)
    result = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise OrbitError(400, "INVALID_STRUCTURE", "关联UUID必须为字符串", f"{pointer}/{index}")
        result.append(uuid_value(value, f"{pointer}/{index}"))
    if len(set(result)) != len(result):
        raise OrbitError(422, "DUPLICATE_VALUE", "不能重复选择同一项", pointer)
    return sorted(result)


def ownership(value):
    if not isinstance(value, dict):
        raise OrbitError(400, "INVALID_STRUCTURE", "归属字段不完整或包含未知字段", "/ownership")
    required = {"owner_team_id", "data_owner_user_ids"}
    for field in value:
        if field not in required:
            raise OrbitError(
                400, "UNKNOWN_FIELD", "归属包含未知字段", pointer(("ownership", field))
            )
    for field in sorted(required - value.keys()):
        raise OrbitError(
            400, "INVALID_STRUCTURE", "归属缺少必填字段", pointer(("ownership", field))
        )
    if not isinstance(value["owner_team_id"], str):
        raise OrbitError(
            400, "INVALID_STRUCTURE", "归属团队UUID必须为字符串", "/ownership/owner_team_id"
        )
    return {
        "owner_team_id": uuid_value(value["owner_team_id"], "/ownership/owner_team_id"),
        "data_owner_user_ids": ids(value["data_owner_user_ids"], "/ownership/data_owner_user_ids"),
    }


def parse_import(raw):
    value = _parse_json(raw)
    if isinstance(value, dict) and "kind" in value and not isinstance(value["kind"], str):
        raise OrbitError(400, "INVALID_STRUCTURE", "资料类别必须为字符串", "/kind")
    try:
        result = ReferenceImport.model_validate(value)
    except ValidationError as error:
        raise schema_error(error) from None
    for index, row in enumerate(result.items):
        row_structure(row, index, result.kind)
    result.source = short_text(result.source, 255, "/source")
    result.reason = short_text(result.reason, 1000, "/reason")
    return result


def normalize_row(row, kind):
    required = {
        "id",
        "name",
        "availability",
        "owner_team_id",
        "data_owner_user_ids",
        "source_key",
        "kind",
    }
    if kind == "PRODUCT":
        required.add("allowed_agent_ids")
    if set(row) != required or row.get("kind") != kind:
        raise OrbitError(422, "ROW_STRUCTURE_INVALID", "行字段必须完整且类别与导入一致")
    result = dict(row)
    for field in ("name", "source_key", "availability", "kind"):
        if not isinstance(row[field], str):
            raise OrbitError(422, "FIELD_INVALID", "资料文本字段必须为字符串", "/" + field)
    result["id"] = uuid_value(row["id"], "/id")
    result["name"] = short_text(row["name"], 255, "/name")
    result["source_key"] = short_text(row["source_key"], 128, "/source_key")
    if row["availability"] not in {"AVAILABLE", "UNAVAILABLE"}:
        raise OrbitError(422, "FIELD_INVALID", "资料可用状态无效", "/availability")
    result.update(ownership({key: row[key] for key in ("owner_team_id", "data_owner_user_ids")}))
    if kind == "PRODUCT":
        result["allowed_agent_ids"] = ids(row["allowed_agent_ids"], "/allowed_agent_ids")
    return result
