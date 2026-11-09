# -*- coding:utf-8 -*-
"""飞书「MP媒介资料表」账户登记同步 → 主副 Mongo plat.feishu_account_used_record。

四张工作表只取在用账户:GC企业户的状态词是"使用中",另外三张是"在用账户"。
电子表格没有稳定行 ID(行号随插入/删除漂移),所以用 account_id 做唯一键 upsert。
"""
import logging
import re
import unicodedata
from datetime import datetime

from pymongo import UpdateOne

from db.clients import mongo_client, mongo_client_new, tz_cst
from utils.common_util import handle_error
from utils.feishu import (
    list_sheets,
    read_sheet_rows,
    resolve_spreadsheet_token,
    sheet_value_to_datetime,
)

FEISHU_APP_ID = "cli_aa8e9ed5bc319bb3"
FEISHU_APP_SECRET = "REDACTED_REFERENCE_SECRET"
DOC_URL = "https://fcnk6kec61ac.feishu.cn/wiki/J7vpwWXBBibEFHkaSqjcZEfGnIf"

_COLLECTION = "feishu_account_used_record"

# (sheet_id, 在用状态值, 账户ID列名) —— GC企业户的状态词和列名都跟另外三张不同
_SHEETS = [
    ("OfzOzi", "在用账户", "账户ID"),
    ("felLWu", "在用账户", "账户ID"),
    ("Of0fXe", "在用账户", "账户ID"),
    ("xJJ3yu", "使用中", "账户id"),
]

# channel 取"内部代号"而不是"购买渠道":后者在渠道充值账户/GC企业户里没有该列
_TEXT_FIELDS = {
    "channel": "内部代号",
    "account_type": "户类型",
    "account_attribute": "账户属性",
    "user_name": "当前使用人",
}
# 渠道充值账户/GC企业户没有这五列；缺列时不更新，避免清空已有信息。
_OPTIONAL_TEXT_FIELDS = {
    "purchase_detail": "购买详情(BMID)",
    "management_bm": "管理bm",
    "backup_management_bm": "备份管理bm",
    "card_platform": "卡台",
    "card_number": "卡号",
}
_DATE_FIELDS = {
    "delivery_date": "日期",
    "usage_time": "首次分配日期",
}


def _normalize_column(column: str) -> str:
    """表头忽略大小写、空白及全角半角差异。"""
    return "".join(unicodedata.normalize("NFKC", column).split()).casefold()


def _split_bm(value) -> tuple[str | None, str | None]:
    """BM 单元格末行纯数字为 ID，其余行是名称；ID 保持字符串。"""
    if value is None:
        return None, None
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    if not lines:
        return None, None
    if re.fullmatch(r"[0-9]+", lines[-1]):
        return "\n".join(lines[:-1]) or None, lines[-1]
    return "\n".join(lines), None


def _build_doc(row: dict, account_id: str, sheet_title: str, sync_time: datetime) -> dict:
    doc = {
        "account_id": account_id,
        "source_sheet": sheet_title,
        "source_row": row["_row"],
        "in_use": True,
        "sync_time": sync_time,
    }
    for field, column in _TEXT_FIELDS.items():
        value = row.get(column)
        doc[field] = str(value).strip() if value is not None else None
    optional_values = {_normalize_column(column): value for column, value in row.items()}
    for field, column in _OPTIONAL_TEXT_FIELDS.items():
        key = _normalize_column(column)
        if key not in optional_values:
            continue
        value = optional_values[key]
        doc[field] = str(value).strip() if value is not None else None
        if field in {"management_bm", "backup_management_bm"}:
            # 保留原文供核对，另外拆出名称和 ID；空单元格同时清空这两个字段。
            doc[f"{field}_name"], doc[f"{field}_id"] = _split_bm(value)
    for field, column in _DATE_FIELDS.items():
        doc[field] = sheet_value_to_datetime(row.get(column))
    return doc


def _write_records(database, operations: list[UpdateOne], account_ids: list[str], label: str):
    """每个库先写在用账户，成功后再标记下线；失败交给调用方处理。"""
    collection = database[_COLLECTION]
    result = collection.bulk_write(operations, ordered=False)
    # 表格里已不在用的账户不删,只落 in_use=False;sync_time 停在最后一次在用的时刻
    retired = collection.update_many(
        {"account_id": {"$nin": account_ids}, "in_use": {"$ne": False}},
        {"$set": {"in_use": False}},
    )
    logging.info(
        "飞书账户登记同步完成[%s]: 提交 %s 行, 新增 %s, 更新 %s, 标记下线 %s",
        label, len(operations), result.upserted_count, result.modified_count,
        retired.modified_count,
    )


@handle_error(error_message="飞书账户登记同步失败")
def sync_feishu_account_records():
    token = resolve_spreadsheet_token(
        DOC_URL, app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET
    )
    sheets = {
        s["sheet_id"]: s
        for s in list_sheets(token, app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
    }

    sync_time = datetime.now(tz_cst)
    operations, seen = [], {}
    for sheet_id, active_status, id_column in _SHEETS:
        sheet = sheets.get(sheet_id)
        if sheet is None:
            # 不能跳过继续:少读一张表会让它名下的账户被当成已下线,误标 in_use=False
            raise RuntimeError(f"飞书文档中找不到工作表 sheet_id={sheet_id},疑似被删除或改名")

        rows = read_sheet_rows(
            token,
            sheet_id,
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            row_count=sheet["row_count"],
            column_count=sheet["column_count"],
        )
        active = [r for r in rows if r.get("账户状态") == active_status]

        kept, no_id = 0, 0
        for row in active:
            account_id = str(row.get(id_column) or "").strip()
            # GC企业户里大量"使用中"的行是主页记录,没有账户 ID,不是账户
            if not account_id or not account_id.isdigit():
                no_id += 1
                continue
            if account_id in seen:
                logging.warning(
                    f"[飞书账户同步] 账户 {account_id} 在 {seen[account_id]} 和 "
                    f"{sheet['title']} 重复出现,保留前者"
                )
                continue
            seen[account_id] = sheet["title"]
            operations.append(
                UpdateOne(
                    {"account_id": account_id},
                    {"$set": _build_doc(row, account_id, sheet["title"], sync_time)},
                    upsert=True,
                )
            )
            kept += 1

        logging.info(
            f"[飞书账户同步] {sheet['title']}: 非空 {len(rows)} 行, "
            f"状态={active_status} {len(active)} 行, 入库 {kept} 行, 无账户ID {no_id} 行"
        )

    if not operations:
        logging.warning("[飞书账户同步] 本轮无在用账户,跳过写库")
        return

    account_ids = list(seen)
    _write_records(mongo_client, operations, account_ids, "主 Mongo")
    try:
        _write_records(mongo_client_new, operations, account_ids, "副 Mongo")
    except Exception:
        # 对齐资产同步的双写策略：副库失败单独告警，下轮全量同步会再次对账。
        logging.exception("[飞书账户同步] 副 Mongo 同步失败 collection=%s", _COLLECTION)


if __name__ == "__main__":
    from conf.log_conf import init

    init("feishu_account_sync")
    sync_feishu_account_records()
