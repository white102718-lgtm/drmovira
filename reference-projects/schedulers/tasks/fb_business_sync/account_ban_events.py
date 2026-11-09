# -*- coding: utf-8 -*-
"""广告账户封户事件：判定状态转换、写入新 Mongo 并维护查询索引。"""

import logging
from datetime import datetime
from uuid import uuid4

from pymongo import ASCENDING, ReturnDocument

from db.clients import mongo_client_new

BAN_EVENT_COLLECTION = "fb_ad_account_ban_events"
BAN_EVENT_INDEXES = (
    (
        [("detected_at", ASCENDING), ("_id", ASCENDING)],
        "idx_ban_event_window",
    ),
)
LEGACY_BAN_EVENT_INDEXES = (
    "idx_ban_event_detected",
    "idx_ban_event_account",
)


def _normalized_status(value):
    """将 Facebook 账户状态统一为整数，无法解析时返回 None。"""
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        logging.warning("无法解析账户状态值: %r", value)
        return None


def claim_ban_transition(account_id: str, set_data: dict) -> dict | None:
    """原子取得一次“非 2 → 2”转换前的旧账户，供后续生成唯一封户事件。"""
    if _normalized_status(set_data.get("account_status")) != 2:
        return None

    # 多消费者可能同时同步同一广告户，新 Mongo 上的原子状态转换决定唯一事件生产者。
    return mongo_client_new["fb_ad_accounts"].find_one_and_update(
        {"_id": account_id, "account_status": {"$nin": [2, "2"]}},
        {"$set": set_data},
        projection={"name": 1, "currency": 1, "account_status": 1},
        return_document=ReturnDocument.BEFORE,
    )


def record_ban_event(previous: dict | None, current: dict, now: datetime) -> bool:
    """将真实封户转换记录到新 Mongo；首次同步和重复状态不产生事件。"""
    if previous is None:
        return False

    previous_status = _normalized_status(previous.get("account_status"))
    current_status = _normalized_status(current.get("account_status"))
    if previous_status is None or previous_status == 2 or current_status != 2:
        return False

    event = {
        "_id": uuid4().hex,
        "account_id": current["account_id"],
        "account_name": current.get("name") or previous.get("name"),
        "currency": current.get("currency") or previous.get("currency"),
        "previous_status": previous_status,
        "current_status": current_status,
        "disable_reason": current.get("disable_reason"),
        "detected_at": now,
        "source": "fb_business_sync",
        "created_at": now,
    }
    try:
        mongo_client_new[BAN_EVENT_COLLECTION].insert_one(event)
    except Exception:
        # 封户事件失败不能中断当前个人号剩余资源同步，但必须留下可定位的事件信息。
        logging.exception(
            "[account_ban_events] 新 Mongo 封户事件写入失败 event_id=%s",
            event["_id"],
        )
        return False
    return True


def ensure_ban_event_indexes() -> bool:
    """在新 Mongo 创建封户窗口索引，成功后移除不匹配查询方向的旧索引。"""
    collection = mongo_client_new[BAN_EVENT_COLLECTION]
    try:
        for keys, name in BAN_EVENT_INDEXES:
            collection.create_index(keys, name=name)
    except Exception:
        logging.exception("[account_ban_events] 创建新 Mongo 封户事件索引失败")
        return False

    # 新索引全部可用后再清理旧索引，避免部署期间出现无索引窗口。
    try:
        existing_indexes = collection.index_information()
    except Exception:
        logging.exception("[account_ban_events] 读取新 Mongo 封户事件索引失败")
        return False

    for name in LEGACY_BAN_EVENT_INDEXES:
        if name not in existing_indexes:
            continue
        try:
            collection.drop_index(name)
        except Exception:
            logging.exception(
                "[account_ban_events] 删除旧封户事件索引失败 index=%s", name
            )
            return False
    return True
