from typing import Optional, List

from fastapi import APIRouter, Depends, UploadFile, File, Query
from pydantic import BaseModel

from app.core.security import auth_current_user, require_roles
from app.model_type_defs.user_models import UserModel, Roles
from app.services import material_common_service as svc

router = APIRouter(prefix="/material-common", tags=["公共素材"])


class BatchDeleteBody(BaseModel):
    ids: List[str]


class UpdateTagsBody(BaseModel):
    ids: List[str]
    tags_new: List[str]


@router.post("/")
async def upload_common_material(
    file: UploadFile = File(...),
    tags_new: Optional[List[str]] = None,
    current_user: UserModel = Depends(auth_current_user),
):
    return await svc.upload(file, current_user, tags_new)


@router.get("/")
async def list_common_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=400),
    filetype: Optional[str] = Query(None),
    basename: Optional[str] = Query(None),
):
    return await svc.list_materials(page, page_size, filetype, basename)


@router.get("/by_ids")
async def get_common_materials_by_ids(
    ids: List[str] = Query(..., description="公共素材ID列表"),
):
    """公共素材详情：预览面板用，返回 origin_filename / tags_tree / 现签 url。"""
    return await svc.get_by_ids(ids)


@router.put("/tags")
async def update_common_material_tags(body: UpdateTagsBody):
    return await svc.update_tags(body.ids, body.tags_new)


@router.post("/batch_delete")
async def batch_delete_common_materials(body: BatchDeleteBody):
    return await svc.batch_delete(body.ids)


@router.post("/zip")
async def zip_common_materials(file_ids: List[str]):
    """公共素材打包下载：立即返回 {task_id}，前端轮询 GET /upload-tasks/{task_id} 取 {url, filename}。"""
    return await svc.zip_materials(file_ids)
