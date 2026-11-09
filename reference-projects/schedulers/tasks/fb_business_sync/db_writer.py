# -*- coding:utf-8 -*-
"""
MongoDB写入器 - upsert操作,主副 Mongo 双写
"""

import logging
from datetime import datetime, timezone

from db.clients import mongo_client, mongo_client_new
from model_type_defs.fb_asset_type import TokenType
from tasks.fb_business_sync.account_ban_events import (
    claim_ban_transition,
    record_ban_event,
)


def _update_one(collection: str, filter_: dict, update: dict, upsert: bool = False):
    """主 Mongo 写完再写副 Mongo。副库失败只告警不抛:调用方的 @handle_error
    不 reraise,抛出去会让当前号剩下的资源全部不再拉取。
    """
    mongo_client[collection].update_one(filter_, update, upsert=upsert)
    try:
        mongo_client_new[collection].update_one(filter_, update, upsert=upsert)
    except Exception:
        logging.exception(
            f"[db_writer] 副 Mongo 写入失败 collection={collection} filter={filter_}"
        )


def upsert_business_(data: dict):
    """
    Upsert Business记录

    参数：
    - data: {"business_id", "business_name", "data"}

    表：fb_businesses
    """
    now = datetime.now(timezone.utc)

    update_ops = {
        "$set": {
            "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
    }

    field_name = (
        data["data_type"]
        if data["data_type"] in {"accounts", "pages", "pixels"}
        else None
    )

    if field_name:
        # 确保 data["data"] 是一个列表，如果是单值需要转为列表
        new_items = data["data"] if isinstance(data["data"], list) else [data["data"]]

        # 不去重，直接追加
        update_ops["$set"][field_name] = new_items

    _update_one(
        "fb_businesses",
        {"business_id": data["business_id"]},  # 主键查询
        update_ops,
        upsert=True,
    )
    logging.debug(f"Upsert Business: {data['business_id']}")


def upsert_business(data: dict):
    """
    Upsert Business记录

    参数：
    - data: {"business_id", "business_name", "developer_id"}

    表：fb_businesses
    """
    now = datetime.now(timezone.utc)

    _update_one(
        "fb_businesses",
        {"_id": f"{data['business_id']}_{data['doc_id']}"},  # 主键查询
        {
            "$set": {
                "business_id": data["business_id"],
                "business_name": data["business_name"],
                "doc_id": data["doc_id"],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},  # 仅插入时设置
        },
        upsert=True,  # 不存在则插入
    )
    logging.debug(f"Upsert Business: {data['business_id']}")


def upsert_account(data: dict):
    """
    Upsert Account记录

    参数：
    - data: Facebook API返回的account数据

    表：fb_ad_accounts,
    """
    now = datetime.now(timezone.utc)
    account_id = data.get("account_id")
    if not account_id:
        logging.warning(f"跳过处理：数据中缺少有效的 id 字段。Data: {data}")
        return

    set_data = {
        "name": data.get("name"),
        "account_status": data.get("account_status"),
        "disable_reason": data.get("disable_reason"),
        "currency": data.get("currency"),
        "amount_spent": data.get("amount_spent"),
        "balance": data.get("balance"),
        "created_time": _parse_api_time_to_utc(data.get("created_time")),
        "timezone_name": data.get("timezone_name"),
        "age": data.get("age"),
        "end_advertiser": data.get("end_advertiser"),
        "funding_source_details": data.get("funding_source_details"),
        "is_prepay_account": data.get("is_prepay_account"),
        "spend_cap": data.get("spend_cap"),
        "owner": data.get("owner"),
        "tax_id_status": data.get("tax_id_status"),
        "updated_at": now,
    }
    # 只有上游明确提供限额时才更新，避免当前资源同步把外部回调写入的值清空。
    if "account_dsl" in data:
        set_data["account_dsl"] = data.get("account_dsl")

    previous = claim_ban_transition(account_id, set_data)

    _update_one(
        "fb_ad_accounts",
        {"_id": account_id},  # 主键
        {
            "$set": set_data,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    record_ban_event(previous, {**data, "account_id": account_id}, now)
    logging.debug(f"Upsert Account: {data.get('account_id')}")


def upsert_page(data: dict):
    """
    Upsert Page记录

    参数：
    - data: Facebook API返回的page数据

    表：fb_pages

    注意：Page的主键是'id'字段，在MongoDB中保存为page_id
    """
    now = datetime.now(timezone.utc)
    page_id = data.get("id")
    if not page_id:
        logging.warning(f"跳过处理：数据中缺少有效的 id 字段。Data: {data}")
        return

    set_data = {
        "name": data.get("name"),
        "is_published": data.get("is_published"),
        "username": data.get("username"),
        "verification_status": data.get("verification_status"),
        "link": data.get("link"),
        "fan_count": data.get("fan_count"),
        "category": data.get("category"),
        "followers_count": data.get("followers_count"),
        "talking_about_count": data.get("talking_about_count"),
        "is_unclaimed": data.get("is_unclaimed"),
        "can_post": data.get("can_post"),
        "new_like_count": data.get("new_like_count"),
        "picture": data.get("picture", {}).get("data", {}),
        "updated_at": now,
    }
    if "access_token" in data:
        set_data["access_token"] = data.get("access_token")
    if "instagram_user_id" in data:
        set_data["instagram_user_id"] = data.get("instagram_user_id")

    _update_one(
        "fb_pages",
        {"_id": page_id},  # 注意：API返回的是'id'字段
        {"$set": set_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logging.debug(f"Upsert Page: {data.get('id')}")


def upsert_pixel(data: dict):
    """
    Upsert Pixel记录

    参数：
    - data: Facebook API返回的pixel数据

    表：fb_pixels

    注意：Pixel的主键是'id'字段，在MongoDB中保存为pixel_id
    """
    now = datetime.now(timezone.utc)
    pixel_id = data.get("id")
    if not pixel_id:
        logging.warning(f"跳过处理：数据中缺少有效的 id 字段。Data: {data}")
        return

    _update_one(
        "fb_pixels",
        {"_id": pixel_id},  # 注意：API返回的是'id'字段
        {
            "$set": {
                "name": data.get("name"),
                "last_fired_time": _parse_api_time_to_utc(data.get("last_fired_time")),
                "data_use_setting": data.get("data_use_setting"),
                "is_unavailable": data.get("is_unavailable"),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    logging.debug(f"Upsert Pixel: {data.get('id')}")


def upsert_account_pixel(data: dict):
    """
    upsert_account_pixel 的
    更换账户下的 像素集合
    :param data: 说明
    :type data: dict
    """
    now = datetime.now(timezone.utc)
    account_id = data.get("account_id")
    if not account_id:
        logging.warning(f"跳过处理：数据中缺少有效的 id 字段。Data: {data}")
        return

    _update_one(
        "fb_ad_accounts",
        {"_id": account_id},  # 主键
        {"$set": {"updated_at": now, "pixels": data["data"]}},
    )
    logging.debug(f"Upsert Account: {data.get('account_id')}")


def merge_account_pixels(data: dict):
    """按 id 把像素合并进户的 pixels 列表,不覆盖已有集合(定向同步用)。

    参数与 upsert_account_pixel 同形: {"account_id", "data"}
    """
    now = datetime.now(timezone.utc)
    account_id = data["account_id"]
    doc = mongo_client["fb_ad_accounts"].find_one({"_id": account_id}, {"pixels": 1})
    merged = {
        p["id"]: p
        for p in (doc.get("pixels") if doc else None) or []
        if isinstance(p, dict) and p.get("id")
    }
    for item in data["data"]:
        merged[item["id"]] = item

    _update_one(
        "fb_ad_accounts",
        {"_id": account_id},
        {"$set": {"pixels": list(merged.values()), "updated_at": now}},
    )
    logging.debug(f"Merge Account Pixels: {account_id} +{len(data['data'])}")


def upsert_personal_account(data: dict):
    """
    更新 personal_accounts 或 fb_system_users 表的资源ID列表

    参数：
    - data: {
        "_id": "...",  # 个号为 facebook_id，系统用户为 app_id（由调用方决定）
        "token_type": "personal" / "system_user",  # 默认 personal
        "data_type": "accounts" / "pages" / "pixels" / "business",
        "data": [{"id": "xxx", "name": "xxx"}, ...],
      }
    """
    now = datetime.now(timezone.utc)
    token_type = data.get("token_type", TokenType.PERSONAL)
    collection = (
        "fb_system_users"
        if token_type == TokenType.SYSTEM_USER
        else "personal_accounts"
    )

    update_ops = {
        "$set": {"updated_at": now},
    }

    field_name = (
        data["data_type"]
        if data["data_type"] in {"accounts", "pages", "pixels", "business"}
        else None
    )

    if field_name:
        new_items = data["data"] if isinstance(data["data"], list) else [data["data"]]
        update_ops["$set"][field_name] = new_items

    _update_one(collection, {"_id": data["_id"]}, update_ops, upsert=True)
    logging.debug(
        f"Upsert {collection}: {data['_id']} - "
        f"{data['data_type']}: {len(data['data'])} 个"
    )


def _parse_api_time_to_utc(time_str: str) -> datetime | None:
    """
    api返回的时间格式 转utc时间
    """
    if not time_str:
        return None

    dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S%z")

    return dt.astimezone(timezone.utc)
