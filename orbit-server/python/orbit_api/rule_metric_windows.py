"""规则指标纯业务日窗口；不是调度、来源证明、Simulation或授权票据。"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_WINDOW_BATCH = 200
_WINDOW_DAYS = {"TODAY": (0, 0), "YESTERDAY": (1, 1), "LAST_3D": (2, 0), "LAST_7D": (6, 0)}
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class RuleMetricWindowError(ValueError):
    """纯输入/日期边界异常；HTTP层不得将它解释为来源已核验。"""

    def __init__(self, reason_code, message):
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True)
class AccountMetricTimezone:
    account_id: str
    timezone_name: str


@dataclass(frozen=True)
class ResolvedRuleMetricWindow:
    account_id: str
    timezone_name: str
    evaluated_at: datetime
    window: str
    local_today: date
    date_from: date
    date_to: date


def _instant_and_window(evaluated_at, window):
    if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
        raise RuleMetricWindowError("EVALUATION_INSTANT_INVALID", "评估时刻须为明确UTC时间")
    try:
        if evaluated_at.utcoffset() != timedelta(0):
            raise RuleMetricWindowError("EVALUATION_INSTANT_INVALID", "评估时刻须为明确UTC时间")
        instant = evaluated_at.astimezone(UTC)
    except (OverflowError, TypeError) as exc:
        raise RuleMetricWindowError("EVALUATION_INSTANT_INVALID", "评估时刻不可表示") from exc
    if type(window) is not str or window not in _WINDOW_DAYS:
        raise RuleMetricWindowError("WINDOW_INVALID", "只支持原规则四种观察窗口")
    return instant


def _resolve(instant, window, account):
    if type(account) is not AccountMetricTimezone:
        raise RuleMetricWindowError("ACCOUNT_INPUT_INVALID", "须提供明确账户及账户时区")
    if type(account.account_id) is not str or _UUID.fullmatch(account.account_id) is None:
        raise RuleMetricWindowError("ACCOUNT_ID_INVALID", "账户ID须为完整UUID")
    name = account.timezone_name
    if type(name) is not str or not 1 <= len(name) <= 64:
        raise RuleMetricWindowError("TIMEZONE_INVALID", "账户时区不可用")
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RuleMetricWindowError("TIMEZONE_INVALID", "账户时区不可用") from exc
    try:
        today = instant.astimezone(zone).date()
        start_back, end_back = _WINDOW_DAYS[window]
        start, end = today - timedelta(days=start_back), today - timedelta(days=end_back)
    except (OverflowError, ValueError) as exc:
        raise RuleMetricWindowError("WINDOW_DATE_OVERFLOW", "账户业务日超出可表示日期范围") from exc
    return ResolvedRuleMetricWindow(
        account.account_id.lower(), name, instant, window, today, start, end
    )


def resolve_rule_metric_window(evaluated_at, window, account):
    """按账户真实IANA时区解析包含端点的当地日期，不将调度时区传作替代值。"""
    return _resolve(_instant_and_window(evaluated_at, window), window, account)


def resolve_rule_metric_windows(evaluated_at, window, accounts):
    """每批最多200账户；全任务各批必须由调用方复用同一可信evaluated_at。

    不消费无界迭代器，不发明当前时间；任一非法输入整批拒绝，不返回部分窗口。
    仅计算日历日期，不生成UTC日区间；国际日期变更跳过的日期保留为日历标签，
    是否存在完整采集单元由受信来源判断，本函数不补零或声称已采集。
    """
    instant = _instant_and_window(evaluated_at, window)
    if type(accounts) not in (tuple, list) or len(accounts) > MAX_WINDOW_BATCH:
        raise RuleMetricWindowError("WINDOW_BATCH_LIMIT", "账户窗口每批最多200项")
    result, seen = [], set()
    for account in accounts:
        resolved = _resolve(instant, window, account)
        if resolved.account_id in seen:
            raise RuleMetricWindowError("DUPLICATE_ACCOUNT", "同批账户不能重复")
        seen.add(resolved.account_id)
        result.append(resolved)
    return tuple(result)
