"""独立代称严格合同；不扩大原ReferenceInput或ReferenceValue。"""

from pydantic import ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, schema_error, uuid_value


class VendorAliasWrite(StrictInput):
    alias: str | None
    reason: str


def parse_vendor_alias(raw):
    try:
        value = VendorAliasWrite.model_validate(_parse_json(raw))
    except ValidationError as error:
        raise schema_error(error) from None
    if value.alias is not None:
        value.alias = short_text(value.alias, 30, "/alias")
    value.reason = short_text(value.reason, 1000, "/reason")
    return value.model_dump()


def vendor_ids(raw):
    identifiers = raw.split(",")
    if not 1 <= len(identifiers) <= 200 or len(set(identifiers)) != len(identifiers):
        raise OrbitError(422, "FIELD_INVALID", "请选择1至200个不重复的户商UUID", "/ids")
    return [uuid_value(value, "/ids") for value in identifiers]
