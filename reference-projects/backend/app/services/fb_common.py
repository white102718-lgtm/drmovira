import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from app.db.clients import redis_cli_2 as redis_db
from app.db.mongo import cols

QUEUE_KEY = "fb:business:sync:queue"

# 素材推送 FB 素材库（消费者在 schedulers/tasks/fb_material_push）
MATERIAL_PUSH_QUEUE_KEY = "fb:material:push:queue"
MATERIAL_PUSH_TTL = 24 * 60 * 60  # 进度/去重/任务指纹统一 1 天时效


def material_push_task_key(task_id: str) -> str:
    return f"fb:material:push:task:{task_id}"


def material_push_dedup_key(target_type: str, target_id: str, basename: str) -> str:
    return f"fb:material:push:dedup:{target_type}:{target_id}:{basename}"


def material_push_fp_key(target_type: str, target_id: str, basenames: list) -> str:
    fp = hashlib.sha1(
        f"{target_type}:{target_id}:{','.join(sorted(basenames))}".encode()
    ).hexdigest()
    return f"fb:material:push:fp:{fp}"


class TokenType(str, Enum):
    PERSONAL = "personal"
    SYSTEM_USER = "system_user"


@dataclass
class SyncFlags:
    """同步控制标志（缺省均为 False）"""

    sync_personal: bool = False  # 是否同步个号信息 + 广告账户 + 主页
    sync_bm: bool = False  # 是否同步 BM 信息 + BM 下的资产
    sync_pixels: bool = False  # 是否同步个号下各广告账户的 pixels


async def resolve_token_proxy(
    personal_id: str, personal_type: TokenType
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """返回 (access_token, app_id, app_secret, proxy, error_msg)."""
    if personal_type == TokenType.PERSONAL:
        personal = await cols.personal_accounts.find_one(
            {"_id": personal_id, "status": True},
            {"access_token": 1, "app_id": 1},
        )
        if not personal:
            return None, None, None, None, "未找到对应启用状态的个人号"
        dev = await cols.accounts.find_one(
            {"app_id": personal["app_id"], "status": 1},
            {"proxy": 1, "app_secret": 1},
        )
        proxy = dev.get("proxy") if dev else None
        # personal_accounts.app_secret 可能为空,从 accounts 兜底
        app_secret = dev.get("app_secret") if dev else None
        return personal["access_token"], personal["app_id"], app_secret, proxy, None

    dev = await cols.accounts.find_one(
        {"_id": ObjectId(personal_id), "status": 1},
        {"access_token": 1, "app_id": 1, "app_secret": 1, "proxy": 1},
    )
    if not dev:
        return None, None, None, None, "未找到对应启用状态的系统开发者"
    return (
        dev.get("access_token"),
        dev.get("app_id"),
        dev.get("app_secret"),
        dev.get("proxy"),
        None,
    )


async def push_personal_to_sync_queue(
    facebook_id: str,
    personal_type: TokenType,
    app_id: str,
    app_secret: str,
    access_token: str,
    proxy: str=None,
    targets: dict=None,
):
    """targets 非空时消费者只定向拉指定资产,格式见 schedulers SyncTargets:
    {"accounts": [{"account_id", "pixel_ids"?}], "page_ids": [...]}"""
    if proxy is None:
        dev_config = await cols.accounts.find_one(
            {"app_id": app_id, "account_usage.facebook_login": True, "status": 1},
            projection={"proxy": 1},
        )
        if dev_config and dev_config["proxy"]:
            proxy = dev_config["proxy"]
    task_data = {
        "_id": app_id if personal_type == TokenType.SYSTEM_USER else facebook_id,
        "app_id": app_id,
        "app_secret": app_secret,
        "access_token": access_token,
        "proxy": proxy,
        "token_type": personal_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sync_flags": dataclasses.asdict(
            SyncFlags() if targets else SyncFlags(sync_personal=True, sync_pixels=True)
        ),
    }
    if targets:
        task_data["targets"] = targets
    await redis_db.rpush(QUEUE_KEY, json.dumps(task_data))
