"""061真实DDL及可选sealed manifest探针；不等于完整RuleVersion或业务验收。"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pymysql
from pymysql.constants import CLIENT

ROOT = Path(__file__).resolve().parents[1]


def seed_history(cursor):
    """仅建立原025/057有成员的sealed manifest；不冒充完整RuleVersion升级。"""
    tenant, team, owner, account, snapshot, manifest, rule = (str(uuid4()) for _ in range(7))
    digest = "a" * 64
    cursor.execute("INSERT INTO orbit_tenant(id,name) VALUES(%s,'061旧历史技术样本')", (tenant,))
    cursor.execute(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'旧团队')", (tenant, team)
    )
    cursor.execute(
        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(%s,%s,1,%s)",
        (tenant, owner, team),
    )
    cursor.execute(
        "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
        "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
        "bound_at,created_at) VALUES(%s,%s,'000061','旧账户','旧账户',%s,%s,'USD',"
        "'Asia/Shanghai','AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (tenant, account, owner, team),
    )
    frozen = [[account, "000061", "旧账户", 1, owner, team, "USD"]]
    root = hashlib.sha256(
        json.dumps(frozen, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    ids_root = hashlib.sha256(json.dumps([account], separators=(",", ":")).encode()).hexdigest()
    cursor.execute(
        "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,scope_version,"
        "auth_fingerprint,request_key,request_hash,request_json,created_at) "
        "VALUES(%s,%s,1,1,%s,'legacy-061',%s,'{}',UTC_TIMESTAMP(3))",
        (tenant, snapshot, digest, digest),
    )
    cursor.execute(
        "INSERT INTO orbit_account_scope_member(tenant_id,snapshot_id,account_id,external_id,"
        "name,name_prefix,account_revision,owner_user_id,owner_team_id,currency) "
        "VALUES(%s,%s,%s,'000061','旧账户','旧账户',1,%s,%s,'USD')",
        (tenant, snapshot, account, owner, team),
    )
    cursor.execute(
        "UPDATE orbit_account_scope_snapshot SET member_count=1,members_hash=%s,ready=1 "
        "WHERE tenant_id=%s AND id=%s",
        (root, tenant, snapshot),
    )
    cursor.execute(
        "INSERT INTO orbit_rule_scope_manifest(tenant_id,id,rule_id,source_snapshot_id,"
        "source_snapshot_hash,member_ids_hash,member_count,created_by,creator_auth_fingerprint,"
        "owner_user_id,owner_team_id,owner_auth_fingerprint) "
        "VALUES(%s,%s,%s,%s,%s,%s,1,1,%s,%s,%s,%s)",
        (tenant, manifest, rule, snapshot, root, ids_root, digest, owner, team, digest),
    )
    cursor.execute(
        "INSERT INTO orbit_rule_scope_member(tenant_id,manifest_id,account_id,"
        "frozen_owner_user_id,frozen_owner_team_id,frozen_currency,frozen_revision) "
        "VALUES(%s,%s,%s,%s,%s,'USD',1)",
        (tenant, manifest, account, owner, team),
    )
    cursor.execute(
        "UPDATE orbit_rule_scope_manifest SET sealed=1 WHERE tenant_id=%s AND id=%s",
        (tenant, manifest),
    )
    tables = (
        "orbit_account_scope_snapshot",
        "orbit_account_scope_member",
        "orbit_rule_scope_manifest",
        "orbit_rule_scope_member",
    )
    original = {}
    for table in tables:
        cursor.execute("SELECT * FROM " + table + " WHERE tenant_id=%s", (tenant,))
        original[table] = ([col[0] for col in cursor.description], cursor.fetchall())
    return tenant, manifest, snapshot, original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-history", action="store_true")
    args = parser.parse_args()
    database = "orbit_py_it_" + uuid4().hex
    candidate = ROOT / "docs/orbit/sql-drafts/061_rule_editor_scopes_candidate.sql"
    report = {
        "status": "RUNNING",
        "scope": "EMPTY_SCHEMA_ONLY_NOT_SEALED_HISTORY_OR_BUSINESS_ACCEPTANCE",
        "time": datetime.now(UTC).isoformat(),
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.with_history:
        report["scope"] = "SEALED_SCOPE_MANIFEST_ONLY_NOT_RULE_VERSION_OR_BUSINESS_ACCEPTANCE"
    with (
        pymysql.connect(
            host="127.0.0.1",
            port=13306,
            user="root",
            password="",
            autocommit=True,
            charset="utf8mb4",
            client_flag=CLIENT.MULTI_STATEMENTS,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT @@datadir")
        actual = Path(cursor.fetchone()[0]).resolve()
        assert actual == (ROOT.parent / ".runtime/mysql-it/data").resolve()
        created = False
        try:
            cursor.execute(
                f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
            )
            created = True
            cursor.execute(f"USE `{database}`")

            def apply(path):
                cursor.execute(path.read_text(encoding="utf-8"))
                while cursor.nextset():
                    pass

            apply(ROOT / "python/ruoyi_fastapi/sql/ruoyi-fastapi.sql")
            for path in sorted((ROOT / "python/orbit_api/migrations").glob("*.sql")):
                if int(path.name.partition("_")[0]) <= 60:
                    apply(path)
            cursor.execute(
                "SELECT CONSTRAINT_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s "
                "AND TABLE_NAME='orbit_rule_scope_manifest' AND REFERENCED_TABLE_NAME IS NOT NULL "
                "ORDER BY CONSTRAINT_NAME,ORDINAL_POSITION",
                (database,),
            )
            report["old_foreign_keys"] = cursor.fetchall()
            old_source = [
                r for r in report["old_foreign_keys"] if r[0] == "orbit_rule_scope_manifest_ibfk_2"
            ]
            assert old_source == [
                (
                    "orbit_rule_scope_manifest_ibfk_2",
                    "tenant_id",
                    "orbit_account_scope_snapshot",
                    "tenant_id",
                ),
                (
                    "orbit_rule_scope_manifest_ibfk_2",
                    "source_snapshot_id",
                    "orbit_account_scope_snapshot",
                    "id",
                ),
            ]

            def guards():
                cursor.execute(
                    "SELECT TRIGGER_NAME,ACTION_STATEMENT FROM information_schema.TRIGGERS "
                    "WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE='orbit_rule_scope_manifest' "
                    "ORDER BY TRIGGER_NAME",
                    (database,),
                )
                return dict(cursor.fetchall())

            before = guards()
            assert len(before) == 3
            history = seed_history(cursor) if args.with_history else None
            apply(candidate)
            after = guards()
            assert all(after.get(name) == statement for name, statement in before.items())
            report["old_trigger_definitions_unchanged"] = True
            if history:
                tenant, manifest, snapshot, original = history
                for table, (columns, rows) in original.items():
                    cursor.execute(
                        "SELECT " + ",".join(columns) + " FROM " + table + " WHERE tenant_id=%s",
                        (tenant,),
                    )
                    assert cursor.fetchall() == rows
                cursor.execute(
                    "SELECT source_kind,account_source_snapshot_id,rule_source_snapshot_id "
                    "FROM orbit_rule_scope_manifest WHERE tenant_id=%s AND id=%s",
                    (tenant, manifest),
                )
                assert cursor.fetchone() == ("ACCOUNT", snapshot, None)
                report["legacy_four_tables_original_columns_unchanged"] = True
                for statement in (
                    "UPDATE orbit_rule_scope_manifest SET source_kind='RULE' "
                    "WHERE tenant_id=%s AND id=%s",
                    "UPDATE orbit_rule_scope_manifest SET source_snapshot_hash=REPEAT('b',64) "
                    "WHERE tenant_id=%s AND id=%s",
                    "DELETE FROM orbit_rule_scope_manifest WHERE tenant_id=%s AND id=%s",
                ):
                    try:
                        cursor.execute(statement, (tenant, manifest))
                    except pymysql.MySQLError as error:
                        assert error.args[0] == 1644
                    else:
                        raise AssertionError("SEALED_HISTORY_WRITE_ACCEPTED")
                report["sealed_history_three_mutations_rejected_1644"] = True
            report["status"] = "PASS"
        except Exception as error:
            report["status"] = "FAIL"
            report["failure_type"] = type(error).__name__
            report["database_error_code"] = (
                error.args[0] if error.args and type(error.args[0]) is int else None
            )
        finally:
            if created:
                cursor.execute(f"DROP DATABASE `{database}`")
            name = (
                "python-rule-scope061-sealed-manifest.json"
                if args.with_history
                else "python-rule-scope061-empty-schema.json"
            )
            (ROOT / "docs/orbit/evidence" / name).write_text(
                json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
            )
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
