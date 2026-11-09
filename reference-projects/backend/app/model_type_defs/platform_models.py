from typing import List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from bson import ObjectId


class PackageType(str, Enum):
    """包类型枚举"""
    W2A = "W2A"      # Web2App
    PWA = "PWA"      # Progressive Web App
    STORE = "Store"  # 应用商店（Google Play）


class CampaignType(str, Enum):
    """代理线系列目标"""
    OUTCOME_SALES = "OUTCOME_SALES",
    OUTCOME_TRAFFIC = "OUTCOME_TRAFFIC",
    OUTCOME_LEADS = "OUTCOME_LEADS",
    OUTCOME_ENGAGEMENT = "OUTCOME_ENGAGEMENT",
    OUTCOME_AWARENESS = "OUTCOME_AWARENESS",
    OUTCOME_APP_PROMOTION = "OUTCOME_APP_PROMOTION",


class PydanticObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class PlatformConfigBase(BaseModel):
    game_platform: str = Field(..., alias="_id", description="游戏平台名称，作为主键")
    attribution_platform: str = Field(..., description="归因平台")
    agent_lines: List[str] = Field(..., description="代理线列表")
    enabled: bool = Field(False, description="是否启用")
    visible: bool = Field(True, description="是否显示")
    total_budget: Optional[float] = Field(None, description="总预算")
    target_region: Optional[List[str]] = Field(None, description="投放地区")
    material_category_ids: List[str] = Field(default=[], description="素材分类ID列表")

    class Config:
        populate_by_name = True


class PlatformConfigCreate(BaseModel):
    game_platform: str = Field(..., alias="_id", description="游戏平台名称，作为主键")
    total_budget: Optional[float] = Field(None, description="总预算")
    target_region: Optional[List[str]] = Field(None, description="投放地区")
    departments: Optional[List[str]] = Field(None, description="部门")

    class Config:
        populate_by_name = True


class PlatformConfigUpdate(BaseModel):
    # 不允许在此接口直接覆盖 agent_lines,只能通过 link_agent_lines_to_platform /
    # soft_delete_agent_line 这两条专用通道,否则被踢掉的 line 不会进 trash → 孤儿
    attribution_platform: Optional[str] = None
    enabled: Optional[bool] = Field(None, description="是否启用")
    visible: Optional[bool] = Field(None, description="是否显示")
    total_budget: Optional[float] = Field(None, description="总预算")
    target_region: Optional[List[str]] = Field(None, description="投放地区")
    material_category_ids: Optional[List[str]] = Field(None, description="素材分类ID列表")
    departments: Optional[List[str]] = Field(None, description="部门")

    @field_validator("target_region", mode="before")
    @classmethod
    def normalize_target_region(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            # 兼容旧的单字符串格式，转为列表
            return [v] if v else []
        return v


class AgentLineConfigCreate(BaseModel):
    """创建代理线配置时使用的模型，_id为代理线名称，必填"""
    id: str = Field(..., alias="_id", description="代理线名称，作为主键")
    objective: Optional[CampaignType] = Field(None, description="系列目标")
    package_url: Optional[str] = Field(None, description="投放链接")
    pixel_name: Optional[str] = Field(None, description="像素名称")
    page_id: Optional[str] = Field(None, description="主页ID")
    optimizer: Optional[str] = Field(None, description="优化师")
    package_type: Optional[PackageType] = Field(None, description="包类型")
    package_name: Optional[str] = Field(None, description="包名")
    enabled: bool = Field(True, description="是否启用")
    auto_run: Optional[bool] = Field(None, description="自动运行")
    is_send: Optional[bool] = Field(None, description="是否发送")
    budget_cap: Optional[int] = Field(None, description="预算上限")
    budget_floor: Optional[int] = Field(None, description="预算下限")
    history_package_urls: Optional[List[str]] = Field([], description="历史投放链接")

    @field_validator('package_url')
    @classmethod
    def strip_package_url(cls, v: Optional[str]) -> Optional[str]:
        """去除投放链接首尾空格"""
        if v is not None:
            return v.strip()
        return v

    @model_validator(mode='after')
    def set_package_type_for_google_play(self):
        """如果投放链接是 Google Play 链接，强制设置包类型为 Store"""
        if self.package_url and self.package_url.startswith('https://play.google.com'):
            self.package_type = PackageType.STORE
        return self

    model_config = ConfigDict(populate_by_name=True)


AgentLineConfigUpdate = AgentLineConfigCreate


class AgentLineKpiConfig(BaseModel):
    game_platform: Optional[str] = None
    agent_lines: Optional[List[str]] = Field(default=[], description="代理线名称")
    target_purpose: Optional[str] = Field(None, description="目标用途")
    target_cost: Optional[float] = Field(None, description="目标成本")
    target_lost_percent: Optional[float] = Field(None, description="目标损失率")
    target_lifetime_hour: Optional[int] = Field(
        None, description="目标生命周期(小时)"
    )
    max_target_cost: Optional[float] = Field(None, description="最高目标成本")
    check_hourly: Optional[str] = Field(None, description="检查方式")
    event_name: Optional[str] = Field(None, description="事件名称")
    event_field: Optional[str] = Field(None, description="事件字段")
    type: Optional[str] = Field(None, description="类型")


# ==================== 素材分类相关模型 ====================


class MaterialContent(BaseModel):
    """素材内容模型"""
    id: str = Field(..., description="内容ID")
    type: str = Field(..., description="类型(text/image/video等)")
    text: Optional[str] = Field(None, description="文本内容或MinIO文件名")
    name: str = Field(..., description="内容名称")
    remark: Optional[str] = Field(None, description="备注")


class MaterialSubCategory(BaseModel):
    """二级分类模型"""
    id: str = Field(..., description="二级分类ID")
    name: str = Field(..., description="二级分类名称")
    contents: List[MaterialContent] = Field(default=[], description="内容列表")


class MaterialCategoryCreate(BaseModel):
    """创建一级分类"""
    name: str = Field(..., description="一级分类名称")
    sub_categories: List[MaterialSubCategory] = Field(default=[], description="二级分类列表")


class MaterialCategoryUpdate(BaseModel):
    """更新一级分类"""
    name: Optional[str] = Field(None, description="一级分类名称")
    sub_categories: Optional[List[MaterialSubCategory]] = Field(None, description="二级分类列表")


# ==================== 分类树操作模型 ====================


class CategoryNodeCreate(BaseModel):
    """新增分类节点（一级或二级通用）"""
    name: str = Field(..., description="分类名称")
    description: Optional[str] = Field(None, description="分类描述")


class CategoryNodeUpdate(BaseModel):
    """修改分类节点（一级或二级通用）"""
    name: Optional[str] = Field(None, description="新名称")
    description: Optional[str] = Field(None, description="分类描述")
