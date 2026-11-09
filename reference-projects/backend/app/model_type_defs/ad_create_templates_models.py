"""
广告配置模板数据模型
集合名称: ad_create_templates

数据结构包含完整的广告设置：
- series: 广告系列设置
- adGroup: 广告组设置
- regionGroup: 地区组定向设置
- derived: 派生设置
"""

from typing import Optional
from pydantic import BaseModel, Field


class Series(BaseModel):
    """广告系列设置"""
    purchaseType: str = Field("竞拍", description="购买类型")
    seriesType: str = Field("销量", description="系列类型")
    objectiveType: str = Field("广告系列预算", description="目标类型")
    budgetType: str = Field("单日预算", description="预算类型")
    budget: float = Field(0, description="预算金额")
    currency: str = Field("USD", description="货币类型")
    targetPrice: str = Field("最高数量或价值", description="目标价格")
    optimizationMethod: str = Field("标准", description="优化方式")
    flowOptimization: str = Field("不限", description="流量优化")
    flowOptimizationAmount: float = Field(0, description="流量优化金额")
    targetValue: str = Field("", description="目标值")


class SeriesUpdate(BaseModel):
    """广告系列设置（更新用，所有字段可选）"""
    purchaseType: Optional[str] = Field(None, description="购买类型")
    seriesType: Optional[str] = Field(None, description="系列类型")
    objectiveType: Optional[str] = Field(None, description="目标类型")
    budgetType: Optional[str] = Field(None, description="预算类型")
    budget: Optional[float] = Field(None, description="预算金额")
    currency: Optional[str] = Field(None, description="货币类型")
    targetPrice: Optional[str] = Field(None, description="目标价格")
    optimizationMethod: Optional[str] = Field(None, description="优化方式")
    flowOptimization: Optional[str] = Field(None, description="流量优化")
    flowOptimizationAmount: Optional[float] = Field(None, description="流量优化金额")
    targetValue: Optional[str] = Field(None, description="目标值")


class AdGroup(BaseModel):
    """广告组设置"""
    conversionLocation: str = Field("WEBSITE", description="转化位置")
    performanceGoal: str = Field("OFFSITE_CONVERSIONS", description="成效目标")
    conversionEvent: str = Field("PURCHASE", description="转化事件")
    schedule_start_time: str = Field("", description="排期开始时间")
    schedule_end_time: str = Field("", description="排期结束时间")


class AdGroupUpdate(BaseModel):
    """广告组设置（更新用，所有字段可选）"""
    conversionLocation: Optional[str] = Field(None, description="转化位置")
    performanceGoal: Optional[str] = Field(None, description="成效目标")
    conversionEvent: Optional[str] = Field(None, description="转化事件")
    schedule_start_time: Optional[str] = Field(None, description="排期开始时间")
    schedule_end_time: Optional[str] = Field(None, description="排期结束时间")


class RegionGroup(BaseModel):
    """地区组定向设置"""
    deliveryPosition: str = Field("网站", description="投放位置")
    optimizationTarget: str = Field("OFFSITE_CONVERSIONS", description="优化目标")
    billingEvent: str = Field("IMPRESSIONS", description="计费事件")
    conversionGoal: str = Field("PURCHASE", description="转化目标")
    conversionLocation: str = Field("APP", description="转化位置")
    applicationId: str = Field("", description="应用ID")
    objectStoreUrl: str = Field("", description="对象存储URL")
    country: str = Field("", description="国家代码")
    language: str = Field("", description="语言")
    ageRangeStart: int = Field(18, description="年龄范围起始")
    ageStart: int = Field(18, description="年龄起始")
    ageRangeEnd: int = Field(65, description="年龄范围结束")
    gender: str = Field("", description="性别: 空字符串表示不限, 1=男, 2=女")
    publisher_platforms: list[str] = Field(default_factory=list, description="发布平台列表")
    device_platforms: list[str] = Field(default_factory=list, description="设备平台列表")
    user_os: list[str] = Field(default_factory=list, description="用户操作系统列表")
    user_device: list[str] = Field(default_factory=list, description="用户设备列表")
    user_os_version: str = Field("", description="用户操作系统版本")
    isNewModelEnabled: bool = Field(False, description="是否启用新模型")
    isExpanded: bool = Field(False, description="是否展开")


class RegionGroupUpdate(BaseModel):
    """地区组定向设置（更新用，所有字段可选）"""
    deliveryPosition: Optional[str] = Field(None, description="投放位置")
    optimizationTarget: Optional[str] = Field(None, description="优化目标")
    billingEvent: Optional[str] = Field(None, description="计费事件")
    conversionGoal: Optional[str] = Field(None, description="转化目标")
    conversionLocation: Optional[str] = Field(None, description="转化位置")
    applicationId: Optional[str] = Field(None, description="应用ID")
    objectStoreUrl: Optional[str] = Field(None, description="对象存储URL")
    country: Optional[str] = Field(None, description="国家代码")
    language: Optional[str] = Field(None, description="语言")
    ageRangeStart: Optional[int] = Field(None, description="年龄范围起始")
    ageStart: Optional[int] = Field(None, description="年龄起始")
    ageRangeEnd: Optional[int] = Field(None, description="年龄范围结束")
    gender: Optional[str] = Field(None, description="性别")
    publisher_platforms: Optional[list[str]] = Field(None, description="发布平台列表")
    device_platforms: Optional[list[str]] = Field(None, description="设备平台列表")
    user_os: Optional[list[str]] = Field(None, description="用户操作系统列表")
    user_device: Optional[list[str]] = Field(None, description="用户设备列表")
    user_os_version: Optional[str] = Field(None, description="用户操作系统版本")
    isNewModelEnabled: Optional[bool] = Field(None, description="是否启用新模型")
    isExpanded: Optional[bool] = Field(None, description="是否展开")


class ConversionEventOption(BaseModel):
    """转化事件选项"""
    value: str = Field("", description="值")
    label: str = Field("", description="标签")


class Derived(BaseModel):
    """派生设置"""
    conversionEventLabel: str = Field("转化事件", description="转化事件标签")
    shouldShowConversionEvent: bool = Field(True, description="是否显示转化事件")
    isValueOptimizationDisabled: bool = Field(False, description="是否禁用价值优化")
    isAppLocationDisabled: bool = Field(True, description="是否禁用应用位置")
    currentConversionEventOptions: list[ConversionEventOption] = Field(
        default_factory=lambda: [ConversionEventOption()],
        description="当前转化事件选项"
    )


class DerivedUpdate(BaseModel):
    """派生设置（更新用，所有字段可选）"""
    conversionEventLabel: Optional[str] = Field(None, description="转化事件标签")
    shouldShowConversionEvent: Optional[bool] = Field(None, description="是否显示转化事件")
    isValueOptimizationDisabled: Optional[bool] = Field(None, description="是否禁用价值优化")
    isAppLocationDisabled: Optional[bool] = Field(None, description="是否禁用应用位置")
    currentConversionEventOptions: Optional[list[ConversionEventOption]] = Field(
        None, description="当前转化事件选项"
    )


class Settings(BaseModel):
    """完整设置"""
    series: Series = Field(default_factory=Series, description="广告系列设置")
    adGroup: AdGroup = Field(default_factory=AdGroup, description="广告组设置")
    regionGroup: RegionGroup = Field(default_factory=RegionGroup, description="地区组定向设置")
    derived: Derived = Field(default_factory=Derived, description="派生设置")


class SettingsUpdate(BaseModel):
    """完整设置（更新用，所有字段可选）"""
    series: Optional[SeriesUpdate] = Field(None, description="广告系列设置")
    adGroup: Optional[AdGroupUpdate] = Field(None, description="广告组设置")
    regionGroup: Optional[RegionGroupUpdate] = Field(None, description="地区组定向设置")
    derived: Optional[DerivedUpdate] = Field(None, description="派生设置")


class AdCreateTemplateCreate(BaseModel):
    """创建广告配置模板"""
    name: str = Field(..., description="模板名称，同一用户下唯一")
    real_name: str = Field(..., description="创建者名称")
    description: Optional[str] = Field(None, description="模板描述")
    settings: dict = Field(default_factory=dict, description="完整设置，原样存储")


class AdCreateTemplateUpdate(BaseModel):
    """更新广告配置模板"""
    name: Optional[str] = Field(None, description="模板名称")
    real_name: Optional[str] = Field(None, description="创建者名称")
    description: Optional[str] = Field(None, description="模板描述")
    settings: Optional[dict] = Field(None, description="完整设置，原样替换")


# ==================== 素材模板模型 ====================


class MaterialTemplateCreate(BaseModel):
    """创建素材模板"""
    name: str = Field(..., description="模板名称，同一用户下唯一")
    real_name: str = Field(..., description="创建者名称")
    description: Optional[str] = Field(None, description="模板描述")
    batchTitle: str = Field("", description="标题")
    batchDescription: str = Field("", description="正文")


class MaterialTemplateUpdate(BaseModel):
    """更新素材模板"""
    name: Optional[str] = Field(None, description="模板名称")
    real_name: Optional[str] = Field(None, description="创建者名称")
    description: Optional[str] = Field(None, description="模板描述")
    batchTitle: Optional[str] = Field(None, description="标题")
    batchDescription: Optional[str] = Field(None, description="正文")


# ==================== 广告结构-素材组模型 ====================


class MaterialItem(BaseModel):
    """素材组中的单个素材配置"""
    material_id: str = Field(..., description="素材ID（引用materials集合）")
    title: str = Field(default="", description="广告标题")
    body: str = Field(default="", description="广告正文")
    call_to_action: Optional[str] = Field(default=None, description="CTA按钮类型（如LEARN_MORE, ORDER_NOW等）")


class MaterialGroupCreate(BaseModel):
    """创建素材组请求"""
    name: str = Field(..., min_length=1, max_length=100, description="素材组名称（必填）")
    description: str = Field(default="", max_length=500, description="素材组描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    materials: list[MaterialItem] = Field(..., description="素材列表")


class MaterialGroupUpdate(BaseModel):
    """更新素材组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="素材组名称")
    description: Optional[str] = Field(None, max_length=500, description="素材组描述")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    materials: Optional[list[MaterialItem]] = Field(None, description="素材列表")


class MaterialGroupInDB(BaseModel):
    """素材组数据库存储模型"""
    id: str = Field(..., alias="_id", description="素材组ID")
    name: str = Field(..., description="素材组名称")
    description: str = Field(default="", description="素材组描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    materials: list[MaterialItem] = Field(..., description="素材列表")
    materials_count: int = Field(..., description="素材数量")
    user_id: str = Field(..., description="创建者user_id")
    real_name: str = Field(..., description="创建者姓名")
    created_at: str = Field(..., description="创建时间（ISO格式）")
    updated_at: str = Field(..., description="更新时间（ISO格式）")

    class Config:
        populate_by_name = True


class MaterialGroupHistory(BaseModel):
    """素材组应用历史记录"""
    id: str = Field(..., alias="_id", description="历史记录ID")
    group_id: str = Field(..., description="关联的素材组ID")
    group_name: str = Field(..., description="素材组名称（快照）")
    materials_count: int = Field(..., description="素材数量")
    materials: list[MaterialItem] = Field(..., description="应用时的素材配置快照")
    applied_at: str = Field(..., description="应用时间（ISO格式）")
    user_id: str = Field(..., description="应用操作的用户ID")
    real_name: str = Field(..., description="用户姓名")
    apply_mode: str = Field(..., description="应用方式: replace=替换, append=追加")

    class Config:
        populate_by_name = True