"""048/049真实SQL边界专项；技术SQL夹具不是生产发行/采集/查询Store验收。"""

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import uuid4

METRIC_FACT_SCHEMA_CASES = (
    "pythonMetricFact048049ActualMetadataAndSingleImmutableNameDimension",
    "pythonMetricFactExactTenantAccountKindEntityParentAndCellForeignKeys",
    "pythonMetricQueryExactPublicationGenerationAndProfileCompositeAnchor",
    "pythonMetricFactPublishedHeadAndAllChildrenRejectInsertUpdateDelete",
    "pythonMetricQueryReadyRowsTotalsExpectedAndOldGenerationRejectMutation",
    "pythonMetricFactLatestCompleteEmptyOmittedAndLate110NeverBackfill120",
    "pythonMetricFactOriginalContainsLiteralWildcardAndLeadingZeroId",
)

BASE_METRIC_TRIGGER_NAMES = frozenset(
    (
        "metric_entity_snapshot_immutable_update",
        "metric_entity_snapshot_immutable_delete",
        "metric_fact_clock_monotonic",
        "metric_publication_intent_guard",
        "metric_publication_immutable_update",
        "metric_publication_immutable_delete",
        "metric_cell_insert_guard",
        "metric_cell_update_guard",
        "metric_cell_delete_guard",
        "metric_fact_insert_guard",
        "metric_fact_update_guard",
        "metric_fact_delete_guard",
        "metric_fact_asset_insert_guard",
        "metric_fact_asset_update_guard",
        "metric_fact_asset_delete_guard",
        "metric_fact_launch_insert_guard",
        "metric_fact_launch_update_guard",
        "metric_fact_launch_delete_guard",
        "metric_query_identity_guard",
        "metric_query_ready_guard",
        "metric_query_parent_delete_guard",
        "metric_query_request_update_guard",
        "metric_query_request_delete_guard",
        "metric_query_account_insert_guard",
        "metric_query_account_update_guard",
        "metric_query_account_delete_guard",
        "metric_query_row_insert_guard",
        "metric_query_row_update_guard",
        "metric_query_row_delete_guard",
        "metric_query_total_insert_guard",
        "metric_query_total_update_guard",
        "metric_query_total_delete_guard",
    )
)


def validate_metric_trigger_names(names, *, has_expected_manifest):
    if type(has_expected_manifest) is not bool:
        raise ValueError("预期根迁移状态必须明确")
    expected = BASE_METRIC_TRIGGER_NAMES | (
        {"metric_query_expected_manifest_guard"} if has_expected_manifest else set()
    )
    assert len(BASE_METRIC_TRIGGER_NAMES) == 32
    assert len(names) == len(expected) and set(names) == expected


LATEST_CELL_SQL = """
WITH ranked AS (
 SELECT c.id,c.account_id,c.capture_sequence,c.empty_result,p.generation,
 ROW_NUMBER() OVER(PARTITION BY c.tenant_id,c.account_id,c.business_date,
 c.profile_id,c.profile_version,c.breakdown_key ORDER BY c.capture_sequence DESC) AS rn
 FROM orbit_metric_capture_cell c JOIN orbit_metric_publication p
 ON p.tenant_id=c.tenant_id AND p.id=c.publication_id
 WHERE c.tenant_id=%s AND c.account_id=%s AND c.business_date=%s
 AND c.profile_id=%s AND c.profile_version=%s AND p.state='PUBLISHED'
 AND p.generation<=%s
)
SELECT c.id,c.capture_sequence,c.empty_result,f.ad_id
FROM ranked c LEFT JOIN orbit_metric_ad_fact_version f
 ON f.tenant_id=%s AND f.cell_id=c.id AND f.is_deleted=0
WHERE c.rn=1 ORDER BY f.ad_id
"""

TABLE_COLUMNS = {
    "orbit_metric_entity_snapshot": (
        "tenant_id id account_id entity_kind entity_id external_id name "
        "parent_snapshot_id parent_kind content_hash"
    ),
    "orbit_metric_publication": (
        "tenant_id id generation profile_id profile_version profile_hash "
        "authority_kind source_config_id source_config_revision source_proof_json "
        "state expected_cell_count expected_cells_hash captured_cells_hash "
        "cell_count fact_count capture_sequence_max manifest_hash publisher_actor_id "
        "request_id oldest_observed_at created_at published_at"
    ),
    "orbit_metric_capture_cell": (
        "tenant_id id publication_id account_id account_snapshot_id "
        "account_snapshot_kind business_date profile_id profile_version "
        "breakdown_key capture_sequence timezone_name currency owner_user_id "
        "owner_team_id attribution_version expected_page_count received_page_count "
        "expected_entity_count fact_count empty_result empty_field_mask "
        "critical_complete inventory_hash source_hash oldest_observed_at"
    ),
    "orbit_metric_ad_fact_version": (
        "tenant_id id cell_id account_id business_date profile_id profile_version "
        "capture_sequence breakdown_key ad_id adset_id campaign_id "
        "account_snapshot_id account_snapshot_kind campaign_snapshot_id "
        "campaign_snapshot_kind adset_snapshot_id adset_snapshot_kind ad_snapshot_id "
        "ad_snapshot_kind channel_id product_name_snapshot parent_mapping_hash "
        "asset_mapping_state asset_mapping_hash launch_mapping_hash is_deleted spend "
        "impressions clicks registrations purchases purchase_value observed_at "
        "fact_hash"
    ),
    "orbit_metric_fact_asset_binding": (
        "tenant_id fact_id asset_id asset_revision creative_external_id mapping_hash evidence_hash"
    ),
    "orbit_metric_fact_launch_binding": (
        "tenant_id fact_id plan_id source_revision ad_local_id mapping_hash evidence_hash"
    ),
    "orbit_metric_query_snapshot": (
        "tenant_id id actor_id subject_id auth_version auth_fingerprint query_hash "
        "query_json account_scope_snapshot_id account_scope_hash account_scope_count "
        "source_publication_id source_generation profile_id profile_version "
        "profile_hash algorithm_version state build_generation build_token_hash "
        "lease_until row_count row_bytes totals_count expected_account_count "
        "expected_cell_count missing_count rows_hash totals_hash data_as_of "
        "created_at sealed_at failure_code cleanup_requested "
        "expected_unit_hash expected_membership_hash "
        "expected_membership_count expected_manifest_version"
    ),
    "orbit_metric_query_expected_account": (
        "tenant_id query_id build_generation account_id timezone_name expectation_hash"
    ),
    "orbit_metric_query_sorted_row": (
        "tenant_id query_id build_generation ordinal row_key_hash payload_json "
        "payload_hash payload_bytes"
    ),
    "orbit_metric_query_total": (
        "tenant_id query_id build_generation currency profile_id payload_json payload_hash"
    ),
    "orbit_metric_query_request": (
        "tenant_id actor_id key_hash request_hash query_id after_ordinal page_size "
        "request_id created_at"
    ),
}


def validate_metric_fact_schema_target(admin, database):
    if (
        not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("指标事实专项仅允许127.0.0.1:13306本轮UUID隔离库")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def literal_contains(value):
    """使用显式!作为转义字符；名称包含不能偷换成前缀或把%/_当通配符。"""
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


class MetricFactSqlFixture:
    """只供主线UUID数据库工具，所有标识符限静态allowlist，禁止作为生产issuer。"""

    def __init__(self, admin, database):
        validate_metric_fact_schema_target(admin, database)
        self.admin = admin
        self.database = database
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            if cursor.fetchone()[0] != database:
                raise ValueError("当前实际数据库不属于本轮隔离目标")
            cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
            self.tenant, self.owner, self.team = cursor.fetchone()
        self.now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    def sql(self, statement, values=(), *, fetch=False):
        import pymysql

        try:
            with self.admin.cursor() as cursor:
                cursor.execute(statement, values)
                result = cursor.fetchall() if fetch else cursor.rowcount
            self.admin.commit()
            return result
        except pymysql.MySQLError as error:
            self.admin.rollback()
            code = error.args[0] if error.args and type(error.args[0]) is int else None
            raise AssertionError({"unexpected_sql_code": code}) from None

    def insert(self, table, row, *, deny=None):
        allowed = TABLE_COLUMNS.get(table)
        if allowed is None or not row or not set(row).issubset(allowed.split()):
            raise ValueError("只允许专项静态表列")
        columns = tuple(row)
        statement = (
            "INSERT INTO "
            + table
            + "("
            + ",".join(columns)
            + ") VALUES("
            + ",".join(["%s"] * len(columns))
            + ")"
        )
        if deny is not None:
            self.denied(statement, tuple(row[key] for key in columns), deny)
        else:
            self.sql(statement, tuple(row[key] for key in columns))
        return row

    def denied(self, statement, values, expected):
        """必须真实失败且仅报告安全code；失败SQL不污染后续事务。"""
        import pymysql

        self.admin.begin()
        try:
            with self.admin.cursor() as cursor:
                cursor.execute(statement, values)
        except pymysql.MySQLError as error:
            code = error.args[0] if error.args and type(error.args[0]) is int else None
            if code not in set(expected):
                raise AssertionError(
                    {"expected_sql_codes": sorted(expected), "actual_sql_code": code}
                ) from None
        else:
            raise AssertionError("预期SQL边界拒绝却成功")
        finally:
            self.admin.rollback()

    def account(self, tenant=None):
        tenant = tenant or self.tenant
        identifier = str(uuid4())
        self.sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
            "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
            "value_json,details_json,bound_at,created_at) VALUES(%s,%s,%s,'SQL_ONLY',"
            "'SQL_ONLY',%s,%s,'USD','Asia/Shanghai','AUTHORIZED','ACTIVE','{}','{}',%s,%s)",
            (tenant, identifier, str(uuid4().int), self.owner, self.team, self.now, self.now),
        )
        return identifier

    def dimension(self, account, kind, *, parent=None, tenant=None, name=None, entity=None):
        tenant = tenant or self.tenant
        row = {
            "tenant_id": tenant,
            "id": str(uuid4()),
            "account_id": account,
            "entity_kind": kind,
            "entity_id": entity or (account if kind == "ACCOUNT" else str(uuid4())),
            "external_id": "000" + str(uuid4().int),
            "name": name or "SQL_ONLY_" + kind,
            "parent_snapshot_id": parent["id"] if parent else None,
            "parent_kind": parent["entity_kind"] if parent else None,
        }
        row["content_hash"] = digest({key: value for key, value in row.items() if key != "id"})
        return self.insert("orbit_metric_entity_snapshot", row)

    def tree(self, account, *, tenant=None, name=None):
        result = []
        for kind in ("ACCOUNT", "CAMPAIGN", "ADSET", "AD"):
            result.append(
                self.dimension(
                    account, kind, tenant=tenant, parent=result[-1] if result else None, name=name
                )
            )
        return result

    def publication(self, profile, profile_hash, *, sequence=120, cells=1):
        return self.insert(
            "orbit_metric_publication",
            {
                "tenant_id": self.tenant,
                "id": str(uuid4()),
                "profile_id": profile["id"],
                "profile_version": profile["version"],
                "profile_hash": profile_hash,
                "authority_kind": "ISOLATED_TEST",
                "source_proof_json": json.dumps({"kind": "SQL_ONLY_NOT_PLATFORM"}),
                "expected_cell_count": cells,
                "expected_cells_hash": "a" * 64,
                "capture_sequence_max": sequence,
                "publisher_actor_id": 1,
                "request_id": str(uuid4()),
                "created_at": self.now,
            },
        )

    def cell(self, publication, tree, *, sequence=120, day="2026-01-01", empty=False):
        return self.insert(
            "orbit_metric_capture_cell",
            {
                "tenant_id": self.tenant,
                "id": str(uuid4()),
                "publication_id": publication["id"],
                "account_id": tree[0]["account_id"],
                "account_snapshot_id": tree[0]["id"],
                "business_date": day,
                "profile_id": publication["profile_id"],
                "profile_version": publication["profile_version"],
                "capture_sequence": sequence,
                "timezone_name": "Asia/Shanghai",
                "currency": "USD",
                "owner_user_id": self.owner,
                "owner_team_id": self.team,
                "attribution_version": 1,
                "expected_page_count": 1,
                "received_page_count": 1,
                "expected_entity_count": 0 if empty else 1,
                "fact_count": 0 if empty else 1,
                "empty_result": empty,
                "empty_field_mask": 63 if empty else 0,
                "critical_complete": True,
                "inventory_hash": "b" * 64,
                "source_hash": "c" * 64,
                "oldest_observed_at": self.now,
            },
        )

    def fact(self, cell, tree, *, changes=None, deny=None):
        return self.insert(
            "orbit_metric_ad_fact_version",
            {
                "tenant_id": self.tenant,
                "id": str(uuid4()),
                "cell_id": cell["id"],
                "account_id": cell["account_id"],
                "business_date": cell["business_date"],
                "profile_id": cell["profile_id"],
                "profile_version": cell["profile_version"],
                "capture_sequence": cell["capture_sequence"],
                "ad_id": tree[3]["entity_id"],
                "adset_id": tree[2]["entity_id"],
                "campaign_id": tree[1]["entity_id"],
                **{
                    kind.lower() + "_snapshot_id": item["id"]
                    for kind, item in zip(("ACCOUNT", "CAMPAIGN", "ADSET", "AD"), tree, strict=True)
                },
                "parent_mapping_hash": "d" * 64,
                "is_deleted": False,
                "spend": "120.000000",
                "impressions": "1000.000000",
                "clicks": "12.000000",
                "registrations": None,
                "purchases": "2.000000",
                "purchase_value": "240.000000",
                "observed_at": self.now,
                "fact_hash": "e" * 64,
                **(changes or {}),
            },
            deny=deny,
        )

    def publish(self, publication, *, facts=1):
        generation = self.sql(
            "SELECT COALESCE(MAX(generation),0)+1 FROM orbit_metric_publication WHERE tenant_id=%s",
            (self.tenant,),
            fetch=True,
        )[0][0]
        self.sql(
            "UPDATE orbit_metric_publication SET state='SEALED' WHERE tenant_id=%s AND id=%s",
            (self.tenant, publication["id"]),
        )
        self.sql(
            "UPDATE orbit_metric_publication SET "
            "state='PUBLISHED',generation=%s,cell_count=expected_cell_count,"
            "captured_cells_hash=expected_cells_hash,fact_count=%s,"
            "manifest_hash=%s,published_at=%s "
            "WHERE tenant_id=%s AND id=%s",
            (generation, facts, "f" * 64, self.now, self.tenant, publication["id"]),
        )
        return generation

    def query(self, publication, generation, **changes):
        return self.insert(
            "orbit_metric_query_snapshot",
            {
                "tenant_id": self.tenant,
                "id": str(uuid4()),
                "actor_id": 1,
                "subject_id": self.owner,
                "auth_version": 1,
                "auth_fingerprint": "a" * 64,
                "query_hash": "b" * 64,
                "query_json": json.dumps({"kind": "SQL_ONLY_NOT_QUERY_STORE"}),
                "source_publication_id": publication["id"],
                "source_generation": generation,
                "profile_id": publication["profile_id"],
                "profile_version": publication["profile_version"],
                "profile_hash": publication["profile_hash"],
                "algorithm_version": "SQL_ONLY",
                "build_token_hash": "c" * 64,
                "lease_until": self.now,
                "data_as_of": self.now,
                "created_at": self.now,
                **changes,
            },
        )


def run_metric_fact_schema_checks(admin, database, cases):
    validate_metric_fact_schema_target(admin, database)
    fixture = MetricFactSqlFixture(admin, database)
    from metric_profile_query_checks import seed_metric_profile_browser_fixture

    seeded = seed_metric_profile_browser_fixture(admin, database)
    profile, other_profile = seeded["profiles"][:2]
    profile_hash = digest(profile)
    tenant = fixture.tenant
    account = fixture.account()
    tree = fixture.tree(account)
    publication = fixture.publication(profile, profile_hash)
    cell = fixture.cell(publication, tree)
    fact = fixture.fact(cell, tree)

    rows = fixture.sql(
        "SELECT "
        "TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,COLLATION_NAME,COLUMN_COMMENT "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME LIKE 'orbit_metric_%%'",
        (database,),
        fetch=True,
    )
    columns = {(row[0], row[1]): row[2:] for row in rows}
    expected = set(TABLE_COLUMNS) | {"orbit_metric_fact_clock"}
    assert expected.issubset({row[0] for row in rows})
    for table in expected:
        assert all(value[2] for key, value in columns.items() if key[0] == table)
        assert columns[(table, "tenant_id")][1] == "utf8mb4_0900_as_cs"
    assert columns[("orbit_metric_capture_cell", "profile_version")][1] == "utf8mb4_bin"
    assert columns[("orbit_metric_query_snapshot", "profile_version")][1] == "utf8mb4_bin"
    assert sum("longtext" in value[0] for key, value in columns.items() if key[0] in expected) == 1
    trigger_rows = fixture.sql(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s "
        "AND (EVENT_OBJECT_TABLE IN (" + ",".join(["%s"] * len(expected)) + "))",
        (database, *sorted(expected)),
        fetch=True,
    )
    validate_metric_trigger_names(
        [row[0] for row in trigger_rows],
        has_expected_manifest=("orbit_metric_query_snapshot", "expected_unit_hash") in columns,
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[0])

    other_account = fixture.account()
    other_tree = fixture.tree(other_account)
    cousin = [tree[0]]
    for kind in ("CAMPAIGN", "ADSET", "AD"):
        cousin.append(fixture.dimension(account, kind, parent=cousin[-1]))
    foreign_tenant = str(uuid4())
    fixture.sql(
        "INSERT INTO orbit_tenant(id,name) VALUES(%s,'SQL_ONLY_METRIC_FOREIGN')", (foreign_tenant,)
    )
    foreign_tree = fixture.tree(fixture.account(foreign_tenant), tenant=foreign_tenant)
    alternative_account = fixture.dimension(account, "ACCOUNT", name="renamed_ACCOUNT")
    wrong_adset_parent = fixture.dimension(
        account, "ADSET", parent=cousin[1], entity=tree[2]["entity_id"]
    )
    wrong_ad_parent = fixture.dimension(
        account, "AD", parent=cousin[2], entity=tree[3]["entity_id"]
    )
    for index, changes in enumerate(
        (
            {"account_id": other_account},
            {"account_snapshot_id": other_tree[0]["id"]},
            {"campaign_snapshot_id": tree[2]["id"]},
            {"campaign_id": str(uuid4())},
            {"adset_snapshot_id": wrong_adset_parent["id"]},
            {"ad_snapshot_id": wrong_ad_parent["id"]},
            {"campaign_snapshot_id": foreign_tree[1]["id"]},
            {"account_snapshot_id": alternative_account["id"]},
        )
    ):
        # 每个负例使用全新合法cell/grain，避免先撞唯一键掩盖精确FK失败。
        negative_pub = fixture.publication(profile, profile_hash, sequence=200 + index)
        negative_cell = fixture.cell(negative_pub, tree, sequence=200 + index)
        fixture.fact(negative_cell, tree, changes=changes, deny={1452})
    fixture.insert(
        "orbit_metric_entity_snapshot",
        tree[1] | {"id": str(uuid4()), "parent_kind": None, "content_hash": "1" * 64},
        deny={3819},
    )
    for statement in (
        "UPDATE orbit_metric_entity_snapshot SET name=name WHERE tenant_id=%s AND id=%s",
        "DELETE FROM orbit_metric_entity_snapshot WHERE tenant_id=%s AND id=%s",
    ):
        fixture.denied(statement, (tenant, tree[3]["id"]), {1644})
    # 同hash唯一冲突不是全文比较协议：这里仅证明SQL键，不伪证issuer已经实现。
    fixture.insert(
        "orbit_metric_entity_snapshot",
        tree[3] | {"id": str(uuid4()), "name": "different raw text"},
        deny={1062},
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[1])

    # 仅为两个历史绑定FK提供真实存在的数据库对象；UPLOADING绝不伪装CLEAN/READY。
    asset_id, plan_id = str(uuid4()), str(uuid4())
    fixture.sql(
        "INSERT INTO orbit_material_asset(tenant_id,id,owner_user_id,owner_team_id,name,"
        "category_id,kind,mime,state,sha256,byte_size,object_upload_id) "
        "VALUES(%s,%s,%s,%s,'SQL_ONLY',%s,'IMAGE','image/png','UPLOADING',%s,1,%s)",
        (tenant, asset_id, fixture.owner, fixture.team, str(uuid4()), "a" * 64, str(uuid4())),
    )
    fixture.sql(
        "INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,owner_team_id,name,state,"
        "revision,payload_json,payload_hash,payload_bytes,account_count,asset_count,created_at,"
        "updated_at) VALUES(%s,%s,%s,%s,'SQL_ONLY','DRAFT',1,'{}',%s,2,0,0,%s,%s)",
        (tenant, plan_id, fixture.owner, fixture.team, "a" * 64, fixture.now, fixture.now),
    )
    fixture.sql(
        "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,"
        "payload_hash,dependency_json,created_at,created_by) VALUES(%s,%s,1,'{}',%s,'{}',%s,1)",
        (tenant, plan_id, "a" * 64, fixture.now),
    )
    asset_binding = fixture.insert(
        "orbit_metric_fact_asset_binding",
        {
            "tenant_id": tenant,
            "fact_id": fact["id"],
            "asset_id": asset_id,
            "asset_revision": 1,
            "creative_external_id": "001",
            "mapping_hash": "a" * 64,
            "evidence_hash": "b" * 64,
        },
    )
    launch_binding = fixture.insert(
        "orbit_metric_fact_launch_binding",
        {
            "tenant_id": tenant,
            "fact_id": fact["id"],
            "plan_id": plan_id,
            "source_revision": 1,
            "ad_local_id": str(uuid4()),
            "mapping_hash": "a" * 64,
            "evidence_hash": "b" * 64,
        },
    )
    generation = fixture.publish(publication)
    query = fixture.query(publication, generation)
    other_pub = fixture.publication(other_profile, digest(other_profile), cells=0)
    other_gen = fixture.publish(other_pub, facts=0)
    for changes in (
        {"source_generation": other_gen},
        {"source_publication_id": other_pub["id"], "source_generation": other_gen},
        {
            "profile_id": other_profile["id"],
            "profile_version": other_profile["version"],
            "profile_hash": digest(other_profile),
        },
        {"profile_version": profile["version"].upper()},
    ):
        fixture.insert(
            "orbit_metric_query_snapshot", query | {"id": str(uuid4())} | changes, deny={1452}
        )
    building = fixture.publication(profile, profile_hash, cells=0)
    fixture.insert(
        "orbit_metric_query_snapshot",
        query | {"id": str(uuid4()), "source_publication_id": building["id"]},
        deny={1452},
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[2])

    child_rows = (
        ("orbit_metric_capture_cell", cell | {"id": str(uuid4())}),
        ("orbit_metric_ad_fact_version", fact | {"id": str(uuid4())}),
        ("orbit_metric_fact_asset_binding", asset_binding),
        ("orbit_metric_fact_launch_binding", launch_binding),
    )
    for table, row in child_rows:
        fixture.insert(table, row, deny={1644})
    for table, column, identifier in (
        ("orbit_metric_publication", "id", publication["id"]),
        ("orbit_metric_capture_cell", "id", cell["id"]),
        ("orbit_metric_ad_fact_version", "id", fact["id"]),
        ("orbit_metric_fact_asset_binding", "fact_id", fact["id"]),
        ("orbit_metric_fact_launch_binding", "fact_id", fact["id"]),
    ):
        fixture.denied(
            "UPDATE "
            + table
            + " SET "
            + column
            + "="
            + column
            + " WHERE tenant_id=%s AND "
            + column
            + "=%s",
            (tenant, identifier),
            {1644},
        )
        fixture.denied(
            "DELETE FROM " + table + " WHERE tenant_id=%s AND " + column + "=%s",
            (tenant, identifier),
            {1644},
        )
    cases.append(METRIC_FACT_SCHEMA_CASES[3])

    expected_row = {
        "tenant_id": tenant,
        "query_id": query["id"],
        "build_generation": 1,
        "account_id": account,
        "timezone_name": "Asia/Shanghai",
        "expectation_hash": "a" * 64,
    }
    sorted_row = {
        "tenant_id": tenant,
        "query_id": query["id"],
        "build_generation": 1,
        "ordinal": 1,
        "row_key_hash": "b" * 64,
        "payload_json": "{}",
        "payload_hash": "c" * 64,
        "payload_bytes": 2,
    }
    total_row = {
        "tenant_id": tenant,
        "query_id": query["id"],
        "build_generation": 1,
        "currency": "USD",
        "profile_id": profile["id"],
        "payload_json": "{}",
        "payload_hash": "d" * 64,
    }
    for table, row in (
        ("orbit_metric_query_expected_account", expected_row),
        ("orbit_metric_query_sorted_row", sorted_row),
        ("orbit_metric_query_total", total_row),
    ):
        fixture.insert(table, row)
    fixture.sql(
        "UPDATE orbit_metric_query_snapshot SET "
        "state='READY',sealed_at=%s,rows_hash=%s,totals_hash=%s WHERE tenant_id=%s AND id=%s",
        (fixture.now, "a" * 64, "b" * 64, tenant, query["id"]),
    )
    for table, row in (
        ("orbit_metric_query_expected_account", expected_row),
        ("orbit_metric_query_sorted_row", sorted_row),
        ("orbit_metric_query_total", total_row),
    ):
        fixture.insert(table, row, deny={1644})
        fixture.denied(
            "UPDATE "
            + table
            + " SET build_generation=build_generation WHERE tenant_id=%s AND query_id=%s",
            (tenant, query["id"]),
            {1644},
        )
        fixture.denied(
            "DELETE FROM " + table + " WHERE tenant_id=%s AND query_id=%s",
            (tenant, query["id"]),
            {1644},
        )
    fixture.denied(
        "UPDATE orbit_metric_query_snapshot SET row_count=row_count+1 WHERE tenant_id=%s AND id=%s",
        (tenant, query["id"]),
        {1644},
    )
    request = fixture.insert(
        "orbit_metric_query_request",
        {
            "tenant_id": tenant,
            "actor_id": 1,
            "key_hash": digest(str(uuid4())),
            "request_hash": digest({"kind": "SQL_ONLY"}),
            "query_id": query["id"],
            "after_ordinal": 0,
            "page_size": 20,
            "request_id": str(uuid4()),
            "created_at": fixture.now,
        },
    )
    for operation in (
        "UPDATE orbit_metric_query_request SET page_size=50",
        "DELETE FROM orbit_metric_query_request",
    ):
        fixture.denied(
            operation + " WHERE tenant_id=%s AND actor_id=1 AND key_hash=%s",
            (tenant, request["key_hash"]),
            {1644},
        )
    reclaimed = fixture.query(publication, generation, build_generation=2)
    fixture.insert(
        "orbit_metric_query_sorted_row", sorted_row | {"query_id": reclaimed["id"]}, deny={1452}
    )
    fixture.insert(
        "orbit_metric_query_sorted_row",
        sorted_row | {"query_id": reclaimed["id"], "build_generation": 2},
    )
    fixture.sql(
        "DELETE FROM orbit_metric_query_sorted_row WHERE tenant_id=%s AND "
        "query_id=%s AND build_generation=1",
        (tenant, reclaimed["id"]),
    )
    assert fixture.sql(
        "SELECT build_generation FROM orbit_metric_query_sorted_row WHERE "
        "tenant_id=%s AND query_id=%s",
        (tenant, reclaimed["id"]),
        fetch=True,
    ) == ((2,),)
    fixture.sql(
        "UPDATE orbit_metric_query_snapshot SET cleanup_requested=1 WHERE tenant_id=%s AND id=%s",
        (tenant, query["id"]),
    )
    fixture.sql(
        "DELETE FROM orbit_metric_query_sorted_row WHERE tenant_id=%s AND query_id=%s",
        (tenant, query["id"]),
    )
    fixture.denied(
        "DELETE FROM orbit_metric_query_snapshot WHERE tenant_id=%s AND id=%s",
        (tenant, query["id"]),
        {1644},
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[4])

    def latest(account_id, day, cutoff):
        return fixture.sql(
            LATEST_CELL_SQL,
            (tenant, account_id, day, profile["id"], profile["version"], cutoff, tenant),
            fetch=True,
        )

    # 100非空→120完整空→迟到110非空：截止水位与采集序号不可混为一谈。
    old = fixture.publication(profile, profile_hash, sequence=100)
    old_cell = fixture.cell(old, tree, sequence=100, day="2026-01-02")
    fixture.fact(old_cell, tree)
    old_gen = fixture.publish(old)
    empty = fixture.publication(profile, profile_hash, sequence=120)
    empty_cell = fixture.cell(empty, tree, day="2026-01-02", empty=True)
    empty_gen = fixture.publish(empty, facts=0)
    late = fixture.publication(profile, profile_hash, sequence=110)
    late_cell = fixture.cell(late, tree, sequence=110, day="2026-01-02")
    fixture.fact(late_cell, tree)
    late_gen = fixture.publish(late)
    assert latest(account, "2026-01-02", old_gen) == (
        (old_cell["id"], 100, 0, tree[3]["entity_id"]),
    )
    for cutoff in (empty_gen, late_gen):
        assert latest(account, "2026-01-02", cutoff) == ((empty_cell["id"], 120, 1, None),)
    old_ad = fixture.publication(profile, profile_hash, sequence=100)
    old_ad_cell = fixture.cell(old_ad, tree, sequence=100, day="2026-01-03")
    fixture.fact(old_ad_cell, tree)
    fixture.publish(old_ad)
    new_ad = fixture.publication(profile, profile_hash)
    new_ad_cell = fixture.cell(new_ad, cousin, day="2026-01-03")
    fixture.fact(new_ad_cell, cousin)
    new_ad_gen = fixture.publish(new_ad)
    assert latest(account, "2026-01-03", new_ad_gen) == (
        (new_ad_cell["id"], 120, 0, cousin[3]["entity_id"]),
    )
    # 更晚global截止仍能读取此前publication中的本profile完整cell，不要求都在最后一批。
    assert latest(account, "2026-01-01", new_ad_gen) == (
        (cell["id"], 120, 0, tree[3]["entity_id"]),
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[5])

    special = fixture.tree(fixture.account(), name="前段_字面%中间!后段")
    for term in ("中间", "_字面%", "!后"):
        found = fixture.sql(
            "SELECT id FROM orbit_metric_entity_snapshot WHERE tenant_id=%s "
            "AND account_id=%s AND name LIKE %s ESCAPE '!' ORDER BY id",
            (tenant, special[0]["account_id"], literal_contains(term)),
            fetch=True,
        )
        assert {row[0] for row in found} == {item["id"] for item in special}
    assert (
        fixture.sql(
            "SELECT id FROM orbit_metric_entity_snapshot WHERE tenant_id=%s "
            "AND account_id=%s AND name LIKE %s ESCAPE '!'",
            (tenant, special[0]["account_id"], literal_contains("不存在")),
            fetch=True,
        )
        == ()
    )
    external = special[3]["external_id"]
    assert fixture.sql(
        "SELECT id FROM orbit_metric_entity_snapshot WHERE tenant_id=%s AND "
        "entity_kind='AD' AND external_id=%s",
        (tenant, external),
        fetch=True,
    ) == ((special[3]["id"],),)
    assert (
        fixture.sql(
            "SELECT id FROM orbit_metric_entity_snapshot WHERE tenant_id=%s "
            "AND entity_kind='AD' AND external_id=%s",
            (tenant, external.lstrip("0")),
            fetch=True,
        )
        == ()
    )
    cases.append(METRIC_FACT_SCHEMA_CASES[6])
    return {
        "kind": "SQL_ONLY_NOT_PLATFORM",
        "checks": len(METRIC_FACT_SCHEMA_CASES),
        "tenant_id": tenant,
    }
