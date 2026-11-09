"""原AccountIdentities响应合同边界；验证结构不证明平台能力已经核验。"""

import re

from orbit_api.account_details_contract import timestamp
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid

KINDS = {"PAGE", "PIXEL", "APPLICATION"}


def invalid(pointer):
    raise OrbitError(422, "FIELD_INVALID", "账户身份资源不符合原合同", pointer)


def identity_text(value, minimum, maximum, pointer):
    # 不把数字ID转整数，不strip名称；原始前导零和允许的空名称均保留。
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        invalid(pointer)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        invalid(pointer)
    return value


def resource(value, pointer):
    if not isinstance(value, dict) or set(value) != {
        "external_id",
        "name",
        "kind",
        "usable",
        "reason_code",
    }:
        invalid(pointer)
    external_id = identity_text(value["external_id"], 1, 64, pointer + "/external_id")
    if not re.fullmatch(r"[0-9]+", external_id):
        invalid(pointer + "/external_id")
    name = identity_text(value["name"], 0, 255, pointer + "/name")
    if not isinstance(value["kind"], str) or value["kind"] not in KINDS:
        invalid(pointer + "/kind")
    if type(value["usable"]) is not bool:
        invalid(pointer + "/usable")
    reason = value["reason_code"]
    if reason is not None:
        reason = identity_text(reason, 1, 64, pointer + "/reason_code")
    return {
        "external_id": external_id,
        "name": name,
        "kind": value["kind"],
        "usable": value["usable"],
        "reason_code": reason,
    }


def identities(value, *, expected_account_id):
    """内部发布/读取均可复用；空资源合法性及目标账户能力证据由存储层另核验。

    原schema没有complete/source/TTL字段，这里不扩写公开正文，也不把结构合法当已同步。
    """
    if not isinstance(value, dict) or set(value) != {
        "account_id",
        "resources",
        "capability_version",
        "observed_at",
    }:
        invalid("/")
    if not isinstance(value["account_id"], str):
        invalid("/account_id")
    identifier = _uuid(value["account_id"], "/account_id")
    if identifier != expected_account_id:
        invalid("/account_id")
    if not isinstance(value["resources"], list) or len(value["resources"]) > 5000:
        invalid("/resources")
    version = identity_text(value["capability_version"], 1, 64, "/capability_version")
    observed_at = timestamp(value["observed_at"], "/observed_at")
    resources, seen = [], set()
    for index, item in enumerate(value["resources"]):
        pointer = f"/resources/{index}"
        parsed = resource(item, pointer)
        key = (parsed["kind"], parsed["external_id"])
        if key in seen:
            raise OrbitError(422, "DUPLICATE_VALUE", "身份资源种类与ID不能重复", pointer)
        seen.add(key)
        resources.append(parsed)
    return {
        "account_id": identifier,
        "resources": resources,
        "capability_version": version,
        "observed_at": observed_at,
    }
