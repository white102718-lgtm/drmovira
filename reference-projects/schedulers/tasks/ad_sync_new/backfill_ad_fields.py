"""
回填原帖广告的 landing_url 及代理线信息。

原帖投放的广告没有 landing_url，通过 post_id 找到同帖在该日期之前
最近一条有 landing_url 的记录，把 landing_url / agent_line / placer_id /
department / game_platform 回填。
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import mysql_client

UK_COLUMNS = {
    "ad_daily_detail": [
        "date",
        "ad_platform",
        "timezone_name",
        "account_id",
        "campaign_id",
        "ad_set_id",
        "ad_id",
    ],
    "ad_hourly_detail": [
        "date",
        "ad_platform",
        "timezone_name",
        "account_id",
        "campaign_id",
        "ad_set_id",
        "ad_id",
    ],
}
FILL_COLUMNS = ["landing_url", "agent_line", "placer_id", "department", "game_platform"]


def backfill_ad_fields(
    lookback_hours: int = 3,
    start_date: str | None = None,
    end_date: str | None = None,
    force: bool = False,
    url_lookback_days: int = 7,
):
    """回填广告数据，同时执行：
    1. 仅回填 landing_url（不过滤 objective）
    2. 回填 landing_url + 代理线等全部字段（仅限特定 objective）

    两种模式：
    - 指定 start_date / end_date（格式 'YYYY-MM-DD'）：回填该时间范围内的数据
    - 否则按 lookback_hours 回填最近 N 小时的数据

    Args:
        force: 强制覆盖已有的 landing_url（用于修正之前错误回填的数据）
    """
    tz = ZoneInfo("Asia/Shanghai")
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(
            days=1
        )
    else:
        end = datetime.now(tz)
        start = end - timedelta(hours=lookback_hours)

    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    while day_start < end:
        day_end = min(day_start + timedelta(days=1), end)
        days.append(
            (
                max(start, day_start).strftime("%Y-%m-%d %H:%M:%S"),
                day_end.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        day_start += timedelta(days=1)

    for table in ("ad_daily_detail", "ad_hourly_detail"):
        total_url = 0
        total_all = 0
        for day_cutoff, day_end_ in days:
            total_all += _backfill_all_fields(
                table, day_cutoff, day_end_, force=force, url_lookback_days=url_lookback_days
            )
            total_url += _backfill_landing_url(
                table, day_cutoff, day_end_, force=force, url_lookback_days=url_lookback_days
            )
        logging.info(
            f"{table}: 回填完成，仅landing_url {total_url} 行，landing_url+代理线 {total_all} 行"
        )

    logging.info("回填完成")


def _backfill_landing_url(
    table: str,
    cutoff: str,
    end: str,
    batch_size: int = 10000,
    force: bool = False,
    url_lookback_days: int = 7,
) -> int:
    """仅回填 landing_url，不过滤 objective。"""
    uk_cols = UK_COLUMNS[table]
    uk_select = ", ".join(f"a.{c}" for c in uk_cols)
    insert_columns = uk_cols + ["landing_url"]
    columns_str = ", ".join(insert_columns)
    placeholders = ", ".join(["%s"] * len(insert_columns))

    null_filter = "" if force else "AND (landing_url IS NULL OR landing_url = '')"
    uk_cols_str = ", ".join(uk_cols)
    url_since = (
        datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=url_lookback_days)
    ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        WITH targets AS (
            SELECT {uk_cols_str}, post_id
            FROM {table}
            WHERE post_id IS NOT NULL
              {null_filter}
              AND china_date >= '{cutoff}'
              AND china_date < '{end}'
              AND objective IN ('OUTCOME_TRAFFIC', 'OUTCOME_SALES', 'OUTCOME_APP_PROMOTION', 'OUTCOME_LEADS', 'OUTCOME_ENGAGEMENT')
        )
        SELECT {uk_select}, b.landing_url
        FROM targets a
        JOIN (
            SELECT post_id, landing_url,
                   ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY date DESC) AS rn
            FROM {table}
            WHERE landing_url IS NOT NULL
              AND landing_url <> ''
              AND post_id IS NOT NULL
              AND china_date >= '{url_since}'
              AND china_date < '{end}'
              AND post_id IN (SELECT post_id FROM targets)
        ) b ON a.post_id = b.post_id AND b.rn = 1
    """
    rows = mysql_client.read(sql)

    if not rows:
        return 0

    total = len(rows)
    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")
        for i in range(0, total, batch_size):
            cur.executemany(insert_sql, list(rows[i : i + batch_size]))
    logging.info(f"{table}: [{cutoff[:10]}] landing_url 回填 {total} 行")
    return total


def _backfill_all_fields(
    table: str,
    cutoff: str,
    end: str,
    batch_size: int = 10000,
    force: bool = False,
    url_lookback_days: int = 7,
) -> int:
    """回填 landing_url + 代理线等全部字段，仅限特定 objective。"""
    uk_cols = UK_COLUMNS[table]
    uk_select = ", ".join(f"a.{c}" for c in uk_cols)
    fill_select = ", ".join(f"b.{c}" for c in FILL_COLUMNS)
    insert_columns = uk_cols + FILL_COLUMNS
    columns_str = ", ".join(insert_columns)
    placeholders = ", ".join(["%s"] * len(insert_columns))

    null_filter = "" if force else "AND (landing_url IS NULL OR landing_url = '')"
    uk_cols_str = ", ".join(uk_cols)
    url_since = (
        datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=url_lookback_days)
    ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        WITH targets AS (
            SELECT {uk_cols_str}, post_id
            FROM {table}
            WHERE post_id IS NOT NULL
              {null_filter}
              AND china_date >= '{cutoff}'
              AND china_date < '{end}'
              AND objective IN ('OUTCOME_TRAFFIC', 'OUTCOME_SALES', 'OUTCOME_APP_PROMOTION')
        )
        SELECT {uk_select}, {fill_select}
        FROM targets a
        JOIN (
            SELECT post_id, {", ".join(FILL_COLUMNS)},
                   ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY date DESC) AS rn
            FROM {table}
            WHERE landing_url IS NOT NULL
              AND landing_url <> ''
              AND post_id IS NOT NULL
              AND china_date >= '{url_since}'
              AND china_date < '{end}'
              AND post_id IN (SELECT post_id FROM targets)
        ) b ON a.post_id = b.post_id AND b.rn = 1
    """
    rows = mysql_client.read(sql)

    if not rows:
        return 0

    total = len(rows)
    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")
        for i in range(0, total, batch_size):
            cur.executemany(insert_sql, list(rows[i : i + batch_size]))
    logging.info(f"{table}: [{cutoff[:10]}] landing_url+代理线 回填 {total} 行")
    return total


if __name__ == "__main__":
    init("backfill_ad_fields.py")
    # force=True 强制覆盖已有的错误 landing_url
    backfill_ad_fields(start_date="2026-04-15", end_date="2026-04-17", force=False)
