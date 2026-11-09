"""049/056结果Store真实SQL技术专项；不是Meta发行、平台采集或公开API验收。"""

import asyncio
import base64
import hashlib
import json
import re
import time
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from metric_fact_schema_checks import MetricFactSqlFixture, digest
from metric_profile_query_checks import seed_metric_profile_browser_fixture
from metrics_query_read_checks import RegisteredSqlReadSource, guard_target, require
from metrics_query_read_checks import query as read_query
from sqlalchemy import URL, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_result_contract import (
    ExpectedEntityMembership,
    ExpectedUnitManifest,
    ExpectedUnitProvider,
    ExpectedUnitReceipt,
    QuerySourceIdentity,
)
from orbit_api.metrics_query_result_store import MetricsQueryResultStore, ResultBuildBudget
from orbit_api.metrics_query_store import (
    MetricsQueryStore,
    metric_query_hash,
    publication_validation_binding,
)
from orbit_api.metrics_scope_access import authorize_metric_scope

METRIC_QUERY_RESULT_CASES = (
    "pythonMetricsResultDefaultProviderNoneActualZeroSql",
    "pythonMetricsResultAllFourDatasetsSummaryDayThreeCurrenciesExactDtos",
    "pythonMetricsResult201AdsFourPageSizesCompleteFrozenTotals",
    "pythonMetricsResultLatestNameWholeWindowLiteralWildcardAndLeadingZeroId",
    "pythonMetricsResultSameKeyReplayAndDifferentIntentConflict",
    "pythonMetricsResultLeaseBusyRecoveryAndOldNonceCannotMutateNewGeneration",
    "pythonMetricsResultFailureOriginalCidDropAndPoolStateUnpolluted",
    "pythonMetricsResultCancelActualServerLockWaitDrainsOriginalCidWithinTwoSeconds",
)
METRIC_RESULT_CANCEL_REPORT = (
    Path(__file__).resolve().parents[1] / ".runtime" / "metric-result-cancel-diagnostic.json"
)
# MySQL8.4 trx0i_s.cc按最后一次读取时间保护100ms缓存，20ms轮询会使旧缓存常驻。
TRX_OBSERVER_IDLE_SECONDS = 0.125


async def fresh_trx_observer_window(*, sleep=asyncio.sleep):
    """只调整采样节奏；调用方原cancel_at+2s截止与双零断言不变。"""
    await sleep(TRX_OBSERVER_IDLE_SECONDS)


def query(profile_id, **changes):
    return read_query(
        {"id": profile_id}, **({"date_from": "2026-01-01", "date_to": "2026-01-02"} | changes)
    )


def expected_table(value):
    if type(value) is not str or re.fullmatch(r"it_metric_expect_[a-f0-9]{16}", value) is None:
        raise ValueError("预期技术登记表名不属于本轮随机目标")
    return value


def stream_hash(records):
    value = hashlib.sha256()
    for record in records:
        value.update(canonical(record.record()).encode() + b"\n")
    return value.hexdigest()


def safe_cancel_diagnostic(row, *, transactions, waits, connection, cleanup_state):
    """只输出固定枚举/计数；绝不读取PROCESSLIST_INFO或完整SQL。"""
    command, state, event_name, timeout = row or (None, None, None, None)
    return {
        "stage": "metric_result_cancel_original_connection",
        "command": command
        if command in {"Sleep", "Query", "Killed"}
        else "ABSENT"
        if row is None
        else "OTHER",
        "state": state
        if state
        in {
            "executing",
            "statistics",
            "Sending data",
            "System lock",
            "Waiting for table metadata lock",
        }
        else "NONE"
        if not state
        else "OTHER",
        "wait_event": event_name
        if type(event_name) is str and re.fullmatch(r"[A-Za-z0-9_/]{1,160}", event_name)
        else None,
        "session_lock_wait_seconds": int(timeout)
        if type(timeout) in {int, str} and str(timeout).isdigit()
        else None,
        "remaining_transactions": transactions,
        "remaining_lock_waits": waits,
        "client_invalidated": bool(connection.invalidated),
        "client_closed": bool(connection.closed),
        "cleanup_state": cleanup_state
        if cleanup_state in {"PENDING", "FAILED", "DROPPED"}
        else "OTHER",
    }


def save_cancel_diagnostic(value):
    """断言前独立安全JSON；主线无需读取可能含driver原文的整日志。"""
    target = METRIC_RESULT_CANCEL_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "recorded_at": datetime.now(UTC).isoformat(), "diagnostic": value},
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)


def encode_manifest(manifest):
    value = asdict(manifest)
    value["date_from"], value["date_to"] = (
        manifest.date_from.isoformat(),
        manifest.date_to.isoformat(),
    )
    return value


class RegisteredSqlExpected(ExpectedUnitProvider):
    """独立预登记完整原文与hash，不能把传入的manifest/head即刻echo成权威。"""

    kind = "ISOLATED_TEST"

    def __init__(self, table):
        self.table = expected_table(table)

    async def _read(self, session, scope, query_body, source_id):
        saved = (
            (
                await session.execute(
                    text(
                        "SELECT body_json,body_hash,revoked FROM "
                        + self.table
                        + " WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND query_hash=:hash AND source_id=:source FOR SHARE"
                    ),
                    {
                        "tenant": scope.current.tenant_id,
                        "actor": scope.current.actor_id,
                        "hash": metric_query_hash(query_body),
                        "source": source_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(saved) != 1 or saved[0]["revoked"] != 0:
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术预期来源未登记")
        try:
            raw = saved[0]["body_json"]
            body = json.loads(raw) if type(raw) is str else raw
            if (
                type(body) is not dict
                or set(body) != {"kind", "manifest", "units", "members"}
                or body["kind"] != "SQL_ONLY_NOT_PLATFORM"
                or digest(body) != saved[0]["body_hash"]
                or len(canonical(body).encode()) > 2 * 1024 * 1024
                or len(body["units"]) > 1000
                or len(body["members"]) > 1000
            ):
                raise ValueError
            value = dict(body["manifest"])
            value["source"] = QuerySourceIdentity(**value["source"])
            for field in ("date_from", "date_to"):
                value[field] = date.fromisoformat(value[field])
            manifest = ExpectedUnitManifest(**value)
            units, members = [], []
            for row in body["units"]:
                if type(row) is not list or len(row) != 13:
                    raise ValueError
                values = list(row)
                values[2] = date.fromisoformat(values[2])
                units.append(ExpectedUnitReceipt(*values))
            for row in body["members"]:
                if type(row) is not list or len(row) != 10:
                    raise ValueError
                values = list(row)
                values[2] = date.fromisoformat(values[2])
                values[9] = datetime.fromisoformat(values[9])
                members.append(ExpectedEntityMembership(*values))
            return manifest, tuple(units), tuple(members)
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术预期来源完整原文不符") from None

    async def prepare_manifest(self, session, scope, query_body, source):
        manifest = (await self._read(session, scope, query_body, source.publication_id))[0]
        if manifest.source != source:
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术预期来源版本不符")
        return manifest

    async def revalidate_manifest(self, session, scope, query_body, manifest):
        value = (await self._read(session, scope, query_body, manifest.source.publication_id))[0]
        if value != manifest:
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术预期来源已变化")
        return value

    async def iter_unit_batches(self, session, scope, query_body, manifest):
        value, units, _ = await self._read(
            session, scope, query_body, manifest.source.publication_id
        )
        if value != manifest:
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术预期根已变化")
        for index in range(0, len(units), 200):
            yield units[index : index + 200]

    async def iter_membership_batches(self, session, scope, query_body, manifest):
        value, _, members = await self._read(
            session, scope, query_body, manifest.source.publication_id
        )
        if value != manifest:
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术实体根已变化")
        for index in range(0, len(members), 200):
            yield members[index : index + 200]


def run_metrics_query_result_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    from config.asyncmy_compat import install_windows_asyncmy_compat

    install_windows_asyncmy_compat()
    fixture = MetricFactSqlFixture(admin, database)
    profile = seed_metric_profile_browser_fixture(admin, database)["profiles"][0]
    tenant, owner, team = fixture.tenant, fixture.owner, fixture.team
    sql = fixture.sql
    source_table = "it_metric_read_" + uuid4().hex[:16]
    expectation_table = expected_table("it_metric_expect_" + uuid4().hex[:16])
    gate_table = "it_metric_gate_" + uuid4().hex[:16]
    configuration = str(uuid4())
    with ExitStack() as cleanup:
        sql(
            "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,enabled,"
            "settings_json,secrets_json) "
            "VALUES(%s,%s,'METRICS',%s,1,'{}','{}')",
            (configuration, tenant, "SQL_ONLY_" + uuid4().hex[:12]),
        )
        sql(
            "CREATE TABLE "
            + source_table
            + "(tenant_id CHAR(36) NOT NULL,publication_id CHAR(36) NOT NULL,"
            "binding_json JSON NOT NULL,binding_hash CHAR(64) NOT NULL,"
            "revoked TINYINT NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,publication_id)) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
        )
        cleanup.callback(sql, "DROP TABLE " + source_table)
        sql(
            "CREATE TABLE "
            + expectation_table
            + "(tenant_id CHAR(36) NOT NULL,actor_id BIGINT NOT NULL,"
            "query_hash CHAR(64) NOT NULL,source_id CHAR(36) NOT NULL,"
            "body_json JSON NOT NULL,body_hash CHAR(64) NOT NULL,"
            "revoked TINYINT NOT NULL DEFAULT 0,"
            "PRIMARY KEY(tenant_id,actor_id,query_hash,source_id)) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
        )
        cleanup.callback(sql, "DROP TABLE " + expectation_table)
        sql("CREATE TABLE " + gate_table + "(id INT NOT NULL PRIMARY KEY)")
        cleanup.callback(sql, "DROP TABLE " + gate_table)
        sql("INSERT INTO " + gate_table + " VALUES(1)")
        accounts = [fixture.account() for _ in range(3)]
        trees = [fixture.tree(account) for account in accounts]
        for account, currency in zip(accounts, ("USD", "EUR", "GBP"), strict=True):
            sql(
                "UPDATE orbit_ad_account SET currency=%s WHERE tenant_id=%s AND id=%s",
                (currency, tenant, account),
            )
        ads = [trees[0][3]]
        for index in range(1, 201):
            ads.append(
                fixture.dimension(
                    accounts[0], "AD", parent=trees[0][2], name=f"分页技术广告{index:03}"
                )
            )
        renamed = dict(ads[0]) | {"id": str(uuid4()), "name": "新名称字面%_!"}
        renamed["content_hash"] = digest(
            {key: value for key, value in renamed.items() if key not in {"id", "content_hash"}}
        )
        fixture.insert("orbit_metric_entity_snapshot", renamed)
        publication = fixture.insert(
            "orbit_metric_publication",
            {
                "tenant_id": tenant,
                "id": str(uuid4()),
                "profile_id": profile["id"],
                "profile_version": profile["version"],
                "profile_hash": digest(profile),
                "authority_kind": "ISOLATED_TEST",
                "source_config_id": configuration,
                "source_config_revision": 1,
                "source_proof_json": '{"kind":"SQL_ONLY_NOT_PLATFORM"}',
                "expected_cell_count": 4,
                "expected_cells_hash": "a" * 64,
                "capture_sequence_max": 120,
                "publisher_actor_id": 1,
                "request_id": str(uuid4()),
                "created_at": fixture.now,
            },
        )
        for day in ("2026-01-01", "2026-01-02"):
            selected = fixture.cell(publication, trees[0], day=day)
            sql(
                "UPDATE orbit_metric_capture_cell SET expected_entity_count=201,fact_count=201 "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, selected["id"]),
            )
            for index, ad in enumerate(ads):
                chosen = renamed if index == 0 and day.endswith("02") else ad
                fixture.fact(selected, trees[0][:3] + [chosen])
            empty = fixture.cell(publication, trees[1], day=day, empty=True)
            sql(
                "UPDATE orbit_metric_capture_cell SET currency='EUR' WHERE tenant_id=%s AND id=%s",
                (tenant, empty["id"]),
            )
        generation = fixture.publish(publication, facts=402)
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM orbit_metric_publication WHERE tenant_id=%s AND id=%s",
                (tenant, publication["id"]),
            )
            head = dict(zip((col[0] for col in cursor.description), cursor.fetchone(), strict=True))
        admin.commit()
        binding = publication_validation_binding(head)
        sql(
            "INSERT INTO "
            + source_table
            + "(tenant_id,publication_id,binding_json,binding_hash) VALUES(%s,%s,%s,%s)",
            (tenant, publication["id"], canonical(binding), digest(binding)),
        )

        async def run():
            engine = create_async_engine(
                URL.create(
                    "mysql+asyncmy",
                    username="root",
                    password="",
                    host="127.0.0.1",
                    port=13306,
                    database=database,
                ),
                echo=False,
                hide_parameters=True,
                pool_size=2,
                max_overflow=0,
            )
            budget = ResultBuildBudget(100000, 10000, 64 * 1024 * 1024, 32 * 1024 * 1024, 45)
            tokens = DirectoryTokens(
                CredentialCipher("fixture", {"fixture": base64.b64encode(b"r" * 32).decode()})
            )
            source = RegisteredSqlReadSource(source_table)
            expected = RegisteredSqlExpected(expectation_table)
            store = MetricsQueryResultStore(
                MetricsQueryStore(source), expected, budget=budget, tokens=tokens
            )
            authorization = headers.get("Authorization", "")

            async def register(body):
                async with AsyncSession(engine) as session, session.begin():
                    scope = await authorize_metric_scope(session, 1, None)
                kind = body["dataset"]
                memberships, units = [], []
                numeric = re.fullmatch(r"[0-9]{1,64}", body["q"]) is not None
                for account_index, tree in enumerate(trees):
                    for day_text in (body["date_from"], body["date_to"]):
                        day = date.fromisoformat(day_text)
                        entity_rows = (
                            (
                                ads
                                if kind == "AD"
                                else [tree[{"ACCOUNT": 0, "CAMPAIGN": 1, "ADSET": 2}[kind]]]
                            )
                            if account_index == 0
                            else (
                                []
                                if account_index == 1 and kind != "ACCOUNT"
                                else [
                                    tree[{"ACCOUNT": 0, "CAMPAIGN": 1, "ADSET": 2, "AD": 3}[kind]]
                                ]
                            )
                        )
                        chosen_rows = []
                        for dimension in entity_rows:
                            latest = (
                                renamed
                                if account_index == 0
                                and dimension["entity_id"] == ads[0]["entity_id"]
                                and kind == "AD"
                                else dimension
                            )
                            if (
                                body["q"]
                                and body["q"] not in latest["name"]
                                and not (numeric and body["q"] == latest["external_id"])
                            ):
                                continue
                            chosen = (
                                renamed
                                if latest is renamed and day_text.endswith("02")
                                else dimension
                            )
                            chosen_rows.append(
                                ExpectedEntityMembership(
                                    tenant,
                                    tree[0]["account_id"],
                                    day,
                                    profile["id"],
                                    profile["version"],
                                    kind,
                                    chosen["entity_id"],
                                    chosen["id"],
                                    120,
                                    fixture.now.replace(tzinfo=UTC),
                                )
                            )
                        chosen_rows.sort(key=lambda item: item.key())
                        memberships.extend(chosen_rows)
                        units.append(
                            ExpectedUnitReceipt(
                                tenant,
                                tree[0]["account_id"],
                                day,
                                profile["id"],
                                profile["version"],
                                owner,
                                team,
                                ("USD", "EUR", "GBP")[account_index],
                                "Asia/Shanghai",
                                tree[0]["id"],
                                1,
                                len(chosen_rows),
                                stream_hash(chosen_rows),
                            )
                        )
                units.sort(key=lambda item: item.key())
                memberships.sort(key=lambda item: item.key())
                manifest = ExpectedUnitManifest(
                    QuerySourceIdentity(
                        tenant,
                        publication["id"],
                        generation,
                        profile["id"],
                        profile["version"],
                        digest(profile),
                        "ISOLATED_TEST",
                    ),
                    1,
                    scope.current.subject_id,
                    scope.auth_version,
                    scope.auth_fingerprint,
                    metric_query_hash(body),
                    kind,
                    date.fromisoformat(body["date_from"]),
                    date.fromisoformat(body["date_to"]),
                    None,
                    None,
                    None,
                    len(units),
                    stream_hash(units),
                    len(memberships),
                    stream_hash(memberships),
                )
                saved = {
                    "kind": "SQL_ONLY_NOT_PLATFORM",
                    "manifest": encode_manifest(manifest),
                    "units": [item.record() for item in units],
                    "members": [item.record() for item in memberships],
                }
                sql(
                    "INSERT IGNORE INTO "
                    + expectation_table
                    + "(tenant_id,actor_id,query_hash,source_id,body_json,body_hash) "
                    "VALUES(%s,1,%s,%s,%s,%s)",
                    (
                        tenant,
                        manifest.query_hash,
                        publication["id"],
                        canonical(saved),
                        digest(saved),
                    ),
                )
                return manifest

            async def execute(body, *, target=store, key=None):
                await register(body)
                return await target.run(
                    engine, 1, body, key or str(uuid4()), str(uuid4()), authorization
                )

            async def collect(body, *, target=store):
                first = await execute(body, target=target)
                items = list(first["items"])
                cursor, pages = first["next_cursor"], 1
                while cursor is not None:
                    value = await target.run(
                        engine,
                        1,
                        body | {"cursor": cursor},
                        str(uuid4()),
                        str(uuid4()),
                        authorization,
                    )
                    require(
                        value["query_snapshot_id"] == first["query_snapshot_id"]
                        and value["totals"] == first["totals"],
                        "metric_result_frozen_page",
                    )
                    items.extend(value["items"])
                    cursor, pages = value["next_cursor"], pages + 1
                    require(pages <= 100, "metric_result_fixture_page_bound")
                return first, items

            async def expect_error(call, status, code=None):
                try:
                    await call()
                except OrbitError as error:
                    require(
                        error.status == status and (code is None or error.code == code),
                        "metric_result_expected_error",
                    )
                    return
                raise AssertionError("metric_result_expected_rejection")

            async def pool_state():
                async with engine.connect() as connection:
                    return tuple(
                        (
                            await connection.execute(
                                text(
                                    "SELECT @@autocommit,@@transaction_isolation,@@sql_mode,"
                                    "@@SESSION.innodb_lock_wait_timeout"
                                )
                            )
                        ).one()
                    )

            async def no_temp(stage):
                async with engine.connect() as connection:
                    for kind, name in stage.names.items():
                        if kind not in stage.created:
                            continue
                        try:
                            await connection.execute(text("SELECT 1 FROM " + name + " LIMIT 1"))
                        except DBAPIError as error:
                            require(
                                error.orig.args[0] == 1146, "metric_result_next_pool_table_absent"
                            )
                            await connection.rollback()
                        else:
                            raise AssertionError("metric_result_temp_pool_leak")

            try:
                counts = {"sql": 0}

                def count_sql(*args):
                    counts["sql"] += 1

                event.listen(engine.sync_engine, "before_cursor_execute", count_sql)
                await expect_error(
                    lambda: MetricsQueryResultStore().run(
                        engine, 1, query(profile["id"]), str(uuid4()), str(uuid4()), authorization
                    ),
                    503,
                )
                require(counts["sql"] == 0, "metric_result_default_zero_sql")
                cases.append(METRIC_QUERY_RESULT_CASES[0])
                for kind in ("ACCOUNT", "CAMPAIGN", "ADSET", "AD"):
                    for granularity in ("SUMMARY", "DAY"):
                        body = query(profile["id"], dataset=kind, granularity=granularity)
                        first, items = await collect(body)
                        totals = {item["currency"]: item for item in first["totals"]}
                        require(
                            set(totals) == {"USD", "EUR", "GBP"}, "metric_result_three_currencies"
                        )
                        require(
                            totals["USD"]["values"]["spend"] == "48240"
                            and totals["USD"]["ad_count"] == 201,
                            "metric_result_whole_totals_dedup",
                        )
                        require(
                            totals["EUR"]["values"]["spend"] == "0"
                            and totals["EUR"]["coverage"] == "1",
                            "metric_result_verified_empty_zero",
                        )
                        require(
                            totals["GBP"]["values"]["spend"] is None
                            and totals["GBP"]["coverage"] == "0"
                            and first["missing_count"] == 2,
                            "metric_result_missing_is_not_zero",
                        )
                        expected_rows = (
                            (201 if kind == "AD" else 1) + 1 + (1 if kind == "ACCOUNT" else 0)
                        )
                        require(
                            len(items) == expected_rows * (2 if granularity == "DAY" else 1),
                            "metric_result_dataset_grain_count",
                        )
                        require(
                            all(len(item) == 15 and len(item["values"]) == 12 for item in items),
                            "metric_result_original_fields",
                        )
                        require(
                            all(
                                item["quality"] == "UNKNOWN"
                                for item in items
                                if item["currency"] == "GBP"
                            ),
                            "metric_result_unknown_name_proof",
                        )
                cases.append(METRIC_QUERY_RESULT_CASES[1])
                sets = []
                for size in (20, 50, 100, 200):
                    _, items = await collect(query(profile["id"], page_size=size))
                    identifiers = [item["entity_id"] for item in items]
                    require(
                        len(identifiers) == 202 and len(set(identifiers)) == 202,
                        "metric_result_four_page_complete",
                    )
                    sets.append(identifiers)
                require(
                    all(value == sets[0] for value in sets), "metric_result_four_page_order_same"
                )
                cases.append(METRIC_QUERY_RESULT_CASES[2])
                for term in ("新名称", "%_!", renamed["external_id"]):
                    first, items = await collect(query(profile["id"], q=term))
                    require(
                        len(items) == 1
                        and items[0]["entity_id"] == renamed["entity_id"]
                        and items[0]["values"]["spend"] == "240",
                        "metric_result_q_keeps_two_days",
                    )
                    require(items[0]["name"] == renamed["name"], "metric_result_q_latest_name")
                cases.append(METRIC_QUERY_RESULT_CASES[3])
                body, key = query(profile["id"]), str(uuid4())
                first = await execute(body, key=key)
                again = await execute(body, key=key)
                require(
                    first["query_snapshot_id"] == again["query_snapshot_id"]
                    and first["items"] == again["items"],
                    "metric_result_same_key_same_snapshot",
                )
                await expect_error(
                    lambda: store.run(
                        engine, 1, body | {"page_size": 50}, key, str(uuid4()), authorization
                    ),
                    409,
                    "IDEMPOTENCY_CONFLICT",
                )
                cases.append(METRIC_QUERY_RESULT_CASES[4])
                await register(body)
                async with engine.connect() as connection, AsyncSession(bind=connection) as session:
                    async with session.begin():
                        intent = await store.prepare(session, 1, body, str(uuid4()), str(uuid4()))
                    async with session.begin():
                        old = await store.claim(session, 1, intent["query_id"])
                    async with session.begin():
                        await expect_error(
                            lambda: store.claim(session, 1, intent["query_id"]),
                            409,
                            "METRICS_QUERY_BUSY",
                        )
                    sql(
                        "UPDATE orbit_metric_query_snapshot SET "
                        "lease_until=DATE_SUB(UTC_TIMESTAMP(3),INTERVAL 1 SECOND) "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, intent["query_id"]),
                    )
                    async with session.begin():
                        current = await store.claim(session, 1, intent["query_id"])
                    require(current is not old, "metric_result_new_nonce_ticket")
                    async with session.begin():
                        await expect_error(
                            lambda: store.fail(session, old, "METRICS_DATA_UNVERIFIED"),
                            409,
                            "METRICS_BUILD_CLAIM_LOST",
                        )
                cases.append(METRIC_QUERY_RESULT_CASES[5])
                initial_state = await pool_state()

                class Failed(MetricsQueryResultStore):
                    async def aggregate_stage(self, session, handle):
                        self.report = self._stages[handle][1]
                        self.query_id = self._claims[self._stages[handle][0]].query_id
                        await super().aggregate_stage(session, handle)

                    async def publish(self, session, handle):
                        await super().publish(session, handle)
                        raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "固定故障技术夹具")

                failed = Failed(store.read, expected, budget=budget, tokens=tokens)
                await expect_error(
                    lambda: execute(body, target=failed), 503, "METRICS_DATA_UNVERIFIED"
                )
                require(
                    failed.report.cleanup_verified and failed.report.cleanup_state == "DROPPED",
                    "metric_result_original_cid_cleanup",
                )
                failed_header = sql(
                    "SELECT state,row_count,totals_count FROM orbit_metric_query_snapshot "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, failed.query_id),
                    fetch=True,
                )
                require(failed_header == (("FAILED", 0, 0),), "metric_result_ready_rollback_atomic")
                for table in (
                    "orbit_metric_query_sorted_row",
                    "orbit_metric_query_total",
                    "orbit_metric_query_expected_account",
                ):
                    require(
                        sql(
                            "SELECT COUNT(*) FROM " + table + " WHERE tenant_id=%s AND query_id=%s",
                            (tenant, failed.query_id),
                            fetch=True,
                        )[0][0]
                        == 0,
                        "metric_result_no_partial_children",
                    )
                require(
                    sql(
                        "SELECT COUNT(*) FROM information_schema.innodb_trx "
                        "WHERE trx_mysql_thread_id=%s",
                        (failed.report.connection_id,),
                        fetch=True,
                    )[0][0]
                    == 0,
                    "metric_result_failure_no_trx",
                )
                await no_temp(failed.report)
                require(await pool_state() == initial_state, "metric_result_failure_pool_settings")
                cases.append(METRIC_QUERY_RESULT_CASES[6])
                started = asyncio.Event()

                class Cancelled(MetricsQueryResultStore):
                    async def aggregate_stage(self, session, handle):
                        self.report = self._stages[handle][1]
                        started.set()
                        await session.execute(
                            text("SELECT id FROM " + gate_table + " WHERE id=1 FOR UPDATE")
                        )

                cancelled = Cancelled(store.read, expected, budget=budget, tokens=tokens)
                # 观察连接独立autocommit，避免holder事务的read-view干扰退出诊断。
                import pymysql

                observer = cleanup.enter_context(
                    pymysql.connect(
                        host="127.0.0.1",
                        port=13306,
                        user="root",
                        password="",
                        database=database,
                        autocommit=True,
                        read_timeout=2,
                        write_timeout=2,
                    )
                )
                guard_target(observer, database)
                admin.begin()
                with admin.cursor() as cursor:
                    cursor.execute("SELECT id FROM " + gate_table + " WHERE id=1 FOR UPDATE")
                # body已独立登记；持gate期间绝不能再调用会admin.commit的register/sql助手。
                task = asyncio.create_task(
                    cancelled.run(engine, 1, body, str(uuid4()), str(uuid4()), authorization)
                )
                try:
                    await asyncio.wait_for(started.wait(), 30)
                    cid = cancelled.report.connection_id
                    deadline = time.monotonic() + 2
                    while True:
                        with observer.cursor() as cursor:
                            cursor.execute(
                                "SELECT COUNT(*) FROM performance_schema.data_lock_waits w "
                                "JOIN performance_schema.threads t "
                                "ON t.THREAD_ID=w.REQUESTING_THREAD_ID WHERE t.PROCESSLIST_ID=%s",
                                (cid,),
                            )
                            waiting = cursor.fetchone()[0]
                        if waiting:
                            break
                        require(
                            time.monotonic() < deadline, "metric_result_actual_server_wait_observed"
                        )
                        await asyncio.sleep(0.02)
                    with observer.cursor() as cursor:
                        cursor.execute(
                            "SELECT v.VARIABLE_VALUE FROM performance_schema.variables_by_thread v "
                            "JOIN performance_schema.threads t ON t.THREAD_ID=v.THREAD_ID "
                            "WHERE t.PROCESSLIST_ID=%s "
                            "AND v.VARIABLE_NAME='innodb_lock_wait_timeout'",
                            (cid,),
                        )
                        configured = cursor.fetchone()
                    require(
                        configured is not None and int(configured[0]) == 1,
                        "metric_result_actual_owned_session_lock_wait_one_second",
                    )
                    cancel_at = time.monotonic()
                    task.cancel()
                    done, _ = await asyncio.wait({task}, timeout=2)
                    require(task in done, "metric_result_cancel_client_drain_2s")
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("metric_result_cancel_not_cancelled")
                    while True:
                        # 第一次也留空窗，避免把取消前读取的旧cache零/非零当作当前证明。
                        await fresh_trx_observer_window()
                        with observer.cursor() as cursor:
                            cursor.execute(
                                "SELECT COUNT(*) FROM performance_schema.threads "
                                "WHERE PROCESSLIST_ID=%s",
                                (cid,),
                            )
                            threads = cursor.fetchone()[0]
                            cursor.execute(
                                "SELECT COUNT(*) FROM information_schema.innodb_trx "
                                "WHERE trx_mysql_thread_id=%s",
                                (cid,),
                            )
                            active = cursor.fetchone()[0]
                        if threads == 0 and active == 0:
                            break
                        if time.monotonic() - cancel_at >= 2:
                            with observer.cursor() as cursor:
                                cursor.execute(
                                    "SELECT t.PROCESSLIST_COMMAND,t.PROCESSLIST_STATE,e.EVENT_NAME,"
                                    "v.VARIABLE_VALUE FROM performance_schema.threads t "
                                    "LEFT JOIN performance_schema.events_waits_current e "
                                    "ON e.THREAD_ID=t.THREAD_ID "
                                    "LEFT JOIN performance_schema.variables_by_thread v "
                                    "ON v.THREAD_ID=t.THREAD_ID "
                                    "AND v.VARIABLE_NAME='innodb_lock_wait_timeout' "
                                    "WHERE t.PROCESSLIST_ID=%s",
                                    (cid,),
                                )
                                server_row = cursor.fetchone()
                                cursor.execute(
                                    "SELECT COUNT(*) FROM performance_schema.data_lock_waits w "
                                    "JOIN performance_schema.threads t "
                                    "ON t.THREAD_ID=w.REQUESTING_THREAD_ID "
                                    "WHERE t.PROCESSLIST_ID=%s",
                                    (cid,),
                                )
                                waits = cursor.fetchone()[0]
                            save_cancel_diagnostic(
                                safe_cancel_diagnostic(
                                    server_row,
                                    transactions=active,
                                    waits=waits,
                                    connection=cancelled.report.connection,
                                    cleanup_state=cancelled.report.cleanup_state,
                                )
                            )
                        require(
                            time.monotonic() - cancel_at < 2,
                            "metric_result_original_server_cid_exit_2s",
                        )
                    require(
                        time.monotonic() - cancel_at < 2 and not cancelled.report.cleanup_verified,
                        "metric_result_cancel_proof_not_fake_drop",
                    )
                finally:
                    # holder只在成功证据或已失败之后释放，绝不以释放制造drain通过。
                    admin.rollback()
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, 6)
                        except (asyncio.CancelledError, Exception):
                            pass
                await no_temp(cancelled.report)
                require(await pool_state() == initial_state, "metric_result_cancel_pool_settings")
                cases.append(METRIC_QUERY_RESULT_CASES[7])
                return {
                    "kind": "SQL_ONLY_NOT_PLATFORM",
                    "ads": 201,
                    "datasets": 4,
                    "currencies": 3,
                    "original_server_cid_drained": True,
                }
            finally:
                await engine.dispose()

        return asyncio.run(run())
