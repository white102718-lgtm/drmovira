"""
广告配置 / FB 操作记录拉取 worker (Redis 队列消费者)

backend 往对象集合插 status=pending 种子文档并 rpush 任务到 AD_CONFIG_QUEUE_KEY,
本 worker BLPOP 领取:doris 反查所属账户 → 选个号 token(优先带企业登录的 app)
→ 调 FB SDK 拉取 → 结果更新回种子文档(done/failed+error),整棵树其他对象作为
兄弟文档插入(共享 request_id)。查询只走 mongo。

用法:
    python -m tasks.ad_config.ad_config_worker
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign
from facebook_business.api import FacebookAdsApi, FacebookSession

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import mongo_client, mysql_client, redis_cli_2
from model_type_defs.ad_config_type import (
    AD_ACTIVITY_COLLECTION,
    AD_ACTIVITY_DAY_COLLECTION,
    AD_CONFIG_COLLECTIONS,
    AD_CONFIG_QUEUE_KEY,
    AdConfigMessage,
)

BLPOP_TIMEOUT_SECONDS = 30
# 同一开发者(个号/系统)同一时间只允许一个拉取在跑;TTL 仅作进程崩溃兜底,正常在 finally 释放
DEV_LOCK_TTL_SECONDS = 300

# level -> doris ad_daily_detail 里对应的 ID 列(level='ad' 的行里三列都有)
LEVEL_ID_COLUMN = {"ad": "ad_id", "adset": "ad_set_id", "campaign": "campaign_id"}

AD_CONFIG_FIELDS = [
    "id", "name", "status", "effective_status", "adset_id", "campaign_id",
    "created_time", "updated_time",
    "creative{id,name,title,body,thumbnail_url,image_url,video_id,"
    "call_to_action_type,object_story_spec}",
]
ADSET_CONFIG_FIELDS = [
    "id", "name", "status", "effective_status", "campaign_id",
    "optimization_goal", "billing_event", "bid_strategy", "bid_amount",
    "daily_budget", "lifetime_budget", "budget_remaining", "targeting",
    "promoted_object", "destination_type", "start_time", "end_time",
    "created_time", "updated_time",
]
CAMPAIGN_CONFIG_FIELDS = [
    "id", "name", "objective", "status", "effective_status", "buying_type",
    "bid_strategy", "daily_budget", "lifetime_budget", "budget_remaining",
    "special_ad_categories", "special_ad_category_country",
    "start_time", "stop_time", "created_time", "updated_time",
]
ACTIVITY_FIELDS = [
    "actor_id", "actor_name", "event_type", "translated_event_type",
    "event_time", "date_time_in_timezone", "object_id", "object_name",
    "object_type", "extra_data",
]


def _resolve_account_campaign(level: str, object_id: str) -> tuple | None:
    """按层级从 doris 反查该对象最新一行的 (account_id, account_name, campaign_id)。"""
    col = LEVEL_ID_COLUMN[level]
    rows = mysql_client.read(
        "SELECT account_id, account_name, campaign_id FROM ad_daily_detail "
        f"WHERE level = 'ad' AND {col} = {object_id} ORDER BY date DESC LIMIT 1"
    )
    return rows[0] if rows else None


def _resolve_personal_token(account_id: str) -> dict | None:
    """挑一个可访问该账户的个号 token,优先其 app 开发者带企业登录(facebook_login)权限。

    doris account_id 不带 act_ 前缀,而 personal_accounts.accounts.id 可能带,故两形态都匹配。
    """
    personals = list(
        mongo_client["personal_accounts"].find(
            {"accounts.id": {"$in": [account_id, f"act_{account_id}"]}, "status": True},
            {"_id": 1, "app_id": 1, "access_token": 1},
        )
    )
    if not personals:
        return None

    app_ids = list({p["app_id"] for p in personals if p.get("app_id")})
    devs = {
        d["app_id"]: d
        for d in mongo_client["accounts"].find(
            {"app_id": {"$in": app_ids}, "status": 1},
            {"app_id": 1, "app_secret": 1, "proxy": 1, "account_usage.facebook_login": 1},
        )
    }

    def _has_login(p: dict) -> bool:
        dev = devs.get(p.get("app_id")) or {}
        return bool((dev.get("account_usage") or {}).get("facebook_login"))

    for p in sorted(personals, key=lambda p: 0 if _has_login(p) else 1):
        dev = devs.get(p.get("app_id"))
        if not dev or not dev.get("app_secret") or not dev.get("proxy"):
            continue
        if not p.get("access_token"):
            continue
        return {
            "dev_id": str(p["_id"]),
            "app_id": p["app_id"],
            "app_secret": dev["app_secret"],
            "access_token": p["access_token"],
            "proxy": dev["proxy"],
        }
    return None


def _build_api(token: dict) -> FacebookAdsApi:
    return FacebookAdsApi(
        FacebookSession(
            token["app_id"],
            token["app_secret"],
            token["access_token"],
            proxies=get_proxies(token["proxy"]),
            timeout=(15, 180),
        )
    )


def _base_doc(ctx: dict, level: str, object_id, campaign_id, ad_set_id) -> dict:
    """对象文档公共字段;归属靠 campaign_id + ad_set_id 外键表达。配置/操作记录各自补 config / activities。"""
    return {
        "request_id": ctx["request_id"],
        "level": level,
        "object_id": str(object_id),
        "campaign_id": str(campaign_id) if campaign_id else None,
        "ad_set_id": str(ad_set_id) if ad_set_id else None,
        "account_id": ctx["account_id"],
        "account_name": ctx["account_name"],
        "real_name": ctx["real_name"],
        "status": "done",
        "created_at": datetime.now(timezone.utc),
    }


def _collect_config_objects(
    api: FacebookAdsApi, level: str, object_id: str, campaign_id, include_related: bool, ctx: dict
) -> list[dict]:
    if not include_related:
        if level == "campaign":
            d = Campaign(object_id, api=api).api_get(fields=CAMPAIGN_CONFIG_FIELDS).export_all_data()
            return [{**_base_doc(ctx, "campaign", object_id, object_id, None), "config": d}]
        if level == "adset":
            d = AdSet(object_id, api=api).api_get(fields=ADSET_CONFIG_FIELDS).export_all_data()
            return [{**_base_doc(ctx, "adset", object_id, d.get("campaign_id"), None), "config": d}]
        d = Ad(object_id, api=api).api_get(fields=AD_CONFIG_FIELDS).export_all_data()
        return [{**_base_doc(ctx, "ad", object_id, d.get("campaign_id"), d.get("adset_id")), "config": d}]

    cid = str(campaign_id)
    camp = Campaign(cid, api=api).api_get(fields=CAMPAIGN_CONFIG_FIELDS).export_all_data()
    docs = [{**_base_doc(ctx, "campaign", cid, cid, None), "config": camp}]
    for a in Campaign(cid, api=api).get_ad_sets(fields=ADSET_CONFIG_FIELDS):
        d = a.export_all_data()
        docs.append({**_base_doc(ctx, "adset", d["id"], cid, None), "config": d})
    for a in Campaign(cid, api=api).get_ads(fields=AD_CONFIG_FIELDS):
        d = a.export_all_data()
        docs.append(
            {**_base_doc(ctx, "ad", d["id"], d.get("campaign_id") or cid, d.get("adset_id")), "config": d}
        )
    return docs


def _pull_account_activities(api: FacebookAdsApi, account_id: str, since: int, until: int) -> list[dict]:
    """FB 只在账户节点暴露 activities 边(campaign/adset/ad 节点访问会报 #100 nonexisting
    field),按账户拉时间窗内全部操作记录,调用方再按 object_id 过滤到具体对象/整棵树。
    since/until 为绝对 Unix 秒(见 _china_day_unix),不要传日期串——FB 会按 UTC 解释。"""
    return [
        a.export_all_data()
        for a in AdAccount(f"act_{account_id}", api=api).get_activities(
            fields=ACTIVITY_FIELDS, params={"since": since, "until": until, "limit": 500}
        )
    ]


def _collect_activity_objects(
    api: FacebookAdsApi, level: str, object_id: str, account_id: str,
    campaign_id, include_related: bool, date: str, ctx: dict
) -> list[dict]:
    since, until = _china_day_unix(date)

    def _doc(lvl, oid, cid, asid, items):
        return {**_base_doc(ctx, lvl, oid, cid, asid), "date": date, "activities": items}

    if not include_related:
        acts = [
            d for d in _pull_account_activities(api, account_id, since, until)
            if str(d.get("object_id") or "") == str(object_id)
        ]
        return [_doc(level, object_id, campaign_id, None, acts)] if acts else []

    # 整棵系列树:先拿树内 id + ad→adset 映射,再拉账户当天操作记录(游标自动翻页)按对象归并
    cid = str(campaign_id)
    adset_ids = {str(a["id"]) for a in Campaign(cid, api=api).get_ad_sets(fields=["id"])}
    ad_to_adset = {
        str(a["id"]): (str(a.get("adset_id")) if a.get("adset_id") else None)
        for a in Campaign(cid, api=api).get_ads(fields=["id", "adset_id"])
    }
    tree_ids = {cid} | adset_ids | set(ad_to_adset)

    by_obj: dict[str, list] = defaultdict(list)
    for d in _pull_account_activities(api, account_id, since, until):
        oid = str(d.get("object_id") or "")
        if oid in tree_ids:
            by_obj[oid].append(d)

    docs = []
    for oid, items in by_obj.items():
        if oid == cid:
            docs.append(_doc("campaign", oid, cid, None, items))
        elif oid in adset_ids:
            docs.append(_doc("adset", oid, cid, None, items))
        else:
            docs.append(_doc("ad", oid, cid, ad_to_adset.get(oid), items))
    return docs


def _fail_pull(msg: AdConfigMessage, error: str) -> None:
    """失败回写:activities 按种子文档 _id;config 按层级实体表 _id=object_id。"""
    now = datetime.now(timezone.utc)
    if msg.get("pull_type") == "activities":
        mongo_client[AD_ACTIVITY_COLLECTION].update_one(
            {"_id": ObjectId(msg["request_id"])},
            {"$set": {"status": "failed", "error": error, "updated_at": now}},
        )
        return
    coll = AD_CONFIG_COLLECTIONS.get(msg.get("level") or "")
    if coll and msg.get("object_id"):
        mongo_client[coll].update_one(
            {"_id": str(msg["object_id"])},
            {"$set": {"status": "failed", "error": error, "updated_at": now}},
        )


def process_pull(msg: AdConfigMessage) -> bool:
    """业务核心:解析账户/token → 抢开发者锁 → 调 FB → 结果落 mongo:
    config 整棵树对象各自 upsert 进层级实体表;activities 回写种子文档 +
    插兄弟文档;失败回写 failed+error。

    返回 True=已处理;False=该开发者正被别处拉取,任务已回队尾待重试。
    与队列解耦,可直接传 msg 调试。
    """
    request_id = msg.get("request_id")
    try:
        level = msg["level"]
        object_id = str(msg["object_id"])
        include_related = bool(msg.get("include_related"))
        if level not in LEVEL_ID_COLUMN:
            raise ValueError(f"非法 level: {level}")
        if not object_id.isdigit():
            raise ValueError(f"非法 object_id: {object_id}")

        row = _resolve_account_campaign(level, object_id)
        if not row:
            raise LookupError("doris ad_daily_detail 未找到该对象")
        account_id, account_name, campaign_id = str(row[0]), row[1], row[2]
        if include_related and not campaign_id:
            raise LookupError("未能定位所属系列(campaign_id 为空),无法拉整棵系列树")

        token = _resolve_personal_token(account_id)
        if not token:
            raise LookupError("未找到可访问该账户的可用个号 token")
    except Exception as e:
        logging.error(f"[{request_id}] 拉取失败: {e}", exc_info=True)
        _fail_pull(msg, str(e))
        return True

    # 同一开发者串行:抢不到锁就把任务回队尾,让别的开发者的任务先走(多 worker 时天然并行)
    lock_key = f"ad_config:lock:{token['dev_id']}"
    if not redis_cli_2.set(lock_key, request_id, nx=True, ex=DEV_LOCK_TTL_SECONDS):
        redis_cli_2.rpush(AD_CONFIG_QUEUE_KEY, json.dumps(msg, ensure_ascii=False))
        logging.info(f"[{request_id}] 开发者 {token['dev_id']} 拉取中,任务回队尾等待")
        return False

    ctx = {
        "request_id": request_id,
        "account_id": account_id,
        "account_name": account_name,
        "real_name": msg.get("real_name", ""),
    }
    try:
        api = _build_api(token)
        if msg.get("pull_type") == "activities":
            docs = _collect_activity_objects(
                api, level, object_id, account_id, campaign_id, include_related, msg["date"], ctx
            )
            # 目标对象自身的结果更新回种子文档,其余对象插兄弟文档
            seed_fields = None
            related = []
            for d in docs:
                if seed_fields is None and d["object_id"] == object_id:
                    seed_fields = d
                else:
                    related.append(d)
            mongo_client[AD_ACTIVITY_COLLECTION].update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {
                        "status": "done",
                        "error": None,
                        "account_id": account_id,
                        "account_name": account_name,
                        "campaign_id": (seed_fields or {}).get("campaign_id")
                        or (str(campaign_id) if campaign_id else None),
                        "ad_set_id": (seed_fields or {}).get("ad_set_id"),
                        "activities": seed_fields["activities"] if seed_fields else [],
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            if related:
                mongo_client[AD_ACTIVITY_COLLECTION].insert_many(related)
        else:
            docs = _collect_config_objects(
                api, level, object_id, campaign_id, include_related, ctx
            )
            # 整棵树对象各自 upsert 进层级实体表(含目标对象自身),一对象一条最新态
            now = datetime.now(timezone.utc)
            for d in docs:
                update = {k: v for k, v in d.items() if k != "created_at"}
                update["error"] = None
                update["updated_at"] = now
                mongo_client[AD_CONFIG_COLLECTIONS[d["level"]]].update_one(
                    {"_id": d["object_id"]},
                    {"$set": update, "$setOnInsert": {"created_at": now}},
                    upsert=True,
                )
        logging.info(
            f"[{request_id}] {msg.get('pull_type')} 拉取完成 {level}={object_id} "
            f"related={include_related} objects={len(docs)}"
        )
    except Exception as e:
        logging.error(f"[{request_id}] 拉取失败: {e}", exc_info=True)
        _fail_pull(msg, str(e))
    finally:
        redis_cli_2.delete(lock_key)
    return True


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _china_day_unix(date: str) -> tuple[int, int]:
    """中国日 [00:00, 次日00:00) 的绝对 Unix 秒。
    FB 的 since/until 传日期串会被当 UTC 解释,和中国日错 8 小时、裁掉中国上午的操作;
    改传绝对时间戳,窗口就精确等于中国日,与面板同口径。"""
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=_SHANGHAI)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _is_china_date_sealed(date: str) -> bool:
    """缓存的是中国日窗口,中国日已过 → 窗口内绝对时间全过去、不会再有操作,封存后直读缓存。"""
    return datetime.strptime(date, "%Y-%m-%d").date() < datetime.now(_SHANGHAI).date()


def _fail_activity_day(account_id: str, date: str, error: str) -> None:
    mongo_client[AD_ACTIVITY_DAY_COLLECTION].update_one(
        {"account_id": account_id, "date": date},
        {"$set": {"status": "failed", "error": error, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def process_activity_day(msg: AdConfigMessage) -> bool:
    """按(账户+天)拉取整天操作记录写入 ad_config_activity_days:一次账户级拉取给当天所有对象共用。
    返回 True=已处理;False=该开发者正被别处拉取,任务回队尾待重试。"""
    account_id = str(msg["account_id"])
    date = msg["date"]
    try:
        token = _resolve_personal_token(account_id)
        if not token:
            raise LookupError("未找到可访问该账户的可用个号 token")
    except Exception as e:
        logging.error(f"[activity_day {account_id}/{date}] 拉取失败: {e}", exc_info=True)
        _fail_activity_day(account_id, date, str(e))
        return True

    lock_key = f"ad_config:lock:{token['dev_id']}"
    if not redis_cli_2.set(lock_key, f"{account_id}:{date}", nx=True, ex=DEV_LOCK_TTL_SECONDS):
        redis_cli_2.rpush(AD_CONFIG_QUEUE_KEY, json.dumps(msg, ensure_ascii=False))
        return False

    try:
        api = _build_api(token)
        since, until = _china_day_unix(date)
        acts = _pull_account_activities(api, account_id, since, until)
        sealed = _is_china_date_sealed(date)
        now = datetime.now(timezone.utc)
        mongo_client[AD_ACTIVITY_DAY_COLLECTION].update_one(
            {"account_id": account_id, "date": date},
            {
                "$set": {
                    "activities": acts,
                    "sealed": sealed,
                    "status": "done",
                    "error": None,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        logging.info(
            f"[activity_day {account_id}/{date}] 拉取完成 sealed={sealed} records={len(acts)}"
        )
    except Exception as e:
        logging.error(f"[activity_day {account_id}/{date}] 拉取失败: {e}", exc_info=True)
        _fail_activity_day(account_id, date, str(e))
    finally:
        redis_cli_2.delete(lock_key)
    return True


def main():
    init("ad_config_worker")
    logging.info(f"启动 ad_config_worker, queue={AD_CONFIG_QUEUE_KEY}")
    while True:
        try:
            popped = redis_cli_2.blpop(AD_CONFIG_QUEUE_KEY, timeout=BLPOP_TIMEOUT_SECONDS)
        except Exception as e:
            logging.error(f"Redis BLPOP 异常: {e}")
            time.sleep(1)
            continue
        if not popped:
            continue
        _, payload = popped
        try:
            msg = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        except Exception as e:
            logging.error(f"消息 JSON 解析失败: {e}, raw={payload!r}")
            continue
        try:
            handler = process_activity_day if msg.get("pull_type") == "activity_day" else process_pull
            if not handler(msg):
                time.sleep(1)  # 锁被占并已回队尾,退避一下避免热轮询
        except Exception as e:
            logging.error(f"处理消息异常: {e}", exc_info=True)


if __name__ == "__main__":
    main()
