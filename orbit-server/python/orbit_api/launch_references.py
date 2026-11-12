"""非空计划引用必须当前调用者与实际目标拥有者双重可读，空草稿不强加来源菜单。"""

from sqlalchemy import bindparam, text

from orbit_api import account_access
from orbit_api.account_scope_store import AccountScopeStore
from orbit_api.authorization import require_business_access
from orbit_api.channel_store import ChannelStore
from orbit_api.configuration_store import _decode
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest, owner
from orbit_api.launch_expansion import expanded_counts
from orbit_api.launch_identity_references import (
    prepare_identity_sources,
    resolve_identity_dependencies,
)
from orbit_api.material_references import require_allocation_assets
from orbit_api.reference_access import clock as reference_clock


async def source_contexts(session, current, ownership, owner_actor, menu):
    caller = await require_business_access(session, current.actor_id, menu, menu + ".read")
    try:
        target = await require_business_access(
            session, owner_actor, menu, menu + ".read", acting_subject=False
        )
    except OrbitError as error:
        if error.status == 403:
            raise OrbitError(404, "NOT_FOUND", "目标拥有者无权引用所选资源") from None
        raise
    if (
        caller.tenant_id != current.tenant_id
        or target.tenant_id != current.tenant_id
        or target.subject_id != ownership["owner_user_id"]
        or target.team_id != ownership["owner_team_id"]
    ):
        raise OrbitError(404, "NOT_FOUND", "引用权限或目标拥有者范围已变化")
    return caller, target


async def validate_sources(session, current, value, *, permission, isolated_fixture=False):
    """先来源clock/有序对象锁，再由调用者拿launch clock及计划CAS锁。"""
    # 指标契约还复用执行类型；仅在调用时加载，避免Store/预检类型的模块初始化环。
    from orbit_api.metric_profile_references import (
        collect_metric_profile_ids,
        resolve_metric_profile_dependencies,
    )

    ownership = value["ownership"]
    owner_actor = await owner(session, current, ownership)
    if value.get("profile_binding_ids"):
        raise OrbitError(
            503,
            "LAUNCH_IDENTITY_DEPENDENCY_UNAVAILABLE",
            "逐账户环境绑定核验尚未接入",
            "/profile_binding_ids",
        )
    identity_sources = {}
    if value.get("identity_bindings"):
        # 权限先于来源发现；统一预锁来源，避免范围消费后反向补锁配置/发行。
        caller, _ = await source_contexts(session, current, ownership, owner_actor, "accounts")
        identity_sources = await prepare_identity_sources(
            session, caller, value["identity_bindings"]
        )
    metric_dependencies = await resolve_metric_profile_dependencies(
        session,
        current,
        owner_actor,
        ownership,
        collect_metric_profile_ids(value["campaigns"]),
        permission=permission,
        isolated_fixture=isolated_fixture,
    )
    # 仅操作调用方的工作副本；原请求幂等意图与死锁重试输入由LaunchStore保留。
    scope_dependency = await resolve_account_scope(session, current, value)
    result = {"accounts": {}, "assets": {}, "channel": None}
    if metric_dependencies["metric_profiles"]:
        result.update(metric_dependencies)
    if scope_dependency is not None:
        result["account_scope_snapshot"] = scope_dependency
    if value["account_ids"]:
        caller, target = await source_contexts(session, current, ownership, owner_actor, "accounts")
        result["account_clock"] = await account_access.clock(session, caller)
        sql = (
            """SELECT a.id,a.revision,a.owner_user_id,a.owner_team_id,a.currency,a.timezone_id,
        a.auth_status,a.account_status,a.unbound_at FROM orbit_ad_account a WHERE
        a.tenant_id=:tenant AND a.id IN :ids AND ("""
            + account_access.visible_clause(caller, "a")
            + ") AND ("
            + account_access.visible_clause(target, "a")
            .replace(":subject", ":target_subject")
            .replace(":actor", ":target_actor")
            + ") ORDER BY a.id FOR SHARE"
        )
        rows = (
            (
                await session.execute(
                    text(sql).bindparams(bindparam("ids", expanding=True)),
                    account_access.parameters(caller)
                    | {
                        "ids": sorted(value["account_ids"]),
                        "target_subject": target.subject_id,
                        "target_actor": target.actor_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if {row["id"] for row in rows} != set(value["account_ids"]):
            raise OrbitError(404, "NOT_FOUND", "部分账户不存在或当前双方不可读", "/account_ids")
        if any(
            row["owner_user_id"] != ownership["owner_user_id"]
            or row["owner_team_id"] != ownership["owner_team_id"]
            or row["unbound_at"] is not None
            for row in rows
        ):
            raise OrbitError(
                422, "ACCOUNT_SCOPE_MISMATCH", "账户须归属同一投手团队且仍绑定", "/account_ids"
            )
        if len({row["currency"] for row in rows}) != 1 or any(not row["currency"] for row in rows):
            raise OrbitError(
                422, "ACCOUNT_CURRENCY_MISMATCH", "账户币种必须已知且一致", "/account_ids"
            )
        result["accounts"] = {
            row["id"]: {
                key: row[key]
                for key in ("revision", "currency", "timezone_id", "auth_status", "account_status")
            }
            for row in rows
        }
        currency = rows[0]["currency"]
        for ci, campaign in enumerate(value["campaigns"]):
            budgets = [(campaign.get("budget"), f"/campaigns/{ci}/budget")]
            budgets.extend(
                (adset.get("budget"), f"/campaigns/{ci}/adsets/{si}/budget")
                for si, adset in enumerate(campaign["adsets"])
            )
            for budget, path in budgets:
                if budget and budget["currency"] != currency:
                    raise OrbitError(
                        422, "ACCOUNT_CURRENCY_MISMATCH", "预算币种必须与当前账户一致", path
                    )
    if value["asset_ids"]:
        identifiers = sorted(value["asset_ids"])
        for offset in range(0, len(identifiers), 200):
            batch = await require_allocation_assets(
                session,
                current,
                ownership["owner_user_id"],
                ownership["owner_team_id"],
                identifiers[offset : offset + 200],
            )
            result["assets"].update(
                {
                    key: {field: row[field] for field in ("revision", "sha256")}
                    for key, row in batch.items()
                }
            )
    if value.get("channel_id"):
        caller, target = await source_contexts(session, current, ownership, owner_actor, "channels")
        result["reference_clock"] = dict(await reference_clock(session, caller))
        store = ChannelStore(None)
        channel = await store.row(session, caller, value["channel_id"])
        await store.row(session, target, value["channel_id"])
        data = _decode(channel["value_json"])
        if (
            data["status"] != "ENABLED"
            or data["ownership"]["owner_team_id"] != ownership["owner_team_id"]
            or ownership["owner_user_id"] not in data["ownership"]["data_owner_user_ids"]
        ):
            raise OrbitError(
                422, "CHANNEL_UNAVAILABLE", "渠道须启用且允许目标拥有者使用", "/channel_id"
            )
        result["channel"] = {"id": channel["id"], "revision": channel["revision"]}
    result.update(await resolve_identity_dependencies(session, current, value, identity_sources))
    return result


async def resolve_account_scope(session, current, value):
    """A025真实冻结范围消费；不接受列表cursor，不代替下方调用者+目标账户交集。"""
    scope_id = value.get("account_scope_snapshot_id")
    if scope_id is None:
        return None
    if value["account_ids"]:
        raise OrbitError(
            422, "FIELD_VALIDATION_FAILED", "范围快照与显式账户不可同时非空", "/account_ids"
        )
    ownership = value["ownership"]
    # resolve_for_plan只走实时数据库授权/冻结成员，未签发或验证游标，无需构造Token对象。
    identifiers = await AccountScopeStore(None).resolve_for_plan(
        session,
        current,
        scope_id,
        owner_user_id=ownership["owner_user_id"],
        owner_team_id=ownership["owner_team_id"],
    )
    if not 1 <= len(identifiers) <= 500:
        raise OrbitError(
            422, "PLAN_ACCOUNT_LIMIT", "计划仅允许1至500个账户，不允许截断范围", "/account_ids"
        )
    if len(set(identifiers)) != len(identifiers):
        raise OrbitError(409, "SCOPE_CHANGED", "冻结账户集合异常，请重新选择")
    identifiers = sorted(identifiers)
    # 先按实际账户乘数保护展开，再改工作副本，不能让原空数组绕过10000节点上限。
    expanded_counts(value | {"account_ids": identifiers})
    snapshot = (
        (
            await session.execute(
                text("""SELECT scope_version,members_hash,auth_fingerprint,member_count
        FROM orbit_account_scope_snapshot WHERE tenant_id=:tenant AND id=:id
        AND actor_id=:actor AND ready=1 FOR SHARE"""),
                {"tenant": current.tenant_id, "id": scope_id, "actor": current.actor_id},
            )
        )
        .mappings()
        .one()
    )
    if snapshot["member_count"] != len(identifiers):
        raise OrbitError(409, "SCOPE_CHANGED", "冻结成员数量已变化")
    value["account_ids"] = identifiers
    # 已消费的范围作为版本依赖保存；公开Plan保持可按原PlanWrite互斥规则再次编辑。
    value["account_scope_snapshot_id"] = None
    return {
        "scope_id": scope_id,
        "members_hash": snapshot["members_hash"],
        "scope_version": snapshot["scope_version"],
        "auth_fingerprint": snapshot["auth_fingerprint"],
        "resolved_ids_hash": digest(identifiers),
        "count": len(identifiers),
    }
