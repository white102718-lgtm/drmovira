"""已授权账户业务的内部代称冻结，不新增或扩大任何HTTP读取权限。"""

from collections.abc import Mapping
from typing import Literal

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.configuration import short_text
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams, readable
from orbit_api.reference_contract import uuid_value
from orbit_api.reference_store import records
from orbit_api.team_store import state_hash
from orbit_api.vendor_alias_store import alias_rows


def vendor_fingerprint(row):
    """输入必须是records返回的原始受锁行，不接受显示对象或仅名称拼出的资料。"""
    try:
        if (
            not isinstance(row, Mapping)
            or row["kind"] != "VENDOR"
            or type(row["revision"]) is not int
            or not 1 <= row["revision"] <= MAX_REVISION
            or type(row["catalog_revision"]) is not int
        ):
            raise ValueError
        value = _decode(row["value_json"])
        if not isinstance(value, dict) or value["kind"] != "VENDOR" or value["id"] != row["id"]:
            raise ValueError
        return state_hash([row["id"], row["kind"], row["revision"], row["catalog_revision"], value])
    except (KeyError, TypeError, ValueError):
        raise OrbitError(
            422, "VENDOR_REFERENCE_CHANGED", "户商必须为当前事务核验的真实资料"
        ) from None


def alias_snapshot(row):
    """真实值与未知严格分开；缺行不伪造维护版本或来源，也不推测名称。"""
    if row is None:
        return {
            "alias": None,
            "alias_revision": 1,
            "source": "UNSET",
            "vendor_availability": "AVAILABLE",
        }
    alias = row["alias"]
    if (
        type(row["revision"]) is not int
        or not 2 <= row["revision"] <= MAX_REVISION
        or alias is not None
        and (not isinstance(alias, str) or short_text(alias, 30, "/alias") != alias)
    ):
        raise OrbitError(422, "ALIAS_SOURCE_INVALID", "真实户商代称来源不符合合同")
    return {
        "alias": alias,
        "alias_revision": row["revision"],
        "source": "VENDOR_ALIAS",
        "vendor_availability": "AVAILABLE",
    }


async def freeze_vendor_alias_snapshots(
    session,
    context: BusinessContext,
    vendors: Mapping[str, dict],
    *,
    permission: Literal["accounts.import", "accounts.assign"],
    acting_subject: bool = True,
):
    """调用者先验AVAILABLE/team/目标owner交集；返回值仅用于同事务不可变历史记录。

    import-only调用不要求accounts.read。后台Worker显式acting_subject=False，仍重新校验
    原actor当前业务动作/租户/人员状态；不能以浏览器参数调用，也不能把返回值直通HTTP。
    本函数只读并持有真实资料/代称共享锁，不提交、不创建快照或更改任何版本。
    """
    if not isinstance(context, BusinessContext) or permission not in {
        "accounts.import",
        "accounts.assign",
    }:
        raise OrbitError(403, "PERMISSION_DENIED", "只能在已授权账户导入或分配事务中冻结代称")
    if not isinstance(vendors, Mapping) or len(vendors) > 200:
        raise OrbitError(422, "FIELD_INVALID", "一次最多冻结200个真实户商")
    current = await require_business_access(
        session, context.actor_id, "accounts", permission, acting_subject=acting_subject
    )
    if current != context:
        raise OrbitError(403, "PERMISSION_DENIED", "账户业务身份或范围已变化")
    identifiers = [uuid_value(identifier, "/vendor_ids") for identifier in vendors]
    if set(identifiers) != set(vendors):
        raise OrbitError(422, "VENDOR_REFERENCE_CHANGED", "户商UUID必须使用规范受锁记录键")
    current_rows = await records(session, current.tenant_id, identifiers)
    managed = await managed_teams(session, current)
    if set(current_rows) != set(identifiers):
        raise OrbitError(422, "VENDOR_REFERENCE_CHANGED", "户商不存在或不属于当前业务租户")
    for identifier in identifiers:
        original = vendors[identifier]
        actual = current_rows[identifier]
        if vendor_fingerprint(original) != vendor_fingerprint(actual):
            raise OrbitError(422, "VENDOR_REFERENCE_CHANGED", "户商版本或归属已变化")
        value = _decode(actual["value_json"])
        if value["availability"] != "AVAILABLE" or not readable(current, managed, value):
            raise OrbitError(422, "VENDOR_REFERENCE_CHANGED", "户商已停用或超出当前业务范围")
    aliases = await alias_rows(session, current.tenant_id, identifiers)
    return {identifier: alias_snapshot(aliases.get(identifier)) for identifier in identifiers}
