# -*- coding:utf-8 -*-
"""
ERP 渠道同步: 把 ERP fbad_channel 增量同步到 Doris ad.fb_ad_channel,每两小时一次。

- 增量:取近 2h10m 内 update_time 变化的渠道,以及户(fbad_channel_account)变化所属的渠道,
  反查整行后经 Stream Load 写入 UNIQUE KEY(id) 表,按 id upsert 覆盖。
- account_ids_json:按受影响 channel_id 重查户,每个户拼上时区(fbad_ad_account.timezone_name)、
  账户类型(fbad_channel_account.account_type)、所属 BM 列表(fbad_fb_user_bm_account → fbad_bm_management,
  business_id=-1 跳过),整列以 JSON 数组写入 Doris JSON 列(无关联为 [])。
"""
import json
import logging
from datetime import datetime, timedelta

from db.clients import erp_db, tz_cst
from db.doris_stream_load import stream_load
from utils.common_util import handle_error

_CHANNEL_COLUMNS = [
    "id", "channel_name", "service_fee", "activation_fee", "rebate_rate",
    "settlement_method", "total_consumption", "usage_status", "payment_address",
    "login_url", "remark", "status", "create_time", "channel_type",
    "channel_short_name", "channel_code", "belong_team"
]
_INSERT_COLUMNS = _CHANNEL_COLUMNS + ["account_ids_json"]
_BATCH_SIZE = 200


def _sql_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _in_clause(values) -> str:
    return ", ".join(_sql_str(str(v)) for v in values)


def _fetch_timezone_map(account_ids):
    """account_id -> timezone_name。"""
    rows = erp_db.read(
        "SELECT account_id, timezone_name FROM fbad_ad_account "
        f"WHERE account_id IN ({_in_clause(account_ids)})"
    )
    return {str(a): tz for a, tz in rows if a is not None}


def _fetch_account_bm_map(account_ids):
    """account_id -> [business_id, ...],去重,跳过 business_id 为空或 -1 的。"""
    rows = erp_db.read(
        "SELECT account_id, business_id FROM fbad_fb_user_bm_account "
        f"WHERE account_id IN ({_in_clause(account_ids)})"
    )
    result = {}
    for account_id, business_id in rows:
        if account_id is None or business_id is None:
            continue
        bid = str(business_id).strip()
        if not bid or bid == "-1":
            continue
        bucket = result.setdefault(str(account_id), [])
        if bid not in bucket:
            bucket.append(bid)
    return result


def _fetch_bm_name_map(business_ids):
    """business_id -> bm_name。"""
    if not business_ids:
        return {}
    rows = erp_db.read(
        "SELECT bm_id, bm_name FROM fbad_bm_management "
        f"WHERE bm_id IN ({_in_clause(business_ids)})"
    )
    return {str(b): name for b, name in rows if b is not None}


def _fetch_account_info_grouped(channel_ids=None):
    """{channel_id: [account_obj, ...]},account_obj 含 timezone_name/account_type/bms。
    跳过 channel_id 或 fb_account_id 为空的行;同一渠道内按 account_id 去重。
    channel_ids 非空时只查这些渠道的户。"""
    sql = "SELECT channel_id, fb_account_id, account_type FROM fbad_channel_account"
    if channel_ids is not None:
        if not channel_ids:
            return {}
        sql += " WHERE channel_id IN (" + ", ".join(str(int(c)) for c in channel_ids) + ")"
    rows = erp_db.read(sql)

    grouped_raw = {}  # channel_id -> [(account_id, account_type), ...]
    seen = {}         # channel_id -> {account_id}
    all_account_ids = set()
    for channel_id, fb_account_id, account_type in rows:
        if channel_id is None:
            continue
        acc = (str(fb_account_id).strip() if fb_account_id is not None else "")
        if not acc:
            continue
        bucket_seen = seen.setdefault(channel_id, set())
        if acc in bucket_seen:
            continue
        bucket_seen.add(acc)
        grouped_raw.setdefault(channel_id, []).append((acc, account_type))
        all_account_ids.add(acc)

    if not all_account_ids:
        return {}

    tz_map = _fetch_timezone_map(all_account_ids)
    bm_ids_map = _fetch_account_bm_map(all_account_ids)
    bm_name_map = _fetch_bm_name_map({b for bms in bm_ids_map.values() for b in bms})

    grouped = {}
    for channel_id, accs in grouped_raw.items():
        grouped[channel_id] = [
            {
                "account_id": acc,
                "timezone_name": tz_map.get(acc),
                "account_type": account_type,
                "bms": [
                    {"business_id": b, "bm_name": bm_name_map.get(b)}
                    for b in bm_ids_map.get(acc, [])
                ],
            }
            for acc, account_type in accs
        ]
    return grouped


@handle_error(error_message="ERP 渠道同步失败")
def sync_erp_channel_to_doris():
    # update_time 'YYYY-MM-DD HH:MM:SS' 字符串字典序==时间序,直接比较走索引;窗口比 2h 间隔多 10min 防边界漏跑
    start = (datetime.now(tz_cst) - timedelta(hours=2, minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    select_cols = ", ".join(_CHANNEL_COLUMNS)

    rows = list(erp_db.read(
        f"SELECT {select_cols} FROM fbad_channel"
    ))

    # 渠道本身未更新但其下户更新,也要重算该渠道:用户更新行的 channel_id 反查 fbad_channel
    acc_channel_rows = erp_db.read(
        "SELECT DISTINCT channel_id FROM fbad_channel_account "
        f"WHERE update_time >= '{start}' AND channel_id IS NOT NULL"
    )
    seen_ids = {row[0] for row in rows}
    extra_ids = [cid for (cid,) in acc_channel_rows if cid not in seen_ids]
    if extra_ids:
        ids = ", ".join(str(int(c)) for c in extra_ids)
        rows.extend(erp_db.read(
            f"SELECT {select_cols} FROM fbad_channel WHERE id IN ({ids})"
        ))

    if not rows:
        logging.info("近 2h10m 无渠道/户更新,跳过")
        return

    account_info_grouped = _fetch_account_info_grouped([row[0] for row in rows])

    records = []
    for row in rows:
        channel_id = row[0]
        info = account_info_grouped.get(channel_id, [])
        record = dict(zip(_CHANNEL_COLUMNS, row))
        record["account_ids_json"] = json.dumps(info, ensure_ascii=False)
        records.append(record)

    total = len(records)
    logging.info(f"ERP 渠道同步开始: 共 {total} 个渠道")

    for i in range(0, total, _BATCH_SIZE):
        stream_load("fb_ad_channel", records[i:i + _BATCH_SIZE], _INSERT_COLUMNS, partial=False)

    logging.info(f"ERP 渠道同步完成: 处理渠道={total}")


if __name__ == "__main__":
    from conf.log_conf import init

    init("erp_channel_sync")
    sync_erp_channel_to_doris()
