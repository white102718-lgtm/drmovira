"""仅五万synthetic账户与原scope创建/250页；不执行日事实或并发账户容量门禁。"""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

if __package__:
    from .account_scope_capacity_diagnostics import collect_timeout_diagnostic, guard_output
else:
    from account_scope_capacity_diagnostics import collect_timeout_diagnostic, guard_output

SCOPE_CREATE_PROFILE_CASES = [
    "pythonScopeCreateProfileActualSyntheticFiftyThousandAccountsWithoutDailyFacts",
    "pythonScopeCreateProfileOriginal201FiveFieldsAndAllFrozenValuesHash",
    "pythonScopeCreateProfileAll250PagesExactIdsNoDuplicatesOmissionsOrHashDrift",
]
COUNT = 50000
PAGE_SIZE = 200


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("SCOPE_PROFILE_ISOLATED_TARGET_REQUIRED")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def member_digest(rows):
    result = hashlib.sha256(b"[")
    for index, row in enumerate(rows):
        if len(row) != 7:
            raise ValueError("ORIGINAL_SEVEN_FROZEN_FIELDS_REQUIRED")
        if index:
            result.update(b",")
        result.update(canonical(list(row)).encode())
    result.update(b"]")
    return result.hexdigest()


def run_scope_create_profile_checks(
    client, admin, headers, password, cache, database, cases, *, diagnostic_dir
):
    guard_target(admin, database)
    directory = guard_output(diagnostic_dir)
    if client.timeout.read != 10:
        raise ValueError("SCOPE_PROFILE_ORIGINAL_TEN_SECOND_READ_TIMEOUT_REQUIRED")
    report = {
        "status": "RUNNING",
        "synthetic_accounts": 0,
        "daily_facts": 0,
        "member_pages": 0,
        "platform_writes": 0,
        "diagnostic_only": True,
    }

    def save():
        try:
            (directory / "scope-profile-report.json").write_text(
                canonical(report), encoding="utf-8"
            )
        except OSError:
            # 诊断写入失败不得替代原ReadTimeout/业务异常。
            report["diagnostic_write_failures"] = report.get("diagnostic_write_failures", 0) + 1

    def checked(response, status):
        assert response.status_code == status, {
            "expected_status": status,
            "actual_status": response.status_code,
        }
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("x-request-id")
        return response.json()

    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            assert cursor.fetchone()[0] == database
            cursor.execute(
                "SELECT @@global.innodb_buffer_pool_size,@@global.innodb_redo_log_capacity,"
                "@@global.innodb_flush_log_at_trx_commit"
            )
            report["mysql_settings"] = dict(
                zip(
                    ("buffer_pool_bytes", "redo_capacity_bytes", "flush_log_at_trx_commit"),
                    cursor.fetchone(),
                    strict=True,
                )
            )
            # 原runner root头由真实bootstrap1登录；不依赖其他工具的全局owner对象。
            cursor.execute(
                "SELECT b.tenant_id,b.id,b.team_id FROM orbit_business_user b "
                "JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0' "
                "JOIN orbit_business_team t ON t.tenant_id=b.tenant_id AND t.id=b.team_id "
                "AND t.enabled=1 JOIN orbit_user_scope s ON s.user_id=b.user_id "
                "AND s.tenant_id=b.tenant_id AND s.enabled=1 "
                "WHERE b.user_id=1 AND b.enabled=1 AND b.invited=0"
            )
            mapping = cursor.fetchall()
            assert len(mapping) == 1
            tenant, owner, team = mapping[0]
        admin.commit()
        ids = sorted(str(uuid4()) for _ in range(COUNT))
        assert len(set(ids)) == COUNT
        marker = "ScopeProfile-" + uuid4().hex[:16]
        seed_start = time.perf_counter()
        insert = (
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
            "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
            "value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        with admin.cursor() as cursor:
            for offset in range(0, COUNT, 500):
                admin.begin()
                try:
                    cursor.executemany(
                        insert,
                        [
                            (
                                tenant,
                                account,
                                str(10**30 + index),
                                marker,
                                marker,
                                owner,
                                team,
                                "USD" if index % 2 == 0 else "EUR",
                                "Asia/Shanghai",
                                "AUTHORIZED",
                                "ACTIVE",
                                "{}",
                                "{}",
                                datetime(2020, 1, 1),
                                now,
                            )
                            for index, account in enumerate(ids[offset : offset + 500], offset)
                        ],
                    )
                    admin.commit()
                except BaseException:
                    admin.rollback()
                    raise
                report["synthetic_accounts"] = offset + 500
                save()
            admin.begin()
            try:
                cursor.execute(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
                assert cursor.rowcount == 1
                admin.commit()
            except BaseException:
                admin.rollback()
                raise
            cursor.execute(
                "SELECT id,external_id,name,revision,owner_user_id,owner_team_id,currency "
                "FROM orbit_ad_account WHERE tenant_id=%s AND name_prefix=%s ORDER BY id",
                (tenant, marker),
            )
            frozen_rows = cursor.fetchall()
            assert len(frozen_rows) == COUNT
            for index, row in enumerate(frozen_rows):
                assert tuple(row) == (
                    ids[index],
                    str(10**30 + index),
                    marker,
                    1,
                    owner,
                    team,
                    "USD" if index % 2 == 0 else "EUR",
                )
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_account_spend_day f JOIN orbit_ad_account a "
                "ON a.tenant_id=f.tenant_id AND a.id=f.account_id "
                "WHERE a.tenant_id=%s AND a.name_prefix=%s",
                (tenant, marker),
            )
            assert cursor.fetchone()[0] == 0
        admin.commit()
        expected_hash = member_digest(frozen_rows)
        report["seed_seconds"] = time.perf_counter() - seed_start
        cases.append(SCOPE_CREATE_PROFILE_CASES[0])
        caps = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200)
        assert isinstance(caps.get("csrf_token"), str)
        started = time.perf_counter()
        try:
            response = client.post(
                "/api/v1/scope-snapshots",
                headers=headers
                | {
                    "X-CSRF-Token": caps["csrf_token"],
                    "Idempotency-Key": "scope-profile-" + uuid4().hex,
                },
                json={
                    "mode": "FILTER",
                    "account_ids": [],
                    "filter": {
                        "q": marker,
                        "status": None,
                        "auth_status": None,
                        "operator_user_id": None,
                        "vendor_id": None,
                    },
                },
            )
        except httpx.ReadTimeout:
            report["create_seconds"] = time.perf_counter() - started
            report["status"] = "READ_TIMEOUT"
            try:
                report["timeout_diagnostic"] = collect_timeout_diagnostic(
                    admin, database, directory
                )
            except Exception:
                report["timeout_diagnostic"] = {"collected": False}
            save()
            raise
        frozen = checked(response, 201)
        assert set(frozen) == {"id", "count", "scope_version", "hash", "created_at"}
        assert type(frozen["count"]) is int and frozen["count"] == COUNT
        assert str(UUID(frozen["id"])) == frozen["id"]
        assert (
            type(frozen["scope_version"]) is int
            and 1 <= frozen["scope_version"] <= 9007199254740991
        )
        assert frozen["hash"] == expected_hash
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", frozen["created_at"])
        datetime.fromisoformat(frozen["created_at"].replace("Z", "+00:00"))
        report["create_seconds"] = time.perf_counter() - started
        report["all_seven_frozen_fields_hash_matches"] = True
        cases.append(SCOPE_CREATE_PROFILE_CASES[1])
        seen, cursors, cursor, all_members = [], set(), None, []
        while True:
            params = {"page_size": "200"}
            if cursor is not None:
                params["cursor"] = cursor
            page = checked(
                client.get(
                    f"/api/v1/scope-snapshots/{frozen['id']}/members",
                    headers=headers,
                    params=params,
                ),
                200,
            )
            assert set(page) == {"items", "next_cursor", "data_as_of", "scope_version"}
            assert (
                page["data_as_of"] == frozen["created_at"]
                and page["scope_version"] == frozen["scope_version"]
            )
            assert len(page["items"]) == PAGE_SIZE
            for item in page["items"]:
                assert set(item) == {"account_id", "external_id", "name"}
                index = len(seen)
                assert item == {
                    "account_id": ids[index],
                    "external_id": str(10**30 + index),
                    "name": marker,
                }
                seen.append(item["account_id"])
                all_members.append(
                    (
                        item["account_id"],
                        item["external_id"],
                        item["name"],
                        1,
                        owner,
                        team,
                        "USD" if index % 2 == 0 else "EUR",
                    )
                )
            report["member_pages"] += 1
            assert report["member_pages"] <= 250
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert isinstance(cursor, str) and 1 <= len(cursor) <= 2048 and cursor not in cursors
            cursors.add(cursor)
        assert report["member_pages"] == 250 and seen == ids and len(set(seen)) == COUNT
        assert member_digest(all_members) == frozen["hash"] == expected_hash
        report.update(
            status="PASS",
            members=COUNT,
            omissions=0,
            duplicates=0,
            create_and_members_seconds=time.perf_counter() - started,
        )
        cases.append(SCOPE_CREATE_PROFILE_CASES[2])
        save()
        return report
    except BaseException:
        if report["status"] != "READ_TIMEOUT":
            report["status"] = "FAIL"
        save()
        raise
