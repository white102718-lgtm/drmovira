"""按系列定向同步:操作广告(预算/暂停/开启/删除)成功后,立刻把该系列子树的
状态/预算列刷进 Doris 三张表,不用等半小时一轮的全量同步。

只拉实体元数据(3~4 个 FB 小调用,不碰 async insights 报告),复用 transform
的状态推导 / 预算沿层级累加,写入前裁剪到 UK + 状态/预算列 —— flexible 部分列
更新下,消耗指标等其余列一律不写、保留旧值。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping

from conf.api_conf import get_proxies
from db.clients import mongo_client
from utils.common import MinuteFormat

from tasks.ad_sync_new import transform
from tasks.ad_sync_new.airbyte import (
    API,
    fetch_ad_account,
    fetch_ads_under_campaigns,
    fetch_adsets_under_campaigns,
    fetch_campaigns_by_ids,
)
from tasks.ad_sync_new.doris_writer import UK_COLUMNS, write_to_doris
from tasks.ad_sync_new.pipeline import (
    ACTIVE_AD_STATUSES,
    ACTIVE_ADSET_STATUSES,
    AD_ACCOUNT_FIELDS,
    AD_SETS_LIST_FIELDS,
    CAMPAIGNS_LIST_FIELDS,
    DELETED_STATUSES,
)


logger = logging.getLogger(__name__)

# 骨架行的消耗指标全是 None,flexible 模式下出现即覆盖,只放行状态/预算相关列。
# fetch_time 不写:它是面板"最新时间"(消耗新鲜度),本同步不拉消耗,保留全量同步的旧值
_KEEP_COLUMNS = set(UK_COLUMNS) | {
    "level",
    "status",
    "delivery",
    "delivery_str",
    "learning_stage",
    "pixel_id",
    "account_status",
    "budget",
    "cam_budget",
    "adset_budget",
}

# 不需要 creative / created_time:对应列都会被裁掉
_ADS_FIELDS = ["id", "name", "adset_id", "campaign_id", "status", "effective_status"]


def _current_half_hour_date() -> str:
    """与 producer 的 hourly china_date 同算法:当前中国时间截到半点。"""
    now_cn = datetime.now(timezone(timedelta(hours=8)))
    slot_minute = 30 if now_cn.minute >= 30 else 0
    return now_cn.replace(minute=slot_minute, second=0, microsecond=0).strftime(MinuteFormat)


def sync_campaign_to_doris(
    dev_app: Mapping[str, Any], account_id: str, campaign_id: str
) -> bool:
    """拉系列子树实体 → transform → 裁剪列 → 部分列更新写 Doris。

    返回是否撞到 IN_PROCESS(FB 变更还在异步生效,effective_status 是瞬态):
    True = 本轮不写(避免面板闪"处理中"),由调用方安排延迟重试。"""
    app_doc = mongo_client["accounts"].find_one(
        {"app_id": dev_app["app_id"]},
        projection={"_id": 0, "ad_platform": 1, "dev_id": 1},
    ) or {}
    message: Dict[str, Any] = {
        "app_id": dev_app["app_id"],
        "app_secret": dev_app["app_secret"],
        "access_token": dev_app["access_token"],
        "proxy": dev_app.get("proxy"),
        "account_id": account_id,
        "ad_platform": app_doc.get("ad_platform", "facebook"),
        "dev_id": app_doc.get("dev_id"),
        "date": _current_half_hour_date(),
    }
    api = API(
        app_id=message["app_id"],
        app_secret=message["app_secret"],
        access_token=message["access_token"],
        proxies=get_proxies(message.get("proxy")),
    )

    cids = [str(campaign_id)]
    bundle: Dict[str, Any] = {
        "ad_account": fetch_ad_account(message, fields=AD_ACCOUNT_FIELDS, api=api),
        "campaigns": fetch_campaigns_by_ids(
            message, cids, fields=CAMPAIGNS_LIST_FIELDS, api=api
        ),
        "ad_sets": fetch_adsets_under_campaigns(
            message, cids, fields=AD_SETS_LIST_FIELDS,
            filter_statuses=ACTIVE_ADSET_STATUSES + DELETED_STATUSES, api=api,
        ),
        "ads": fetch_ads_under_campaigns(
            message, cids, fields=_ADS_FIELDS,
            filter_statuses=ACTIVE_AD_STATUSES + DELETED_STATUSES, api=api,
        ),
    }

    rows = transform.bundle_to_doris_rows(message, bundle)
    # account 行的预算累加只见得到这一个系列,必须丢弃,防止把账户行预算写小
    slim: List[Dict[str, Any]] = [
        {k: v for k, v in row.items() if k in _KEEP_COLUMNS}
        for row in rows
        if row.get("level") != "account"
    ]
    if any(row.get("delivery_str") == "IN_PROCESS" for row in slim):
        logger.info(
            "[campaign_sync] account=%s campaign=%s 有 IN_PROCESS 行,本轮不写等重试",
            account_id, campaign_id,
        )
        return True
    write_to_doris(slim)
    logger.info(
        "[campaign_sync] account=%s campaign=%s 定向刷新 %d 行",
        account_id, campaign_id, len(slim),
    )
    return False
