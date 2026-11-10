"""账户列表每日消费采集；沿用账户事实发布器，不需要转化指标口径。"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from orbit_api.account_details_contract import amount, iso
from orbit_api.errors import OrbitError
from orbit_api.meta_read_contract import InsightWindow, decimal_value, external_id, fail

SPEND_FIELDS = "account_id,account_currency,date_start,date_stop,spend"


async def read_daily_spend(adapter, account_id, currency, timezone, *, now=None):
    """90个账户当地日；只有完整分页中的明确日行可以成为事实，缺行不补零。"""
    account_id = external_id(account_id)
    observed = now or datetime.now(UTC)
    today = observed.astimezone(ZoneInfo(timezone)).date()
    window = InsightWindow(today - timedelta(days=89), today, timezone)
    stamp = iso(observed)

    def normalize(row):
        if row.get("account_id") != account_id or row.get("account_currency") != currency:
            fail("META_ACCOUNT_MISMATCH")
        try:
            day = date.fromisoformat(row["date_start"])
            if day.isoformat() != row["date_start"] or row.get("date_stop") != row["date_start"]:
                fail()
            if not window.since <= day <= window.until:
                fail()
            value = decimal_value(row.get("spend"))
            if value is not None:
                amount(value, "/spend")
        except (ValueError, TypeError, KeyError, OrbitError):
            fail()
        return dict(
            business_date=day.isoformat(),
            amount=value,
            coverage="COMPLETE" if value is not None else "PARTIAL",
            currency=currency,
            source="META_INSIGHTS",
            observed_at=stamp,
        )

    result, seen, checkpoint = [], set(), None
    for _ in range(5):
        page = await adapter._page(
            "act_" + account_id + "/insights",
            {"fields": SPEND_FIELDS, "level": "account", "limit": "200", **window.parameters()},
            normalize,
            checkpoint=checkpoint,
            extra=timezone,
            key=lambda row: row["business_date"],
        )
        for row in page.items:
            if row["business_date"] in seen:
                fail("META_PAGINATION_INVALID")
            seen.add(row["business_date"])
            result.append(row)
        if page.complete:
            return result
        if page.checkpoint is None:
            fail("META_PAGINATION_INVALID")
        checkpoint = page.checkpoint
    fail("META_PAGE_LIMIT")


async def publish_daily_spend(session, current, account_id, facts):
    """调用方先锁原账户并复验来源/claim；原发布器继续复验权限和冻结历史归属。"""
    if not facts:
        return
    if not session.in_transaction():
        raise ValueError("每日消费必须与账户同步显式同事务发布")
    from orbit_api.account_details_store import AccountDetailsStore

    store = AccountDetailsStore(None)
    watermark = await store.watermark(session, current.tenant_id, write=True)
    prior = {
        row["business_date"].isoformat(): row["observed_at"].replace(tzinfo=UTC)
        for row in (
            await session.execute(
                text(
                    "SELECT business_date,observed_at FROM orbit_account_spend_day "
                    "WHERE tenant_id=:tenant AND account_id=:account "
                    "AND business_date BETWEEN :start AND :end FOR UPDATE"
                ),
                {
                    "tenant": current.tenant_id,
                    "account": account_id,
                    "start": min(row["business_date"] for row in facts),
                    "end": max(row["business_date"] for row in facts),
                },
            )
        ).mappings()
    }
    fresh = [
        row | {"account_id": account_id}
        for row in facts
        if row["business_date"] not in prior
        or datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        > prior[row["business_date"]]
    ]
    if fresh:
        await store.publish(session, current.actor_id, watermark["revision"], facts=fresh)


async def enqueue_initial_sync(session, importer, account_id, source, request_id):
    """仅新建自动导入账户复用原SYNC命令；导入权限不能代替当前同步许可。"""
    import hashlib
    from uuid import UUID, uuid5

    from orbit_api.account_actions_store import AccountActionsStore
    from orbit_api.authorization import require_business_access
    from orbit_api.directory_tokens import canonical
    from orbit_api.meta_account_sources import account_source, connection_row, source_marker

    try:
        authorized = await require_business_access(
            session, importer.actor_id, "accounts", "accounts.sync", acting_subject=False
        )
    except OrbitError as error:
        if error.status == 403:
            return False
        raise
    if (authorized.tenant_id, authorized.subject_id) != (importer.tenant_id, importer.subject_id):
        return False
    store = AccountActionsStore(None)
    current, _, account = await store.lock_account(session, importer.actor_id, account_id, "SYNC")
    if (current.tenant_id, current.subject_id) != (importer.tenant_id, importer.subject_id):
        return False
    selected = await account_source(session, current.tenant_id, account_id)
    configuration = source.configuration
    if selected is None or (selected["connection_id"], selected["connection_revision"]) != (
        configuration.source_config_id,
        configuration.source_config_revision,
    ):
        raise OrbitError(409, "ACCOUNT_SYNC_SOURCE_CHANGED", "初次同步来源已变化")
    await connection_row(
        session, current.tenant_id, selected["connection_id"], selected["connection_revision"]
    )
    payload = {"reason": "授权自动导入后读取每日消费"}
    key = str(uuid5(UUID(account_id), "INITIAL_ACCOUNT_SYNC"))
    await store.command(
        session,
        current,
        account,
        "SYNC",
        "WAITING_EXECUTOR",
        key,
        hashlib.sha256(canonical(payload).encode()).hexdigest(),
        payload,
        str(uuid5(UUID(request_id), "INITIAL_ACCOUNT_SYNC")),
        source={
            "id": selected["connection_id"],
            "revision": selected["connection_revision"],
            "meta_source": source_marker(selected),
        },
    )
    return True
