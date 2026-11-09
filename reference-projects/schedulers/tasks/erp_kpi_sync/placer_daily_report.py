# -*- coding:utf-8 -*-
"""投手日报: 指定日期的数据按投手拆成 Excel，通过飞书应用推给投手本人。"""
import logging
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from db.clients import mongo_client_user, mysql_client
from utils.feishu import get_feishu_open_ids_by_mobiles, send_feishu_file


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
FEISHU_APP_ID = "cli_aab8e929373cdbfc"
FEISHU_APP_SECRET = "REDACTED_REFERENCE_SECRET"

HEADERS = (
    "日期", "渠道号", "平台", "帐户类型", "账户ID", "日报消耗", "展示", "点击",
    "账户内安装", "账户内注册", "账户内首充", "账户内首充", "ROAS", "注册量",
    "首充人数", "注册成本", "首充成本", "后台注册成本", "后台首充成本", "调整金额",
    "含回流消耗", "实际消耗(自动)", "备注", "姓名辅助列", "项目名称",
)
METRIC_COLUMNS = (
    "placer_id", "game_platform", "agent_line", "account_id", "ad_platform",
    "amount_spent", "impressions", "clicks", "app_installs", "registrations",
    "first_recharges", "first_recharge_value", "registrations_1d", "first_recharges_1d",
)


def _report_date(now: datetime, days_ago: int = 1) -> str:
    """按北京时间计算 T-N 日期，用于查询账户时区的对应日报。"""
    return (now.astimezone(CHINA_TIMEZONE).date() - timedelta(days=days_ago)).isoformat()


def _fetch_metrics(report_date: str) -> list[dict]:
    """按 账户 × 项目 × 代理线 聚合指定日期的 ad 层数据。

    只能用 level='ad': URL 匹配的代理线只回填 ad 行(match_agent_line_daily),
    改用 campaign 层会漏掉靠 URL 匹配上的那部分消耗。
    """
    sql = f"""
SELECT
    placer_id,
    game_platform,
    agent_line,
    account_id,
    ad_platform,
    ROUND(SUM(amount_spent), 2)    AS amount_spent,
    SUM(impressions)               AS impressions,
    SUM(clicks_all)                AS clicks,
    SUM(app_installs)              AS app_installs,
    SUM(complete_registration)     AS registrations,
    SUM(purchases)                 AS first_recharges,
    ROUND(SUM(purchases_value), 2) AS first_recharge_value,
    SUM(register_1dclick)          AS registrations_1d,
    SUM(purchases_1dclick)         AS first_recharges_1d
FROM ad_daily_detail
WHERE date = '{report_date}'
  AND level = 'ad'
  AND placer_id IS NOT NULL AND placer_id <> ''
  AND agent_line IS NOT NULL AND agent_line <> ''
  AND game_platform IS NOT NULL AND game_platform <> ''
GROUP BY placer_id, game_platform, agent_line, account_id, ad_platform
ORDER BY placer_id ASC, game_platform ASC, amount_spent DESC
"""
    return [dict(zip(METRIC_COLUMNS, raw)) for raw in mysql_client.read(sql)]


def _fetch_channel_map(account_ids: set[str]) -> dict[str, str]:
    """account_id -> 渠道名。一个户挂多个渠道时取 id 最小的那个。

    account_ids_json 在 Doris 侧展开: 整表 JSON 拉回本地解析要 150s+，展开后只回需要的行。
    """
    if not account_ids:
        return {}
    in_clause = ", ".join("'" + str(a).replace("'", "") + "'" for a in account_ids)
    sql = f"""
SELECT
    get_json_string(item, '$.account_id') AS account_id,
    c.channel_name
FROM fb_ad_channel c
LATERAL VIEW explode_json_array_json(c.account_ids_json) t AS item
WHERE get_json_string(item, '$.account_id') IN ({in_clause})
ORDER BY c.id ASC
"""
    channel_map: dict[str, str] = {}
    for account_id, channel_name in mysql_client.read(sql):
        account_id = str(account_id or "").replace("act_", "")
        if account_id and account_id not in channel_map:
            channel_map[account_id] = channel_name or ""
    return channel_map


def _fetch_placer_profiles(real_names: list[str]) -> dict[str, dict]:
    """placer_id(real_name) -> {_id, full_name, mobile, feishu_id}。"""
    docs = mongo_client_user["user"].find(
        {"real_name": {"$in": real_names}},
        {"real_name": 1, "full_name": 1, "username": 1, "phone": 1, "feishu_id": 1},
    )
    return {
        doc["real_name"]: {
            "_id": doc["_id"],
            "full_name": doc.get("full_name") or doc["real_name"],
            "mobile": str(doc.get("phone") or doc.get("username") or ""),
            "feishu_id": doc.get("feishu_id") or "",
        }
        for doc in docs
    }


def _resolve_open_ids(profiles: dict[str, dict]) -> dict[str, str]:
    """placer_id -> open_id。user.feishu_id 命中即用，否则按手机号查一次并回写。"""
    open_ids = {
        placer_id: profile["feishu_id"]
        for placer_id, profile in profiles.items()
        if profile["feishu_id"]
    }
    pending = {
        placer_id: profile
        for placer_id, profile in profiles.items()
        if placer_id not in open_ids and profile["mobile"]
    }
    if not pending:
        return open_ids

    open_id_by_mobile = get_feishu_open_ids_by_mobiles(
        [profile["mobile"] for profile in pending.values()],
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
    )
    for placer_id, profile in pending.items():
        open_id = open_id_by_mobile.get(profile["mobile"])
        if not open_id:
            continue
        open_ids[placer_id] = open_id
        mongo_client_user["user"].update_one(
            {"_id": profile["_id"]}, {"$set": {"feishu_id": open_id}}
        )
    return open_ids


def _num(value, default=0):
    return default if value is None else value


def _cost(spend, count):
    """成本 = 消耗 / 转化数，转化数为 0 时留空。"""
    count = _num(count)
    return round(float(_num(spend, 0.0)) / count, 2) if count else ""


def _build_workbook(
    report_date: str,
    rows: list[dict],
    full_name: str,
    channel_map: dict[str, str],
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "日报"
    sheet.append(list(HEADERS))
    for index, row in enumerate(rows, start=2):
        spend = float(_num(row["amount_spent"], 0.0))
        first_recharge_value = float(_num(row["first_recharge_value"], 0.0))
        sheet.append([
            report_date,
            row["agent_line"],  # 渠道号列写代理线
            row["ad_platform"] or "",
            channel_map.get(str(row["account_id"]), ""),  # 帐户类型列写渠道名
            str(row["account_id"]),
            spend,
            _num(row["impressions"]),
            _num(row["clicks"]),
            _num(row["app_installs"]),
            _num(row["registrations"]),
            _num(row["first_recharges"]),
            first_recharge_value,
            round(first_recharge_value / spend, 4) if spend else "",
            _num(row["registrations_1d"]),
            _num(row["first_recharges_1d"]),
            _cost(spend, row["registrations_1d"]),
            _cost(spend, row["first_recharges_1d"]),
            "",  # 后台注册成本
            "",  # 后台首充成本
            "",  # 调整金额
            spend,  # 含回流消耗
            f"=U{index}+T{index}",  # 实际消耗(自动)
            "",  # 备注
            full_name,
            row["game_platform"],
        ])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def push_placer_daily_report(
    report_date: str | None = None,
    *,
    days_ago: int = 1,
    output_dir: str = "",
) -> None:
    """生成并推送投手日报 Excel。

    未指定 report_date 时按北京时间取 T-days_ago，默认 T-1；
    days_ago > 1 时文件名标注对应的回流版本。
    output_dir 非空时只落盘不推送，用于本地核对。
    """
    report_date = report_date or _report_date(datetime.now(CHINA_TIMEZONE), days_ago)
    rows = _fetch_metrics(report_date)
    if not rows:
        logging.warning("投手日报无数据: report_date=%s", report_date)
        return

    channel_map = _fetch_channel_map({str(row["account_id"]) for row in rows})
    rows_by_placer: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_placer.setdefault(row["placer_id"], []).append(row)

    profiles = _fetch_placer_profiles(list(rows_by_placer))
    missing_profiles = [name for name in rows_by_placer if name not in profiles]
    if missing_profiles:
        logging.warning("投手日报: 查不到用户档案，跳过 %s", missing_profiles)

    open_ids = {} if output_dir else _resolve_open_ids(profiles)

    sent = failed = 0
    for placer_id, placer_rows in rows_by_placer.items():
        profile = profiles.get(placer_id)
        if not profile:
            failed += 1
            continue
        full_name = profile["full_name"]
        report_suffix = f"_T-{days_ago}回流" if days_ago > 1 else ""
        file_name = f"{report_date}_{full_name}_日报{report_suffix}.xlsx"
        content = _build_workbook(report_date, placer_rows, full_name, channel_map)

        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            Path(output_dir, file_name).write_bytes(content)
            sent += 1
            continue

        open_id = open_ids.get(placer_id)
        if not open_id:
            logging.warning(
                "投手日报: 拿不到飞书 open_id，跳过 placer_id=%s mobile=%s",
                placer_id, profile["mobile"],
            )
            failed += 1
            continue
        if send_feishu_file(
            content,
            file_name,
            open_id,
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
        ):
            sent += 1
        else:
            failed += 1

    logging.info(
        "投手日报完成: report_date=%s, 数据行=%s, 投手=%s, 成功=%s, 失败=%s",
        report_date, len(rows), len(rows_by_placer), sent, failed,
    )


if __name__ == "__main__":
    from conf.log_conf import init

    init("placer_daily_report")
    push_placer_daily_report(output_dir="/tmp/placer_daily_report")
