"""专属UUID库真实5万账户/100万日事实；记录20并发性能，不冒充平台采集或全模块容量。"""

import hashlib
import json
import math
import os
import platform
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import psutil

CASES = [
    "pythonAccountCapacityActualFiftyThousandAccountsAndMillionDailyFacts",
    "pythonAccountCapacityActualTwoHundredFiftyPagesHaveNoDuplicateOrOmission",
    "pythonAccountCapacityTwentyConcurrentReadsP95WithinOriginalOneSecondTarget",
]
SCOPE_CAPACITY_CASES = ["pythonAccountScopeCapacityActuallyFreezesFiftyThousandAndReadsAll250Pages"]


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def run_account_capacity_checks(
    client,
    admin,
    headers,
    owner,
    team,
    database,
    cases,
    backend_pid,
    *,
    include_scope=False,
    diagnostic_dir=None,
):
    """直接SQL仅建立容量夹具；接口始终使用真实身份、权限、游标和日期聚合。"""
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("容量工具仅允许本轮隔离MySQL库")
    output = Path(__file__).resolve().parents[2] / ".runtime/account-capacity-current.json"
    report = {
        "result": "RUNNING",
        "scope": "账户目录/当前日消费事实专项；非所有报表、任务、导出、范围冻结或平台容量验收",
        "cache_note": "首读和暖读；装载后数据库缓存可能已热，未声称真实冷启动",
        "machine": {
            "os": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": psutil.virtual_memory().total,
        },
        "target_p95_seconds": 1.0,
        "concurrency": 20,
        "errors": 0,
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def rss():
        return psutil.Process(backend_pid).memory_info().rss

    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE(),VERSION()")
            actual_database, version = cursor.fetchone()
            assert actual_database == database
            report["mysql_version"] = version
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
            cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner,))
            tenant = cursor.fetchone()[0]
        identifiers = sorted(str(uuid4()) for _ in range(50000))
        marker, snapshot = "Capacity-" + uuid4().hex[:12], str(uuid4())
        start = time.monotonic()
        with admin.cursor() as cursor:
            for offset in range(0, 50000, 500):
                # 所有值使用占位符，命中PyMySQL真正批量INSERT路径；每1万事实一个事务。
                # 混合SQL字面量/函数会让executemany退回逐行，不可用于容量夹具装载。
                admin.begin()
                cursor.executemany(
                    "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                    "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
                    "value_json,details_json,bound_at,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            tenant,
                            identifier,
                            str(10**30 + offset + index),
                            marker,
                            marker,
                            owner,
                            team,
                            "USD" if (offset + index) % 2 == 0 else "EUR",
                            "Asia/Shanghai",
                            "AUTHORIZED",
                            "ACTIVE",
                            "{}",
                            "{}",
                            datetime(2020, 1, 1),
                            datetime.now(UTC).replace(tzinfo=None),
                        )
                        for index, identifier in enumerate(identifiers[offset : offset + 500])
                    ],
                )
                # 每批1万条日事实，内存不保留100万行列表。
                cursor.executemany(
                    "INSERT INTO orbit_account_spend_day(tenant_id,account_id,business_date,"
                    "currency,amount,coverage,owner_user_id,owner_team_id,source,observed_at,"
                    "revision,snapshot_id,attribution_version,attribution_reason) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            tenant,
                            identifier,
                            date(2026, 10, 1) + timedelta(days=day),
                            "USD" if (offset + index) % 2 == 0 else "EUR",
                            "1.250000",
                            "COMPLETE",
                            owner,
                            team,
                            "VERIFIED_INGESTION",
                            datetime(2026, 10, 22),
                            1,
                            snapshot,
                            1,
                            "COVERED",
                        )
                        for index, identifier in enumerate(identifiers[offset : offset + 500])
                        for day in range(20)
                    ],
                )
                admin.commit()
                report["seed_progress"] = {"accounts": offset + 500, "facts": (offset + 500) * 20}
                save()
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
            cursor.execute(
                "UPDATE orbit_account_details_clock SET revision=revision+1,snapshot_id=%s "
                "WHERE tenant_id=%s",
                (snapshot, tenant),
            )
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s AND name=%s",
                (tenant, marker),
            )
            assert cursor.fetchone()[0] == 50000
            cursor.execute(
                "SELECT currency,COUNT(*),SUM(amount) FROM orbit_account_spend_day "
                "WHERE tenant_id=%s AND snapshot_id=%s GROUP BY currency",
                (tenant, snapshot),
            )
            totals = cursor.fetchall()
            assert set(totals) == {
                ("USD", 500000, Decimal("625000.000000")),
                ("EUR", 500000, Decimal("625000.000000")),
            }
            count = sum(row[1] for row in totals)
            report["seed"] = {
                "accounts": 50000,
                "facts": count,
                "seconds": time.monotonic() - start,
            }
            cursor.execute("SHOW INDEX FROM orbit_ad_account")
            report["account_indexes"] = [list(row) for row in cursor.fetchall()]
            cursor.execute(
                "EXPLAIN ANALYZE SELECT id FROM orbit_ad_account WHERE tenant_id=%s "
                "AND name_prefix LIKE %s AND unbound_at IS NULL AND id>%s ORDER BY id LIMIT 201",
                (tenant, marker + "%", "00000000-0000-0000-0000-000000000000"),
            )
            report["first_page_explain_analyze"] = [row[0] for row in cursor.fetchall()]
        cases.append(CASES[0])
        query = {
            "q": marker,
            "page_size": "200",
            "date_from": "2026-10-01",
            "date_to": "2026-10-20",
        }
        report["backend_rss_before_bytes"] = rss()

        def read(extra=None):
            began = time.perf_counter()
            response = client.get(
                "/api/v1/accounts/extended", headers=headers, params=query | (extra or {})
            )
            elapsed = time.perf_counter() - began
            assert response.status_code == 200, "容量读取未成功，不能忽略失败样本"
            value = response.json()
            for row in value["items"]:
                money = row["account"]["spend"]
                assert Decimal(money["amount"]) == Decimal("25.000000")
                assert money["currency"] == row["account"]["currency"]
            return value, elapsed

        page, first = read()
        report["first_read_seconds"] = first
        seen, cursors, pages = [], set(), 0
        while True:
            pages += 1
            seen.extend(row["account"]["id"] for row in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
            assert cursor not in cursors and pages <= 250
            cursors.add(cursor)
            page, _ = read({"cursor": cursor})
        assert pages == 250 and seen == identifiers and len(set(seen)) == 50000
        report["pagination"] = {"pages": pages, "unique_accounts": len(set(seen)), "omissions": 0}
        cases.append(CASES[1])
        # 固定20个工作线程同时发起，每线程10次；不包含预热数据，失败不能从分位数剔除。
        report["warm_by_page_size"] = {}
        for page_size in (20, 50, 100, 200):
            barrier = threading.Barrier(20)

            def worker(_, selected_size=page_size, selected_barrier=barrier):
                selected_barrier.wait(timeout=10)
                samples = []
                for _ in range(10):
                    _, elapsed = read({"page_size": str(selected_size)})
                    samples.append(elapsed)
                return samples

            began = time.perf_counter()
            with ThreadPoolExecutor(max_workers=20) as pool:
                samples = [sample for group in pool.map(worker, range(20)) for sample in group]
            elapsed = time.perf_counter() - began
            measurement = {
                "samples": len(samples),
                "p50_seconds": percentile(samples, 0.50),
                "p95_seconds": percentile(samples, 0.95),
                "p99_seconds": percentile(samples, 0.99),
                "throughput_per_second": len(samples) / elapsed,
                "elapsed_seconds": elapsed,
                "backend_rss_after_bytes": rss(),
            }
            report["warm_by_page_size"][str(page_size)] = measurement
            if page_size == 20:
                # 保留原20行样本字段，历史证据不能因此被重写为四档已测。
                report["warm"] = measurement
            save()
            assert len(samples) == 200 and measurement["p95_seconds"] <= 1.0
        cases.append(CASES[2])
        if include_scope:
            scope_start = time.perf_counter()
            caps = client.get("/api/v1/scope-snapshots/capabilities", headers=headers)
            assert caps.status_code == 200
            try:
                selected = client.post(
                    "/api/v1/scope-snapshots",
                    headers=headers
                    | {
                        "X-CSRF-Token": caps.json()["csrf_token"],
                        "Idempotency-Key": "capacity-scope-" + uuid4().hex,
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
                if diagnostic_dir is not None:
                    from account_scope_capacity_diagnostics import collect_timeout_diagnostic

                    try:
                        report["scope_timeout_diagnostic"] = collect_timeout_diagnostic(
                            admin, database, diagnostic_dir
                        )
                    except Exception as error:
                        report["scope_timeout_diagnostic"] = {
                            "collected": False,
                            "failure_type": type(error).__name__,
                        }
                raise
            assert selected.status_code == 201 and selected.json()["count"] == 50000
            frozen = selected.json()
            created_seconds = time.perf_counter() - scope_start
            expected_hash = hashlib.sha256(b"[")
            for index, identifier in enumerate(identifiers):
                if index:
                    expected_hash.update(b",")
                expected_hash.update(
                    json.dumps(
                        [
                            identifier,
                            str(10**30 + index),
                            marker,
                            1,
                            owner,
                            team,
                            "USD" if index % 2 == 0 else "EUR",
                        ],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                )
            expected_hash.update(b"]")
            assert frozen["hash"] == expected_hash.hexdigest()
            frozen_ids, frozen_cursors, member_cursor, member_pages = [], set(), None, 0
            while True:
                params = {"page_size": "200"}
                if member_cursor:
                    params["cursor"] = member_cursor
                members = client.get(
                    f"/api/v1/scope-snapshots/{frozen['id']}/members",
                    headers=headers,
                    params=params,
                )
                assert members.status_code == 200
                member_page = members.json()
                assert all(
                    set(row) == {"account_id", "external_id", "name"}
                    for row in member_page["items"]
                )
                frozen_ids.extend(row["account_id"] for row in member_page["items"])
                member_pages += 1
                member_cursor = member_page["next_cursor"]
                if not member_cursor:
                    break
                assert member_cursor not in frozen_cursors and member_pages <= 250
                frozen_cursors.add(member_cursor)
            assert (
                member_pages == 250 and frozen_ids == identifiers and len(set(frozen_ids)) == 50000
            )
            report["scope_capacity"] = {
                "frozen_members": 50000,
                "pages": 250,
                "omissions": 0,
                "duplicates": 0,
                "hash_matches_full_frozen_values": True,
                "create_seconds": created_seconds,
                "create_and_members_seconds": time.perf_counter() - scope_start,
            }
            cases.append(SCOPE_CAPACITY_CASES[0])
        report["result"] = "PASS"
        return report
    except Exception:
        report["result"] = "FAIL"
        report["errors"] += 1
        raise
    finally:
        # 记录原始测量，失败也保留；无数据库密码、Token或私人账户信息。
        save()
