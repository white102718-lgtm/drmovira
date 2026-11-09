"""全体范围可见性SQL实测：不缓存授权、不改生产索引，不重复百万事实。"""

import hashlib
import json
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from orbit_api.account_access import visible_clause
from orbit_api.authorization import BusinessContext

CASES = (
    ["pythonScopeVisibilityActualFiftyThousandAccountsAndThreeRoleSnapshots"]
    + [
        "pythonScopeVisibility" + role + suffix
        for role in ("SUPER_ADMIN", "TEAM_ADMIN", "USER")
        for suffix in ("EquivalentPlansMeasured", "NoClockMutationStillDenied")
    ]
    + ["pythonScopeVisibilityExclusiveFixtureCleanup"]
)


def summary(plan):
    """保存真实索引/估算行数，丢弃包含夹具UUID常量的where文本。"""
    rows = []
    if isinstance(plan, dict):
        if "table_name" in plan:
            rows.append(
                {
                    key: plan[key]
                    for key in (
                        "table_name",
                        "access_type",
                        "possible_keys",
                        "key",
                        "used_key_parts",
                        "rows_examined_per_scan",
                        "rows_produced_per_join",
                        "filtered",
                        "cost_info",
                    )
                    if key in plan
                }
            )
        for value in plan.values():
            rows.extend(summary(value))
    elif isinstance(plan, list):
        for value in plan:
            rows.extend(summary(value))
    return rows


def prepare_plan_identities(client, admin, headers, password, cache):
    """专用read角色走真实API；两个人员仅本轮隔离库，ID占用则拒绝覆盖。"""
    from fixture_login import fixture_login

    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id IN(990360,990361)")
        assert cursor.fetchone()[0] == 0, "性能身份专用ID已占用，拒绝覆盖"
    cap = client.get("/api/v1/roles/capabilities", headers=headers)
    assert cap.status_code == 200
    response = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": cap.json()["csrf_token"],
            "Idempotency-Key": "plan-role-" + uuid4().hex,
        },
        json={
            "name": "范围计划只读-" + uuid4().hex[:12],
            "menu_codes": ["accounts"],
            "permission_codes": ["accounts.read"],
        },
    )
    assert response.status_code == 201
    identities = {
        "SUPER_ADMIN": {
            "headers": headers,
            "actor_id": 1,
            "owner_user_id": root_owner,
            "owner_team_id": team,
        }
    }
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, response.json()["id"]),
        )
        role_id = cursor.fetchone()[0]
        for native, role in ((990360, "TEAM_ADMIN"), (990361, "USER")):
            owner, name = str(uuid4()), "scope_plan_" + uuid4().hex[:12]
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (native, name, "范围计划只读夹具", name + "@fixture.example.org"),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, role_id)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,%s)",
                (native, tenant, role),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
                "invited,created_at) VALUES(%s,%s,%s,%s,'范围计划只读夹具',0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team),
            )
            if role == "TEAM_ADMIN":
                cursor.execute(
                    "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
                    "VALUES(%s,%s,%s)",
                    (tenant, native, team),
                )
            identities[role] = {
                "actor_id": native,
                "owner_user_id": owner,
                "owner_team_id": team,
                "username": name,
            }
    admin.commit()
    for role in ("TEAM_ADMIN", "USER"):
        identity = identities[role]
        login = fixture_login(
            client, cache, {"username": identity.pop("username"), "password": password}
        )
        assert login.status_code == 200 and login.json().get("token")
        identity["headers"] = {"Authorization": "Bearer " + login.json()["token"]}
    return identities


def run_account_scope_visibility_plan_checks(
    client, admin, headers, password, cache, database, cases
):
    """自行准备真实SUPER/TEAM/USER read身份；仅SQL计划微基准，不冒充HTTP成员性能。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("可见性性能仅允许主线当前UUID独立MySQL库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
    identities = prepare_plan_identities(client, admin, headers, password, cache)
    output = (
        Path(__file__).resolve().parents[2] / ".runtime/account-scope-visibility-plan-current.json"
    )
    marker = "VisibilityPlan-" + uuid4().hex
    shadow = "scope_plan_" + uuid4().hex  # 只含本工具生成的ASCII标识，不插入请求值。
    identifiers = sorted(str(uuid4()) for _ in range(50000))
    snapshots = {role: str(uuid4()) for role in identities}
    contexts, measurements = {}, []
    report = {
        "result": "RUNNING",
        "account_count": 50000,
        "snapshot_count": 3,
        "member_count_per_snapshot": 50000,
        "daily_fact_count": 0,
        "cache_note": "装载后首读/暖读SQL微基准，不是冷缓存或完整HTTP容量验收",
        "candidate_note": "覆盖索引只在同连接TEMPORARY影子表，不改变生产表/索引",
        "measurements": measurements,
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE(),VERSION()")
        actual, report["mysql_version"] = cursor.fetchone()
        assert actual == database
        for role, identity in identities.items():
            response = client.get(
                "/api/v1/scope-snapshots/capabilities", headers=identity["headers"]
            )
            assert response.status_code == 200, (role, response.status_code)
            cursor.execute(
                "SELECT s.tenant_id,s.data_role,b.id,b.team_id,i.auth_version "
                "FROM orbit_user_scope s "
                "JOIN orbit_business_user b ON b.tenant_id=s.tenant_id AND b.user_id=s.user_id "
                "JOIN sys_identity_subject i ON i.user_id=s.user_id WHERE s.user_id=%s",
                (identity["actor_id"],),
            )
            tenant, actual_role, subject, team, version = cursor.fetchone()
            assert actual_role == role and subject == identity["owner_user_id"]
            contexts[role] = (
                BusinessContext(identity["actor_id"], tenant, role, subject, team),
                version,
            )
        assert len({current.tenant_id for current, _ in contexts.values()}) == 1
        tenant = contexts["USER"][0].tenant_id
        owner, team = contexts["USER"][0].subject_id, contexts["USER"][0].team_id
        manager = contexts["TEAM_ADMIN"][0].actor_id
        cursor.execute(
            "SELECT 1 FROM orbit_business_team_manager WHERE tenant_id=%s "
            "AND manager_user_id=%s AND team_id=%s AND enabled=1",
            (tenant, manager, team),
        )
        assert cursor.fetchone(), "TEAM_ADMIN必须明确管理USER夹具所在团队"
    created = False
    try:
        created = True
        now = datetime.now(UTC).replace(tzinfo=None)
        digest = hashlib.sha256("\n".join(identifiers).encode()).hexdigest()
        start = time.perf_counter()
        with admin.cursor() as cursor:
            for role, (current, version) in contexts.items():
                cursor.execute(
                    "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,scope_version,"
                    "auth_fingerprint,request_key,request_hash,request_json,member_count,members_hash,"
                    "ready,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,50000,%s,0,%s)",
                    (
                        tenant,
                        snapshots[role],
                        current.actor_id,
                        version,
                        "0" * 64,
                        marker + role,
                        digest,
                        "{}",
                        digest,
                        now,
                    ),
                )
            for offset in range(0, 50000, 500):
                batch = identifiers[offset : offset + 500]
                cursor.executemany(
                    "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                    "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
                    "value_json,details_json,bound_at,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            tenant,
                            identifier,
                            str(10**29 + uuid4().int % 10**28),
                            marker,
                            marker,
                            owner,
                            team,
                            "USD",
                            "UTC",
                            "AUTHORIZED",
                            "ACTIVE",
                            "{}",
                            "{}",
                            now,
                            now,
                        )
                        for identifier in batch
                    ],
                )
                for snapshot in snapshots.values():
                    cursor.executemany(
                        "INSERT INTO orbit_account_scope_member(tenant_id,snapshot_id,account_id,"
                        "external_id,name,name_prefix,account_revision,owner_user_id,"
                        "owner_team_id,currency) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        [
                            (
                                tenant,
                                snapshot,
                                identifier,
                                "1",
                                marker,
                                marker,
                                1,
                                owner,
                                team,
                                "USD",
                            )
                            for identifier in batch
                        ],
                    )
                admin.commit()
            for snapshot in snapshots.values():
                cursor.execute(
                    "UPDATE orbit_account_scope_snapshot SET ready=1 WHERE tenant_id=%s AND id=%s",
                    (tenant, snapshot),
                )
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
        report["seed_seconds"] = time.perf_counter() - start
        cases.append(CASES[0])

        with admin.cursor() as cursor:
            cursor.execute(f"CREATE TEMPORARY TABLE {shadow} LIKE orbit_ad_account")
            cursor.execute(
                f"INSERT INTO {shadow} SELECT * FROM orbit_ad_account "
                "WHERE tenant_id=%s AND name_prefix=%s",
                (tenant, marker),
            )
            cursor.execute(
                f"ALTER TABLE {shadow} ADD KEY fixture_visibility_cover "
                "(tenant_id,id,owner_user_id,owner_team_id)"
            )
        for index, (role, (current, _version)) in enumerate(contexts.items()):
            visible = visible_clause(current, "a")
            params = {
                "tenant": tenant,
                "snapshot": snapshots[role],
                "subject": current.subject_id,
                "actor": current.actor_id,
            }
            variants = {}
            for label, table in (("production", "orbit_ad_account"), ("shadow_cover", shadow)):
                # FORCE只适用于影子候选索引，不通过hint修改正式查询的被测计划。
                hint = " FORCE INDEX(fixture_visibility_cover)" if table == shadow else ""
                variants[label + "_left"] = (
                    "SELECT 1 FROM orbit_account_scope_member m LEFT JOIN "
                    + table
                    + " a"
                    + hint
                    + " ON a.tenant_id=m.tenant_id AND a.id=m.account_id "
                    "WHERE m.tenant_id=%(tenant)s AND m.snapshot_id=%(snapshot)s AND "
                    "(a.id IS NULL OR NOT (" + visible + ")) LIMIT 1"
                )
                variants[label + "_exists"] = (
                    "SELECT 1 FROM orbit_account_scope_member m WHERE m.tenant_id=%(tenant)s "
                    "AND m.snapshot_id=%(snapshot)s AND NOT EXISTS(SELECT 1 FROM "
                    + table
                    + " a"
                    + hint
                    + " WHERE a.tenant_id=m.tenant_id AND a.id=m.account_id AND ("
                    + visible
                    + ")) LIMIT 1"
                )
            variants = {
                key: sql.replace(":subject", "%(subject)s").replace(":actor", "%(actor)s")
                for key, sql in variants.items()
            }
            for state in ("all_visible", "one_invisible_without_clock_bump"):
                # SUPER没有owner撤权，负例用移出本租户的等价缺失行；仅独占最后一条夹具。
                hidden = identifiers[-1]
                if state != "all_visible":
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT * FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                            (tenant, hidden),
                        )
                        hidden_row = cursor.fetchone()
                        column_names = [entry[0] for entry in cursor.description]
                        assert all(re.fullmatch(r"[a-z_]+", column) for column in column_names)
                        cursor.execute(
                            "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,)
                        )
                        before_clock = cursor.fetchone()[0]
                        for table in ("orbit_ad_account", shadow):
                            if role == "SUPER_ADMIN":
                                cursor.execute(
                                    f"DELETE FROM {table} WHERE tenant_id=%s AND id=%s",
                                    (tenant, hidden),
                                )
                            else:
                                cursor.execute(
                                    f"UPDATE {table} SET owner_user_id=%s,owner_team_id=%s "
                                    "WHERE tenant_id=%s AND id=%s",
                                    (str(uuid4()), str(uuid4()), tenant, hidden),
                                )
                    admin.commit()
                for name, sql in variants.items():
                    timings = []
                    with admin.cursor() as cursor:
                        for _ in range(3):
                            begin = time.perf_counter()
                            cursor.execute(sql, params)
                            result = cursor.fetchone()
                            timings.append(time.perf_counter() - begin)
                            assert (result is None) == (state == "all_visible"), (role, state, name)
                        cursor.execute("EXPLAIN FORMAT=JSON " + sql, params)
                        tables = summary(json.loads(cursor.fetchone()[0]))
                        cursor.execute("EXPLAIN ANALYZE " + sql, params)
                        tree = cursor.fetchone()[0]
                    measurements.append(
                        {
                            "role": role,
                            "state": state,
                            "variant": name,
                            "seconds": timings,
                            "median_seconds": statistics.median(timings),
                            "selected_plan_tables": tables,
                            "analyze_tree": re.sub(
                                r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                                "<fixture-uuid>",
                                tree,
                            ),
                        }
                    )
                    save()
                if state != "all_visible":
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,)
                        )
                        assert cursor.fetchone()[0] == before_clock
                        if role == "SUPER_ADMIN":
                            # 从删除前已保存的实际同宽行恢复，不从已不存在的行SELECT空结果。
                            for table in ("orbit_ad_account", shadow):
                                cursor.execute(
                                    f"INSERT INTO {table}("
                                    + ",".join(column_names)
                                    + ") VALUES("
                                    + ",".join(["%s"] * len(column_names))
                                    + ")",
                                    hidden_row,
                                )
                        else:
                            for table in ("orbit_ad_account", shadow):
                                cursor.execute(
                                    f"UPDATE {table} SET owner_user_id=%s,owner_team_id=%s "
                                    "WHERE tenant_id=%s AND id=%s",
                                    (owner, team, tenant, hidden),
                                )
                    admin.commit()
            cases.extend(CASES[1 + index * 2 : 3 + index * 2])
        report["result"] = "PASS"
    except Exception:
        report["result"] = "FAIL"
        raise
    finally:
        if created:
            admin.rollback()
            with admin.cursor() as cursor:
                cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {shadow}")
                for snapshot in snapshots.values():
                    cursor.execute(
                        "UPDATE orbit_account_scope_snapshot SET cleanup_requested=1 "
                        "WHERE tenant_id=%s AND id=%s AND ready=1",
                        (tenant, snapshot),
                    )
                    cursor.execute(
                        "DELETE FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                        "AND snapshot_id=%s",
                        (tenant, snapshot),
                    )
                    cursor.execute(
                        "DELETE FROM orbit_account_scope_member WHERE tenant_id=%s "
                        "AND snapshot_id=%s",
                        (tenant, snapshot),
                    )
                    cursor.execute(
                        "DELETE FROM orbit_account_scope_snapshot WHERE tenant_id=%s AND id=%s",
                        (tenant, snapshot),
                    )
                    for table in ("orbit_account_scope_snapshot", "orbit_account_scope_member"):
                        key = "id" if table.endswith("snapshot") else "snapshot_id"
                        cursor.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s AND {key}=%s",
                            (tenant, snapshot),
                        )
                        assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "DELETE FROM orbit_ad_account WHERE tenant_id=%s AND name_prefix=%s",
                    (tenant, marker),
                )
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s AND name_prefix=%s",
                    (tenant, marker),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
            admin.commit()
            report["cleanup"] = "PASS"
            if report["result"] == "PASS":
                cases.append(CASES[-1])
        save()
