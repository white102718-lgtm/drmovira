import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import mongo_client, mongo_client_user, redis_cli
from utils.feishu import send_feishu_bot_webhook

# 群机器人 webhook 地址(待补:把飞书群机器人的 webhook URL 填这里)
PIXEL_ALERT_WEBHOOK = "https://open.larksuite.com/open-apis/bot/v2/hook/eba43d00-5b3a-4ed9-a850-fbb0b75bb018"
# 机器人「签名校验」密钥(待补:把飞书机器人安全设置里的签名密钥填这里)
PIXEL_ALERT_SECRET = "REDACTED_REFERENCE_SECRET"

DEPARTMENT = "技术部"
PIXEL_ALERT_SET_KEY = "feishu:check_ad_status:fb_pixel_alert"


def _build_message(grouped_pixels: dict[str, list[dict[str, str]]]) -> str:
    total = sum(len(pixels) for pixels in grouped_pixels.values())
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    blocks = [f"Facebook 像素状态异常通知\n像素不可用 · 共 {total} 个\n时间：{now_cn}"]
    for optimizer in sorted(grouped_pixels):
        pixels = grouped_pixels[optimizer]
        if not pixels:
            continue
        lines = [f"【{optimizer}】"]
        for pixel in sorted(pixels, key=lambda p: (p["agent_line"], p["pixel_name"])):
            lines.append(
                f'{pixel["agent_line"]}　{pixel["pixel_name"]}　{pixel["pixel_id"]}'
            )
        blocks.append("\n".join(lines))
    return "\n\n━━━━━━━━━━━━━━\n\n".join(blocks)


def _normalize_redis_members(members) -> set[str]:
    normalized_members = set()
    for member in members:
        if isinstance(member, bytes):
            member = member.decode()
        member = str(member).strip()
        if member:
            normalized_members.add(member)
    return normalized_members


def _is_active_tech_optimizer(real_name: str) -> bool:
    """优化师属技术部且账号启用(user.status: 1=启用, 0=停用)。"""
    user_doc = mongo_client_user["user"].find_one(
        {"$or": [{"real_name": real_name}, {"full_name": real_name}]},
        {"department": 1, "status": 1},
    )
    if not user_doc:
        return False
    return user_doc.get("department") == DEPARTMENT and user_doc.get("status") != 0


def _load_tech_agent_line_rows() -> list[dict[str, str]]:
    """技术部项目下、优化师属技术部且账号启用的启用代理线, 带 pixel_name。"""
    platform_rows = mongo_client["platform_config"].find(
        {
            "$or": [{"internal_team": DEPARTMENT}, {"external_team": DEPARTMENT}],
            "enabled": {"$ne": False},
        },
        projection={"agent_lines": 1},
    )
    agent_line_names = {
        line for row in platform_rows for line in row.get("agent_lines") or [] if line
    }
    if not agent_line_names:
        return []

    agent_line_rows = mongo_client["agent_line_config"].find(
        {
            "_id": {"$in": list(agent_line_names)},
            "enabled": {"$ne": False},
            "pixel_name": {"$nin": [None, ""]},
        },
        projection={"optimizer": 1, "pixel_name": 1},
    )
    active_tech_by_optimizer: dict[str, bool] = {}
    rows = []
    for row in agent_line_rows:
        optimizer = (row.get("optimizer") or "").strip()
        pixel_name = (row.get("pixel_name") or "").strip()
        if not optimizer or not pixel_name:
            continue
        if optimizer not in active_tech_by_optimizer:
            active_tech_by_optimizer[optimizer] = _is_active_tech_optimizer(optimizer)
        if not active_tech_by_optimizer[optimizer]:
            continue
        rows.append(
            {"agent_line": row["_id"], "optimizer": optimizer, "pixel_name": pixel_name}
        )
    return rows


def check_tech_department_pixel_status() -> None:
    agent_line_rows = _load_tech_agent_line_rows()
    if not agent_line_rows:
        logging.info("未查询到技术部代理线的像素配置，跳过通知")
        return

    pixel_names = {row["pixel_name"] for row in agent_line_rows}
    matched_pixels = mongo_client["fb_pixels"].find(
        {"name": {"$in": list(pixel_names)}},
        projection={"_id": 1, "name": 1, "is_unavailable": 1},
    )
    pixels_by_name: dict[str, list[dict]] = defaultdict(list)
    for row in matched_pixels:
        name = (row.get("name") or "").strip()
        if name:
            pixels_by_name[name].append(row)

    # 同名匹配到多个像素说明 pixel_name 是脏配置(如 "1"), 按名匹配不可信, 跳过
    pixel_ids_by_name: dict[str, str] = {}
    for name, pixels in pixels_by_name.items():
        if len(pixels) > 1:
            logging.warning(
                "像素名 %s 在 fb_pixels 匹配到 %s 个像素, 视为脏配置跳过",
                name,
                len(pixels),
            )
            continue
        if pixels[0].get("is_unavailable") is True:
            pixel_ids_by_name[name] = str(pixels[0]["_id"])

    if not pixel_ids_by_name:
        logging.info("技术部代理线像素未发现 is_unavailable=true 的异常数据")
        return

    sent_pixel_names = _normalize_redis_members(redis_cli.smembers(PIXEL_ALERT_SET_KEY))
    pending_pixel_names = set(pixel_ids_by_name) - sent_pixel_names
    if not pending_pixel_names:
        logging.info("异常像素当天均已推送过，跳过通知")
        return

    grouped_pixels: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in agent_line_rows:
        if row["pixel_name"] not in pending_pixel_names:
            continue
        grouped_pixels[row["optimizer"]].append(
            {
                "agent_line": row["agent_line"],
                "pixel_name": row["pixel_name"],
                "pixel_id": pixel_ids_by_name[row["pixel_name"]],
            }
        )

    if not PIXEL_ALERT_WEBHOOK:
        logging.warning("PIXEL_ALERT_WEBHOOK 未配置，跳过像素异常通知")
        return
    message = _build_message(grouped_pixels)
    send_feishu_bot_webhook(PIXEL_ALERT_WEBHOOK, message, PIXEL_ALERT_SECRET)
    redis_cli.sadd(PIXEL_ALERT_SET_KEY, *pending_pixel_names)
    logging.info("像素异常通知：已发送\n%s", message)


if __name__ == "__main__":
    init("check pixel status to feishu")
    check_tech_department_pixel_status()
