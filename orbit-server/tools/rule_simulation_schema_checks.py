"""063候选显式SQL护栏工具；无真实模拟/source发行或平台权威。

仅由root七参runner调用，不连接数据库、不读env、不复制正式migration。
原Rule/scope走既有HTTP；048与063均为标注SQL_ONLY的技术约束样本。
"""

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

RULE_SIMULATION_SCHEMA_CASES = (
    "pythonRuleSimulationCandidateEightTablesTwentyFourTriggersAndStrictSession",
    "pythonRuleSimulationCandidateOriginalRuleScopeProfilePublicationExactForeignGraph",
    "pythonRuleSimulationCandidateWhitespaceRawBytesSemanticMatchAndImmutableReceipt",
    "pythonRuleSimulationCandidateOtherValidRawWithItsOwnCorrectHashRejected",
    "pythonRuleSimulationCandidateStoredJsonDifferentFromValidRawRejected",
    "pythonRuleSimulationCandidateConditionsArrayReorderingRejected",
    "pythonRuleSimulationCandidateInvalidUtf8RawRejectedWithoutPartialReceipt",
    "pythonRuleSimulationCandidateFinalReceiptFailureRollsBackAllEightTables",
)
BASE = Path(__file__).resolve().parents[1]
CANDIDATE = BASE / "docs/orbit/sql-drafts/063_rule_simulation_candidate.sql"
TABLES = (
    "orbit_rule_simulation",
    "orbit_rule_simulation_account",
    "orbit_rule_simulation_unit",
    "orbit_rule_simulation_entity",
    "orbit_rule_simulation_condition",
    "orbit_rule_simulation_request",
    "orbit_rule_simulation_audit",
    "orbit_rule_simulation_outbox",
)


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) is None
    ):
        raise ValueError("SIM_SCHEMA_ISOLATED_UUID_REQUIRED")


def raw_hash(raw):
    if type(raw) is not bytes:
        raise ValueError("SIM_SCHEMA_RAW_BYTES_REQUIRED")
    return hashlib.sha256(raw).hexdigest()


def same_response(raw, document):
    """仅工具输入自检，不能代替实际MySQL拒绝；数组顺序保留。"""
    from orbit_api.configuration import _parse_json
    from orbit_api.directory_tokens import canonical

    return canonical(_parse_json(raw)) == canonical(document)


def candidate_bytes():
    content = CANDIDATE.read_bytes()
    if (
        CANDIDATE.parent != BASE / "docs/orbit/sql-drafts"
        or CANDIDATE.name != "063_rule_simulation_candidate.sql"
    ):
        raise ValueError("SIM_SCHEMA_FIXED_CANDIDATE_REQUIRED")
    if len(content) > 131072:
        raise ValueError("SIM_SCHEMA_CANDIDATE_SIZE_INVALID")
    return content


def run_rule_simulation_schema_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .metric_fact_schema_checks import MetricFactSqlFixture, digest
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import definition_body
        from .rule_editor_checks import checked
    else:
        from metric_fact_schema_checks import MetricFactSqlFixture, digest
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import definition_body
        from rule_editor_checks import checked
    import pymysql
    from pymysql.constants import CLIENT

    from orbit_api.directory_tokens import canonical
    from orbit_api.rule_contract import Simulation, parse_rule_response
    from orbit_api.rule_simulation_contract import OriginalSimulationReceipt

    def sql(statement, values=(), *, rows=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            return cursor.fetchall() if rows else cursor.rowcount

    if sql("SELECT DATABASE()", rows=True) != ((database,),):
        raise ValueError("SIM_SCHEMA_SELECTED_DATABASE_REQUIRED")
    if not admin.client_flag & CLIENT.MULTI_STATEMENTS:
        raise ValueError("SIM_SCHEMA_EXPLICIT_MULTI_STATEMENTS_REQUIRED")
    modes, foreign_keys = sql("SELECT @@SESSION.sql_mode,@@SESSION.foreign_key_checks", rows=True)[
        0
    ]
    if "STRICT_TRANS_TABLES" not in modes.split(",") or foreign_keys != 1:
        raise ValueError("SIM_SCHEMA_STRICT_FOREIGN_KEYS_REQUIRED")
    placeholders = ",".join(["%s"] * len(TABLES))
    if (
        sql(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE "
            "TABLE_SCHEMA=%s AND TABLE_NAME IN (" + placeholders + ")",
            (database, *TABLES),
            rows=True,
        )[0][0]
        != 0
    ):
        raise ValueError("SIM_SCHEMA_EXISTING_CANDIDATE_TABLES_REFUSED")
    # 原baseline必须含正式062菜单，不能在未知半schema上应用候选。
    assert sql("SELECT COUNT(*) FROM sys_menu WHERE menu_id=31047", rows=True)[0][0] == 1
    source = candidate_bytes()
    with admin.cursor() as cursor:
        cursor.execute(source.decode("utf-8"))
        while cursor.nextset():
            pass
    actual_tables = sql(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s "
        "AND TABLE_NAME IN (" + placeholders + ")",
        (database, *TABLES),
        rows=True,
    )
    assert {row[0] for row in actual_tables} == set(TABLES)
    trigger_rows = sql(
        "SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE FROM information_schema.TRIGGERS "
        "WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE IN (" + placeholders + ")",
        (database, *TABLES),
        rows=True,
    )
    assert len(trigger_rows) == 24 and all(name.startswith("rule_sim_") for name, _ in trigger_rows)
    assert all(sum(table == row[1] for row in trigger_rows) == 3 for table in TABLES)
    cases.append(RULE_SIMULATION_SCHEMA_CASES[0])

    fixture = MetricFactSqlFixture(admin, database)
    tenant, owner, team = fixture.tenant, fixture.owner, fixture.team
    account = fixture.account()
    fixture.sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    profile, profile_source = seed_metric_reference_profile(admin, database, tenant, index=963)
    cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    frozen = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": [account], "filter": None},
        ),
        201,
    )
    body = definition_body(
        "候选SQL形状-" + uuid4().hex[:8], owner, team, frozen["id"], profile["id"]
    )
    body["window"] = "TODAY"
    body["groups"][0]["conditions"].append(
        {"metric": "clicks", "operator": "GTE", "threshold": "1.000000"}
    )
    cap = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"})
    )
    rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=body,
        ),
        201,
    )
    manifest, member_count = sql(
        "SELECT manifest_id,(SELECT member_count FROM orbit_rule_scope_manifest m "
        "WHERE m.tenant_id=h.tenant_id AND m.id=h.manifest_id AND "
        "m.sealed=1) FROM orbit_rule_head h "
        "WHERE h.tenant_id=%s AND h.id=%s",
        (tenant, rule["id"]),
        rows=True,
    )[0]
    assert member_count == 1 and rule["revision"] == 1
    tree = fixture.tree(account)
    publication = fixture.publication(profile, profile_source["profile_hash"], cells=0)
    # 纯SQL约束形状：不调用issuer、不声称已证明完整指标/预期，不用于simulation API。
    generation = sql(
        "SELECT COALESCE(MAX(generation),0)+1 FROM orbit_metric_publication WHERE tenant_id=%s",
        (tenant,),
        rows=True,
    )[0][0]
    sql(
        "UPDATE orbit_metric_publication SET "
        "state='PUBLISHED',generation=%s,cell_count=0,fact_count=0,"
        "captured_cells_hash=expected_cells_hash,manifest_hash=%s,published_at=UTC_TIMESTAMP(3) "
        "WHERE tenant_id=%s AND id=%s",
        (generation, "a" * 64, tenant, publication["id"]),
    )

    def insert(table, values):
        assert table in TABLES
        names = tuple(values)
        assert all(re.fullmatch(r"[a-z_]+", name) for name in names)
        return sql(
            "INSERT INTO "
            + table
            + "("
            + ",".join("`" + name + "`" for name in names)
            + ") VALUES("
            + ",".join(["%s"] * len(names))
            + ")",
            tuple(values.values()),
        )

    def prepare():
        admin.begin()
        try:
            now = sql("SELECT UTC_TIMESTAMP(6)", rows=True)[0][0]
            identifier, snapshot_id = str(uuid4()), str(uuid4())
            key = raw_hash(uuid4().bytes)
            common = {"tenant_id": tenant, "simulation_id": identifier}
            insert(
                TABLES[0],
                {
                    "tenant_id": tenant,
                    "id": identifier,
                    "snapshot_id": snapshot_id,
                    "actor_id": 1,
                    "key_hash": key,
                    "intent_hash": "b" * 64,
                    "rule_id": rule["id"],
                    "rule_revision": 1,
                    "manifest_id": manifest,
                    "scope_snapshot_id": frozen["id"],
                    "profile_id": profile["id"],
                    "profile_version": profile["version"],
                    "profile_hash": profile_source["profile_hash"],
                    "source_publication_id": publication["id"],
                    "source_generation": generation,
                    "input_json": '{"scope":"SQL_ONLY_NOT_SOURCE_AUTHORITY"}',
                    "input_hash": "c" * 64,
                    "expected_account_count": 1,
                    "expected_unit_count": 1,
                    "expected_entity_count": 1,
                    "leaf_count": 2,
                    "build_epoch": 1,
                    "build_token_hash": "d" * 64,
                    "evaluated_at": now,
                    "lease_until": now + timedelta(minutes=5),
                },
            )
            insert(
                TABLES[1],
                common
                | {
                    "manifest_id": manifest,
                    "account_id": account,
                    "timezone_name": "Asia/Shanghai",
                    "currency": "USD",
                    "owner_user_id": owner,
                    "owner_team_id": team,
                    "date_from": now.date(),
                    "date_to": now.date(),
                    "expected_units_hash": "e" * 64,
                },
            )
            insert(
                TABLES[2],
                common
                | {
                    "account_id": account,
                    "business_date": now.date(),
                    "profile_id": profile["id"],
                    "profile_version": profile["version"],
                    "status": "MISSING",
                    "expectation_hash": "e" * 64,
                    "selected_hash": "f" * 64,
                },
            )
            insert(
                TABLES[3],
                common
                | {
                    "entity_id": tree[3]["entity_id"],
                    "account_id": account,
                    "source_snapshot_id": tree[3]["id"],
                    "entity_kind": "AD",
                    "currency": "USD",
                    "truth": "UNKNOWN",
                    "entity_hash": "a" * 64,
                },
            )
            leaves = [
                {
                    "entity_id": tree[3]["entity_id"],
                    "condition_index": index,
                    "value": None,
                    "result": "UNKNOWN",
                    "reason_code": "METRIC_MISSING",
                }
                for index in range(2)
            ]
            for leaf in leaves:
                insert(TABLES[4], common | leaf)
            insert(
                TABLES[5],
                {
                    "tenant_id": tenant,
                    "actor_id": 1,
                    "key_hash": key,
                    "intent_hash": "b" * 64,
                    "simulation_id": identifier,
                    "build_epoch": 1,
                },
            )
            admin.commit()
            return {"id": identifier, "snapshot_id": snapshot_id, "key": key, "leaves": leaves}
        except BaseException:
            admin.rollback()
            raise

    build = prepare()
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_rule_simulation_condition WHERE "
            "tenant_id=%s AND simulation_id=%s",
            (tenant, build["id"]),
            rows=True,
        )[0][0]
        == 2
    )
    cases.append(RULE_SIMULATION_SCHEMA_CASES[1])

    def persistent_rows():
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", rows=True) for table in TABLES)

    def response(build, now):
        return {
            "id": build["id"],
            "rule_id": rule["id"],
            "revision": 1,
            "snapshot_id": build["snapshot_id"],
            "hash": "f" * 64,
            "account_count": 1,
            "scanned_count": 1,
            "hit_count": 0,
            "unknown_count": 1,
            "false_count": 0,
            "conditions": build["leaves"],
            "expires_at": (now + timedelta(minutes=15)).isoformat(timespec="microseconds") + "Z",
            "next_cursor": None,
        }

    def seal(build, now, raw, document):
        event = str(uuid4())
        insert(
            TABLES[6],
            {
                "tenant_id": tenant,
                "id": event,
                "simulation_id": build["id"],
                "actor_id": 1,
                "request_id": str(uuid4()),
                "action": "READY",
                "details_json": '{"scope":"SQL_ONLY_NOT_SIMULATION_ISSUER"}',
            },
        )
        insert(TABLES[7], {"tenant_id": tenant, "event_id": event})
        sql(
            "UPDATE orbit_rule_simulation SET "
            "state='READY',sealed_at=%s,expires_at=%s,scanned_count=1,"
            "hit_count=0,unknown_count=1,false_count=0,condition_count=2,entity_ids_root=%s,results_root=%s,"
            "business_hash=%s WHERE tenant_id=%s AND id=%s AND state='BUILDING'",
            (now, now + timedelta(minutes=15), "a" * 64, "e" * 64, "f" * 64, tenant, build["id"]),
        )
        sql(
            "UPDATE orbit_rule_simulation_request SET "
            "state='COMPLETED',response_json=%s,response_bytes=%s,"
            "response_hash=%s WHERE tenant_id=%s AND actor_id=1 AND "
            "key_hash=%s AND state='PENDING'",
            (canonical(document), raw, raw_hash(raw), tenant, build["key"]),
        )

    def reject(build, mutation):
        before = persistent_rows()
        admin.begin()
        try:
            now = sql("SELECT UTC_TIMESTAMP(6)", rows=True)[0][0]
            original = response(build, now)
            raw, stored = mutation(original)
            seal(build, now, raw, stored)
        except pymysql.MySQLError as error:
            errno = error.args[0] if error.args and type(error.args[0]) is int else None
            print(
                json.dumps(
                    {
                        "scope": "simulation-schema-fixture",
                        "phase": "expected-rejection",
                        "errno": errno,
                    }
                ),
                flush=True,
            )
            assert errno == 1644
        else:
            raise AssertionError("SIM_SCHEMA_INVALID_RECEIPT_ACCEPTED")
        finally:
            admin.rollback()
        assert persistent_rows() == before

    admin.begin()
    try:
        now = sql("SELECT UTC_TIMESTAMP(6)", rows=True)[0][0]
        document = response(build, now)
        assert parse_rule_response(Simulation, document).model_dump() == document
        raw = json.dumps(document, ensure_ascii=False, indent=2).encode()
        assert same_response(raw, document) and raw != canonical(document).encode()
        seal(build, now, raw, document)
        admin.commit()
    except BaseException:
        admin.rollback()
        raise
    stored_json, stored_raw, stored_hash = sql(
        "SELECT response_json,response_bytes,response_hash FROM "
        "orbit_rule_simulation_request WHERE tenant_id=%s AND key_hash=%s",
        (tenant, build["key"]),
        rows=True,
    )[0]
    assert (
        stored_raw == raw and stored_hash == raw_hash(raw) and json.loads(stored_json) == document
    )
    header = {
        key: value for key, value in document.items() if key not in {"conditions", "next_cursor"}
    }
    OriginalSimulationReceipt.bind(
        stored_raw,
        response_json=stored_json,
        header=header,
        first_conditions=build["leaves"],
        next_cursor=None,
    )
    # 封存头、叶、原receipt、audit不可变精确1644；不drop trigger做破坏。
    for table, field in (
        (TABLES[0], "business_hash"),
        (TABLES[4], "reason_code"),
        (TABLES[5], "response_hash"),
    ):
        admin.begin()
        try:
            sql(
                "UPDATE " + table + " SET " + field + "=" + field + " WHERE tenant_id=%s", (tenant,)
            )
        except pymysql.MySQLError as error:
            assert error.args[0] == 1644
        else:
            raise AssertionError("SIM_SCHEMA_SEALED_UPDATE_ACCEPTED")
        finally:
            admin.rollback()
    cases.append(RULE_SIMULATION_SCHEMA_CASES[2])

    build = prepare()

    def different_raw(document):
        other = {**document, "id": str(uuid4())}
        assert parse_rule_response(Simulation, other).model_dump() == other
        raw = canonical(other).encode()
        assert raw_hash(raw) == digest(other) and not same_response(raw, document)
        return raw, document

    reject(build, different_raw)
    cases.append(RULE_SIMULATION_SCHEMA_CASES[3])

    def different_json(document):
        other = {**document, "hash": "1" * 64}
        return canonical(document).encode(), other

    reject(build, different_json)
    cases.append(RULE_SIMULATION_SCHEMA_CASES[4])

    def reversed_raw(document):
        return canonical(
            {**document, "conditions": list(reversed(document["conditions"]))}
        ).encode(), document

    reject(build, reversed_raw)
    cases.append(RULE_SIMULATION_SCHEMA_CASES[5])
    reject(build, lambda document: (b"\xff" + canonical(document).encode(), document))
    cases.append(RULE_SIMULATION_SCHEMA_CASES[6])
    # 上述每次实际head+audit+outbox已写后receipt失败，八表原值完整不变。
    assert sql(
        "SELECT state FROM orbit_rule_simulation WHERE tenant_id=%s AND id=%s",
        (tenant, build["id"]),
        rows=True,
    ) == (("BUILDING",),)
    assert sql(
        "SELECT state,response_bytes FROM orbit_rule_simulation_request "
        "WHERE tenant_id=%s AND key_hash=%s",
        (tenant, build["key"]),
        rows=True,
    ) == (("PENDING", None),)
    cases.append(RULE_SIMULATION_SCHEMA_CASES[7])
    return {
        "candidate_sha256": raw_hash(source),
        "tables": 8,
        "triggers": 24,
        "technical_sql_only": True,
        "simulation_http_called": False,
        "source_authority_verified": False,
    }
