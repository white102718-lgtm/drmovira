# -*- coding:utf-8 -*-
"""ad_config 模块常量与消息类型(与 backend ad-config 路由对齐)

流程:backend 标记 pending 并 rpush 任务到 AD_CONFIG_QUEUE_KEY,worker BLPOP 领取拉 FB:
- config:层级实体表一对象一条(_id=FB 对象 id),backend upsert pending,
  worker 拉完把整棵树对象各自 upsert 回对应层级表(done/failed+error)
- activities:backend 插 ObjectId 种子文档,worker 回写种子 + 插兄弟文档(共享 request_id)
查询只走 mongo。
"""

from typing import NotRequired, TypedDict

# backend 用 redis db2 rpush 此 key,worker BLPOP 消费
AD_CONFIG_QUEUE_KEY = "ad:config:queue"
# 配置实体表按层级分三张:一对象一条最新态,_id=FB 对象 id;归属靠 campaign_id + ad_set_id
# 前缀 ad_config_ 是本功能专属命名空间,勿用 fb_ 前缀(fb_ads 等已被资料库爬虫/其他功能占用)
AD_CONFIG_COLLECTIONS = {
    "campaign": "ad_config_campaigns",
    "adset": "ad_config_adsets",
    "ad": "ad_config_ads",
}
AD_ACTIVITY_COLLECTION = "ad_config_activities"
# 查看记录:按(账户+天)缓存整天操作记录 + 拉取状态/封存标记,独立于 ad_config_activities
AD_ACTIVITY_DAY_COLLECTION = "ad_config_activity_days"


class AdConfigMessage(TypedDict):
    pull_type: str  # "config" | "activities" | "activity_day"
    real_name: str  # 提交人
    date: NotRequired[str | None]  # activities / activity_day 用,YYYY-MM-DD
    # config / activities:种子文档在对象集合,按 object 拉
    request_id: NotRequired[str]  # 种子文档 _id(str),worker 按它回写结果
    level: NotRequired[str]  # "ad" | "adset" | "campaign"
    object_id: NotRequired[str]
    include_related: NotRequired[bool]  # True=拉整棵系列树,False=只拉本层
    # activity_day:拉取状态写在 ad_config_activity_days,不碰 ad_config_activities
    account_id: NotRequired[str]
