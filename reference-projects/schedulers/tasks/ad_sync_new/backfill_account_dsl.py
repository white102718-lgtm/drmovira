"""
把 Mongo fb_ad_accounts.account_dsl 定时盖到 Doris 明细表。

ad_sync_new 写行时不带 account_dsl,callback 只在收到回调那一刻更新当时的最新行,
之后新生成的行该字段为 NULL。本任务把非被封账户的 account_dsl 盖到
hourly / daily 当前中国整点(china_date=当前小时)的 level='account' 行上。
"""

import logging

from datetime import datetime
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import mongo_client, mysql_client
from db.doris_stream_load import stream_load

UK_COLUMNS = [
    "date",
    "ad_platform",
    "timezone_name",
    "account_id",
    "campaign_id",
    "ad_set_id",
    "ad_id",
]
ACCOUNT_ID_CHUNK = 1000
INSERT_BATCH_SIZE = 10000


def backfill_account_dsl():
    """account_status=2(DISABLED)的户跳过;只更新 china_date=当前整点的 account 行。"""
    dsl_map = {
        doc["_id"]: doc["account_dsl"]
        for doc in mongo_client["fb_ad_accounts"].find(
            {"account_status": {"$ne": 2}, "account_dsl": {"$ne": None}},
            projection={"account_dsl": 1},
        )
    }
    if not dsl_map:
        logging.info("account_dsl: Mongo 无可用账户")
        return

    # china_date 按 "%Y-%m-%d %H" 存中国时区整点, 当前整点行由 :00/:30 sync 刷新
    hour = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H")
    account_ids = list(dsl_map)
    uk_select = ", ".join(UK_COLUMNS)
    insert_columns = UK_COLUMNS + ["account_dsl"]

    for table in ("ad_hourly_detail", "ad_daily_detail"):
        records = []
        for i in range(0, len(account_ids), ACCOUNT_ID_CHUNK):
            chunk = account_ids[i : i + ACCOUNT_ID_CHUNK]
            ids_in = ", ".join(f"'{aid}'" for aid in chunk)
            rows = mysql_client.read(f"""
                SELECT {uk_select}
                FROM {table}
                WHERE level = 'account'
                  AND china_date = '{hour}'
                  AND account_id IN ({ids_in})
            """)
            for row in rows:
                record = dict(zip(UK_COLUMNS, row))
                record["account_dsl"] = dsl_map[record["account_id"]]
                records.append(record)
        for i in range(0, len(records), INSERT_BATCH_SIZE):
            stream_load(table, records[i : i + INSERT_BATCH_SIZE], insert_columns)
        logging.info(f"{table}: account_dsl 更新 {len(records)} 行")


if __name__ == "__main__":
    init("backfill_account_dsl")
    backfill_account_dsl()
