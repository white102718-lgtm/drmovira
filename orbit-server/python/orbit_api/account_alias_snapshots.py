"""020业务时点代称只追加写入；由原受理及绑定事务内部调用，无独立HTTP入口。"""

from collections.abc import Mapping

from sqlalchemy import text

from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.vendor_alias_snapshot import freeze_vendor_alias_snapshots


async def append_account_alias_snapshot(
    session,
    context,
    vendor,
    *,
    resource_type,
    resource_id,
    resource_revision,
    request_id,
    permission,
    acting_subject=True,
):
    """原动作已锁账户/批次/区间并验证户商后调用；与业务、审计、outbox同一外层事务。

    不查当前别名回填旧历史，不UPsert。同对象同版本重复插入应由数据库拒绝并回滚；
    原命令幂等重放须走既有保存响应分支，不重新捕获当时标签。
    """
    expected = {
        "IMPORT": "accounts.import",
        "ACCOUNT_BINDING": "accounts.import",
        "IMPORT_ASSIGNMENT": "accounts.import",
        "ASSIGNMENT": "accounts.assign",
    }
    if not isinstance(resource_type, str) or expected.get(resource_type) != permission:
        raise OrbitError(403, "PERMISSION_DENIED", "业务代称冻结动作不匹配")
    if (
        not isinstance(vendor, Mapping)
        or type(resource_revision) is not int
        or not 1 <= resource_revision <= MAX_REVISION
        or type(acting_subject) is not bool
    ):
        raise OrbitError(422, "FIELD_INVALID", "代称业务快照参数无效")
    identifier = _uuid(resource_id, "/resource_id")
    request = _uuid(request_id, "/request_id")
    vendor_id = _uuid(vendor.get("id"), "/vendor_id")
    if not session.in_transaction():
        raise ValueError("代称业务快照必须与原业务显式事务一同提交")
    # B助手重新检查原动作（允许import-only，不附加read），并复核真实受锁资料指纹。
    frozen = (
        await freeze_vendor_alias_snapshots(
            session,
            context,
            {vendor_id: dict(vendor)},
            permission=permission,
            acting_subject=acting_subject,
        )
    )[vendor_id]
    value = _decode(vendor["value_json"])
    params = {
        "tenant": context.tenant_id,
        "type": resource_type,
        "id": identifier,
        "revision": resource_revision,
        "vendor": vendor_id,
        "vendor_revision": vendor["revision"],
        "name": value["name"],
        "alias": frozen["alias"],
        "alias_revision": frozen["alias_revision"],
        "source": frozen["source"],
        "request": request,
    }
    await session.execute(
        text(
            "INSERT INTO orbit_account_vendor_alias_snapshot "
            "(tenant_id,resource_type,resource_id,resource_revision,vendor_id,vendor_revision,"
            "vendor_name_snapshot,alias,alias_revision,alias_source,request_id,captured_at) "
            "VALUES(:tenant,:type,:id,:revision,:vendor,:vendor_revision,:name,:alias,"
            ":alias_revision,:source,:request,UTC_TIMESTAMP(3))"
        ),
        params,
    )
