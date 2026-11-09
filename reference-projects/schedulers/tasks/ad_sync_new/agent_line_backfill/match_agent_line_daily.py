"""ad_daily_detail 代理线回填(合并 campaign_name + url 两种匹配)。

按 date(账户当地日期,表的 UNIQUE KEY 首列)逐天滚动,两趟:
1. campaign_name 匹配代理线(切段查字典,长段优先)→ 回填该 campaign 下所有层级 null_field IS NULL 的行;
2. objective ∈ URL_OBJECTIVES 的广告,按 landing_url 逐条匹配,命中即覆盖 ad 层级该行。

URL 第二趟跑,命中时覆盖 campaign_name 的结果(对齐 transform.py 的 ad 层匹配口径)。
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd

from conf.log_conf import init
from db.clients import mongo_client, mongo_client_user, mysql_client
from db.doris_stream_load import stream_load
from utils.common import (
    build_line_maps,
    get_line_from_campaign_name,
    get_platform_lines,
    url_variants,
)

NullField = Literal["agent_line", "department"]

TABLE = "ad_daily_detail"
UK_COLUMNS = [
    "date",
    "ad_platform",
    "timezone_name",
    "account_id",
    "campaign_id",
    "ad_set_id",
    "ad_id",
]
FILL_COLUMNS = ["agent_line", "placer_id", "department", "game_platform"]
INSERT_BATCH_SIZE = 10000
CID_CHUNK = 200
URL_CHUNK_SIZE = 1000
# 仅这几类 objective 的广告才按 URL 逐条匹配(对齐 utils.common.match_agent_line_by_url)
URL_OBJECTIVES = ["OUTCOME_TRAFFIC", "OUTCOME_SALES", "OUTCOME_APP_PROMOTION"]


def match_agent_line_daily(
    start_date: str,
    end_date: str,
    null_field: NullField = "agent_line",
    agent_line_lookback_hours: int | None = None,
):
    """start_date/end_date: 回填的 date(账户当地日期)范围,格式 YYYY-MM-DD,含两端。
    null_field: 只回填该字段为 NULL 的行(campaign_name 趟生效;URL 趟为覆盖写,不受此限)。
    agent_line_lookback_hours: 只用最近这段时间更新过的代理线做 URL 匹配;None=全量代理线。
    """
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days = [
        (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range((end_dt - start_dt).days, -1, -1)
    ]

    # ── campaign_name 匹配所需(全部平台含禁用;启用平台排前, 同名线优先取启用的)──
    platform_lines = get_platform_lines(include_disabled=True)  # {game_platform: [agent_lines]}
    line_to_gp, line_index = build_line_maps(platform_lines)
    line_to_optimizer = _prefetch_line_optimizer(list(line_to_gp))
    optimizer_to_dept = _prefetch_optimizer_dept(set(line_to_optimizer.values()))
    line_to_dept = {
        line: optimizer_to_dept.get(opt) for line, opt in line_to_optimizer.items()
    }
    logging.info(
        f"代理线总数: {len(line_to_gp)},归一后唯一 line 数: {len(line_index)},"
        f"game_platform 数: {len(platform_lines)},天数: {len(days)}"
    )

    # ── URL 匹配所需:variant_url -> (agent_line, placer_id, department, game_platform) ──
    variant_to_match = _build_url_index(now, agent_line_lookback_hours)
    logging.info(f"URL 变体总数: {len(variant_to_match)}")

    logging.info(f"过滤口径: {null_field} IS NULL")

    for ri, day in enumerate(days, 1):
        rt0 = time.monotonic()
        camp_rows = _backfill_by_campaign(
            day, line_index, line_to_gp,
            line_to_optimizer, line_to_dept, null_field,
        )
        url_rows = _backfill_by_url(day, variant_to_match)
        logging.info(
            f"{TABLE}: day {ri}/{len(days)} [{day}] "
            f"campaign={camp_rows} url={url_rows} 行,耗时 {time.monotonic() - rt0:.1f}s"
        )

    logging.info("回填完成")


# ── campaign_name 匹配 ──────────────────────────────────────────────────────


def _match_campaigns_batch(
    campaigns: list[tuple[str, str]],
    line_index: dict[str, str],
    line_to_gp: dict[str, str],
) -> dict[str, tuple[str, str | None]]:
    result: dict[str, tuple[str, str | None]] = {}
    for campaign_id, campaign_name in campaigns:
        if not campaign_name:
            continue
        line = get_line_from_campaign_name(str(campaign_name), line_index)
        if line:
            result[campaign_id] = (line, line_to_gp.get(line))
    return result


def _prefetch_line_optimizer(agent_lines: list[str]) -> dict[str, str | None]:
    return {
        doc["_id"]: doc.get("optimizer")
        for doc in mongo_client["agent_line_config"].find(
            {"_id": {"$in": agent_lines}}, {"_id": 1, "optimizer": 1}
        )
    }


def _prefetch_optimizer_dept(optimizers: set[str]) -> dict[str, str | None]:
    names = [o for o in optimizers if o]
    result: dict[str, str | None] = {}
    if not names:
        return result
    for u in mongo_client_user["user"].find(
        {"$or": [{"real_name": {"$in": names}}, {"full_name": {"$in": names}}]},
        {"real_name": 1, "full_name": 1, "department": 1},
    ):
        dept = u.get("department")
        if u.get("real_name"):
            result[u["real_name"]] = dept
        if u.get("full_name"):
            result[u["full_name"]] = dept
    return result


def _backfill_by_campaign(
    day: str,
    line_index: dict[str, str],
    line_to_gp: dict[str, str],
    line_to_optimizer: dict[str, str | None],
    line_to_dept: dict[str, str | None],
    null_field: NullField,
) -> int:
    uk_select = ", ".join(UK_COLUMNS)
    discovery_sql = f"""
        SELECT DISTINCT campaign_id, campaign_name
        FROM {TABLE}
        WHERE level = 'ad'
          AND {null_field} IS NULL
          AND date = '{day}'
          AND campaign_id IS NOT NULL
          AND campaign_name IS NOT NULL
    """
    campaigns = mysql_client.read(discovery_sql)
    campaign_to_match = _match_campaigns_batch(list(campaigns), line_index, line_to_gp)
    if not campaign_to_match:
        return 0

    match_df = pd.DataFrame(
        [
            (cid, line, line_to_optimizer.get(line), line_to_dept.get(line), gp)
            for cid, (line, gp) in campaign_to_match.items()
        ],
        columns=["campaign_id", "agent_line", "placer_id", "department", "game_platform"],
    )
    cids = list(campaign_to_match)
    chunks_count = (len(cids) + CID_CHUNK - 1) // CID_CHUNK
    insert_columns = UK_COLUMNS + FILL_COLUMNS

    day_total = 0
    for ci in range(chunks_count):
        chunk = cids[ci * CID_CHUNK : (ci + 1) * CID_CHUNK]
        cids_in = ", ".join("'" + str(c).replace("'", "''") + "'" for c in chunk)
        rows = mysql_client.read(f"""
            SELECT {uk_select}
            FROM {TABLE}
            WHERE {null_field} IS NULL
              AND date = '{day}'
              AND campaign_id IN ({cids_in})
        """)
        if not rows:
            continue
        rows_df = pd.DataFrame(list(rows), columns=UK_COLUMNS)
        merged = rows_df.merge(match_df, on="campaign_id", how="inner")
        if merged.empty:
            continue
        df_out = merged[insert_columns].astype(object).where(merged[insert_columns].notna(), None)
        records = df_out.to_dict("records")
        for i in range(0, len(records), INSERT_BATCH_SIZE):
            stream_load(TABLE, records[i : i + INSERT_BATCH_SIZE], insert_columns)
        day_total += len(records)
    return day_total


# ── URL 匹配(ad 层覆盖) ────────────────────────────────────────────────────


def _build_url_index(
    now: datetime, agent_line_lookback_hours: int | None
) -> dict[str, tuple]:
    agent_filter: dict = {}
    if agent_line_lookback_hours is not None:
        al_start = (now - timedelta(hours=agent_line_lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
        agent_filter = {"update_time": {"$gte": al_start}}
        logging.info(f"URL 匹配仅取 update_time >= {al_start} 的代理线")

    agent_lines = list(
        mongo_client["agent_line_config"].find(
            agent_filter, {"_id": 1, "optimizer": 1, "history_package_urls": 1}
        )
    )
    optimizers = list({d.get("optimizer") for d in agent_lines if d.get("optimizer")})
    optimizer_to_dept = _prefetch_optimizer_dept(set(optimizers))
    agent_line_to_gp = _prefetch_game_platform([d["_id"] for d in agent_lines])

    variant_to_match: dict[str, tuple] = {}
    for doc in agent_lines:
        agent_line = doc["_id"]
        optimizer = doc.get("optimizer")
        info = (
            agent_line,
            optimizer,
            optimizer_to_dept.get(optimizer) if optimizer else None,
            agent_line_to_gp.get(agent_line),
        )
        for url in doc.get("history_package_urls") or []:
            for v in url_variants(url):
                variant_to_match[v] = info
    return variant_to_match


def _prefetch_game_platform(agent_line_ids: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for pdoc in mongo_client["platform_config"].find(
        {"agent_lines": {"$in": agent_line_ids}}, {"_id": 1, "agent_lines": 1}
    ):
        for al in pdoc.get("agent_lines", []):
            result[al] = pdoc["_id"]
    return result


def _backfill_by_url(day: str, variant_to_match: dict[str, tuple]) -> int:
    if not variant_to_match:
        return 0
    uk_select = ", ".join(UK_COLUMNS)
    objectives_in = ", ".join("'" + o + "'" for o in URL_OBJECTIVES)
    variants = list(variant_to_match.keys())
    chunks_count = (len(variants) + URL_CHUNK_SIZE - 1) // URL_CHUNK_SIZE

    insert_columns = UK_COLUMNS + FILL_COLUMNS
    records: list[dict] = []
    for ci in range(chunks_count):
        chunk = variants[ci * URL_CHUNK_SIZE : (ci + 1) * URL_CHUNK_SIZE]
        urls_in = ", ".join("'" + v.replace("'", "''") + "'" for v in chunk)
        rows = mysql_client.read(f"""
            SELECT {uk_select}, landing_url
            FROM {TABLE}
            WHERE level = 'ad'
              AND date = '{day}'
              AND UPPER(objective) IN ({objectives_in})
              AND landing_url IN ({urls_in})
        """)
        for row in rows:
            info = variant_to_match.get(row[len(UK_COLUMNS)])
            if info:
                records.append(dict(zip(insert_columns, list(row[: len(UK_COLUMNS)]) + list(info))))

    if not records:
        return 0
    for i in range(0, len(records), INSERT_BATCH_SIZE):
        stream_load(TABLE, records[i : i + INSERT_BATCH_SIZE], insert_columns)
    return len(records)


if __name__ == "__main__":
    from pyinstrument import Profiler

    init("match_agent_line_daily.py")
    profiler = Profiler()
    profiler.start()
    match_agent_line_daily(
        start_date="2026-06-10",
        end_date="2026-06-12",
        null_field="agent_line",  # "agent_line" 补没匹配的; "department" 补 agent_line 已有但部门为空的
        agent_line_lookback_hours=None,  # None=全量代理线做 URL 匹配; 给小时数=只用最近更新的
    )
    profiler.stop()
    profiler.print()
    """
    sed -i -E 's/start_date="[0-9-]+"/start_date="2026-07-01"/; s/end_date="[0-9-]+"/end_date="2026-07-05"/' \
              tasks/ad_sync_new/agent_line_backfill/match_agent_line_daily.py \
              tasks/ad_sync_new/agent_line_backfill/backfill_hourly_dept_from_daily.py
    python -m tasks.ad_sync_new.agent_line_backfill.match_agent_line_daily
    python -m tasks.ad_sync_new.agent_line_backfill.backfill_hourly_dept_from_daily
    """
