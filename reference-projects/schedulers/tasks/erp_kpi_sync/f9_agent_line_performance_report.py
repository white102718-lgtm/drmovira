# -*- coding:utf-8 -*-
"""指定项目按代理线汇总的多时段成效推送。"""
import logging
from datetime import datetime, time, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from db.clients import mysql_client
from utils.feishu import send_feishu_image


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
UTC_MINUS_3 = timezone(timedelta(hours=-3))
GAME_PLATFORMS = ("456M", "bonu1", )
TITLE_MAP = {
    "456M": "456M",
    "bonu1": "bonu1", 
}
GAME_PLATFORM_SQL = ", ".join(f"'{game_platform}'" for game_platform in GAME_PLATFORMS)
SCHEDULE_HOURS = (0, 3, 6, 9, 12, 15, 18, 21)
PERIOD_KEYS = ("current", "previous", "yesterday_current", "yesterday_previous")
FEISHU_APP_ID = "cli_aaf72a7c1c79dce4"
FEISHU_APP_SECRET = "REDACTED_REFERENCE_SECRET"
FEISHU_CHAT_ID = "oc_0426fec0a3bba265029228c739c78e89"
FEISHU_TEST_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/056ccb13-3520-4b60-9acb-0ccb5a158243"
FEISHU_TEST_WEBHOOK_SECRET = "REDACTED_REFERENCE_SECRET"

IMAGE_WIDTH = 3530
IMAGE_MARGIN = 60
TITLE_HEIGHT = 160
CHART_HEIGHT = 480
CHART_GAP = 24
SECTION_TITLE_HEIGHT = 74
GROUP_HEADER_HEIGHT = 58
METRIC_HEADER_HEIGHT = 74
ROW_HEIGHT = 64
AGENT_LINE_WIDTH = 390
METRIC_COLUMNS = (
    ("消耗", "amount_spent", 180),
    ("注册人数\n（面板）", "registrations", 142),
    ("首充人数\n（面板）", "first_recharge_users", 142),
    ("注册成本\n（面板）", "registration_cost", 142),
    ("首充成本\n（面板）", "first_recharge_cost", 142),
)

PERIOD_STYLES = {
    "current": {"name": "当前时段", "color": "#135FE5", "soft_color": "#EDF4FF"},
    "previous": {"name": "上一个时段", "color": "#0B9A46", "soft_color": "#EDF9F0"},
    "yesterday_current": {"name": "昨日同时段", "color": "#6431C8", "soft_color": "#F5F0FF"},
    "yesterday_previous": {"name": "昨日上个时段", "color": "#EA6500", "soft_color": "#FFF4E9"},
}
CHART_PERIOD_LABELS = {
    "current": "当前时段",
    "previous": "上个时段",
    "yesterday_current": "昨日同时段",
}
TREND_STYLES = {
    "today": {"name": "今日", "color": "#1769F2"},
    "yesterday": {"name": "昨日", "color": "#E5A300"},
}
GRID_COLOR = "#D9E2F0"
TEXT_COLOR = "#17233F"
MUTED_TEXT_COLOR = "#60708A"
_REGULAR_FONT_PATHS = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path.home() / "Library/Fonts/NotoSansCJKsc-Regular.otf",
    Path(r"C:\Windows\Fonts\msyh.ttc"),
)
_BOLD_FONT_PATHS = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path.home() / "Library/Fonts/NotoSansCJKsc-Bold.otf",
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
)


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _BOLD_FONT_PATHS if bold else _REGULAR_FONT_PATHS:
        if path.exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("未找到中文字体，无法生成飞书成效图片")


def _current_schedule_slot(now: datetime) -> datetime:
    """返回当前时刻对应的最近一个北京时间计划节点。"""
    current = now.astimezone(CHINA_TIMEZONE).replace(minute=0, second=0, microsecond=0)
    for schedule_hour in reversed(SCHEDULE_HOURS):
        if schedule_hour <= current.hour:
            return current.replace(hour=schedule_hour)
    return (current - timedelta(days=1)).replace(hour=SCHEDULE_HOURS[-1])


def _previous_schedule_slot(now: datetime) -> datetime:
    """返回当前小时前最近一个北京时间调度节点，支持任意时点调试。"""
    current = now.astimezone(CHINA_TIMEZONE).replace(minute=0, second=0, microsecond=0)
    for schedule_hour in reversed(SCHEDULE_HOURS):
        if schedule_hour < current.hour:
            return current.replace(hour=schedule_hour)
    return (current - timedelta(days=1)).replace(hour=SCHEDULE_HOURS[-1])


def _brazil_day_start(brazil_day) -> datetime:
    """巴西 UTC-3 报表日从 01:00 开始，对应的北京时间。"""
    return datetime.combine(brazil_day, time(hour=1), tzinfo=UTC_MINUS_3).astimezone(
        CHINA_TIMEZONE
    )


def _make_snapshot(
    key: str,
    slot: datetime,
    *,
    full_day: bool,
) -> dict:
    """构造一个报表快照的小时明细累计窗口。"""
    slot = slot.astimezone(CHINA_TIMEZONE).replace(minute=0, second=0, microsecond=0)
    brazil_day = slot.astimezone(UTC_MINUS_3).date()
    if full_day:
        # 北京时间 12:00 是 UTC-3 的 01:00，复核其刚结束的前一个巴西自然日。
        brazil_day -= timedelta(days=1)
        # 排他结束位置为 12:00，故会保留最后一个 11:00 小时快照。
        window_end = datetime.combine(
            brazil_day + timedelta(days=1), time.min, tzinfo=UTC_MINUS_3
        ).astimezone(CHINA_TIMEZONE) + timedelta(hours=1)
    elif slot.hour == 12:
        # 供 15 点等后续时报引用的“12 点时点数据”：新巴西日的首个小时快照，
        # 与 12 点推送的上一巴西日全天复核不同。
        window_end = slot + timedelta(hours=1)
    else:
        # 普通整点报只使用执行时已经完成的小时；例如 09:00 报取到 08:00 快照。
        window_end = slot

    if key == "current":
        detail = "昨日全天" if full_day else f"{slot.hour}点"
    elif key == "previous":
        detail = f"{slot.hour}点"
    elif key == "yesterday_current":
        detail = "前日全天" if full_day else f"昨日{slot.hour}点"
    else:
        detail = f"昨日{slot.hour}点"

    return {
        "key": key,
        "slot": slot,
        "full_day": full_day,
        "report_date": brazil_day,
        "window_start": _brazil_day_start(brazil_day),
        # SQL 使用左闭右开区间。
        "window_end": window_end,
        "detail": detail,
        "group_title": f"{PERIOD_STYLES[key]['name']}（{detail}）",
        "chart_label": detail,
    }


def _build_period_specs(now: datetime) -> list[dict]:
    """生成当前、上个、昨日同节点、昨日上个节点四组累计快照。"""
    current_slot = _current_schedule_slot(now)
    previous_slot = _previous_schedule_slot(current_slot)
    is_full_day_review = current_slot.hour == 12
    return [
        _make_snapshot("current", current_slot, full_day=is_full_day_review),
        _make_snapshot("previous", previous_slot, full_day=False),
        _make_snapshot(
            "yesterday_current", current_slot - timedelta(days=1), full_day=is_full_day_review
        ),
        _make_snapshot("yesterday_previous", previous_slot - timedelta(days=1), full_day=False),
    ]


def _resolve_report_date(now: datetime) -> str:
    """兼容旧调用：返回当前展示时段对应的巴西报表日。"""
    return _build_period_specs(now)[0]["report_date"].isoformat()


def _new_metrics(amount_spent=0, registrations=0, first_recharge_users=0) -> dict:
    amount_spent = float(amount_spent or 0)
    registrations = int(registrations or 0)
    first_recharge_users = int(first_recharge_users or 0)
    return {
        "amount_spent": amount_spent,
        "registrations": registrations,
        "first_recharge_users": first_recharge_users,
        "registration_cost": amount_spent / registrations if registrations else None,
        "first_recharge_cost": amount_spent / first_recharge_users if first_recharge_users else None,
    }


def _empty_periods() -> dict:
    return {key: _new_metrics() for key in PERIOD_KEYS}


def _fetch_agent_line_period_metrics(periods: list[dict]) -> list[dict]:
    """取各时段每条广告的最新累计快照，再按代理线汇总。"""
    period_sql = []
    for period in periods:
        start = period["window_start"].strftime("%Y-%m-%d %H:%M:%S")
        end = period["window_end"].strftime("%Y-%m-%d %H:%M:%S")
        period_sql.append(
            "SELECT "
            f"'{period['key']}' AS period_key, "
            f"CAST('{start}' AS DATETIME) AS window_start, "
            f"CAST('{end}' AS DATETIME) AS window_end"
        )

    sql = f"""
WITH periods AS (
    {' UNION ALL '.join(period_sql)}
), target_ads AS (
    SELECT
        p.period_key,
        d.game_platform,
        CASE
            WHEN d.agent_line IS NULL OR d.agent_line = '' THEN '未匹配代理线'
            ELSE d.agent_line
        END AS agent_line,
        COALESCE(d.amount_spent, 0) AS amount_spent,
        COALESCE(d.complete_registration, 0) AS registrations,
        COALESCE(d.purchases, 0) AS first_recharge_users,
        ROW_NUMBER() OVER (
            PARTITION BY
                p.period_key,
                d.ad_platform,
                d.timezone_name,
                d.account_id,
                d.campaign_id,
                d.ad_set_id,
                d.ad_id
            ORDER BY d.china_date DESC, d.date DESC
        ) AS snapshot_rank
    FROM periods p
    JOIN ad_hourly_detail d
      ON d.china_date >= p.window_start
     AND d.china_date < p.window_end
    WHERE d.level = 'ad'
      AND d.game_platform IN ({GAME_PLATFORM_SQL})
)
SELECT
    period_key,
    game_platform,
    agent_line,
    ROUND(SUM(amount_spent), 2) AS amount_spent,
    SUM(registrations) AS registrations,
    SUM(first_recharge_users) AS first_recharge_users
FROM target_ads
WHERE snapshot_rank = 1
GROUP BY period_key, game_platform, agent_line
ORDER BY game_platform ASC, agent_line ASC, period_key ASC
"""
    columns = (
        "period_key",
        "game_platform",
        "agent_line",
        "amount_spent",
        "registrations",
        "first_recharge_users",
    )
    by_agent: dict[tuple[str, str], dict] = {}
    for raw in mysql_client.read(sql):
        row = dict(zip(columns, raw))
        key = (str(row["game_platform"]), str(row["agent_line"]))
        record = by_agent.setdefault(
            key,
            {
                "game_platform": key[0],
                "agent_line": key[1],
                "periods": _empty_periods(),
            },
        )
        record["periods"][row["period_key"]] = _new_metrics(
            row["amount_spent"], row["registrations"], row["first_recharge_users"]
        )

    rows = list(by_agent.values())
    rows.sort(
        key=lambda row: (
            -row["periods"]["current"]["amount_spent"],
            row["agent_line"],
        )
    )
    return rows


def _brazil_time_to_china(brazil_day, hour: int) -> datetime:
    """将巴西 UTC-3 的整点转换为北京时间。hour 可以为 24。"""
    brazil_time = datetime.combine(brazil_day, time.min, tzinfo=UTC_MINUS_3) + timedelta(
        hours=hour
    )
    return brazil_time.astimezone(CHINA_TIMEZONE)


def _build_chart_snapshot_specs(now: datetime) -> dict:
    """生成顶部图表的巴西整点累计快照规格。

    明细表沿用四时段口径；趋势图则固定按巴西时间每三小时展示。
    任务在北京时间 :30 触发，只查询已完成的整点数据。
    """
    slot = _current_schedule_slot(now)
    brazil_now = slot.astimezone(UTC_MINUS_3)
    is_full_day_review = slot.hour == 12
    brazil_day = brazil_now.date() - timedelta(days=1) if is_full_day_review else brazil_now.date()

    if is_full_day_review:
        # 全天图以 24:00 这一最终累计快照收口。
        end_hour = 24
    else:
        # 例如北京时间 03:30 = 巴西 16:30，图表最后固定展示 15:00。
        end_hour = max(0, (brazil_now.hour - 1) // 3 * 3)

    axis_hours = list(range(0, 25, 3))
    line_hours = [hour for hour in axis_hours if hour <= end_hour]
    speed_start_hour = max(0, end_hour - 3)
    # 第三张图需要连续四个整点累计值，计算最近三个完整小时的小时消耗。
    speed_hours = list(range(speed_start_hour, end_hour + 1))
    # 广告平台在巴西 00:00 对应的小时记录仍可能保留前一广告日累计，
    # 图表将 00:00 作为当天累计的零基线，不查询该污染边界点。
    query_hours = sorted(hour for hour in set(line_hours + speed_hours) if hour > 0)
    points = []
    for series_key, day in (
        ("today", brazil_day),
        ("yesterday", brazil_day - timedelta(days=1)),
    ):
        # 统计口径与下方明细表保持一致：巴西报表日从 01:00 开始。
        # 图上的 00:00 仅作零基线展示，不参与数据库取数。
        day_start = _brazil_day_start(day)
        for hour in query_hours:
            points.append(
                {
                    "series_key": series_key,
                    "brazil_hour": hour,
                    "window_start": day_start,
                    "snapshot_at": _brazil_time_to_china(day, hour),
                }
            )
    return {
        "brazil_day": brazil_day,
        "axis_hours": axis_hours,
        "line_hours": line_hours,
        "speed_start_hour": speed_start_hour,
        "speed_end_hour": end_hour,
        "points": points,
    }


def _fetch_project_chart_metrics(
    chart_specs: dict,
    included_agent_lines: dict[str, set[str]] | None = None,
) -> dict:
    """取项目在每个巴西整点的广告累计快照，用于顶部图表。"""
    point_sql = []
    for point in chart_specs["points"]:
        start = point["window_start"].strftime("%Y-%m-%d %H:%M:%S")
        snapshot_at = point["snapshot_at"].strftime("%Y-%m-%d %H:%M:%S")
        point_sql.append(
            "SELECT "
            f"'{point['series_key']}' AS series_key, "
            f"{point['brazil_hour']} AS brazil_hour, "
            f"CAST('{start}' AS DATETIME) AS window_start, "
            f"CAST('{snapshot_at}' AS DATETIME) AS snapshot_at"
        )

    sql = f"""
WITH chart_points AS (
    {' UNION ALL '.join(point_sql)}
), target_ads AS (
    SELECT
        p.series_key,
        p.brazil_hour,
        d.game_platform,
        CASE
            WHEN d.agent_line IS NULL OR d.agent_line = '' THEN '未匹配代理线'
            ELSE d.agent_line
        END AS agent_line,
        COALESCE(d.amount_spent, 0) AS amount_spent,
        COALESCE(d.complete_registration, 0) AS registrations,
        COALESCE(d.purchases, 0) AS first_recharge_users,
        ROW_NUMBER() OVER (
            PARTITION BY
                p.series_key,
                p.brazil_hour,
                d.ad_platform,
                d.timezone_name,
                d.account_id,
                d.campaign_id,
                d.ad_set_id,
                d.ad_id
            ORDER BY d.china_date DESC, d.date DESC
        ) AS snapshot_rank
    FROM chart_points p
    JOIN ad_hourly_detail d
      ON d.china_date >= p.window_start
     AND d.china_date <= p.snapshot_at
    WHERE d.level = 'ad'
      AND d.game_platform IN ({GAME_PLATFORM_SQL})
)
SELECT
    series_key,
    brazil_hour,
    game_platform,
    agent_line,
    ROUND(SUM(amount_spent), 2) AS amount_spent,
    SUM(registrations) AS registrations,
    SUM(first_recharge_users) AS first_recharge_users
FROM target_ads
WHERE snapshot_rank = 1
GROUP BY series_key, brazil_hour, game_platform, agent_line
ORDER BY game_platform ASC, series_key ASC, brazil_hour ASC, agent_line ASC
"""
    metrics = {
        game_platform: {
            series_key: {hour: _new_metrics() for hour in range(25)}
            for series_key in TREND_STYLES
        }
        for game_platform in GAME_PLATFORMS
    }
    columns = (
        "series_key",
        "brazil_hour",
        "game_platform",
        "agent_line",
        "amount_spent",
        "registrations",
        "first_recharge_users",
    )
    for raw in mysql_client.read(sql):
        row = dict(zip(columns, raw))
        game_platform = str(row["game_platform"])
        if game_platform not in metrics:
            continue
        agent_line = str(row["agent_line"])
        if (
            included_agent_lines is not None
            and agent_line not in included_agent_lines.get(game_platform, set())
        ):
            continue
        point_metrics = metrics[game_platform][str(row["series_key"])][int(row["brazil_hour"])]
        metrics[game_platform][str(row["series_key"])][int(row["brazil_hour"])] = _new_metrics(
            point_metrics["amount_spent"] + row["amount_spent"],
            point_metrics["registrations"] + row["registrations"],
            point_metrics["first_recharge_users"] + row["first_recharge_users"],
        )
    return metrics


def _has_performance(row: dict) -> bool:
    """当前时段消耗、注册、首充全为 0 的代理线不展示。"""
    current = row["periods"]["current"]
    return bool(
        current["amount_spent"]
        or current["registrations"]
        or current["first_recharge_users"]
    )


def _build_summary_metrics(rows: Iterable[dict], period_key: str) -> dict:
    amount_spent = 0.0
    registrations = 0
    first_recharge_users = 0
    for row in rows:
        metrics = row["periods"][period_key]
        amount_spent += metrics["amount_spent"]
        registrations += metrics["registrations"]
        first_recharge_users += metrics["first_recharge_users"]
    return _new_metrics(amount_spent, registrations, first_recharge_users)


def _format_amount(value) -> str:
    return f"{float(value or 0):,.2f}"


def _format_chart_amount(value) -> str:
    """趋势图横轴下方使用紧凑金额，避免全天九个点的数值重叠。"""
    amount = float(value or 0)
    if abs(amount) >= 1000:
        return f"{amount / 1000:,.1f}k"
    return f"{amount:.2f}"


def _format_cost(value) -> str:
    return "-" if value is None else _format_amount(value)


def _format_metric(metrics: dict, field: str) -> str:
    if field == "amount_spent":
        return _format_amount(metrics[field])
    if field in {"registrations", "first_recharge_users"}:
        return f"{int(metrics[field] or 0):,}"
    return _format_cost(metrics[field])


def _truncate_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "..."
    while text and draw.textlength(text + suffix, font=font) > max_width:
        text = text[:-1]
    return text + suffix


def _draw_cell(
    draw: ImageDraw.ImageDraw,
    text: str,
    left: int,
    top: int,
    width: int,
    height: int,
    font,
    align: str = "center",
    color: str = TEXT_COLOR,
) -> None:
    lines = [_truncate_text(draw, line, font, width - 20) for line in str(text).split("\n")]
    text = "\n".join(lines)
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=3, align=align)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    if align == "left":
        x = left + 12
    elif align == "right":
        x = left + width - 12 - text_width
    else:
        x = left + (width - text_width) / 2
    y = top + (height - text_height) / 2 - box[1]
    draw.multiline_text((x, y), text, font=font, fill=color, spacing=3, align=align)


def _draw_icon(draw: ImageDraw.ImageDraw, center: tuple[int, int], kind: str, color: str, font) -> None:
    cx, cy = center
    radius = 28
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
    if kind == "cost":
        symbol = "¥"
        box = draw.textbbox((0, 0), symbol, font=font)
        draw.text(
            (cx - (box[2] - box[0]) / 2, cy - (box[3] - box[1]) / 2 - box[1]),
            symbol,
            font=font,
            fill="white",
        )
        return
    if kind == "speed":
        draw.arc((cx - 13, cy - 13, cx + 13, cy + 13), 205, 335, fill="white", width=4)
        draw.line((cx, cy + 4, cx + 13, cy - 9), fill="white", width=4)
        draw.polygon(((cx + 13, cy - 9), (cx + 7, cy - 8), (cx + 12, cy - 2)), fill="white")
        return
    draw.line((cx - 15, cy + 11, cx - 4, cy), fill="white", width=4)
    draw.line((cx - 4, cy, cx + 5, cy + 5), fill="white", width=4)
    draw.line((cx + 5, cy + 5, cx + 16, cy - 12), fill="white", width=4)
    draw.polygon(((cx + 16, cy - 12), (cx + 7, cy - 9), (cx + 13, cy - 3)), fill="white")


def _axis_value(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _spend_growth_rate(current: dict, previous: dict) -> float | None:
    """计算相邻两个节点间的消耗增长率，单位为百分比。"""
    previous_spend = float(previous["amount_spent"] or 0)
    if previous_spend == 0:
        return None
    return (float(current["amount_spent"] or 0) - previous_spend) / previous_spend * 100


def _draw_line_chart(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    points: list[tuple[str, float | None, str]],
    title: str,
    unit: str,
    icon_kind: str,
    icon_color: str,
    annotation: str = "",
    point_value_formatter=None,
) -> None:
    draw.rounded_rectangle(
        (left, top, left + width, top + height), radius=18, fill="white", outline="#D9E5F5", width=2
    )
    title_font = _load_font(31, bold=True)
    unit_font = _load_font(22)
    axis_font = _load_font(20)
    icon_font = _load_font(32, bold=True)
    _draw_icon(draw, (left + 48, top + 50), icon_kind, icon_color, icon_font)
    draw.text((left + 88, top + 29), title, font=title_font, fill=TEXT_COLOR)
    draw.text((left + 30, top + 93), f"单位：{unit}", font=unit_font, fill=MUTED_TEXT_COLOR)
    if annotation:
        annotation_width = draw.textlength(annotation, font=unit_font)
        draw.text(
            (left + width - 30 - annotation_width, top + 93),
            annotation,
            font=unit_font,
            fill=icon_color,
        )

    chart_left = left + 104
    chart_right = left + width - 34
    chart_top = top + 150
    # 为横轴下方的“时间 / 今日值 / 昨日值”三行信息预留空间。
    chart_bottom = top + height - 118
    values = [value for _, value, _ in points if value is not None]
    low = min(0.0, min(values, default=0.0))
    high = max(0.0, max(values, default=0.0))
    if high == low:
        high = low + 1
    else:
        high += (high - low) * 0.12

    for tick in range(5):
        value = low + (high - low) * tick / 4
        y = chart_bottom - (chart_bottom - chart_top) * tick / 4
        draw.line((chart_left, y, chart_right, y), fill="#E8EEF7", width=1)
        label = _axis_value(value)
        label_width = draw.textlength(label, font=axis_font)
        draw.text((chart_left - 18 - label_width, y - 11), label, font=axis_font, fill=MUTED_TEXT_COLOR)

    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill="#9AA8BC", width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill="#9AA8BC", width=2)
    span = chart_right - chart_left
    x_positions = [
        chart_left + span * index / max(len(points) - 1, 1) for index in range(len(points))
    ]
    y_positions = [
        None
        if value is None
        else chart_bottom - (value - low) / (high - low) * (chart_bottom - chart_top)
        for _, value, _ in points
    ]
    valid_segment = []
    for x, y in zip(x_positions, y_positions):
        if y is None:
            if len(valid_segment) > 1:
                draw.line(valid_segment, fill="#246BFF", width=4)
            valid_segment = []
        else:
            valid_segment.append((x, y))
    if len(valid_segment) > 1:
        draw.line(valid_segment, fill="#246BFF", width=4)

    for (label, value, color), x, y in zip(points, x_positions, y_positions):
        if y is not None:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="white", outline=color, width=4)
            if point_value_formatter:
                value_text = point_value_formatter(value)
                value_width = draw.textlength(value_text, font=axis_font)
                draw.text((x - value_width / 2, y - 35), value_text, font=axis_font, fill=color)
        else:
            draw.text((x - 8, chart_bottom - 34), "-", font=axis_font, fill=MUTED_TEXT_COLOR)
        label_box = draw.multiline_textbbox((0, 0), label, font=axis_font, spacing=2, align="center")
        label_width = label_box[2] - label_box[0]
        label_x = min(
            max(chart_left, x - label_width / 2),
            chart_right - label_width,
        )
        draw.multiline_text(
            (label_x, chart_bottom + 17),
            label,
            font=axis_font,
            fill=color,
            spacing=2,
            align="center",
        )


def _draw_trend_chart(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    axis_hours: list[int],
    series: dict[str, list[float | None]],
    title: str,
    unit: str,
    value_formatter,
) -> None:
    """绘制今日、昨日两条巴西整点累计趋势线。"""
    draw.rounded_rectangle(
        (left, top, left + width, top + height), radius=18, fill="white", outline="#D9E5F5", width=2
    )
    title_font = _load_font(31, bold=True)
    unit_font = _load_font(21)
    axis_font = _load_font(20)
    legend_font = _load_font(19)
    icon_font = _load_font(32, bold=True)
    _draw_icon(draw, (left + 48, top + 50), "spend", "#1769F2", icon_font)
    draw.text((left + 88, top + 29), title, font=title_font, fill=TEXT_COLOR)
    draw.text((left + 30, top + 93), f"单位：{unit}", font=unit_font, fill=MUTED_TEXT_COLOR)

    legend_x = left + width - 42
    for series_key in ("yesterday", "today"):
        style = TREND_STYLES[series_key]
        label = style["name"]
        label_width = draw.textlength(label, font=legend_font)
        legend_x -= label_width
        draw.text((legend_x, top + 45), label, font=legend_font, fill=style["color"])
        legend_x -= 38
        draw.line((legend_x, top + 57, legend_x + 25, top + 57), fill=style["color"], width=3)
        draw.ellipse((legend_x + 8, top + 52, legend_x + 16, top + 60), fill="white", outline=style["color"], width=2)
        legend_x -= 25

    chart_left = left + 104
    chart_right = left + width - 34
    chart_top = top + 150
    chart_bottom = top + height - 88
    values = [value for values in series.values() for value in values if value is not None]
    low = min(0.0, min(values, default=0.0))
    high = max(0.0, max(values, default=0.0))
    if high == low:
        high = low + 1
    else:
        high += (high - low) * 0.12

    for tick in range(5):
        value = low + (high - low) * tick / 4
        y = chart_bottom - (chart_bottom - chart_top) * tick / 4
        draw.line((chart_left, y, chart_right, y), fill="#E8EEF7", width=1)
        label = _axis_value(value)
        label_width = draw.textlength(label, font=axis_font)
        draw.text((chart_left - 18 - label_width, y - 11), label, font=axis_font, fill=MUTED_TEXT_COLOR)

    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill="#9AA8BC", width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill="#9AA8BC", width=2)
    span = chart_right - chart_left
    x_positions = [
        chart_left + span * index / max(len(axis_hours) - 1, 1)
        for index in range(len(axis_hours))
    ]

    for series_key in ("today", "yesterday"):
        color = TREND_STYLES[series_key]["color"]
        values_for_series = series[series_key]
        y_positions = [
            None
            if value is None
            else chart_bottom - (value - low) / (high - low) * (chart_bottom - chart_top)
            for value in values_for_series
        ]
        valid_segment = []
        for x, y in zip(x_positions, y_positions):
            if y is None:
                if len(valid_segment) > 1:
                    draw.line(valid_segment, fill=color, width=4)
                valid_segment = []
            else:
                valid_segment.append((x, y))
        if len(valid_segment) > 1:
            draw.line(valid_segment, fill=color, width=4)

        for x, y in zip(x_positions, y_positions):
            if y is None:
                continue
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="white", outline=color, width=4)

    for index, (x, hour) in enumerate(zip(x_positions, axis_hours)):
        label = f"{hour}点"
        label_width = draw.textlength(label, font=axis_font)
        draw.text((x - label_width / 2, chart_bottom + 17), label, font=axis_font, fill=MUTED_TEXT_COLOR)
        for offset, series_key in ((42, "today"), (66, "yesterday")):
            value = series[series_key][index]
            if value is None:
                continue
            value_text = value_formatter(value)
            value_width = draw.textlength(value_text, font=axis_font)
            value_x = min(max(chart_left, x - value_width / 2), chart_right - value_width)
            draw.text(
                (value_x, chart_bottom + offset),
                value_text,
                font=axis_font,
                fill=TREND_STYLES[series_key]["color"],
            )


def _draw_spend_speed_chart(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    hour_start: int,
    hourly_spends: list[float | None],
    comparison_rate: float | None,
) -> None:
    """绘制最近三小时消耗柱状图和较昨日同期速度变化率。"""
    draw.rounded_rectangle(
        (left, top, left + width, top + height), radius=18, fill="white", outline="#D9E5F5", width=2
    )
    title_font = _load_font(31, bold=True)
    unit_font = _load_font(21)
    axis_font = _load_font(20)
    label_font = _load_font(18)
    icon_font = _load_font(32, bold=True)
    _draw_icon(draw, (left + 48, top + 50), "speed", "#6431C8", icon_font)
    draw.text((left + 88, top + 29), "近 3 小时消耗加速", font=title_font, fill=TEXT_COLOR)
    draw.text((left + 30, top + 93), "每小时消耗 US", font=unit_font, fill=TEXT_COLOR)
    end_hour = hour_start + len(hourly_spends)
    comparison_text = (
        f"{hour_start:02d}:00—{end_hour:02d}:00 ｜ 加速度为 {comparison_rate:+.2f}%"
        if comparison_rate is not None
        else f"{hour_start:02d}:00—{end_hour:02d}:00 ｜ 加速度为 -"
    )
    comparison_width = draw.textlength(comparison_text, font=label_font)
    draw.text(
        (left + width - 30 - comparison_width, top + 45),
        comparison_text,
        font=label_font,
        fill="#6431C8",
    )

    chart_left = left + 104
    chart_right = left + width - 34
    chart_top = top + 150
    chart_bottom = top + height - 100
    chart_values = [max(float(value or 0), 0.0) for value in hourly_spends]
    high = max(chart_values, default=0.0)
    high = high * 1.18 if high else 1.0
    for tick in range(5):
        value = high * tick / 4
        y = chart_bottom - (chart_bottom - chart_top) * tick / 4
        draw.line((chart_left, y, chart_right, y), fill="#E8EEF7", width=1)
        label = _axis_value(value)
        label_width = draw.textlength(label, font=axis_font)
        draw.text((chart_left - 18 - label_width, y - 11), label, font=axis_font, fill=MUTED_TEXT_COLOR)
    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill="#9AA8BC", width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill="#9AA8BC", width=2)

    bar_colors = ("#B9A6FA", "#9A7CF2", "#7C3AED")
    slot_width = (chart_right - chart_left) / max(len(chart_values), 1)
    bar_width = min(108, slot_width * 0.56)
    for index, value in enumerate(chart_values):
        center_x = chart_left + slot_width * (index + 0.5)
        bar_top = chart_bottom - value / high * (chart_bottom - chart_top)
        draw.rounded_rectangle(
            (center_x - bar_width / 2, bar_top, center_x + bar_width / 2, chart_bottom),
            radius=8,
            fill=bar_colors[index % len(bar_colors)],
        )
        value_text = _format_amount(value)
        value_width = draw.textlength(value_text, font=axis_font)
        draw.text((center_x - value_width / 2, bar_top - 32), value_text, font=axis_font, fill="#6431C8")
        label = f"{hour_start + index}点\n{hour_start + index:02d}:00—{hour_start + index + 1:02d}:00"
        label_box = draw.multiline_textbbox((0, 0), label, font=label_font, spacing=2, align="center")
        label_width = label_box[2] - label_box[0]
        draw.multiline_text(
            (center_x - label_width / 2, chart_bottom + 17),
            label,
            font=label_font,
            fill=TEXT_COLOR,
            spacing=2,
            align="center",
        )


def _draw_comparison_table(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    rows: list[dict],
    periods: list[dict],
) -> int:
    period_by_key = {period["key"]: period for period in periods}
    summary_periods = {
        key: _build_summary_metrics(rows, key) for key in PERIOD_KEYS
    }
    table_rows = [*rows, {"agent_line": "汇总", "periods": summary_periods}]
    group_width = sum(width for _, _, width in METRIC_COLUMNS)
    table_width = AGENT_LINE_WIDTH + group_width * len(PERIOD_KEYS)
    table_height = GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT + ROW_HEIGHT * len(table_rows)
    right = left + table_width
    bottom = top + table_height
    header_font = _load_font(25, bold=True)
    metric_header_font = _load_font(21, bold=True)
    row_font = _load_font(23)
    summary_font = _load_font(24, bold=True)

    draw.rounded_rectangle((left, top, right, bottom), radius=12, fill="white", outline=GRID_COLOR, width=2)
    draw.rectangle(
        (left, top, left + AGENT_LINE_WIDTH, top + GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT),
        fill="#0D4DCC",
        outline=GRID_COLOR,
        width=1,
    )
    _draw_cell(
        draw,
        "代理线",
        left,
        top,
        AGENT_LINE_WIDTH,
        GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT,
        header_font,
        color="white",
    )

    x = left + AGENT_LINE_WIDTH
    for key in PERIOD_KEYS:
        period = period_by_key[key]
        style = PERIOD_STYLES[key]
        draw.rectangle(
            (x, top, x + group_width, top + GROUP_HEADER_HEIGHT),
            fill=style["color"],
            outline=GRID_COLOR,
            width=1,
        )
        _draw_cell(
            draw,
            period["group_title"],
            x,
            top,
            group_width,
            GROUP_HEADER_HEIGHT,
            header_font,
            color="white",
        )
        metric_x = x
        for header, _, metric_width in METRIC_COLUMNS:
            draw.rectangle(
                (
                    metric_x,
                    top + GROUP_HEADER_HEIGHT,
                    metric_x + metric_width,
                    top + GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT,
                ),
                fill=style["soft_color"],
                outline=GRID_COLOR,
                width=1,
            )
            _draw_cell(
                draw,
                header,
                metric_x,
                top + GROUP_HEADER_HEIGHT,
                metric_width,
                METRIC_HEADER_HEIGHT,
                metric_header_font,
            )
            metric_x += metric_width
        x += group_width

    row_top = top + GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT
    for row_index, row in enumerate(table_rows):
        current_top = row_top + row_index * ROW_HEIGHT
        is_summary = row["agent_line"] == "汇总"
        row_fill = "#EEF4FF" if is_summary else "white"
        draw.rectangle(
            (left, current_top, left + AGENT_LINE_WIDTH, current_top + ROW_HEIGHT),
            fill=row_fill,
            outline=GRID_COLOR,
            width=1,
        )
        _draw_cell(
            draw,
            row["agent_line"],
            left,
            current_top,
            AGENT_LINE_WIDTH,
            ROW_HEIGHT,
            summary_font if is_summary else row_font,
            align="left",
        )
        x = left + AGENT_LINE_WIDTH
        for key in PERIOD_KEYS:
            metrics = row["periods"][key]
            style = PERIOD_STYLES[key]
            for _, field, metric_width in METRIC_COLUMNS:
                draw.rectangle(
                    (x, current_top, x + metric_width, current_top + ROW_HEIGHT),
                    fill=row_fill,
                    outline=GRID_COLOR,
                    width=1,
                )
                _draw_cell(
                    draw,
                    _format_metric(metrics, field),
                    x,
                    current_top,
                    metric_width,
                    ROW_HEIGHT,
                    summary_font if is_summary else row_font,
                    color=style["color"] if is_summary else TEXT_COLOR,
                )
                x += metric_width
    return bottom


def _report_title(game_platform: str, current_period: dict) -> str:
    title = TITLE_MAP[game_platform]
    if current_period["full_day"]:
        return f"{title} 昨日（巴西时间）全天数据 对比看板"
    return f"{title} {current_period['slot'].hour}点时报 对比看板"


def _render_report_image(
    rows: list[dict],
    game_platform: str,
    now: datetime,
    periods: list[dict],
    chart_specs: dict,
    chart_metrics: dict,
) -> bytes:
    rows = [row for row in rows if _has_performance(row)]
    summaries = {key: _build_summary_metrics(rows, key) for key in PERIOD_KEYS}
    group_width = sum(width for _, _, width in METRIC_COLUMNS)
    table_width = AGENT_LINE_WIDTH + group_width * len(PERIOD_KEYS)
    table_left = (IMAGE_WIDTH - table_width) // 2
    table_height = GROUP_HEADER_HEIGHT + METRIC_HEADER_HEIGHT + ROW_HEIGHT * (len(rows) + 1)
    table_top = TITLE_HEIGHT + CHART_HEIGHT + SECTION_TITLE_HEIGHT
    image_height = table_top + table_height + 72
    image = Image.new("RGB", (IMAGE_WIDTH, image_height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(54, bold=True)
    subtitle_font = _load_font(27)
    section_font = _load_font(31, bold=True)

    period_by_key = {period["key"]: period for period in periods}
    title = _report_title(game_platform, period_by_key["current"])
    title_width = draw.textlength(title, font=title_font)
    draw.text(((IMAGE_WIDTH - title_width) / 2, 30), title, font=title_font, fill="#0C1B3E")
    subtitle = (
        f"当前时段：{period_by_key['current']['detail']}　|　"
        f"上一个时段：{period_by_key['previous']['detail']}　|　"
        f"昨日同时间段：{period_by_key['yesterday_current']['detail']}　|　"
        f"昨日上个时段：{period_by_key['yesterday_previous']['detail']}　|　"
        "图表横轴：巴西时间（UTC-3）"
    )
    subtitle_width = draw.textlength(subtitle, font=subtitle_font)
    draw.text(
        ((IMAGE_WIDTH - subtitle_width) / 2, 105), subtitle, font=subtitle_font, fill=MUTED_TEXT_COLOR
    )

    chart_width = (IMAGE_WIDTH - IMAGE_MARGIN * 2 - CHART_GAP * 2) // 3
    chart_top = TITLE_HEIGHT
    axis_hours = chart_specs["axis_hours"]
    line_hours = chart_specs["line_hours"]
    chart_data = chart_metrics[game_platform]

    def trend_series(field: str) -> dict[str, list[float | None]]:
        return {
            series_key: [
                (
                    0.0
                    if hour == 0 and field == "registration_cost"
                    else chart_data[series_key][hour][field]
                )
                if hour in line_hours
                else None
                for hour in axis_hours
            ]
            for series_key in TREND_STYLES
        }

    speed_start_hour = chart_specs["speed_start_hour"]
    speed_end_hour = chart_specs["speed_end_hour"]
    current_amounts = chart_data["today"]
    yesterday_amounts = chart_data["yesterday"]
    hourly_spends = [
        float(current_amounts[hour + 1]["amount_spent"] or 0)
        - float(current_amounts[hour]["amount_spent"] or 0)
        for hour in range(speed_start_hour, speed_end_hour)
    ]
    current_speed_spend = (
        float(current_amounts[speed_end_hour]["amount_spent"] or 0)
        - float(current_amounts[speed_start_hour]["amount_spent"] or 0)
    )
    yesterday_speed_spend = (
        float(yesterday_amounts[speed_end_hour]["amount_spent"] or 0)
        - float(yesterday_amounts[speed_start_hour]["amount_spent"] or 0)
    )
    comparison_rate = (
        (current_speed_spend - yesterday_speed_spend) / yesterday_speed_spend * 100
        if yesterday_speed_spend
        else None
    )

    _draw_trend_chart(
        draw,
        left=IMAGE_MARGIN,
        top=chart_top,
        width=chart_width,
        height=CHART_HEIGHT,
        axis_hours=axis_hours,
        series=trend_series("amount_spent"),
        title="消耗趋势",
        unit="US",
        value_formatter=_format_chart_amount,
    )
    _draw_trend_chart(
        draw,
        left=IMAGE_MARGIN + chart_width + CHART_GAP,
        top=chart_top,
        width=chart_width,
        height=CHART_HEIGHT,
        axis_hours=axis_hours,
        series=trend_series("registration_cost"),
        title="注册成本趋势",
        unit="US",
        value_formatter=_format_cost,
    )
    _draw_spend_speed_chart(
        draw,
        left=IMAGE_MARGIN + (chart_width + CHART_GAP) * 2,
        top=chart_top,
        width=chart_width,
        height=CHART_HEIGHT,
        hour_start=speed_start_hour,
        hourly_spends=hourly_spends,
        comparison_rate=comparison_rate,
    )

    section_top = TITLE_HEIGHT + CHART_HEIGHT
    draw.rounded_rectangle(
        (IMAGE_MARGIN, section_top + 12, IMAGE_MARGIN + 48, section_top + 60),
        radius=9,
        fill="#1769F2",
    )
    draw.rectangle(
        (IMAGE_MARGIN + 13, section_top + 24, IMAGE_MARGIN + 35, section_top + 30), fill="white"
    )
    draw.rectangle(
        (IMAGE_MARGIN + 13, section_top + 37, IMAGE_MARGIN + 35, section_top + 43), fill="white"
    )
    draw.text((IMAGE_MARGIN + 68, section_top + 18), "各代理线关键指标对比表", font=section_font, fill=TEXT_COLOR)

    table_bottom = _draw_comparison_table(
        draw, left=table_left, top=table_top, rows=rows, periods=periods
    )
    note_font = _load_font(21)
    draw.text(
        (IMAGE_MARGIN, table_bottom + 22),
        "注：成本按各时段的汇总消耗 ÷ 汇总转化人数计算；“-”表示该时段无对应转化数据。",
        font=note_font,
        fill=MUTED_TEXT_COLOR,
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def push_f9_agent_line_performance_report(
    now: datetime | None = None,
    *,
    target: str = "production",
) -> None:
    """推送各项目代理线四时段对比图片。

    target="production" 发应用机器人生产群；target="test" 发测试群 Webhook。
    """
    if target not in {"production", "test"}:
        raise ValueError(f"未知成效报表发送目标: {target}")
    now = now.astimezone(CHINA_TIMEZONE) if now else datetime.now(CHINA_TIMEZONE)
    periods = _build_period_specs(now)
    rows = _fetch_agent_line_period_metrics(periods)
    chart_specs = _build_chart_snapshot_specs(now)
    included_agent_lines = {
        game_platform: {
            row["agent_line"]
            for row in rows
            if row["game_platform"] == game_platform and _has_performance(row)
        }
        for game_platform in GAME_PLATFORMS
    }
    chart_metrics = _fetch_project_chart_metrics(chart_specs, included_agent_lines)
    for game_platform in GAME_PLATFORMS:
        project_rows = [row for row in rows if row["game_platform"] == game_platform]
        image = _render_report_image(
            project_rows,
            game_platform,
            now,
            periods,
            chart_specs,
            chart_metrics,
        )
        result = send_feishu_image(
            image,
            FEISHU_CHAT_ID,
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            target=target,
            webhook_url=FEISHU_TEST_WEBHOOK_URL if target == "test" else "",
            webhook_secret=FEISHU_TEST_WEBHOOK_SECRET if target == "test" else "",
        )
        if result is None:
            raise RuntimeError(f"飞书图片推送失败: game_platform={game_platform}")
    logging.info(
        "项目代理线对比图片已推送: target=%s, current_date=%s, agent_lines=%s, images=%s",
        target,
        periods[0]["report_date"],
        len(rows),
        len(GAME_PLATFORMS),
    )


if __name__ == "__main__":
    from conf.log_conf import init

    init("f9_agent_line_performance_report")
    push_f9_agent_line_performance_report(
        now=datetime(2026, 8, 20, 15, 30, tzinfo=CHINA_TIMEZONE),
        target='test')
