"""原TaskEvent存量防线；整批先验，损坏持久数据不得输出为客户端DTO。"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError

MAX_SAFE_INTEGER = 9007199254740991
MAX_BATCH = 200
PUBLIC_FIELDS = frozenset(
    {
        "event_id",
        "sequence",
        "schema_version",
        "task_id",
        "task_revision",
        "node_id",
        "state",
        "occurred_at",
        "request_id",
    }
)


def unavailable():
    raise OrbitError(503, "TASK_EVENT_STATE_UNAVAILABLE", "持久事件不符合原合同，停止订阅")


def uuid_value(value):
    if not isinstance(value, str):
        unavailable()
    try:
        if str(UUID(value)) != value.lower():
            unavailable()
    except (ValueError, AttributeError):
        unavailable()
    return value


def safe_integer(value):
    if type(value) is not int or not 1 <= value <= MAX_SAFE_INTEGER:
        unavailable()
    return value


def utc_time(value):
    """MySQL DATETIME(3)的naive值按既有协议为UTC；不按本机时区猜测。"""
    if not isinstance(value, datetime) or value.microsecond % 1000:
        unavailable()
    try:
        if value.tzinfo is not None and value.utcoffset() != timedelta(0):
            unavailable()
    except (TypeError, ValueError, OverflowError):
        unavailable()
    return value.replace(tzinfo=None)


def validate_structure(task, events):
    """先校整批再查目录；不加TaskEvent原Schema不存在的state枚举限制。"""
    try:
        if not isinstance(events, (list, tuple)) or len(events) > MAX_BATCH:
            unavailable()
        uuid_value(task["tenant_id"])
        uuid_value(task["id"])
        safe_integer(task["revision"])
        safe_integer(task["latest_sequence"])
        seen = set()
        for row in events:
            if not PUBLIC_FIELDS.issubset(row):
                unavailable()
            event = uuid_value(row["event_id"])
            if event in seen:
                unavailable()
            seen.add(event)
            if row["tenant_id"] != task["tenant_id"] or row["task_id"] != task["id"]:
                unavailable()
            uuid_value(row["task_id"])
            uuid_value(row["request_id"])
            if row["node_id"] is not None:
                uuid_value(row["node_id"])
            if type(row["schema_version"]) is not int or row["schema_version"] != 1:
                unavailable()
            if safe_integer(row["sequence"]) > task["latest_sequence"]:
                unavailable()
            if safe_integer(row["task_revision"]) > task["revision"]:
                unavailable()
            state = row["state"]
            if not isinstance(state, str) or not 1 <= len(state) <= 40:
                unavailable()
            state.encode("utf-8", errors="strict")
            utc_time(row["occurred_at"])
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError):
        unavailable()


def validate_directory(task, events, directory):
    try:
        if len(directory) != len(events):
            unavailable()
        by_id = {row["event_id"]: row for row in directory}
        if len(by_id) != len(directory):
            unavailable()
        for row in events:
            cursor = by_id[row["event_id"]]
            if (
                cursor["tenant_id"] != task["tenant_id"]
                or cursor["task_id"] != task["id"]
                or safe_integer(cursor["sequence"]) != row["sequence"]
                or utc_time(cursor["occurred_at"]) != utc_time(row["occurred_at"])
                or utc_time(cursor["expires_at"])
                != utc_time(row["occurred_at"]) + timedelta(days=7)
            ):
                unavailable()
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError):
        unavailable()


async def validate_persisted_batch(session, task, events):
    validate_structure(task, events)
    if not events:
        return
    directory = list(
        (
            await session.execute(
                text(
                    "SELECT tenant_id,task_id,event_id,sequence,occurred_at,expires_at "
                    "FROM orbit_task_event_cursor WHERE tenant_id=:tenant AND task_id=:task "
                    "AND event_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)),
                {
                    "tenant": task["tenant_id"],
                    "task": task["id"],
                    "ids": [row["event_id"] for row in events],
                },
            )
        ).mappings()
    )
    validate_directory(task, events, directory)
