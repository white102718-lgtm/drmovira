"""原ProfileBinding四字段；登记不接受登录证明或执行能力。"""

from uuid import UUID

from pydantic import ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, schema_error


class Ownership(StrictInput):
    owner_user_id: str
    owner_team_id: str


class ProfileBindingWrite(StrictInput):
    account_id: str
    agent_id: str
    profile_external_id: str
    ownership: Ownership


class UnbindWrite(StrictInput):
    reason: str


def identifier(value, path="/id"):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise OrbitError(422, "FIELD_INVALID", "需要规范UUID", path) from None
    return value


def parse(raw, model):
    try:
        return model.model_validate(_parse_json(raw)).model_dump()
    except ValidationError as error:
        raise schema_error(error) from None


def parse_write(raw):
    value = parse(raw, ProfileBindingWrite)
    for key in ("account_id", "agent_id"):
        identifier(value[key], "/" + key)
    for key in ("owner_user_id", "owner_team_id"):
        identifier(value["ownership"][key], "/ownership/" + key)
    original = value["profile_external_id"]
    normalized = short_text(original, 128, "/profile_external_id")
    if normalized != original:
        raise OrbitError(
            422, "FIELD_INVALID", "Profile ID不能含首尾空白或非规范文本", "/profile_external_id"
        )
    return value


def parse_unbind(raw):
    value = parse(raw, UnbindWrite)
    value["reason"] = short_text(value["reason"], 500, "/reason")
    return value
