# -*- coding:utf-8 -*-
"""
Facebook Business Manager 数据同步 - 主入口（定时任务/生产者）

职责：
1. 查询所有活跃个人号（status=True，来自 personal_accounts 表）
2. 查询需要同步资产的系统账号（ad_platform=facebook, status=1, 且 sync_personal/sync_bm/sync_pixels 任一为 True，来自 accounts 表）
3. 将有效凭证推送到 Redis 队列：fb:business:sync:queue

数据流：
定时任务 → 推送账号到队列 → redis_consumer.py（消费者处理）
"""
import dataclasses
import json
import logging
from datetime import datetime, timezone, timedelta

from db.clients import mongo_client
from db.clients import redis_cli_2 as redis_cli
from utils.common_util import handle_error
from model_type_defs.fb_asset_type import FB_BUSINESS_QUEUE_KEY, TokenType, SyncFlags


def is_token_expired(created_at, expires_in, buffer_days=7):
    """
    检查 access token 是否过期

    参数:
    - created_at: token 创建时间（datetime，UTC）
    - expires_in: token 有效期（秒）
    - buffer_days: 缓冲期（天），提前多少天视为即将过期（默认7天）

    返回:
    - (is_expired, reason):
      - is_expired: True 表示已过期或即将过期
      - reason: 过期原因描述（如果未过期则为 None）
    """
    if created_at is None:
        return True, "缺少 created_at 字段"

    if expires_in is None:
        return True, "缺少 expires_in 字段"

    if not isinstance(expires_in, (int, float)) or expires_in <= 0:
        return True, f"expires_in 无效: {expires_in}"

    if isinstance(created_at, str):
        try:
            created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            created_at = created_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return True, f"created_at 格式无法解析: {created_at}"

    if not isinstance(created_at, datetime):
        return True, f"created_at 类型无效: {type(created_at)}"

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elif created_at.tzinfo != timezone.utc:
        created_at = created_at.astimezone(timezone.utc)

    expiry_time = created_at + timedelta(seconds=expires_in)
    now = datetime.now(timezone.utc)
    buffer_time = expiry_time - timedelta(days=buffer_days)

    if now >= expiry_time:
        days_expired = (now - expiry_time).days
        return (
            True,
            f"已过期 {days_expired} 天（过期时间: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}）",
        )

    if now >= buffer_time:
        days_remaining = (expiry_time - now).days
        return (
            True,
            f"即将过期（剩余 {days_remaining} 天，过期时间: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}）",
        )

    return False, None


def _filter_valid_accounts(accounts, label):
    """
    过滤过期 token，返回 (valid_list, expired_ids)
    """
    valid, expired_ids = [], []
    for account in accounts:
        account_id = str(account.get("_id", "unknown"))
        is_expired, reason = is_token_expired(
            account.get("created_at"), account.get("expires_in"), buffer_days=7
        )
        if is_expired:
            expired_ids.append(account_id)
            logging.warning(f"[{label}] ⚠️ 跳过过期账号: {account_id} - {reason}")
        else:
            valid.append(account)
    return valid, expired_ids


def _push_to_queue(
    accounts, token_type: TokenType, label, sync_flags: SyncFlags = None
):
    """将账号列表推送到 Redis 队列，返回成功数量。"""
    success_count = 0
    total = len(accounts)
    for i, account in enumerate(accounts, 1):
        account_id = account.get("_id", "unknown")
        try:
            app_id = account.get("app_id")
            if sync_flags is None:
                usage = account.get("account_usage") or {}
                current_flags = SyncFlags(
                    sync_personal=bool(usage.get("sync_personal", False)),
                    sync_bm=bool(usage.get("sync_bm", False)),
                    sync_pixels=bool(usage.get("sync_pixels", False)),
                )
            else:
                current_flags = sync_flags
            message = {
                "_id": (
                    app_id if token_type == TokenType.SYSTEM_USER else str(account_id)
                ),
                "app_id": app_id,
                "app_secret": account.get("app_secret"),
                "access_token": account.get("access_token"),
                "proxy": account["proxy"],
                "token_type": token_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sync_flags": dataclasses.asdict(current_flags),
            }
            redis_cli.rpush(FB_BUSINESS_QUEUE_KEY, json.dumps(message))
            success_count += 1
            logging.debug(f"[{label}][{i}/{total}] ✓ 推送个号: {account_id}")
        except Exception as e:
            logging.error(f"[{label}][{i}/{total}] ✗ 推送个号 {account_id} 失败: {e}")
    return success_count


def _sync_personal_accounts() -> int:
    """查询个人号并推送到队列，返回成功推送数量。"""
    personal_accounts = list(
        mongo_client["personal_accounts"].find(
            {"status": True},
            projection={
                "_id": 1,
                "app_id": 1,
                "app_secret": 1,
                "access_token": 1,
                "created_at": 1,
                "expires_in": 1,
            },
        )
    )

    if not personal_accounts:
        logging.warning("未找到个人号")
        return 0

    logging.info(f"找到 {len(personal_accounts)} 个个人号")

    # 从 accounts 补充 proxy / app_secret
    app_ids = list({a.get("app_id") for a in personal_accounts if a.get("app_id")})
    dev_config = {}
    if app_ids:
        dev_config = {
            d["app_id"]: d
            for d in mongo_client["accounts"].find(
                {"app_id": {"$in": app_ids}, "account_usage.facebook_login": True, "status": 1},
                projection={"app_id": 1, "app_secret": 1, "proxy": 1},
            )
        }

    valid, expired = _filter_valid_accounts(personal_accounts, "个人号")
    logging.info(
        f"个人号 Token 校验: 总={len(personal_accounts)}, 有效={len(valid)}, 过期={len(expired)}"
    )

    if not valid:
        return 0

    valid[:] = [
        {
            **account,
            "proxy": cfg["proxy"],
            "app_secret": cfg["app_secret"],
        }
        for account in valid
        if (cfg := dev_config.get(account.get("app_id")))
        or logging.warning(f"{account.get('_id')} 所属应用状态异常,需手动删除数据")
    ]

    cnt = _push_to_queue(
        valid,
        token_type=TokenType.PERSONAL,
        label="个人号",
        sync_flags=SyncFlags(sync_personal=True, sync_bm=True, sync_pixels=True),
    )
    logging.info(f"个人号推送: 成功 {cnt}/{len(valid)}")
    return cnt


def _sync_system_accounts() -> int:
    """查询系统账号并推送到队列，返回成功推送数量。"""
    sys_accounts = list(
        mongo_client["accounts"].find(
            {
                "status": 1,
                "ad_platform": "facebook",
                "$or": [
                    {"account_usage.sync_personal": True},
                    {"account_usage.sync_bm": True},
                    {"account_usage.sync_pixels": True},
                ],
            },
            projection={
                "_id": 1,
                "app_id": 1,
                "app_secret": 1,
                "access_token": 1,
                "proxy": 1,
                "account_usage.sync_personal": 1,
                "account_usage.sync_bm": 1,
                "account_usage.sync_pixels": 1
            },
        )
    )

    # TODO: 临时过滤，只保留指定 app_id，后续删除此行
    # sys_accounts = [a for a in sys_accounts if a["app_id"] == "1651181389181104"]

    if not sys_accounts:
        logging.warning("未找到系统账号")
        return 0

    logging.info(f"找到 {len(sys_accounts)} 个系统账号")
    cnt = _push_to_queue(
        sys_accounts,
        token_type=TokenType.SYSTEM_USER,
        label="系统账号",
    )
    logging.info(f"系统账号推送: 成功 {cnt}/{len(sys_accounts)}")
    return cnt


@handle_error(error_message="Facebook Business 同步失败")
def sync_fb_business_data():
    """
    定时任务（生产者）：查询个人号和系统账号并推送到 Redis 队列

    流程：
    1. 查询所有活跃个人号（status=True，来自 personal_accounts）
    2. 从 accounts 补充个人号的 proxy/app_secret（按 app_id 关联）
    3. 过滤过期 token 的个人号，推送有效个人号到队列
    4. 查询系统账号（status=1，来自 accounts）
    5. 过滤过期 token 的系统账号，推送有效系统账号到队列
    """
    from conf.log_conf import init

    init("fb_business_sync")

    logging.info("=" * 60)
    logging.info("开始 Facebook Business 定时同步（生产者）")
    logging.info("=" * 60)
    total_success = 0
    total_success += _sync_personal_accounts()
    total_success += _sync_system_accounts()

    queue_len = redis_cli.llen(FB_BUSINESS_QUEUE_KEY)
    logging.info("=" * 60)
    logging.info(f"推送完成: 本次共推送 {total_success} 个账号")
    logging.info(f"队列 {FB_BUSINESS_QUEUE_KEY} 当前长度: {queue_len}")
    logging.info("=" * 60)


if __name__ == "__main__":
    sync_fb_business_data()
