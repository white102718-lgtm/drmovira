"""Meta读取运行入口；持久幂等任务复用同一Worker，默认关闭定时调度。"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text

from orbit_api.errors import OrbitError


def business_window(timezone, now, days):
    """包括账户当地今天；跨年、夏令时不使用固定UTC24小时推导业务日。"""
    if now.tzinfo is None or days not in {7, 90}:
        raise ValueError("采集窗口需要明确时区及7/90日")
    end = now.astimezone(ZoneInfo(timezone)).date()
    return end - timedelta(days=days - 1), end


async def enqueue_metrics(session, current, account, request_id, *, days=90):
    from config.orbit_runtime import private_values

    from orbit_api.meta_metric_collection import MetaMetricCollectionStore

    row = (
        (
            await session.execute(
                text(
                    "SELECT p.* FROM orbit_meta_connection_sync_policy p JOIN "
                    "orbit_meta_account_source s ON s.tenant_id=p.tenant_id AND "
                    "s.connection_id=p.connection_id WHERE s.tenant_id=:tenant "
                    "AND s.account_id=:account FOR SHARE"
                ),
                {"tenant": current.tenant_id, "account": account["id"]},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM orbit_meta_sync_policy WHERE tenant_id=:tenant FOR SHARE"),
                    {"tenant": current.tenant_id},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise OrbitError(
            503, "META_METRIC_PROFILE_REQUIRED", "请在Meta采集设置中选择已验证指标口径"
        )
    version = private_values().get("ORBIT_META_GRAPH_VERSION", "")
    begin, end = business_window(account["timezone_id"], datetime.now(UTC), days)
    return await MetaMetricCollectionStore().begin(
        session,
        current.actor_id,
        account["id"],
        row["profile_id"],
        row["adapter_version"],
        begin,
        end,
        version,
        request_id,
    )


class MetaSyncRuntime:
    def __init__(self, sessions, cipher, graph_version):
        self.sessions, self.cipher, self.graph_version = sessions, cipher, graph_version

    async def adapter(self, job):
        from orbit_api.account_platform import AccountReadFailure
        from orbit_api.meta_account_sources import load_connection
        from orbit_api.meta_read_adapter import MetaReadAdapter
        from orbit_api.meta_read_contract import MetaReadFailure

        try:
            async with self.sessions() as session, session.begin():
                source = await load_connection(
                    session,
                    self.cipher,
                    job["tenant_id"],
                    job["connection_id"],
                    job["connection_revision"],
                    self.graph_version,
                )
        except AccountReadFailure as error:
            if error.code in {"META_CONNECTION_SOURCE_CHANGED", "ACCOUNT_SYNC_SOURCE_CHANGED"}:
                raise OrbitError(409, "META_SOURCE_CHANGED", "采集连接来源已变化") from None
            if error.code == "META_CONNECTION_SOURCE_UNAVAILABLE":
                raise MetaReadFailure("META_TRANSIENT_FAILURE", retryable=True) from None
            raise
        return MetaReadAdapter(source.configuration)

    async def close_unavailable(self, candidate, code):
        """已撤权任务不能永久占据队首；只终止未被其他Worker持有的旧任务。"""
        import json

        from orbit_api.meta_metric_collection import MetaMetricCollectionStore

        allowed = {
            "PERMISSION_DENIED",
            "SESSION_REAUTH_REQUIRED",
            "META_REAUTH_REQUIRED",
            "META_SOURCE_CHANGED",
            "NOT_FOUND",
            "META_PROFILE_CHANGED",
            "METRICS_DATA_UNVERIFIED",
            "METRIC_PROFILE_SOURCE_CHANGED",
            "META_RETRY_EXHAUSTED",
        }
        if code not in allowed:
            return
        async with self.sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND "
                            "id=:id AND state NOT IN('PUBLISHED','FAILED') AND "
                            "(lease_expires_at IS NULL OR lease_expires_at<=UTC_TIMESTAMP(6)) "
                            "FOR UPDATE"
                        ),
                        {"tenant": candidate["tenant_id"], "id": candidate["id"]},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return
            checkpoint = (
                json.loads(row["checkpoint_json"])
                if isinstance(row["checkpoint_json"], str)
                else row["checkpoint_json"]
            )
            checkpoint = dict(checkpoint) | {"last_error": code}
            await session.execute(
                text(
                    "UPDATE orbit_meta_metric_job SET "
                    "state='FAILED',checkpoint_json=:checkpoint,updated_at=UTC_TIMESTAMP(6) "
                    "WHERE tenant_id=:tenant AND id=:id"
                ),
                {
                    "tenant": candidate["tenant_id"],
                    "id": candidate["id"],
                    "checkpoint": json.dumps(checkpoint),
                },
            )
            await MetaMetricCollectionStore()._event(session, row, "SOURCE_UNAVAILABLE")

    async def run_one(self):
        from orbit_api.meta_metric_worker import MetaMetricWorker
        from orbit_api.meta_read_contract import MetaReadFailure

        async with self.sessions() as session:
            jobs = (
                (
                    await session.execute(
                        text(
                            "SELECT tenant_id,id,actor_id FROM orbit_meta_metric_job WHERE "
                            "state "
                            "IN('INVENTORY','CAPTURING','SEALED','RETRY_WAIT','WAIT_REPORT') "
                            "AND next_run_at<=UTC_TIMESTAMP(6) AND (lease_expires_at IS NULL OR"
                            " lease_expires_at<=UTC_TIMESTAMP(6)) ORDER BY next_run_at,id LIMIT"
                            " 20"
                        )
                    )
                )
                .mappings()
                .all()
            )
        for job in jobs:
            try:
                return await MetaMetricWorker(self.sessions, self.adapter).run(
                    job["actor_id"], job["id"]
                )
            except MetaReadFailure:
                # Worker already persisted retry/terminal state; never turn transient HTTP
                # failure into process death. Unknown programming failures still propagate.
                continue
            except OrbitError as error:
                await self.close_unavailable(job, error.code)
                continue
        return None

    async def schedule(self):
        """账户逐个短事务入队；单一失效来源不阻断其他租户或账户。"""
        created = 0
        for table, key in (
            ("orbit_meta_sync_policy", "''"),
            ("orbit_meta_connection_sync_policy", "connection_id"),
        ):
            after_tenant, after_connection = "", ""
            while True:
                async with self.sessions() as session:
                    policies = (
                        (
                            await session.execute(
                                text(
                                    f"SELECT *,{key} AS policy_connection FROM {table} "
                                    f"WHERE scheduler_enabled=1 AND (tenant_id>:tenant OR "
                                    f"(tenant_id=:tenant AND {key}>:connection)) "
                                    f"ORDER BY tenant_id,{key} LIMIT 100"
                                ),
                                {"tenant": after_tenant, "connection": after_connection},
                            )
                        )
                        .mappings()
                        .all()
                    )
                if not policies:
                    break
                for policy in policies:
                    after_tenant = policy["tenant_id"]
                    after_connection = policy["policy_connection"]
                    try:
                        created += await self._schedule_policy(dict(policy))
                    except OrbitError:
                        continue
        return created

    async def _schedule_policy(self, policy):
        from orbit_api.account_access import clock, parameters, visible_clause
        from orbit_api.authorization import require_business_access

        connection_id = policy.get("connection_id")
        table = "orbit_meta_connection_sync_policy" if connection_id else "orbit_meta_sync_policy"
        policy_filter = " AND connection_id=:connection" if connection_id else ""
        account_filter = (
            " AND s.connection_id=:connection"
            if connection_id
            else " AND NOT EXISTS(SELECT 1 FROM orbit_meta_connection_sync_policy cp "
            "WHERE cp.tenant_id=s.tenant_id AND cp.connection_id=s.connection_id)"
        )
        now = datetime.now(UTC)
        slot = int(now.timestamp()) // 900
        daily = policy["last_daily_date"] != now.date()
        if not daily and policy["last_fast_slot"] == slot:
            return 0
        after, created = "", 0
        had_failure = False
        while True:
            async with self.sessions() as session, session.begin():
                current = await require_business_access(
                    session, policy["actor_id"], "accounts", "accounts.sync", acting_subject=False
                )
                if current.tenant_id != policy["tenant_id"]:
                    return created
                await clock(session, current)
                accounts = (
                    (
                        await session.execute(
                            text(
                                "SELECT a.* FROM orbit_ad_account a JOIN "
                                "orbit_meta_account_source s ON s.tenant_id=a.tenant_id AND "
                                "s.account_id=a.id JOIN orbit_meta_connection c ON "
                                "c.tenant_id=s.tenant_id AND c.id=s.connection_id AND "
                                "c.revision=s.connection_revision AND c.status='ACTIVE' AND "
                                "c.token_envelope IS NOT NULL AND (c.expires_at IS NULL OR "
                                "c.expires_at>UTC_TIMESTAMP(6)) AND (c.data_access_expires_at "
                                "IS NULL OR c.data_access_expires_at>UTC_TIMESTAMP(6)) WHERE "
                                "a.tenant_id=:tenant AND a.unbound_at IS NULL AND a.id>:after "
                                "AND ("
                                + visible_clause(current, "a")
                                + ")"
                                + account_filter
                                + " ORDER BY a.id LIMIT 100"
                            ),
                            parameters(current) | {"after": after, "connection": connection_id},
                        )
                    )
                    .mappings()
                    .all()
                )
            if not accounts:
                break
            for account in accounts:
                after = account["id"]
                try:
                    async with self.sessions() as session, session.begin():
                        current = await require_business_access(
                            session,
                            policy["actor_id"],
                            "accounts",
                            "accounts.sync",
                            acting_subject=False,
                        )
                        if current.tenant_id != policy["tenant_id"]:
                            return created
                        await clock(session, current, write=True)
                        latest = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT revision,scheduler_enabled FROM "
                                        f"{table} WHERE tenant_id=:tenant {policy_filter} FOR SHARE"
                                    ),
                                    {"tenant": current.tenant_id, "connection": connection_id},
                                )
                            )
                            .mappings()
                            .one()
                        )
                        if (
                            latest["revision"] != policy["revision"]
                            or not latest["scheduler_enabled"]
                        ):
                            return created
                        source = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT s.connection_id,"
                                        "p.connection_id override_connection "
                                        "FROM orbit_meta_account_source s LEFT JOIN "
                                        "orbit_meta_connection_sync_policy p "
                                        "ON p.tenant_id=s.tenant_id "
                                        "AND p.connection_id=s.connection_id WHERE "
                                        "s.tenant_id=:tenant AND s.account_id=:account FOR SHARE"
                                    ),
                                    {"tenant": current.tenant_id, "account": account["id"]},
                                )
                            )
                            .mappings()
                            .first()
                        )
                        if (
                            source is None
                            or (connection_id and source["connection_id"] != connection_id)
                            or (not connection_id and source["override_connection"] is not None)
                        ):
                            continue
                        identifier = str(
                            uuid5(
                                UUID(current.tenant_id),
                                "META:"
                                + (connection_id or "TENANT")
                                + ":"
                                + account["id"]
                                + ":"
                                + str(policy["revision"])
                                + ":"
                                + (
                                    "DAILY:" + now.date().isoformat()
                                    if daily
                                    else "FAST:" + str(slot)
                                ),
                            )
                        )
                        await enqueue_metrics(
                            session, current, account, identifier, days=90 if daily else 7
                        )
                        created += 1
                except OrbitError:
                    had_failure = True
                    continue
        if had_failure:
            return created
        async with self.sessions() as session, session.begin():
            await session.execute(
                text(
                    f"UPDATE {table} SET "
                    "last_fast_slot=:slot,last_daily_date=:day WHERE tenant_id=:tenant AND "
                    f"revision=:revision AND scheduler_enabled=1 {policy_filter}"
                ),
                {
                    "tenant": policy["tenant_id"],
                    "connection": connection_id,
                    "revision": policy["revision"],
                    "slot": slot,
                    "day": now.date() if daily else policy["last_daily_date"],
                },
            )
        return created

    async def initial_backfills(self):
        """首次导入后即排90日任务；不依赖定时开启，必须已有显式指标口径。"""
        from orbit_api.account_access import clock
        from orbit_api.authorization import require_business_access

        after, created = "", 0
        while True:
            async with self.sessions() as session:
                rows = (
                    (
                        await session.execute(
                            text(
                                "SELECT a.*,b.actor_id import_actor FROM orbit_ad_account a "
                                "JOIN orbit_meta_account_source s ON s.tenant_id=a.tenant_id "
                                "AND s.account_id=a.id JOIN orbit_account_import_row r ON "
                                "r.tenant_id=a.tenant_id AND r.account_id=a.id AND "
                                "r.state='SUCCEEDED' JOIN orbit_account_import b ON "
                                "b.tenant_id=r.tenant_id AND b.id=r.batch_id WHERE a.id>:after "
                                "AND a.unbound_at IS NULL AND (EXISTS(SELECT 1 FROM "
                                "orbit_meta_sync_policy p WHERE p.tenant_id=a.tenant_id) OR "
                                "EXISTS(SELECT 1 FROM orbit_meta_connection_sync_policy cp "
                                "WHERE cp.tenant_id=s.tenant_id AND "
                                "cp.connection_id=s.connection_id)) AND NOT EXISTS(SELECT 1 FROM "
                                "orbit_meta_metric_job j WHERE j.tenant_id=a.tenant_id AND "
                                "j.account_id=a.id) ORDER BY a.id LIMIT 100"
                            ),
                            {"after": after},
                        )
                    )
                    .mappings()
                    .all()
                )
            if not rows:
                return created
            for account in rows:
                after = account["id"]
                try:
                    async with self.sessions() as session, session.begin():
                        current = await require_business_access(
                            session,
                            account["import_actor"],
                            "accounts",
                            "accounts.sync",
                            acting_subject=False,
                        )
                        if current.tenant_id != account["tenant_id"]:
                            continue
                        await clock(session, current, write=True)
                        await enqueue_metrics(
                            session,
                            current,
                            account,
                            str(uuid5(UUID(account["id"]), "META_INITIAL_90_DAYS")),
                        )
                        created += 1
                except OrbitError:
                    continue
