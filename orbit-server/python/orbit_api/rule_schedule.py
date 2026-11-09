"""预览/未来调度共用的纯时间核心；不启动任务或宣称持久去重已完成。"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from orbit_api.rule_contract import Schedule, parse_schedule


@dataclass(frozen=True)
class Preview:
    slots: tuple[datetime, ...]
    skipped_local_times: tuple[datetime, ...]


@dataclass(frozen=True)
class Due:
    slot: datetime | None
    missed_slots: int
    skipped_local_times: tuple[datetime, ...]


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("参考时间必须带时区")
    return value.astimezone(UTC)


def _wall_instants(wall, zone):
    """UTC round-trip识别缺失/重复墙钟，重复位置去重后取较早UTC。"""
    values = set()
    for fold in (0, 1):
        try:
            candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if candidate.astimezone(zone).replace(tzinfo=None) == wall:
                values.add(candidate)
        except (OverflowError, ValueError):
            continue
    return tuple(sorted(values))


def _start(day, zone):
    wall = datetime.combine(day, time.min)
    valid = _wall_instants(wall, zone)
    if valid:
        return valid[0]
    return _gap_transition(wall, zone)


def _gap_transition(wall, zone):
    # 午夜在gap内：两种fold给出gap两侧，二分UTC定位转换的首有效时刻。
    # 最多48次（微秒精度），不按分钟扫描缺失日。
    candidates = sorted(wall.replace(tzinfo=zone, fold=f).astimezone(UTC) for f in (0, 1))
    low, high = candidates
    if not (
        low.astimezone(zone).replace(tzinfo=None)
        < wall
        <= high.astimezone(zone).replace(tzinfo=None)
    ):
        raise ValueError("无法确定生效日首有效时刻")
    while high - low > timedelta(microseconds=1):
        middle = low + (high - low) // 2
        if middle.astimezone(zone).replace(tzinfo=None) >= wall:
            high = middle
        else:
            low = middle
    return high


def _definition(schedule):
    schedule = parse_schedule(schedule.model_dump() if isinstance(schedule, Schedule) else schedule)
    zone = ZoneInfo(schedule.timezone)
    start, end = date.fromisoformat(schedule.start_date), date.fromisoformat(schedule.end_date)
    anchor = _start(start, zone)
    if end < date.max:
        finish = _start(end + timedelta(days=1), zone)
    else:
        # 公历终点不能构造10000-01-01；正偏移时其UTC边界仍可精确表示。
        try:
            finish = datetime.max.replace(tzinfo=zone).astimezone(UTC) + timedelta(microseconds=1)
        except OverflowError:
            finish = datetime.max.replace(tzinfo=UTC)
    return schedule, zone, start, end, anchor, finish


def _walls(schedule, zone, start, end):
    clock = time.fromisoformat(schedule.time_of_day)
    # 含首尾最多366个当地日，最多732次round-trip；与经过分钟的数量无关。
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        if schedule.frequency == "WEEKLY" and day.isoweekday() != schedule.weekday:
            continue
        wall = datetime.combine(day, clock)
        valid = _wall_instants(wall, zone)
        if valid:
            yield valid[0], None
        else:
            # gap发生位置只用于决定是否计入本次跳过审计，不平移成运行slot。
            transition = _gap_transition(wall, zone)
            yield transition, wall


def preview_schedule(schedule, after: datetime, limit: int = 10) -> Preview:
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("预览数量必须是1至50")
    after = _utc(after)
    schedule, zone, start, end, anchor, finish = _definition(schedule)
    if after >= finish:
        return Preview((), ())
    slots, skipped = [], []
    if schedule.frequency == "INTERVAL":
        step = timedelta(minutes=schedule.interval_minutes)
        index = max(0, (after - anchor) // step + 1)
        for offset in range(limit):
            try:
                candidate = anchor + (index + offset) * step
            except OverflowError:
                break
            if candidate >= finish:
                break
            slots.append(candidate)
    else:
        for candidate, missing in _walls(schedule, zone, start, end):
            if candidate <= after:
                continue
            if missing is not None:
                skipped.append(missing)
            else:
                slots.append(candidate)
                if len(slots) == limit:
                    break
    return Preview(tuple(slots), tuple(skipped))


def latest_due(schedule, last: datetime, now: datetime, *, enabled: bool) -> Due:
    last, now = _utc(last), _utc(now)
    if type(enabled) is not bool or now < last:
        raise ValueError("调度状态或时间区间无效")
    schedule, zone, start, end, anchor, finish = _definition(schedule)
    if not enabled or now < anchor or now >= finish:
        return Due(None, 0, ())
    if schedule.frequency == "INTERVAL":
        step = timedelta(minutes=schedule.interval_minutes)
        first = max(0, (last - anchor) // step + 1)
        latest = (now - anchor) // step
        return (
            Due(anchor + latest * step, latest - first, ()) if latest >= first else Due(None, 0, ())
        )
    slots, skipped = [], []
    for candidate, missing in _walls(schedule, zone, start, end):
        if last < candidate <= now:
            if missing is not None:
                skipped.append(missing)
            else:
                slots.append(candidate)
    return Due(slots[-1] if slots else None, max(0, len(slots) - 1), tuple(skipped))
