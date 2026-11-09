"""规则展示元数据独立技术DTO；原Rule15/Page4不变。"""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import Field, ValidationError, field_validator

from orbit_api.configuration import short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput
from orbit_api.rule_contract import MAX_SAFE


class RuleDisplayMetadataItem(StrictInput):
    rule_id: str
    revision: int = Field(ge=1, le=MAX_SAFE)
    owner_user_name: str | None
    owner_team_name: str | None
    created_by: int = Field(ge=1, le=MAX_SAFE)
    created_by_name: str | None
    created_at: str

    @field_validator("rule_id")
    @classmethod
    def canonical_id(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("canonical UUID required")
        return value

    @field_validator("owner_user_name", "owner_team_name", "created_by_name")
    @classmethod
    def actual_label(cls, value, info):
        if value is None:
            return None
        try:
            limit = 100 if info.field_name == "owner_team_name" else 50
            if short_text(value, limit, "/" + info.field_name) != value:
                raise ValueError("stored name is not normalized")
        except OrbitError:
            raise ValueError("stored name is invalid") from None
        return value

    @field_validator("created_at")
    @classmethod
    def fixed_utc_milliseconds(cls, value):
        if (
            re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{3}Z", value
            )
            is None
        ):
            raise ValueError("UTC milliseconds required")
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class RuleDisplayMetadataPage(StrictInput):
    items: list[RuleDisplayMetadataItem] = Field(min_length=1, max_length=200)


def parse_rule_ids(value):
    if type(value) is not str or not 1 <= len(value) <= 7399:
        invalid()
    parts = value.split(",")
    if not 1 <= len(parts) <= 200 or len(set(parts)) != len(parts):
        invalid()
    try:
        if any(str(UUID(part)) != part for part in parts):
            invalid()
    except (ValueError, AttributeError):
        invalid()
    return tuple(parts)


def invalid():
    raise OrbitError(422, "FIELD_INVALID", "请选择1至200个不重复的规范规则UUID", "/rule_ids")


def unavailable():
    raise OrbitError(503, "RULE_DISPLAY_METADATA_UNAVAILABLE", "规则展示元数据不完整")


def created_at_text(value):
    if type(value) is not datetime or value.microsecond % 1000:
        unavailable()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value.utcoffset() != timedelta(0):
        unavailable()
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def metadata_response(items):
    try:
        return RuleDisplayMetadataPage.model_validate({"items": items}).model_dump()
    except (ValidationError, ValueError, TypeError, OverflowError):
        unavailable()
