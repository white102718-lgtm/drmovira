"""渠道输入、归属和HTTPS地址校验；绝不探测用户地址或注入链接参数。"""

import ipaddress
import re
from urllib.parse import unquote, urlsplit

from pydantic import Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, ownership, schema_error, uuid_value


class ChannelWrite(StrictInput):
    ownership: dict
    code: str
    name: str
    product_id: str
    agent_id: str
    type: str
    media: str
    url: str
    status: str


class Assignment(StrictInput):
    ownership: dict
    reason: str


class Archive(StrictInput):
    reason: str = Field(min_length=1, max_length=1000)


def https_url(value):
    value = short_text(value, 2048, "/url")
    try:
        decoded = unquote(value, errors="strict")
        if any(ord(char) < 33 or ord(char) == 127 for char in decoded) or "\\" in decoded:
            raise ValueError
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError
        if parsed.port == 0:
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii")
        if host.lower() in {"localhost", "metadata.google.internal"}:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or not re.fullmatch(r"[A-Za-z0-9.-]+", host) or ".." in host:
                raise ValueError from None
        else:
            if not address.is_global:
                raise ValueError
        if re.search(r"%(?![0-9A-Fa-f]{2})", value):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise OrbitError(
            422, "FIELD_INVALID", "请输入无凭据且参数编码有效的公网HTTPS链接", "/url"
        ) from None


def parse_channel(raw, mode="save"):
    model = {"save": ChannelWrite, "owners": Assignment, "archive": Archive}[mode]
    try:
        value = model.model_validate(_parse_json(raw)).model_dump()
    except ValidationError as error:
        raise schema_error(error) from None
    if mode != "archive":
        value["ownership"] = ownership(value["ownership"])
    if mode != "save":
        value["reason"] = short_text(value["reason"], 1000, "/reason")
        return value
    value["code"] = short_text(value["code"], 64, "/code")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value["code"]):
        raise OrbitError(422, "FIELD_INVALID", "渠道ID只允许字母、数字、下划线和短横线", "/code")
    value["name"] = short_text(value["name"], 100, "/name", required=False)
    for key in ("product_id", "agent_id"):
        value[key] = uuid_value(value[key], "/" + key)
    for key, options in (
        ("type", {"APP", "WEBSITE", "OTHER"}),
        ("media", {"META", "GOOGLE", "TIKTOK", "OTHER"}),
        ("status", {"ENABLED", "DISABLED"}),
    ):
        if value[key] not in options:
            raise OrbitError(422, "FIELD_INVALID", "渠道枚举值无效", "/" + key)
    value["url"] = https_url(value["url"])
    return value
