"""原TaskEvent编码及observer控制帧；不把连接撤权写为全局事件。"""

from orbit_api.account_command_contract import database_time
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.task_contract import identifier

PURPOSE = "TASK_EVENT_CHECKPOINT_V1"
CHECKPOINT_SECONDS = 60
BATCH_SIZE = 200
POLL_SECONDS = 0.5
SEND_TIMEOUT_SECONDS = 2
MAX_STREAM_SECONDS = 60
MAX_STREAMS = 64
MAX_ACTOR_STREAMS = 4


def invalid_cursor():
    raise OrbitError(400, "EVENT_CURSOR_INVALID", "事件游标不属于当前任务或无效")


def expired():
    raise OrbitError(410, "EVENT_CURSOR_EXPIRED", "事件已过期，请重新取得任务快照")


def cursor_id(value):
    if value is None:
        return None
    try:
        return identifier(value, "/Last-Event-ID")
    except OrbitError:
        invalid_cursor()


def public_event(row):
    return {
        key: row[key]
        for key in (
            "event_id",
            "sequence",
            "schema_version",
            "task_id",
            "task_revision",
            "node_id",
            "state",
            "request_id",
        )
    } | {"occurred_at": database_time(row["occurred_at"])}


def event_frame(row):
    return ("id: " + row["event_id"] + "\ndata: " + canonical(public_event(row)) + "\n\n").encode()


def revoked_frame():
    return b'event: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED"}\n\n'


class StreamQuota:
    """进程内同时连接有界；跨副本总配额仍需网关或共享限流，不伪称已部署。"""

    def __init__(self, total=MAX_STREAMS, per_actor=MAX_ACTOR_STREAMS):
        self.total, self.per_actor = total, per_actor
        self.active = {}

    def acquire(self, actor):
        if sum(self.active.values()) >= self.total or self.active.get(actor, 0) >= self.per_actor:
            raise OrbitError(429, "TASK_STREAM_LIMIT", "当前事件连接数已达限制，请稍后重连")
        self.active[actor] = self.active.get(actor, 0) + 1

    def release(self, actor):
        count = self.active.get(actor, 0)
        if count <= 1:
            self.active.pop(actor, None)
        else:
            self.active[actor] = count - 1
