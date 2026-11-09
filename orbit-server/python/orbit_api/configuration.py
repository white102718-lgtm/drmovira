"""系统配置字段白名单及明确DTO；公开元数据不含凭据或服务端主密钥。"""

import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from orbit_api.errors import OrbitError

_FIELDS = json.loads(
    (Path(__file__).parent / "contracts/configuration-fields.json").read_text(encoding="utf-8")
)
_CATALOG = {
    section: [field for field in _FIELDS if field["section"] == section]
    for section in dict.fromkeys(f["section"] for f in _FIELDS)
}


def short_text(value: str, maximum: int, pointer: str, *, required: bool = True) -> str:
    """按Unicode码点计数，先拒控制符再trim，不能把末尾换行吞掉后放行。"""
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} or c in "\u2028\u2029" for c in value):
        raise OrbitError(422, "FIELD_INVALID", "文本包含无效字符", pointer)
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) > maximum or (required and not normalized):
        raise OrbitError(422, "FIELD_INVALID", "文本长度或必填条件不符合要求", pointer)
    return normalized


class SecretChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    operation: Literal["KEEP", "REPLACE", "CLEAR"]
    value: SecretStr | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def operation_matches_value(self):
        if self.operation == "REPLACE":
            if self.value is None:
                raise ValueError("替换凭据必须提供新值")
            value = self.value.get_secret_value()
            if (
                not value
                or len(value) > 8192
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)
            ):
                raise ValueError("凭据格式或长度无效")
        elif self.value is not None:
            raise ValueError("保持或清除操作不能附带凭据值")
        return self


class ConfigurationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    section: str
    name: str
    enabled: bool
    settings: dict[str, str | int]
    secrets: dict[str, SecretChange] = Field(repr=False)
    reason: str


def metadata() -> list[dict]:
    """返回全新结构，调用方不能修改进程共享的字段白名单。"""
    return [
        {
            "key": section,
            "label": fields[0]["section_label"],
            "fields": [
                {
                    "key": f["key"],
                    "label": f["label"],
                    "type": f["type"],
                    "required": f["required_when_enabled"],
                    "defaultValue": f["default"],
                    "minimum": f["minimum"],
                    "maximum": f["maximum"],
                    "options": list(f["options"]),
                }
                for f in fields
            ],
        }
        for section, fields in _CATALOG.items()
    ]


def secret_field_names(section: str) -> tuple[str, ...]:
    """字段槽位来自合同；未配置或已清除也必须向页面明确返回未配置状态。"""
    return tuple(field["key"] for field in _CATALOG.get(section, ()) if field["type"] == "secret")


def _parse_json(raw: bytes):
    """重复键、未知字段和结构错误不被静默覆盖；错误不回显任何输入值。"""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise OrbitError(400, "INVALID_STRUCTURE", "请求JSON结构无效") from None


def parse_probe_reason(raw: bytes) -> str:
    data = _parse_json(raw)
    if not isinstance(data, dict) or set(data) != {"reason"} or not isinstance(data["reason"], str):
        raise OrbitError(400, "INVALID_STRUCTURE", "只读测试仅接受人工原因字符串", "/reason")
    return short_text(data["reason"], 500, "/reason")


def parse_write(raw: bytes) -> ConfigurationWrite:
    data = _parse_json(raw)
    try:
        request = ConfigurationWrite.model_validate(data)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        location = first["loc"]
        # Pydantic联合类型分支名不是请求属性，不能出现在JSON Pointer中。
        if len(location) == 3 and location[0] == "settings" and location[-1] in {"str", "int"}:
            location = location[:-1]
        pointer = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in location)
        if first["type"] == "extra_forbidden":
            raise OrbitError(400, "UNKNOWN_FIELD", "请求包含未知字段", pointer) from None
        if first["type"] in {"value_error", "literal_error"}:
            raise OrbitError(422, "FIELD_INVALID", "字段值不符合要求", pointer) from None
        raise OrbitError(400, "INVALID_STRUCTURE", "请求字段缺失或类型无效", pointer) from None
    request.name = short_text(request.name, 100, "/name")
    request.reason = short_text(request.reason, 500, "/reason")
    fields = _CATALOG.get(request.section)
    if fields is None:
        raise OrbitError(422, "INVALID_SECTION", "不支持的系统配置类型", "/section")
    public = {f["key"]: f for f in fields if f["type"] != "secret"}
    secret_fields = {f["key"] for f in fields if f["type"] == "secret"}
    if request.settings.keys() - public.keys() or request.secrets.keys() - secret_fields:
        raise OrbitError(400, "UNKNOWN_FIELD", "配置包含未知字段或凭据字段位置错误")
    normalized: dict[str, str | int] = {}
    for key, field in public.items():
        value = request.settings.get(key, field["default"])
        pointer = "/settings/" + key
        if field["type"] == "integer":
            if type(value) is not int or not field["minimum"] <= value <= field["maximum"]:
                raise OrbitError(422, "FIELD_INVALID", "整数配置超出范围或类型无效", pointer)
        else:
            if not isinstance(value, str):
                raise OrbitError(422, "FIELD_INVALID", "文本配置类型无效", pointer)
            value = short_text(
                value, 500, pointer, required=request.enabled and field["required_when_enabled"]
            )
            if field["type"] == "select" and value not in field["options"]:
                raise OrbitError(422, "FIELD_INVALID", "配置选项无效", pointer)
        normalized[key] = value
    if (
        request.section == "MATERIAL_SCANNER"
        and normalized["profileId"]
        and not re.fullmatch(r"[a-z0-9_-]{1,40}", normalized["profileId"])
    ):
        raise OrbitError(422, "FIELD_INVALID", "扫描候选标识格式无效", "/settings/profileId")
    request.settings = normalized
    if request.section == "AI_SUGGESTIONS" and normalized.get("providerConfigId"):
        try:
            provider = str(UUID(str(normalized["providerConfigId"])))
            if provider != str(normalized["providerConfigId"]).lower():
                raise ValueError
            normalized["providerConfigId"] = provider
        except ValueError:
            raise OrbitError(
                422, "FIELD_INVALID", "请选择有效的AI配置标识", "/settings/providerConfigId"
            ) from None
    patterns = {}
    if request.section.startswith("META_"):
        patterns = {
            "graphVersion": r"v[0-9]{1,3}\.[0-9]{1,2}",
            "appId" if request.section == "META_APP" else "businessId": r"[0-9]{1,64}",
        }
        if request.section == "META_BM":
            patterns["systemUserId"] = r"[0-9]{1,64}"
    if request.section == "AI_CLAUDE":
        patterns = {"workspaceId": r"wrkspc_[A-Za-z0-9]+"}
        try:
            date.fromisoformat(str(normalized["apiVersion"]))
        except ValueError:
            raise OrbitError(
                422, "FIELD_INVALID", "API版本日期无效", "/settings/apiVersion"
            ) from None
    for key, pattern in patterns.items():
        if normalized[key] and not re.fullmatch(pattern, str(normalized[key])):
            raise OrbitError(422, "FIELD_INVALID", "配置字段格式无效", "/settings/" + key)
    for key in ("issuer", "redirectUri", "endpoint", "webhookUrl"):
        if not normalized.get(key):
            continue
        try:
            parsed = urlsplit(str(normalized[key]))
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
            ):
                raise ValueError
        except ValueError:
            raise OrbitError(
                422, "INVALID_URL", "集成地址必须是无凭据和片段的HTTPS地址", "/settings/" + key
            ) from None
    if (
        request.section == "NOTIFICATIONS"
        and request.enabled
        and normalized["channel"] == "WEBHOOK"
        and not normalized["webhookUrl"]
    ):
        raise OrbitError(422, "WEBHOOK_REQUIRED", "启用Webhook必须提供地址", "/settings/webhookUrl")
    return request
