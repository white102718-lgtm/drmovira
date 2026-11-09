# -*- coding:utf-8 -*-
"""
fb_business_sync 模块内部消息类型定义
"""

from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, NotRequired


# ──────────────────────────────────────────────
# 通用枚举 / 字面量
# ──────────────────────────────────────────────


class TokenType(str, Enum):
    """继承 str，枚举值本身就是字符串，比较/序列化与裸字符串完全兼容。"""

    PERSONAL = "personal"
    SYSTEM_USER = "system_user"


# ──────────────────────────────────────────────
# Redis 队列配置常量（生产者 & 消费者共用）
# ──────────────────────────────────────────────

FB_BUSINESS_QUEUE_KEY = "fb:business:sync:queue"

# ──────────────────────────────────────────────
# Redis 输入消息（生产者 → consumer_loop）
# ──────────────────────────────────────────────


@dataclass
class SyncFlags:
    """同步控制标志（缺省均为 False）"""

    sync_personal: bool = False  # 是否走 process_user（个号信息 + 广告账户 + 主页）
    sync_bm: bool = False  # 是否走 process_developer（BM 信息 + BM 下的资产）
    sync_pixels: bool = False  # 是否同步个号下各广告账户的 pixels


class TargetAccount(TypedDict):
    """定向同步的单个户,pixel_ids 缺省则只拉户本身"""

    account_id: str
    pixel_ids: NotRequired[list[str]]


class SyncTargets(TypedDict):
    """定向同步目标,存在时消费者只拉指定资产,不做全量同步"""

    accounts: NotRequired[list[TargetAccount]]
    page_ids: NotRequired[list[str]]


class FbSyncMessage(TypedDict):
    """从 Redis 队列消费的原始任务消息"""

    _id: str  # 文档主键：系统用户为 app_id，个号为 facebook_id
    app_id: str
    app_secret: str
    access_token: str
    token_type: NotRequired[TokenType]  # 默认 "personal"
    proxy: NotRequired[str | None]
    sync_flags: NotRequired[SyncFlags]
    targets: NotRequired[SyncTargets]
