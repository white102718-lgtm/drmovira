"""目录及渠道真实容量专项；SQL仅造隔离样本，读取使用原HTTP权限与游标。"""

import hashlib
import json
import math
import os
import platform
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psutil

from orbit_api.channel_contract import parse_channel
from orbit_api.reference_contract import normalize_row

REFERENCE_CHANNEL_CAPACITY_CASES = (
    "pythonReferenceChannelCapacityActualFiftyThousandEachWithRealOwnership",
    "pythonReferenceChannelCapacityFullKeysetSetsAndFourPageSizes",
    "pythonReferenceChannelCapacityTwentyConcurrentReadsP95AndActualPlans",
)


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def guard_target(admin, database):
    if (
        type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("容量工具仅允许本轮127.0.0.1:13306隔离UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("容量工具实际数据库不符")


def public_ids(items, label):
    # 引用目录保留原value包装，不能把ChannelDTO顶层ID套到ReferenceRecord。
    return [item["id"] if label == "channels" else item["value"]["id"] for item in items]


def require(value, code):
    if not value:
        raise AssertionError(code)


def run_reference_channel_capacity_checks(client, admin, headers, database, cases, backend_pid):
    guard_target(admin, database)
    report = {
        "status": "RUNNING",
        "scope": "5万渠道及5万户商目录SQL技术样本；非真实来源、全部模块或生产冷启动容量",
        "cache_note": "装载后首读及暖读；未清理数据库缓存，不宣称冷启动",
        "concurrency": 20,
        "samples_per_page_size": 200,
        "target_p95_seconds": 1.0,
        "machine": {
            "os": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": psutil.virtual_memory().total,
        },
        "errors": [],
    }
    output = (
        Path(__file__).resolve().parents[2] / ".runtime/reference-channel-capacity-current.json"
    )

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def query(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            return cursor.fetchall()

    try:
        report["mysql_version"] = query("SELECT VERSION()")[0][0]
        tenant, owner, team = query(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1"
        )[0]
        # 使用已经实际导入且关联完整的产品/总代；不猜某个固定UUID或从当前名字推断关联。
        links = query(
            "SELECT p.id,a.id FROM orbit_reference_product_agent x "
            "JOIN orbit_reference_record p ON p.tenant_id=x.tenant_id AND p.id=x.product_id "
            "JOIN orbit_reference_record a ON a.tenant_id=x.tenant_id AND a.id=x.agent_id "
            "WHERE x.tenant_id=%s AND p.kind='PRODUCT' AND a.kind='BUSINESS_AGENT' "
            "AND p.availability='AVAILABLE' AND a.availability='AVAILABLE' "
            "AND p.owner_team_id=%s AND a.owner_team_id=%s ORDER BY p.id,a.id LIMIT 1",
            (tenant, team, team),
        )
        require(len(links) == 1, "capacity_requires_actual_product_agent")
        product, agent = links[0]
        marker = "Cap-" + uuid4().hex[:12]
        channels, references = (
            sorted(str(uuid4()) for _ in range(50000)),
            sorted(str(uuid4()) for _ in range(50000)),
        )
        ownership = {"owner_team_id": team, "data_owner_user_ids": [owner]}
        now = datetime.now(UTC).replace(tzinfo=None)
        revision = (
            query("SELECT revision FROM orbit_reference_clock WHERE tenant_id=%s", (tenant,))[0][0]
            + 1
        )
        report["rss_before_bytes"] = psutil.Process(backend_pid).memory_info().rss
        started = time.monotonic()
        for offset in range(0, 50000, 500):
            channel_rows, reference_rows = [], []
            for index, identifier in enumerate(channels[offset : offset + 500], offset):
                value = parse_channel(
                    json.dumps(
                        {
                            "ownership": ownership,
                            "code": marker + "-" + str(index),
                            "name": marker + "渠道中文" + "界" * 70,
                            "product_id": product,
                            "agent_id": agent,
                            "type": "WEBSITE",
                            "media": "META",
                            "url": "https://example.com/capacity?row=" + str(index),
                            "status": "ENABLED",
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
                channel_rows.append(
                    (
                        tenant,
                        identifier,
                        value["code"],
                        value["name"],
                        team,
                        product,
                        agent,
                        value["status"],
                        json.dumps(value, ensure_ascii=False),
                        0,
                        1,
                        now,
                        now,
                    )
                )
            for identifier in references[offset : offset + 500]:
                value = normalize_row(
                    {
                        "id": identifier,
                        "kind": "VENDOR",
                        "source_key": marker + identifier,
                        "name": marker + "户商中文" + "界" * 220,
                        "availability": "AVAILABLE",
                        **ownership,
                    },
                    "VENDOR",
                )
                reference_rows.append(
                    (
                        tenant,
                        identifier,
                        "VENDOR",
                        value["source_key"],
                        value["name"],
                        "AVAILABLE",
                        team,
                        json.dumps(value, ensure_ascii=False),
                        1,
                        revision,
                        now,
                    )
                )
            admin.begin()
            try:
                with admin.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO orbit_channel(tenant_id,id,code,name,owner_team_id,product"
                        "_id,agent_id,"
                        "status,value_json,product_locked,revision,created_at,updated_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        channel_rows,
                    )
                    cursor.executemany(
                        "INSERT INTO orbit_channel_owner(tenant_id,channel_id,user_id) "
                        "VALUES(%s,%s,%s)",
                        [
                            (tenant, identifier, owner)
                            for identifier in channels[offset : offset + 500]
                        ],
                    )
                    cursor.executemany(
                        "INSERT INTO orbit_reference_record(tenant_id,id,kind,source_key,name,a"
                        "vailability,"
                        "owner_team_id,value_json,revision,catalog_revision,updated_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        reference_rows,
                    )
                    cursor.executemany(
                        "INSERT INTO orbit_reference_owner(tenant_id,reference_id,user_id) "
                        "VALUES(%s,%s,%s)",
                        [
                            (tenant, identifier, owner)
                            for identifier in references[offset : offset + 500]
                        ],
                    )
                admin.commit()
            except BaseException:
                admin.rollback()
                raise
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_reference_clock SET "
                "revision=revision+1,channel_revision=channel_revision+1 WHERE tenant_id=%s",
                (tenant,),
            )
        admin.commit()
        report["load_seconds"] = round(time.monotonic() - started, 3)
        expected_references = [
            row[0]
            for row in query(
                "SELECT r.id FROM orbit_reference_record r WHERE r.tenant_id=%s AND "
                "r.kind='VENDOR' "
                "AND EXISTS(SELECT 1 FROM orbit_reference_owner o WHERE o.tenant_id=r.tenant_id "
                "AND o.reference_id=r.id AND o.user_id=%s) ORDER BY r.id",
                (tenant, owner),
            )
        ]
        require(set(references).issubset(expected_references), "capacity_seed_reference_members")
        report["seeded_counts"] = {"channels": len(channels), "references": len(references)}
        cases.append(REFERENCE_CHANNEL_CAPACITY_CASES[0])
        endpoints = (
            ("channels", "/api/v1/channels", {"q": marker}, channels),
            (
                "references",
                "/api/v1/reference-catalogs/VENDOR",
                {"owner_user_id": owner},
                expected_references,
            ),
        )
        report["full_reads"], report["performance"] = {}, {}
        for label, path, filters, expected in endpoints:
            received, cursor, pages, watermark = [], None, 0, None
            start = time.monotonic()
            while True:
                response = client.get(
                    path,
                    headers=headers,
                    params=filters | {"page_size": 200} | ({"cursor": cursor} if cursor else {}),
                )
                require(response.status_code == 200, "capacity_full_read_" + label)
                body = response.json()
                require(0 < len(body["items"]) <= 200, "capacity_page_bound_" + label)
                current_watermark = (
                    body["data_as_of"] if label == "channels" else body["catalog_revision"],
                    body["scope_version"],
                )
                if watermark is None:
                    watermark = current_watermark
                require(current_watermark == watermark, "capacity_watermark_stable_" + label)
                received.extend(public_ids(body["items"], label))
                pages += 1
                cursor = body["next_cursor"]
                if cursor is None:
                    break
                require(pages <= 300, "capacity_no_cursor_loop_" + label)
            require(
                received == expected and len(set(received)) == len(received),
                "capacity_no_missing_or_duplicate_" + label,
            )
            report["full_reads"][label] = {
                "count": len(received),
                "pages": pages,
                "seconds": round(time.monotonic() - start, 3),
                "ordered_ids_sha256": hashlib.sha256("\n".join(received).encode()).hexdigest(),
            }
            for size in (20, 50, 100, 200):
                response = client.get(path, headers=headers, params=filters | {"page_size": size})
                require(response.status_code == 200, "capacity_page_size_http_" + label)
                require(
                    public_ids(response.json()["items"], label) == expected[:size],
                    "capacity_page_size_content_" + label,
                )
        cases.append(REFERENCE_CHANNEL_CAPACITY_CASES[1])
        for label, path, filters, expected in endpoints:
            report["performance"][label] = {}
            for size in (20, 50, 100, 200):

                def sample(
                    _, path=path, filters=filters, size=size, label=label, expected=expected
                ):
                    before = time.monotonic()
                    response = client.get(
                        path, headers=headers, params=filters | {"page_size": size}
                    )
                    require(response.status_code == 200, "capacity_concurrent_http_" + label)
                    require(
                        public_ids(response.json()["items"], label) == expected[:size],
                        "capacity_concurrent_content_" + label,
                    )
                    return time.monotonic() - before

                with ThreadPoolExecutor(max_workers=20) as pool:
                    durations = list(pool.map(sample, range(200)))
                report["performance"][label][str(size)] = {
                    "samples": len(durations),
                    "p50_seconds": percentile(durations, 0.5),
                    "p95_seconds": percentile(durations, 0.95),
                    "max_seconds": max(durations),
                }
                save()
                require(
                    percentile(durations, 0.95) <= 1.0,
                    "capacity_p95_over_one_second_" + label + "_" + str(size),
                )
        report["plans"] = {
            "channel": [
                row[0]
                for row in query(
                    "EXPLAIN ANALYZE SELECT c.id,c.value_json FROM orbit_channel c WHERE "
                    "c.tenant_id=%s AND c.id>%s "
                    "AND (INSTR(c.name,%s)>0 OR INSTR(c.code,%s)>0) ORDER BY c.id LIMIT 201",
                    (tenant, "", marker, marker),
                )
            ],
            "reference": [
                row[0]
                for row in query(
                    "EXPLAIN ANALYZE SELECT r.id,r.value_json FROM orbit_reference_record r "
                    "WHERE r.tenant_id=%s AND r.kind='VENDOR' "
                    "AND r.id>%s AND EXISTS(SELECT 1 FROM orbit_reference_owner o WHERE "
                    "o.tenant_id=r.tenant_id AND o.reference_id=r.id AND o.user_id=%s) "
                    "ORDER BY r.id LIMIT 201",
                    (tenant, "", owner),
                )
            ],
        }
        report["rss_after_bytes"] = psutil.Process(backend_pid).memory_info().rss
        report["rss_note"] = "前后采样RSS，不是进程峰值或严格泄漏证明"
        cases.append(REFERENCE_CHANNEL_CAPACITY_CASES[2])
        report["status"] = "PASS"
        return report
    except BaseException as error:
        report["status"] = "FAIL"
        report["errors"].append(
            {
                "type": type(error).__name__,
                "code": str(error) if isinstance(error, AssertionError) else "CAPACITY_RUN_FAILED",
            }
        )
        raise
    finally:
        save()
