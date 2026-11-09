"""原Task只读路径；事件流由独立路由提供，不开放执行或控制写接口。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request, Response
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.task_contract import filters
from orbit_api.task_event_store import TaskEventStore
from orbit_api.task_store import TaskStore

router = APIRouter(prefix="/api/v1/tasks", tags=["ORBIT原统一任务只读核心"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]
ALLOWED = {
    "q",
    "cursor",
    "page_size",
    "status",
    "date_from",
    "date_to",
    "operator_user_id",
    "channel_id",
    "metric_profile_id",
    "entity_type",
}


def store():
    return TaskStore(DirectoryTokens(credential_cipher()))


@router.get("")
async def list_tasks(request: Request, response: Response, user: User):
    _read_boundary(request, ALLOWED)
    query, cursor = filters(dict(request.query_params))
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().list(session, user.user.user_id, query, cursor)


@router.get("/{task_id}/nodes")
async def nodes(task_id: str, request: Request, response: Response, user: User):
    _read_boundary(request, ALLOWED)
    query, cursor = filters(dict(request.query_params), nodes=True)
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store().page_nodes(session, user.user.user_id, task_id, query, cursor)


@router.get("/{task_id}")
async def detail(task_id: str, request: Request, response: Response, user: User):
    _read_boundary(request)
    response.headers["Cache-Control"] = "no-store"
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        payload = await store().detail(session, user.user.user_id, task_id)
        # 同一短事务与Task行锁生成快照续传凭证，不能拼接另一版本的事件游标。
        response.headers["X-Task-Event-Checkpoint"] = await TaskEventStore(
            DirectoryTokens(credential_cipher())
        ).checkpoint_for_detail(session, user.user.user_id, task_id, payload)
        return payload
