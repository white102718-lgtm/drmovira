from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Query, Form
from app.core.security import auth_current_user
from app.db.clients import get_db
from app.model_type_defs.user_models import UserModel, Roles
from app.model_type_defs.material_order_models import (
    MaterialOrderCreate,
    MaterialOrderUpdate,
    BatchAssignBody,
    BatchRejectBody,
    BatchDeleteBody,
    DeliverBody,
    DeleteMaterialsBody,
    RejectMaterialsBody,
    AcceptMaterialsBody,
    AcceptBody,
    CommentBody,
    AssignMaterialsBody,
)
from app.services import material_order_service as svc

router = APIRouter(prefix="/material-orders", tags=["素材工单"])


# ==================== Page1 工单新建（operator）====================


@router.post("/attachments")
async def upload_attachment(is_unzip: bool = Form(True), file: UploadFile = File(...)):
    return await svc.upload_attachment(file, is_unzip)


@router.post("/")
async def create_order(
    body: MaterialOrderCreate, current_user: UserModel = Depends(auth_current_user)
):
    return await svc.create_order(body, current_user)


# ==================== Page2 需求池调度/分配（operator_leader）====================


@router.get("/")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    project: Optional[str] = Query(None),
    priority: Optional[List[str]] = Query(None),
    demand_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    operator: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    designers: Optional[List[str]] = Query(None),
    creative_planners: Optional[List[str]] = Query(None),
    country: Optional[str] = Query(None),
    is_green_material: Optional[bool] = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    view: str = Query("pool"),
    current_user: UserModel = Depends(auth_current_user),
):
    return await svc.list_orders(
        page,
        page_size,
        project,
        priority,
        demand_type,
        status,
        keyword,
        operator,
        department,
        designers,
        creative_planners,
        country,
        is_green_material,
        sort,
        order,
        view,
        current_user,
    )


@router.get("/stats")
async def order_stats():
    return await svc.order_stats()


@router.post("/batch-assign")
async def batch_assign(body: BatchAssignBody):
    return await svc.batch_assign(body)


@router.post("/batch-reject")
async def batch_reject(body: BatchRejectBody):
    return await svc.batch_reject(body)


@router.get("/creators")
async def list_creators():
    return await svc.list_creators()


# ==================== Page3 素材师工作台（creator）====================


@router.get("/my-stats")
async def my_stats(current_user: UserModel = Depends(auth_current_user)):
    return await svc.my_stats(current_user)


# ==================== 工单详情 / 编辑 ====================


@router.get("/{order_id}")
async def get_order(order_id: str):
    return await svc.get_order(order_id)


@router.put("/{order_id}")
async def update_order(
    order_id: str,
    body: MaterialOrderUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    return await svc.update_order(order_id, body, current_user)


@router.get("/{order_id}/histories")
async def list_order_histories(order_id: str):
    return await svc.list_order_histories(order_id)


@router.post("/batch-delete-cascade")
async def batch_delete_cascade(body: BatchDeleteBody):
    return await svc.batch_delete_cascade(body)


@router.post("/{order_id}/complete")
async def complete_task(
    order_id: str, current_user: UserModel = Depends(auth_current_user)
):
    return await svc.complete_task(order_id, current_user)


@router.post("/{order_id}/deliver")
async def deliver(
    order_id: str,
    body: DeliverBody,
    current_user: UserModel = Depends(auth_current_user),
):
    return await svc.deliver(order_id, body, current_user)


@router.post(
    "/{order_id}/materials/delete",
)
async def delete_materials(
    order_id: str,
    body: DeleteMaterialsBody,
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    return await svc.delete_materials(order_id, body, current_user, db)


# ==================== Page4 验收页 ====================


@router.get("/{order_id}/materials")
async def list_order_materials(order_id: str):
    return await svc.list_order_materials(order_id)


@router.post("/materials/thumbs")
async def get_material_thumbs(ids: List[str]):
    return await svc.get_material_thumbs(ids)


@router.post("/{order_id}/materials/reject")
async def reject_materials(order_id: str, body: RejectMaterialsBody):
    return await svc.reject_materials(order_id, body)


@router.post("/{order_id}/materials/accept")
async def accept_materials(order_id: str, body: AcceptMaterialsBody):
    return await svc.accept_materials(order_id, body)


@router.post("/{order_id}/materials/cancel-reject")
async def cancel_reject_materials(order_id: str, body: RejectMaterialsBody):
    return await svc.cancel_reject_materials(order_id, body)


@router.post("/zip")
async def zip_order_materials(file_ids: List[str]):
    """产出物打包下载（挑选工单内素材）：立即返回 {task_id}，前端轮询 GET /upload-tasks/{task_id} 取 {url, filename}。"""
    return await svc.zip_order_materials(file_ids)


@router.post("/zip-attachments")
async def zip_order_attachments(object_keys: List[str]):
    """参考资料打包下载"""
    return await svc.zip_order_attachments(object_keys)


@router.post("/{order_id}/accept")
async def accept_order(order_id: str, body: AcceptBody):
    return await svc.accept_order(order_id, body)


@router.get("/{order_id}/comments")
async def list_comments(order_id: str):
    return await svc.list_comments(order_id)


@router.post("/{order_id}/comments")
async def create_comment(
    order_id: str,
    body: CommentBody,
    current_user: UserModel = Depends(auth_current_user),
):
    return await svc.create_comment(order_id, body, current_user)


# ==================== Page5 沉淀入库（operator）====================


@router.post("/{order_id}/assign-materials")
async def assign_materials(
    order_id: str,
    body: AssignMaterialsBody,
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    return await svc.assign_materials(order_id, body, current_user, db)
