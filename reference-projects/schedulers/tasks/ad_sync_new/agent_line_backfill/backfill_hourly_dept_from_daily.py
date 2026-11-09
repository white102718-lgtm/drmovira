"""ad_hourly_detail 中 department 为空的行,关联 ad_daily_detail 同实体当天已填好的
agent_line / placer_id / department / game_platform 写回。

date 字段含小时(hourly 真实小时,daily 为 00),无法直接 join,故按
(ad_platform, timezone_name, account_id, campaign_id, ad_set_id, ad_id) 当天唯一键关联。
按 china_date 按天滚动。
"""

import logging
import time
from datetime import datetime, timedelta

from conf.log_conf import init
from db.clients import mysql_client
from db.doris_stream_load import stream_load

DAILY = "ad_daily_detail"
HOURLY = "ad_hourly_detail"
KEY_COLUMNS = ["ad_platform", "timezone_name", "account_id", "campaign_id", "ad_set_id", "ad_id"]
HOURLY_UK = ["date"] + KEY_COLUMNS
FILL_COLUMNS = ["agent_line", "placer_id", "department", "game_platform"]
INSERT_BATCH_SIZE = 10000


def backfill_hourly_dept_from_daily(start_date: str, end_date: str):
    """start_date/end_date: 回填的 china_date 范围,格式 YYYY-MM-DD,含两端。"""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    day_ranges = list(reversed(_split_by_day(start_dt, end_dt)))
    logging.info(f"天数: {len(day_ranges)}")

    key_select = ", ".join(KEY_COLUMNS)
    insert_columns = HOURLY_UK + FILL_COLUMNS

    for ri, (day_start, day_end) in enumerate(day_ranges, 1):
        rt0 = time.monotonic()

        daily_rows = mysql_client.read(f"""
            SELECT {key_select}, {', '.join(FILL_COLUMNS)}
            FROM {DAILY}
            WHERE china_date >= '{day_start}'
              AND china_date < '{day_end}'
              AND department IS NOT NULL
        """)
        daily_lookup = {tuple(r[: len(KEY_COLUMNS)]): tuple(r[len(KEY_COLUMNS):]) for r in daily_rows}
        if not daily_lookup:
            logging.info(f"{HOURLY}: day {ri}/{len(day_ranges)} [{day_start[:10]}] daily 无可用行")
            continue

        hourly_rows = mysql_client.read(f"""
            SELECT date, {key_select}
            FROM {HOURLY}
            WHERE china_date >= '{day_start}'
              AND china_date < '{day_end}'
              AND department IS NULL
        """)
        records = []
        for r in hourly_rows:
            fill = daily_lookup.get(tuple(r[1:]))
            if fill:
                records.append(dict(zip(insert_columns, list(r) + list(fill))))

        for i in range(0, len(records), INSERT_BATCH_SIZE):
            stream_load(HOURLY, records[i : i + INSERT_BATCH_SIZE], insert_columns)

        logging.info(
            f"{HOURLY}: day {ri}/{len(day_ranges)} [{day_start[:10]}] "
            f"daily={len(daily_lookup)} hourly缺={len(hourly_rows)} 写回={len(records)} 行,"
            f"耗时 {time.monotonic() - rt0:.1f}s"
        )

    logging.info("回填完成")


def _split_by_day(start_dt: datetime, end_dt: datetime) -> list[tuple[str, str]]:
    ranges: list[tuple[str, str]] = []
    cur = start_dt
    while cur < end_dt:
        nxt = min(
            (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            end_dt,
        )
        ranges.append((cur.strftime("%Y-%m-%d %H:%M:%S"), nxt.strftime("%Y-%m-%d %H:%M:%S")))
        cur = nxt
    return ranges


if __name__ == "__main__":
    init("backfill_hourly_dept_from_daily.py")
    backfill_hourly_dept_from_daily(
        start_date="2026-06-10",
        end_date="2026-06-12",
    )
