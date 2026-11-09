"""上传任务状态机：只存 Redis（1 天 TTL 自动清理），不落库。
状态 pending → processing → done/failed；done 带 result，failed 带 error。"""

import asyncio
import json
import uuid

from fastapi.encoders import jsonable_encoder

from app.db.clients import redis_cli_1

TASK_TTL = 24 * 60 * 60  # 任务记录保留 1 天（与下载链接时效一致，过期就该重新发起）

_bg_tasks: set = set()


def spawn(coro) -> None:
    # fire-and-forget：存引用防 GC 回收，完成后自动清理
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _key(task_id: str) -> str:
    return f"upload_task:{task_id}"


async def _save(task_id: str, doc: dict) -> None:
    await redis_cli_1.set(_key(task_id), json.dumps(jsonable_encoder(doc)), ex=TASK_TTL)


async def create() -> str:
    task_id = uuid.uuid4().hex
    await _save(task_id, {"status": "pending", "result": None, "error": None})
    return task_id


async def set_processing(task_id: str) -> None:
    await _save(task_id, {"status": "processing", "result": None, "error": None})


async def done(task_id: str, result) -> None:
    await _save(task_id, {"status": "done", "result": result, "error": None})


async def fail(task_id: str, error: str) -> None:
    await _save(task_id, {"status": "failed", "result": None, "error": error})


async def get(task_id: str):
    raw = await redis_cli_1.get(_key(task_id))
    return json.loads(raw) if raw else None
