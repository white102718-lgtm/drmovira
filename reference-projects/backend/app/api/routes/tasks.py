from fastapi import APIRouter

from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.services import task_service

router = APIRouter(prefix="/upload-tasks", tags=["上传任务"])


@router.get("/{task_id}")
async def get_upload_task(task_id: str):
    """轮询上传任务状态：status=pending|processing|done|failed；
    done 时 result 为原同步返回体，failed 时 error 为错误信息。"""
    task = await task_service.get(task_id)
    if not task:
        return ErrResponse(code=404, message="任务不存在或已过期")
    return ApiResponse(data=task)
