"""独立SSE路由待主线注册；不提供事件写入HTTP或平台执行入口。"""

from config.database import DataSourceRegistry
from exceptions.exception import AuthException
from fastapi import APIRouter, Request
from module_admin.service.login_service import LoginService

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.task_event_contract import StreamQuota, cursor_id
from orbit_api.task_event_session import resolve_actor
from orbit_api.task_event_store import TaskEventStore
from orbit_api.task_event_stream import EventResponse

router = APIRouter(prefix="/api/v1/tasks", tags=["ORBIT原Task事件observer"])
quota = StreamQuota()


async def actor_current(session, request):
    return await resolve_actor(session, request, LoginService, AuthException)


@router.get("/{task_id}/events")
async def events(task_id: str, request: Request):
    _read_boundary(request)
    event_id = cursor_id(request.headers.get("last-event-id"))
    checkpoint = request.headers.get("x-task-event-checkpoint")
    store = TaskEventStore(DirectoryTokens(credential_cipher()))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        actor = await actor_current(session, request)
        after = await store.start(session, actor, task_id, event_id, checkpoint)
    quota.acquire(actor)

    async def operation(after, *, batch):
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            if await actor_current(session, request) != actor:
                raise OrbitError(401, "SESSION_REAUTH_REQUIRED", "当前事件会话身份已改变")
            if batch:
                return await store.batch(session, actor, task_id, after)
            current, row, _ = await store.context(session, actor, task_id)
            from sqlalchemy import text

            now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
            await store.unread_live(
                session,
                {"tenant": current.tenant_id, "task": row["id"]},
                after,
                row["latest_sequence"],
                now,
            )

    return EventResponse(
        actor=actor,
        after=after,
        read_batch=lambda after: operation(after, batch=True),
        guard=lambda after: operation(after, batch=False),
        quota=quota,
    )
