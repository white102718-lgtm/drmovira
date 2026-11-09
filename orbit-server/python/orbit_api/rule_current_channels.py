"""规则范围成员的当前渠道；从当前账户可见范围取交集，不使用历史事实。"""

from orbit_api.account_access import clock, visible_clause
from orbit_api.reference_access import clock as reference_clock
from orbit_api.reference_access import scope_clause


async def channel_watermark(session, access):
    """账户clock→引用clock→ruleclock；绑定改绑、解绑、归属和渠道改名水位。"""
    account = await clock(session, access.current)
    reference = await reference_clock(session, access.current)
    return [account, reference["channel_revision"]]


def joins():
    return (
        " JOIN orbit_rule_scope_member cm ON cm.tenant_id=h.tenant_id AND "
        "cm.manifest_id=h.manifest_id "
        "JOIN orbit_ad_account ca ON ca.tenant_id=cm.tenant_id AND ca.id=cm.account_id "
        "JOIN orbit_account_current_channel cc ON cc.tenant_id=ca.tenant_id AND "
        "cc.account_id=ca.id "
        "JOIN orbit_channel c ON c.tenant_id=cc.tenant_id AND c.id=cc.channel_id "
    )


def current_clause(access):
    # 渠道可停用但历史关联仍存在；只有新关联写入要求ENABLED。
    return (
        "ca.unbound_at IS NULL AND ("
        + visible_clause(access.current, "ca")
        + ") AND ("
        + scope_clause(access.current, "c", "orbit_channel_owner", "channel_id")
        + ")"
    )


def channel_exists(access):
    return (
        "EXISTS(SELECT 1 FROM orbit_rule_scope_member cm "
        "JOIN orbit_ad_account ca ON ca.tenant_id=cm.tenant_id AND ca.id=cm.account_id "
        "JOIN orbit_account_current_channel cc ON cc.tenant_id=ca.tenant_id AND "
        "cc.account_id=ca.id "
        "JOIN orbit_channel c ON c.tenant_id=cc.tenant_id AND c.id=cc.channel_id "
        "WHERE cm.tenant_id=h.tenant_id AND cm.manifest_id=h.manifest_id AND c.id=:channel_id AND "
        + current_clause(access)
        + ")"
    )
