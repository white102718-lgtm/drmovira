from typing import List, Optional, Literal

from pydantic import BaseModel


class OrderStatus:
    """工单状态枚举（贯穿全模块的状态机）"""

    DRAFT = "draft"  # 草稿
    PENDING_ASSIGN = "pending_assign"  # 待分配
    ASSIGNED = "assigned"  # 待处理（已分配素材师）
    IN_PRODUCTION = "in_production"  # 制作中
    PARTIALLY_COMPLETED = "partially_completed"  # 部分完成（部分素材师已完成、整单仍在制作阶段）
    PENDING_ACCEPT = "pending_accept"  # 待验收
    REJECTED = "rejected"  # 已打回/待返工
    ACCEPTED = "accepted"  # 已验收
    ARCHIVED = "archived"  # 已入库
    DEMAND_REJECTED = "demand_rejected"  # 已驳回（需求池组长驳回需求，退回投放师）

    # 分组（同 Roles.OPERATOR_ALL 的写法）
    ASSIGNABLE = [PENDING_ASSIGN, IN_PRODUCTION]  # 可分配 / 可领取
    PRE_ACCEPT = [PENDING_ASSIGN, IN_PRODUCTION, PARTIALLY_COMPLETED]  # 支持分配素材师的工单状态
    MY_TASKS = [IN_PRODUCTION, PARTIALLY_COMPLETED, REJECTED, PENDING_ACCEPT]  # 素材师在办
    UNDONE = [
        PENDING_ASSIGN,
        ASSIGNED,
        IN_PRODUCTION,
        PARTIALLY_COMPLETED,
        PENDING_ACCEPT,
        REJECTED,
    ]  # 未完结（预警口径）
    kanban_statuses = [PENDING_ASSIGN, IN_PRODUCTION, PENDING_ACCEPT]  # 需求池统计面板
    IS_COMPLETE = [PENDING_ACCEPT, ACCEPTED]  # 已完成为待验收，已验收
    DELETABLE = [DRAFT, DEMAND_REJECTED]  # 可删除：草稿、已驳回
    ALLOWED = [IN_PRODUCTION, PARTIALLY_COMPLETED, REJECTED] #素材工单提交使用


class MaterialScope:
    """素材可见范围：个人文件夹（隔离）/ 公共素材库"""

    PERSONAL = "personal"  # 工单沉淀入库的素材，归属 owner，仅本人可见
    PUBLIC = "public"  # 公共素材库（老数据/普通上传无 scope 也视为 public）
    TMP = "tmp" # 公共素材库（表示是从临时广告上传的临时素材）


# 素材列表投影：所有素材 / 个人文件夹两个视图共用，只喂卡片渲染。
# 详情字段由 GET /materials/by_ids 补，预览 url 由 GET /materials/url/{filename} 换。
# 两处必须共用同一份——各自维护一份迟早漂移，同一批素材在两个 Tab 会渲染出不同结果。
MATERIAL_LIST_PROJECTION = {
    "sha3_256": 0,
    "file_md5": 0,
    "updated_at": 0,
    "origin_filename": 0,
    "country": 0,
    "creative_planner": 0,
    "is_green_material": 0,
    "scope": 0,
    "source": 0,
    "order_id": 0,
    "order_no": 0,
    "published_at": 0,
    "analysis_description": 0,
    "tag_description": 0,
}


class MaterialReviewStatus:
    """产出素材验收状态（验收页，写在 material_order_outputs.review_status；无该字段=待验收）"""

    ACCEPTED = "accepted"  # 已验收
    REJECTED = "rejected"  # 驳回
    IN_LIBRARY = "in_library"  # 已入库


class OrderTags(BaseModel):
    country: List[str] = []
    theme: List[str] = []
    gameplay: List[str] = []


class OrderReference(BaseModel):
    type: Literal["upload", "library", "link"]
    name: str
    # upload
    object_key: Optional[str] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    filetype: Optional[str] = None
    img: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    # library
    basename: Optional[str] = None
    # link
    url: Optional[str] = None


class MaterialOrderCreate(BaseModel):
    _id: Optional[str] = None
    order_no: Optional[str] = None
    status: str = OrderStatus.DRAFT
    title: Optional[str] = None
    project: Optional[str] = None
    demand_type: Optional[str] = None
    sizes: List[str] = []
    quantity: Optional[int] = None
    priority: Optional[str] = None
    expected_delivery_at: Optional[str] = None  # "%Y-%m-%d %H:%M"
    product_info: Optional[str] = None
    tags: OrderTags = OrderTags()
    description: Optional[list] = None  # 需求项数组，落库时后端为每项补稳定 id
    references: List[OrderReference] = []
    is_green_material: bool
    department: Optional[str] = None
    language: str


class MaterialOrderUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    project: Optional[str] = None
    demand_type: Optional[str] = None
    sizes: Optional[List[str]] = None
    quantity: Optional[int] = None
    priority: Optional[str] = None
    expected_delivery_at: Optional[str] = None
    product_info: Optional[str] = None
    tags: Optional[OrderTags] = None
    description: Optional[list] = None  # 需求项数组，落库时后端为每项补稳定 id
    references: Optional[List[OrderReference]] = None
    is_green_material: bool
    department: Optional[str] = None
    language: str


class AssignItem(BaseModel):
    id: str
    designers: List[str]
    creative_planners: List[str] = []


class BatchAssignBody(BaseModel):
    items: List[AssignItem]


class RejectItem(BaseModel):
    id: str
    reason: str = ""


class BatchRejectBody(BaseModel):
    items: List[RejectItem]


class BatchDeleteBody(BaseModel):
    ids: List[str]


class DeliverMaterial(BaseModel):
    filename: str
    object_key: str
    basename: Optional[str] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    filetype: Optional[str] = None
    file_md5: Optional[str] = None
    sha3_256: Optional[str] = None
    img: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    req_id: Optional[str] = None  # 关联工单 description 需求项的 id


class DeliverBody(BaseModel):
    materials: List[DeliverMaterial]
    designer: str
    creative_planner: Optional[str] = None


class DeleteMaterialsBody(BaseModel):
    basenames: List[str]


class RejectMaterialsBody(BaseModel):
    ids: List[str]


class AcceptMaterialsBody(BaseModel):
    ids: List[str]


class AcceptBody(BaseModel):
    action: Literal["pass", "reject"]
    rating: Optional[int] = None


class CommentBody(BaseModel):
    content: str
    event: Optional[str] = None


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None


class FolderRename(BaseModel):
    name: str


class FolderMove(BaseModel):
    parent_id: Optional[str] = None


class AssignMaterialsBody(BaseModel):
    ids: List[str]
    scope: Literal["public", "personal"]
    folder_id: Optional[str] = None
