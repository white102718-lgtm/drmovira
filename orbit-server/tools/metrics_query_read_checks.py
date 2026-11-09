"""窄READ真实MySQL/身份专项；独立SQL登记证据不是生产指标发行或平台核验。"""

import asyncio
import json
import re
from contextlib import ExitStack
from uuid import uuid4

from sqlalchemy import URL, bindparam, event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit_api.errors import OrbitError
from orbit_api.metrics_query_store import (
    MetricCellBatch,
    MetricReadContext,
    MetricReadSourceProvider,
    MetricsQueryStore,
    PublicationValidationReceipt,
    publication_validation_binding,
)

METRIC_QUERY_READ_CASES = (
    "pythonMetricReadDefaultNoProviderActualSessionZeroSql503",
    "pythonMetricReadRootUserTeamApplyFrozenHistoricalOwnerNotCurrentAccount",
    "pythonMetricReadOriginal501ScopeWithoutAccountReadAndEmptyIsNotUnrestricted",
    "pythonMetricRead120EmptyOmissionLate110AndChangedOwnerNeverBackfill",
    "pythonMetricReadEveryOldPublicationNeedsExactRegisteredReceiptNoPartialBatch",
    "pythonMetricReadActualChineseLiteralContainsAndLeadingZeroExactId",
    "pythonMetricReadAllOriginalFactDimensionFieldsAndNullableExactDecimalSources",
    "pythonMetricReadPrivateHandleBatchSameStoreSessionAndTransactionBoundaries",
    "pythonMetricReadCurrentMonitorScopeAndProfileRevocationFailClosed",
    "pythonMetricReadActualTechnicalSourceConfigStateRevisionAndReceiptBinding",
)


def guard_target(admin, database):
    if (
        type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("READ专项仅允许127.0.0.1:13306本轮UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("READ专项实际数据库不匹配")
    admin.commit()


def evidence_table(value):
    if type(value) is not str or re.fullmatch(r"it_metric_read_[a-f0-9]{16}", value) is None:
        raise ValueError("只允许本工具随机证据表标识")
    return value


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def query(profile, **changes):
    return {
        "date_from": "2026-01-01",
        "date_to": "2026-01-04",
        "dataset": "AD",
        "metric_profile_id": profile["id"],
        "scope_snapshot_id": None,
        "channel_id": None,
        "operator_user_id": None,
        "q": "",
        "sort": "spend",
        "direction": "DESC",
        "cursor": None,
        "page_size": 20,
        "granularity": "SUMMARY",
        **changes,
    }


class RegisteredSqlReadSource(MetricReadSourceProvider):
    """仅技术SQL：返回预登记完整tuple，绝不把待查头现算hash当成功回执。"""

    kind = "ISOLATED_TEST"

    def __init__(self, table):
        self.table = evidence_table(table)
        self.checked_ids = set()
        self.batches = []

    async def verify_publications(self, session, scope, original_query, heads):
        from metric_fact_schema_checks import digest

        identifiers = tuple(sorted(item["id"] for item in heads))
        require(1 <= len(identifiers) <= 200, "metric_read_receipt_batch_bound")
        self.checked_ids.update(identifiers)
        self.batches.append(identifiers)
        statement = text(
            "SELECT publication_id,binding_json,binding_hash,revoked FROM "
            + self.table
            + " WHERE tenant_id=:tenant AND publication_id IN :ids ORDER BY "
            "publication_id FOR SHARE"
        ).bindparams(bindparam("ids", expanding=True))
        registered = (
            (
                await session.execute(
                    statement,
                    {
                        "tenant": scope.current.tenant_id,
                        "ids": identifiers,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(registered) != len(identifiers):
            raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术来源未完整登记")
        incoming = {item["id"]: item for item in heads}
        receipts = []
        for saved in registered:
            try:
                binding = json.loads(saved["binding_json"])
            except (TypeError, ValueError):
                raise OrbitError(
                    503, "METRICS_DATA_UNVERIFIED", "技术来源登记格式不符合约定"
                ) from None
            expected = publication_validation_binding(incoming[saved["publication_id"]])
            if (
                saved["revoked"] != 0
                or type(binding) is not list
                or digest(binding) != saved["binding_hash"]
                or len(binding) != len(expected)
                or any(
                    type(left) is not type(right) or left != right
                    for left, right in zip(binding, expected, strict=True)
                )
            ):
                raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术来源登记已变化")
            head = incoming[saved["publication_id"]]
            configuration = (
                (
                    await session.execute(
                        text(
                            "SELECT section,enabled,revision,verification_status FROM "
                            "orbit_system_configuration "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        {"tenant": scope.current.tenant_id, "id": head["source_config_id"]},
                    )
                )
                .mappings()
                .first()
            )
            if (
                configuration is None
                or configuration["section"] != "METRICS"
                or configuration["enabled"] != 1
                or configuration["revision"] != head["source_config_revision"]
                or configuration["verification_status"] != "UNTESTED"
            ):
                raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "技术来源配置已变化")
            receipts.append(PublicationValidationReceipt(tuple(binding)))
        return tuple(receipts)


def run_metrics_query_read_checks(
    client, admin, headers, password, cache, database, cases, *, identities=None
):
    guard_target(admin, database)
    from account_scope_visibility_plan_checks import prepare_plan_identities
    from config.asyncmy_compat import install_windows_asyncmy_compat
    from metric_fact_schema_checks import TABLE_COLUMNS, MetricFactSqlFixture, digest
    from metric_profile_query_checks import seed_metric_profile_browser_fixture

    install_windows_asyncmy_compat()
    fixture = MetricFactSqlFixture(admin, database)
    tenant = fixture.tenant
    if identities is None:
        identities = prepare_plan_identities(client, admin, headers, password, cache)
    require(
        set(identities) == {"SUPER_ADMIN", "TEAM_ADMIN", "USER"}, "metric_read_three_identities"
    )
    user, manager = identities["USER"], identities["TEAM_ADMIN"]
    seeded = seed_metric_profile_browser_fixture(admin, database)
    profile = seeded["profiles"][0]
    profile_hash = digest(profile)
    table = evidence_table("it_metric_read_" + uuid4().hex[:16])
    sql = fixture.sql

    def checked(response, status):
        require(response.status_code == status, "metric_read_fixture_http_status")
        return response.json()

    with ExitStack() as cleanup:
        cap = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
        monitor_role = checked(
            client.post(
                "/api/v1/roles",
                headers=headers
                | {
                    "X-CSRF-Token": cap["csrf_token"],
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "name": "READ技术-" + uuid4().hex[:12],
                    "menu_codes": ["monitor"],
                    "permission_codes": ["monitor.read"],
                },
            ),
            201,
        )
        native_role = sql(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, monitor_role["id"]),
            fetch=True,
        )[0][0]
        for identity in (user, manager):
            sql(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (identity["actor_id"], native_role),
            )
        unmanaged_team = str(uuid4())
        sql(
            "INSERT INTO orbit_business_team(tenant_id,id,name,enabled,revision,created_at) "
            "VALUES(%s,%s,%s,1,1,UTC_TIMESTAMP(3))",
            (tenant, unmanaged_team, "READ技术-" + uuid4().hex[:12]),
        )
        source_configuration = str(uuid4())
        sql(
            "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,enabled,"
            "settings_json,"
            "secrets_json) VALUES(%s,%s,'METRICS',%s,1,'{}','{}')",
            (source_configuration, tenant, "SQL_ONLY_UNTESTED_" + uuid4().hex[:12]),
        )
        sql(
            "CREATE TABLE "
            + table
            + "(tenant_id CHAR(36) NOT NULL,publication_id CHAR(36) NOT NULL,"
            "binding_json JSON NOT NULL,binding_hash CHAR(64) NOT NULL,revoked TINYINT "
            "NOT NULL DEFAULT 0,"
            "PRIMARY KEY(tenant_id,publication_id)) CHARACTER SET utf8mb4 "
            "COLLATE utf8mb4_0900_as_cs"
        )

        cleanup.callback(sql, "DROP TABLE " + table)
        publications = []

        def publication(*, sequence=120, count=1):
            value = fixture.insert(
                "orbit_metric_publication",
                {
                    "tenant_id": tenant,
                    "id": str(uuid4()),
                    "profile_id": profile["id"],
                    "profile_version": profile["version"],
                    "profile_hash": profile_hash,
                    "authority_kind": "ISOLATED_TEST",
                    "source_config_id": source_configuration,
                    "source_config_revision": 1,
                    "source_proof_json": json.dumps({"kind": "SQL_ONLY_NOT_PLATFORM"}),
                    "expected_cell_count": count,
                    "expected_cells_hash": "a" * 64,
                    "capture_sequence_max": sequence,
                    "publisher_actor_id": 1,
                    "request_id": str(uuid4()),
                    "created_at": fixture.now,
                },
            )
            publications.append(value)
            return value

        def record(publication, facts):
            fixture.publish(publication, facts=facts)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM orbit_metric_publication WHERE tenant_id=%s AND id=%s",
                    (tenant, publication["id"]),
                )
                names = [column[0] for column in cursor.description]
                head = dict(zip(names, cursor.fetchone(), strict=True))
            admin.commit()
            binding = publication_validation_binding(head)
            # 在任何Store查询前独立登记实际fixture完整头，后续只准从该登记返回原tuple。
            sql(
                "INSERT INTO " + table + "(tenant_id,publication_id,binding_json,binding_hash) "
                "VALUES(%s,%s,%s,%s)",
                (tenant, head["id"], json.dumps(binding), digest(binding)),
            )

        # 四种历史范围，与当前账户owner有意不同；不是平台归属事实证明。
        accounts = [fixture.account() for _ in range(4)]
        trees = [
            fixture.tree(identifier, name="前段_字面%中间!后段" if index == 0 else None)
            for index, identifier in enumerate(accounts)
        ]
        sql(
            "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id IN(%s,%s)",
            (user["owner_user_id"], tenant, accounts[0], accounts[1]),
        )
        principal = publication(count=4)
        owners = [
            (user["owner_user_id"], user["owner_team_id"]),
            (fixture.owner, fixture.team),
            (fixture.owner, unmanaged_team),
            (manager["owner_user_id"], unmanaged_team),
        ]
        principal_facts = []
        for index, (tree, (owner, team)) in enumerate(zip(trees, owners, strict=True)):
            selected = fixture.cell(principal, tree)
            sql(
                "UPDATE orbit_metric_capture_cell SET owner_user_id=%s,owner_team_id=%s "
                "WHERE tenant_id=%s AND id=%s",
                (owner, team, tenant, selected["id"]),
            )
            changes = (
                {
                    "spend": None,
                    "impressions": "0.000000",
                    "clicks": None,
                    "registrations": "1.250000",
                    "purchases": "0.000000",
                    "purchase_value": None,
                }
                if index == 1
                else {}
            )
            principal_facts.append(fixture.fact(selected, tree, changes=changes))
        record(principal, 4)
        old = publication(sequence=100, count=2)
        for day in ("2026-01-02", "2026-01-03"):
            selected = fixture.cell(old, trees[0], sequence=100, day=day)
            sql(
                "UPDATE orbit_metric_capture_cell SET owner_user_id=%s "
                "WHERE tenant_id=%s AND id=%s",
                (user["owner_user_id"], tenant, selected["id"]),
            )
            fixture.fact(selected, trees[0])
        record(old, 2)
        empty = publication(sequence=120)
        empty_cell = fixture.cell(empty, trees[0], day="2026-01-02", empty=True)
        record(empty, 0)
        changed = publication(sequence=120)
        new_tree = [trees[0][0]]
        for kind in ("CAMPAIGN", "ADSET", "AD"):
            new_tree.append(fixture.dimension(accounts[0], kind, parent=new_tree[-1]))
        changed_cell = fixture.cell(changed, new_tree, day="2026-01-03")
        changed_fact = fixture.fact(changed_cell, new_tree)
        record(changed, 1)
        late = publication(sequence=110)
        late_cell = fixture.cell(late, trees[0], sequence=110, day="2026-01-02")
        sql(
            "UPDATE orbit_metric_capture_cell SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
            (user["owner_user_id"], tenant, late_cell["id"]),
        )
        fixture.fact(late_cell, trees[0])
        record(late, 1)

        # 原HTTP冻结501个真实当前账户，之后撤去accounts.read，monitor消费仍完整。
        scope_ids = [accounts[0], accounts[1]] + sorted(str(uuid4()) for _ in range(499))
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s FOR UPDATE",
                    (tenant,),
                )
                cursor.fetchone()
                cursor.executemany(
                    "INSERT INTO "
                    "orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
                    "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
                    "bound_at,created_at) "
                    "VALUES(%s,%s,%s,'SQL_ONLY_READ_SCOPE','SQL_ONLY_READ_SCOPE',%s,%s,"
                    "'USD','Asia/Shanghai','UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                    [
                        (
                            tenant,
                            identifier,
                            str(uuid4().int),
                            user["owner_user_id"],
                            user["owner_team_id"],
                        )
                        for identifier in scope_ids[2:]
                    ],
                )
                cursor.execute(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

        def snapshot(selected):
            cap = checked(
                client.get("/api/v1/scope-snapshots/capabilities", headers=user["headers"]), 200
            )
            body = {"mode": "IDS", "account_ids": selected, "filter": None}
            if not selected:
                body = {
                    "mode": "FILTER",
                    "account_ids": [],
                    "filter": {
                        "q": "不存在_" + uuid4().hex,
                        "status": None,
                        "auth_status": None,
                        "operator_user_id": None,
                        "vendor_id": None,
                    },
                }
            return checked(
                client.post(
                    "/api/v1/scope-snapshots",
                    headers=user["headers"]
                    | {
                        "X-CSRF-Token": cap["csrf_token"],
                        "Idempotency-Key": str(uuid4()),
                    },
                    json=body,
                ),
                201,
            )

        selected_scope, empty_scope = snapshot(scope_ids), snapshot([])
        require(
            selected_scope["count"] == 501 and empty_scope["count"] == 0, "metric_read_scope_count"
        )
        account_grants = sql(
            "SELECT DISTINCT rm.role_id,rm.menu_id FROM sys_role_menu rm "
            "JOIN sys_user_role ur ON ur.role_id=rm.role_id WHERE ur.user_id IN(%s,%s) "
            "AND rm.menu_id=31011",
            (user["actor_id"], manager["actor_id"]),
            fetch=True,
        )
        for grant in account_grants:
            sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s", grant)
            cleanup.callback(sql, "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", grant)

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
            )
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            counts = {"sql": 0}

            def count_sql(*_args):
                counts["sql"] += 1

            event.listen(engine.sync_engine, "before_cursor_execute", count_sql)
            source = RegisteredSqlReadSource(table)
            store = MetricsQueryStore(source)

            async def collect(actor=1, body=None, *, read_dimensions=True):
                cells, facts, dimensions = [], [], {}
                async with sessions() as session, session.begin():
                    context = await store.select_source_anchor(
                        session, actor, body or query(profile)
                    )
                    async for cell_batch in store.iter_latest_cells(session, context):
                        cells.extend(cell_batch.rows)
                        async for fact_batch in store.iter_selected_facts(
                            session, context, cell_batch
                        ):
                            facts.extend(fact_batch.rows)
                            if read_dimensions:
                                for dimension in await store.select_matching_dimensions(
                                    session, context, fact_batch
                                ):
                                    dimensions[dimension["id"]] = dimension
                return cells, facts, dimensions

            async def denied(operation, status, code):
                try:
                    await operation()
                except OrbitError as error:
                    require(
                        (error.status, error.code) == (status, code),
                        "metric_read_denial_status_code",
                    )
                else:
                    raise AssertionError("metric_read_expected_whole_rejection")

            try:
                async with sessions() as session, session.begin():
                    before = counts["sql"]
                    await denied(
                        lambda: MetricsQueryStore().select_source_anchor(
                            session, 1, query(profile)
                        ),
                        503,
                        "METRICS_DATA_UNVERIFIED",
                    )
                    require(
                        counts["sql"] == before, "metric_read_default_provider_must_be_zero_sql"
                    )
                cases.append(METRIC_QUERY_READ_CASES[0])
                body = query(profile, date_to="2026-01-01")
                root_cells, root_facts, root_dims = await collect(body=body)
                user_cells, _, _ = await collect(user["actor_id"], body)
                team_cells, _, _ = await collect(manager["actor_id"], body)
                require(
                    {row["account_id"] for row in root_cells} == set(accounts),
                    "metric_read_root_four_historical",
                )
                require(
                    {row["account_id"] for row in user_cells} == {accounts[0]},
                    "metric_read_user_current_owner_not_history",
                )
                require(
                    {row["account_id"] for row in team_cells}
                    == {accounts[0], accounts[1], accounts[3]},
                    "metric_read_team_explicit_or_self_not_unmanaged_peer",
                )
                cases.append(METRIC_QUERY_READ_CASES[1])
                checked(
                    client.get("/api/v1/scope-snapshots/capabilities", headers=user["headers"]), 403
                )
                scoped, _, _ = await collect(
                    user["actor_id"], body | {"scope_snapshot_id": selected_scope["id"]}
                )
                require(
                    {row["account_id"] for row in scoped} == {accounts[0]},
                    "metric_read_501_full_scope",
                )
                zero, zero_facts, zero_dims = await collect(
                    user["actor_id"], body | {"scope_snapshot_id": empty_scope["id"]}
                )
                require(
                    not zero and not zero_facts and not zero_dims,
                    "metric_read_empty_scope_not_unrestricted",
                )
                await denied(
                    lambda: collect(
                        manager["actor_id"], body | {"scope_snapshot_id": selected_scope["id"]}
                    ),
                    404,
                    "NOT_FOUND",
                )
                cases.append(METRIC_QUERY_READ_CASES[2])
                cells, facts, _ = await collect()
                require(
                    any(row["id"] == empty_cell["id"] for row in cells),
                    "metric_read_latest_empty_cell_present",
                )
                require(
                    not any(row["cell_id"] == empty_cell["id"] for row in facts),
                    "metric_read_empty_never_old_fact",
                )
                require(
                    any(row["id"] == changed_fact["id"] for row in facts),
                    "metric_read_new_ad_present",
                )
                require(
                    not any(row["cell_id"] in {late_cell["id"]} for row in facts),
                    "metric_read_late110_not_latest",
                )
                mine, mine_facts, _ = await collect(user["actor_id"])
                require(
                    len(mine) == len(mine_facts) == 1,
                    "metric_read_new_owner_does_not_authorize_old_user_cell",
                )
                cases.append(METRIC_QUERY_READ_CASES[3])
                source.checked_ids.clear()
                source.batches.clear()
                sql(
                    "UPDATE " + table + " SET revoked=1 WHERE tenant_id=%s AND publication_id=%s",
                    (tenant, principal["id"]),
                )
                try:
                    await denied(lambda: collect(), 503, "METRICS_DATA_UNVERIFIED")
                    require(
                        any(
                            {principal["id"], changed["id"]}.issubset(batch)
                            for batch in source.batches
                        ),
                        "metric_read_all_old_heads_checked",
                    )
                finally:
                    sql(
                        "UPDATE "
                        + table
                        + " SET revoked=0 WHERE tenant_id=%s AND publication_id=%s",
                        (tenant, principal["id"]),
                    )
                cases.append(METRIC_QUERY_READ_CASES[4])
                for term in ("中间", "_字面%", "!后", trees[0][3]["external_id"]):
                    _, _, dimensions = await collect(body=body | {"q": term})
                    require(
                        set(dimensions) == {trees[0][3]["id"]},
                        "metric_read_actual_original_contains_or_exact",
                    )
                _, _, stripped = await collect(
                    body=body | {"q": trees[0][3]["external_id"].lstrip("0")}
                )
                require(not stripped, "metric_read_external_leading_zero_not_integer")
                cases.append(METRIC_QUERY_READ_CASES[5])
                require(
                    all(
                        set(row) == set(TABLE_COLUMNS["orbit_metric_ad_fact_version"].split())
                        for row in root_facts
                    ),
                    "metric_read_all_fact_fields",
                )
                require(
                    all(
                        set(row) == set(TABLE_COLUMNS["orbit_metric_entity_snapshot"].split())
                        for row in root_dims.values()
                    ),
                    "metric_read_all_dimension_fields",
                )
                null_fact = next(row for row in root_facts if row["id"] == principal_facts[1]["id"])
                require(
                    [
                        null_fact[name]
                        for name in (
                            "spend",
                            "impressions",
                            "clicks",
                            "registrations",
                            "purchases",
                            "purchase_value",
                        )
                    ]
                    == [None, "0", None, "1.25", "0", None],
                    "metric_read_six_null_decimal_values",
                )
                cases.append(METRIC_QUERY_READ_CASES[6])
                async with sessions() as session:
                    async with session.begin():
                        context = await store.select_source_anchor(session, 1, body)
                        await denied(
                            lambda: anext(store.iter_latest_cells(session, MetricReadContext())),
                            409,
                            "METRICS_READ_CONTEXT_INVALID",
                        )
                        await denied(
                            lambda: anext(
                                store.iter_selected_facts(session, context, MetricCellBatch())
                            ),
                            409,
                            "METRICS_READ_CONTEXT_INVALID",
                        )
                    async with session.begin():
                        await denied(
                            lambda: anext(store.iter_latest_cells(session, context)),
                            409,
                            "METRICS_READ_CONTEXT_INVALID",
                        )
                cases.append(METRIC_QUERY_READ_CASES[7])
                sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31031", (native_role,))
                try:
                    await denied(lambda: collect(user["actor_id"], body), 403, "PERMISSION_DENIED")
                finally:
                    sql(
                        "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31031)",
                        (native_role,),
                    )
                sql(
                    "UPDATE orbit_metric_profile_head SET "
                    "state='DISABLED',revision=revision+1 WHERE tenant_id=%s AND id=%s",
                    (tenant, profile["id"]),
                )
                try:
                    await denied(lambda: collect(body=body), 503, "METRICS_DATA_UNVERIFIED")
                finally:
                    sql(
                        "UPDATE orbit_metric_profile_head SET "
                        "state='ENABLED',revision=revision+1 WHERE tenant_id=%s AND id=%s",
                        (tenant, profile["id"]),
                    )
                cases.append(METRIC_QUERY_READ_CASES[8])
                original_evidence = sql(
                    "SELECT binding_json,binding_hash FROM "
                    + table
                    + " WHERE tenant_id=%s AND publication_id=%s",
                    (tenant, late["id"]),
                    fetch=True,
                )[0]
                wrong_binding = json.loads(original_evidence[0])
                wrong_binding[17] = "d" * 64  # 真实manifest根未变，篡改登记即使自洽hash也必须拒绝。
                sql(
                    "UPDATE " + table + " SET binding_json=%s,binding_hash=%s "
                    "WHERE tenant_id=%s AND publication_id=%s",
                    (json.dumps(wrong_binding), digest(wrong_binding), tenant, late["id"]),
                )
                try:
                    await denied(lambda: collect(body=body), 503, "METRICS_DATA_UNVERIFIED")
                finally:
                    sql(
                        "UPDATE " + table + " SET binding_json=%s,binding_hash=%s "
                        "WHERE tenant_id=%s AND publication_id=%s",
                        (*original_evidence, tenant, late["id"]),
                    )
                sql(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE tenant_id=%s AND id=%s",
                    (tenant, source_configuration),
                )
                try:
                    await denied(lambda: collect(body=body), 503, "METRICS_DATA_UNVERIFIED")
                finally:
                    sql(
                        "UPDATE orbit_system_configuration SET enabled=1 "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, source_configuration),
                    )
                sql(
                    "UPDATE orbit_system_configuration SET revision=revision+1 WHERE "
                    "tenant_id=%s AND id=%s",
                    (tenant, source_configuration),
                )
                await denied(lambda: collect(body=body), 503, "METRICS_DATA_UNVERIFIED")
                cases.append(METRIC_QUERY_READ_CASES[9])
            finally:
                await engine.dispose()

        asyncio.run(run())
        return {
            "kind": "SQL_ONLY_NOT_PLATFORM",
            "cases": len(METRIC_QUERY_READ_CASES),
            "scope_accounts": 501,
        }
