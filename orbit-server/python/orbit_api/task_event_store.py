"""七天逻辑过期、UUID身份目录与快照checkpoint；每次调用只占短事务。"""

from datetime import timedelta

from sqlalchemy import text

from orbit_api import task_access as access
from orbit_api.errors import OrbitError
from orbit_api.launch_access import parameters, scope_clause
from orbit_api.task_contract import identifier
from orbit_api.task_event_contract import (
    BATCH_SIZE,
    CHECKPOINT_SECONDS,
    PURPOSE,
    expired,
    invalid_cursor,
)
from orbit_api.task_event_validation import validate_persisted_batch


class TaskEventStore:
    def __init__(self, tokens):
        self.tokens = tokens

    def checkpoint(self, row, fingerprint):
        """由GET Task读取同一事务的真实row调用；不重新读取另一版本后拼接。"""
        return self.tokens.issue(
            PURPOSE,
            {
                "tenant": row["tenant_id"],
                "task": row["id"],
                "fingerprint": fingerprint,
                "revision": row["revision"],
                "sequence": row["latest_sequence"],
                "event": row["latest_event_id"],
            },
            ttl=CHECKPOINT_SECONDS,
        )

    async def checkpoint_for_detail(self, session, actor, task_id, payload):
        """主线GET接线点：与原detail共享事务及Task锁，不另开事务拼接版本。"""
        _, row, fingerprint = await self.context(session, actor, task_id)
        if any(
            payload.get(key) != row[column]
            for key, column in (
                ("id", "id"),
                ("revision", "revision"),
                ("latest_event_id", "latest_event_id"),
            )
        ):
            raise OrbitError(503, "TASK_SNAPSHOT_UNAVAILABLE", "任务快照与事件检查点不一致")
        return self.checkpoint(row, fingerprint)

    async def context(self, session, actor, task_id):
        current, _, fingerprint = await access.authorize(session, actor)
        row = await access.task(session, current, identifier(task_id))
        return current, row, fingerprint

    def checkpoint_sequence(self, token, current, row, fingerprint, event_id):
        try:
            claims = self.tokens.verify(PURPOSE, token)
        except OrbitError:
            invalid_cursor()
        if (
            claims.get("tenant") != current.tenant_id
            or claims.get("task") != row["id"]
            or claims.get("fingerprint") != fingerprint
            or claims.get("event") != event_id
            or type(claims.get("revision")) is not int
            or not 1 <= claims["revision"] <= row["revision"]
            or type(claims.get("sequence")) is not int
            or not 1 <= claims["sequence"] <= row["latest_sequence"]
        ):
            invalid_cursor()
        return claims["sequence"]

    async def start(self, session, actor, task_id, event_id=None, checkpoint=None):
        current, row, fingerprint = await self.context(session, actor, task_id)
        params = {"tenant": current.tenant_id, "task": row["id"]}
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        after = 0
        if event_id:
            directory = (
                (
                    await session.execute(
                        text(
                            "SELECT sequence,expires_at FROM orbit_task_event_cursor WHERE "
                            "tenant_id=:tenant AND task_id=:task AND event_id=:event"
                        ),
                        params | {"event": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if directory is None:
                invalid_cursor()
            after = directory["sequence"]
            if checkpoint:
                if (
                    self.checkpoint_sequence(checkpoint, current, row, fingerprint, event_id)
                    != after
                ):
                    invalid_cursor()
            elif directory["expires_at"] <= now:
                expired()
        elif checkpoint:
            invalid_cursor()
        await self.unread_live(session, params, after, row["latest_sequence"], now)
        # 首批连续性在HTTP 200之前核对；不是先开流再把持久缺口吞成空闲。
        await self.batch(session, actor, task_id, after)
        return after

    async def unread_live(self, session, params, after, latest, now):
        expired_unread = (
            await session.execute(
                text(
                    "SELECT 1 FROM orbit_task_event_cursor WHERE tenant_id=:tenant AND "
                    "task_id=:task "
                    "AND sequence>:after AND sequence<=:latest AND expires_at<=:now LIMIT 1"
                ),
                params | {"after": after, "latest": latest, "now": now},
            )
        ).first()
        if expired_unread:
            expired()

    async def batch(self, session, actor, task_id, after):
        current, row, _ = await self.context(session, actor, task_id)
        params = {"tenant": current.tenant_id, "task": row["id"]}
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        await self.unread_live(session, params, after, row["latest_sequence"], now)
        events = list(
            (
                await session.execute(
                    text(
                        "SELECT e.* FROM orbit_task_event e WHERE e.tenant_id=:tenant AND "
                        "e.task_id=:task "
                        "AND e.sequence>:after AND e.sequence<=:latest ORDER BY e.sequence LIMIT "
                        ":limit"
                    ),
                    params
                    | {"after": after, "latest": row["latest_sequence"], "limit": BATCH_SIZE},
                )
            ).mappings()
        )
        # 首次开流和后续批次都先校整批及目录，禁止已损坏行进入SSE编码器。
        await validate_persisted_batch(session, row, events)
        if any(item["sequence"] != after + index + 1 for index, item in enumerate(events)) or (
            not events and after < row["latest_sequence"]
        ):
            raise OrbitError(503, "TASK_EVENT_SEQUENCE_UNAVAILABLE", "持久事件不连续，停止订阅")
        return events

    async def purge(self, session, actor, task_id, *, limit=1000):
        """内部维护入口，须可信维护调用；原tasks.read不因此获得HTTP清理权。"""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("事件清理每批最多1000")
        current, _, _ = await access.authorize(session, actor)
        # 直接取得X锁，避免两个维护者先SHARE再升级造成锁升级死锁。
        row = (
            (
                await session.execute(
                    text(
                        "SELECT t.* FROM orbit_task t WHERE t.tenant_id=:tenant AND t.id=:id "
                        "AND t.manifest_phase='COMPLETE' AND ("
                        + scope_clause(current, "t")
                        + ") FOR UPDATE OF t"
                    ),
                    parameters(current) | {"id": identifier(task_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "任务不存在或不可见")
        params = {"tenant": current.tenant_id, "task": row["id"]}
        await session.execute(
            text(
                "INSERT IGNORE INTO orbit_task_event_retention(tenant_id,task_id) "
                "VALUES(:tenant,:task)"
            ),
            params,
        )
        await session.execute(
            text(
                "SELECT revision FROM orbit_task_event_retention WHERE tenant_id=:tenant "
                "AND task_id=:task FOR UPDATE"
            ),
            params,
        )
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT sequence FROM orbit_task_event WHERE tenant_id=:tenant AND "
                        "task_id=:task "
                        "AND occurred_at<=:cutoff ORDER BY sequence LIMIT :limit"
                    ),
                    params | {"cutoff": now - timedelta(days=7), "limit": limit},
                )
            )
            .scalars()
            .all()
        )
        if rows:
            await session.execute(
                text(
                    "DELETE FROM orbit_task_event WHERE tenant_id=:tenant AND task_id=:task "
                    "AND sequence<=:last AND occurred_at<=:cutoff"
                ),
                params | {"last": rows[-1], "cutoff": now - timedelta(days=7)},
            )
            await session.execute(
                text(
                    "UPDATE orbit_task_event_retention SET purged_through_sequence="
                    "GREATEST(purged_through_sequence,:last),revision=revision+1 "
                    "WHERE tenant_id=:tenant AND task_id=:task"
                ),
                params | {"last": rows[-1]},
            )
        return len(rows)
