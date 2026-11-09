"""根据 ad_daily_detail 里已填好的 agent_line / game_platform 回填 ad_hourly_detail
里同 level、同 id、agent_line IS NULL 的行。

直接在 Doris 端 JOIN + partial-update INSERT INTO ... SELECT,无 Python 中转。
外层按 china_date 倒序逐天滚动:每天每个 level 一条 SQL。跑挂了下一天还能继续。

按 level 分别关联(严格分层):
  - level='campaign' ON h.campaign_id = d.campaign_id
  - level='adset'    ON h.ad_set_id   = d.ad_set_id
  - level='ad'       ON h.ad_id       = d.ad_id
"""

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import mysql_client

LEVEL_TO_ID = {
    "campaign": "campaign_id",
    "adset": "ad_set_id",
    "ad": "ad_id",
}


def _day_ranges(lookback_days: int) -> list[tuple[str, str]]:
    """倒序返回 [(day_start, day_end), ...],day_end 是次日 00:00。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    start_dt = now - timedelta(days=lookback_days)
    ranges: list[tuple[str, str]] = []
    cur = start_dt
    while cur < now:
        nxt = min(
            (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            now,
        )
        ranges.append(
            (cur.strftime("%Y-%m-%d %H:%M:%S"), nxt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        cur = nxt
    return list(reversed(ranges))


def backfill_hourly_agent_line_from_daily(lookback_days: int = 180):
    day_ranges = _day_ranges(lookback_days)
    logging.info(f"待处理天数: {len(day_ranges)}")

    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")

        for ri, (day_start, day_end) in enumerate(day_ranges, 1):
            for level, id_field in LEVEL_TO_ID.items():
                sql = f"""
                    INSERT INTO ad_hourly_detail
                      (`date`, ad_platform, timezone_name, account_id,
                       campaign_id, ad_set_id, ad_id,
                       agent_line, game_platform)
                    SELECT
                      h.`date`, h.ad_platform, h.timezone_name, h.account_id,
                      h.campaign_id, h.ad_set_id, h.ad_id,
                      d.agent_line, d.game_platform
                    FROM ad_hourly_detail h
                    JOIN (
                      SELECT {id_field},
                             MIN(agent_line)    AS agent_line,
                             MIN(game_platform) AS game_platform
                      FROM ad_daily_detail
                      WHERE level = '{level}'
                        AND agent_line IS NOT NULL
                        AND {id_field} IS NOT NULL
                      GROUP BY {id_field}
                    ) d ON h.{id_field} = d.{id_field}
                    WHERE h.level = '{level}'
                      AND h.{id_field} IS NOT NULL
                      AND h.china_date >= '{day_start}'
                      AND h.china_date <  '{day_end}'
                      AND (
                            NOT (h.agent_line    <=> d.agent_line)
                         OR NOT (h.game_platform <=> d.game_platform)
                      )
                """
                t0 = time.monotonic()
                cur.execute(sql)
                logging.info(
                    f"day {ri}/{len(day_ranges)} [{day_start[:10]}] {level}: "
                    f"{cur.rowcount} 行,耗时 {time.monotonic() - t0:.1f}s"
                )

    logging.info("hourly 回填完成")


if __name__ == "__main__":
    init("backfill_hourly_agent_line_from_daily.py")
    backfill_hourly_agent_line_from_daily(lookback_days=180)
    # sed -i -E 's/lookback_days=[0-9]+/lookback_days=30/' scripts/backfill_hourly_agent_line_from_daily.py
