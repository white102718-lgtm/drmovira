import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from conf import Env, env
from conf.log_conf import init
from db.clients import mongo_client, redis_cli
from utils.fb_utils import get_channel_account_mapping, get_channel_names
from utils.feishu import PAY_ERROR_CHAT_ID, PAY_ERROR_TEST_CHAT_ID, send_feishu_card

ACCOUNT_ALERT_SET_KEY = "tg:check_ad_status:fb_account_alert"
FEISHU_CALLBACK_TYPE = "tech_fb_account_status"
FEISHU_CALLBACK_ACTION_PROCESSING = "processing"
FEISHU_CALLBACK_ACTION_RESOLVED = "resolved"


def build_tech_fb_account_status_card(
    grouped_accounts: dict[str, list[dict[str, str]]],
) -> dict:
    total = sum(len(accounts) for accounts in grouped_accounts.values())
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**支付错误** · 共 {total} 个账户\n时间：{now_cn}",
            },
        }
    ]
    for real_name in sorted(grouped_accounts):
        accounts = grouped_accounts[real_name]
        if not accounts:
            continue
        lines = [f"**【{real_name}】**"]
        # 同渠道相邻, 未知渠道的沉底
        for account in sorted(
            accounts,
            key=lambda a: (a["channel_text"] == "未知渠道", a["channel_text"], a["id"]),
        ):
            account_name = account["name"] or "-"
            lines.append(
                f'{account["channel_text"]}　{account_name}　{account["id"]}'
            )
        elements.append({"tag": "hr"})
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}
        )
    elements.append(
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "解决中"},
                    "type": "default",
                    "value": {
                        "type": FEISHU_CALLBACK_TYPE,
                        "action": FEISHU_CALLBACK_ACTION_PROCESSING,
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "已解决"},
                    "type": "primary",
                    "value": {
                        "type": FEISHU_CALLBACK_TYPE,
                        "action": FEISHU_CALLBACK_ACTION_RESOLVED,
                    },
                },
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "Facebook 账户状态异常通知"},
        },
        "elements": elements,
    }


def _normalize_account_id(account_id) -> str:
    return str(account_id).strip()


def _build_channel_text_by_account_id() -> dict[str, str]:
    channel_account_mapping = get_channel_account_mapping()
    channel_name_mapping = get_channel_names(list(channel_account_mapping.keys()))
    account_id_to_channels: dict[str, set[str]] = defaultdict(set)

    for channel_id, account_ids in channel_account_mapping.items():
        normalized_channel_id = str(channel_id).strip()
        if not normalized_channel_id:
            continue

        channel_text = (
            channel_name_mapping.get(normalized_channel_id) or normalized_channel_id
        )

        for account_id in account_ids or []:
            normalized_account_id = _normalize_account_id(account_id)
            if not normalized_account_id:
                continue

            account_id_to_channels[normalized_account_id].add(channel_text)

    return {
        account_id: " / ".join(sorted(channels))
        for account_id, channels in account_id_to_channels.items()
        if channels
    }


def _normalize_redis_members(members) -> set[str]:
    normalized_members = set()
    for member in members:
        if isinstance(member, bytes):
            member = member.decode()
        normalized_member = _normalize_account_id(member)
        if normalized_member:
            normalized_members.add(normalized_member)
    return normalized_members


def _ensure_account_alert_set_ttl(now: datetime) -> None:
    if redis_cli.ttl(ACCOUNT_ALERT_SET_KEY) != -1:
        return

    expire_at = now.replace(hour=23, minute=30, second=0, microsecond=0)
    redis_cli.expireat(ACCOUNT_ALERT_SET_KEY, int(expire_at.timestamp()))


def check_tech_department_fb_account_status() -> None:
    personal_accounts = mongo_client["personal_accounts"].find(
        {"status": True},
        projection={"user_name": 1, "accounts": 1, "_id": 0},
    )

    real_name_to_account_ids: dict[str, set[str]] = defaultdict(set)
    all_account_ids: set[str] = set()
    for row in personal_accounts:
        real_name = (row.get("user_name") or "").strip()
        if not real_name:
            continue

        accounts = row.get("accounts") or []
        for account_id in accounts:
            normalized_id = _normalize_account_id(account_id["id"])
            if not normalized_id:
                continue
            real_name_to_account_ids[real_name].add(normalized_id)
            all_account_ids.add(normalized_id)

    if not all_account_ids:
        logging.info("未查询到启用的 Facebook 账户，跳过通知")
        return

    channel_text_by_account_id = _build_channel_text_by_account_id()
    fb_accounts = mongo_client["fb_ad_accounts"].find(
        {
            "_id": {"$in": list(all_account_ids)},
            "account_status": {"$in": [3, 9]},
            # "updated_at": {"$gte": today_start, "$lt": tomorrow_start},
        },
        projection={"_id": 1, "name": 1},
    )
    abnormal_account_map = {
        _normalize_account_id(row.get("_id")): {
            "id": _normalize_account_id(row.get("_id")),
            "name": (row.get("name") or "").strip(),
            "channel_text": channel_text_by_account_id.get(
                _normalize_account_id(row.get("_id")), "未知渠道"
            ),
        }
        for row in fb_accounts
        if row.get("_id") is not None
    }

    china_timezone = ZoneInfo("Asia/Shanghai")
    now = datetime.now(china_timezone)
    grouped_accounts: dict[str, list[dict[str, str]]] = defaultdict(list)
    current_abnormal_account_ids = set(abnormal_account_map)
    sent_abnormal_account_ids = _normalize_redis_members(
        redis_cli.smembers(ACCOUNT_ALERT_SET_KEY)
    )
    recovered_account_ids = sent_abnormal_account_ids - current_abnormal_account_ids
    if recovered_account_ids:
        redis_cli.srem(ACCOUNT_ALERT_SET_KEY, *recovered_account_ids)
        sent_abnormal_account_ids -= recovered_account_ids
    _ensure_account_alert_set_ttl(now)
    pending_account_ids = current_abnormal_account_ids - sent_abnormal_account_ids

    for account_id in sorted(pending_account_ids):
        abnormal_account = abnormal_account_map.get(account_id)
        if not abnormal_account:
            continue

        owners = [
            real_name
            for real_name, account_ids in real_name_to_account_ids.items()
            if account_id in account_ids
        ]
        if not owners:
            continue

        # 多人共有同一账户时只归到名下账户最多的人, 避免重复发送
        owner = max(owners, key=lambda name: (len(real_name_to_account_ids[name]), name))
        grouped_accounts[owner].append(abnormal_account)

    if not grouped_accounts:
        logging.info("Facebook 账户未发现可发送的 status=3 异常数据")
        return

    chat_id = PAY_ERROR_CHAT_ID if env == Env.PROD else PAY_ERROR_TEST_CHAT_ID
    send_feishu_card(build_tech_fb_account_status_card(grouped_accounts), chat_id)
    redis_cli.sadd(ACCOUNT_ALERT_SET_KEY, *pending_account_ids)
    _ensure_account_alert_set_ttl(now)


if __name__ == "__main__":
    init("check ad status to tg")
    check_tech_department_fb_account_status()
