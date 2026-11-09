from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Optional, Tuple, Dict, List
from app.model_type_defs.ad_operation import OpType
from pydantic import BaseModel, Field, model_validator
from zoneinfo import ZoneInfo

ENGAGEMENT_DESTINATION_TYPES = {
    "MESSENGER",
    "WHATSAPP",
    "INSTAGRAM_DIRECT",
    "ON_AD",
    "FACEBOOK",
    "INSTAGRAM_PROFILE",
}
SALES_DESTINATION_TYPES = {
    "APP",
    "WEBSITE",
    "PHONE_CALL",
    "MESSENGER",
}
ENGAGEMENT_OPTIMIZATION_GOALS = {
    "CONVERSATIONS",
    "LINK_CLICKS",
}


def _normalize_schedule_time(value: str | None) -> str | None:
    if value in (None, ""):
        return None

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

    # 排期是账户当地墙上时间，原样透传，时区在 create_ad 按 timezone_name 落地。
    # 带偏移的是旧模板存量(前端曾提交 UTC)，仍按北京还原。
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))

    return dt.strftime("%Y-%m-%d %H:%M:%S")


class GeoLocations(BaseModel):
    countries: list[str] = Field(..., description="国家代码列表，如 ['US', 'CN', 'JP']")


class TargetingAutomation(BaseModel):
    advantage_audience: int = Field(0, description="赋能型受众选项，1 表示开启")


class TargetingConfig(BaseModel):
    geo_locations: GeoLocations = Field(..., description="地理位置")
    age_range: Tuple[int, int] = Field(default=(18, 65))
    publisher_platforms: Optional[
        list[
            Literal[
                "facebook",
                "instagram",
                "audience_network",
                "messenger",
                "whatsapp",
                "threads",
            ]
        ]
    ] = Field(None, description="发布平台")
    device_platforms: Optional[list[Literal["mobile", "desktop"]]] = Field(
        None, description="设备平台类型"
    )
    user_device: Optional[
        list[
            Literal[
                "Android_Smartphone",
                "Android_Tablet",
                "iPhone",
                "iPad",
                "iPod",
            ]
        ]
    ] = Field(None, description="用户设备类型")
    user_os: Optional[list[str]] = Field(
        None,
        description="用户操作系统，支持基础格式(Android/iOS)或版本限制格式({OS}_ver_{version}_and_above 或 {OS}_ver_{min}_to_{max})"
        "Android_ver_13.0_and_above → Android 13.0 及以上"
        "iOS_ver_14.0_and_above → iOS 14.0 及以上",
    )
    locales: Optional[list[int]] = Field(None, description="语言代码列表")
    genders: Optional[list[Literal[1, 2]]] = Field(
        None, description="性别定向，1=男 2=女，不传=不限"
    )
    targeting_automation: Optional[TargetingAutomation] = Field(
        default_factory=lambda: TargetingAutomation(advantage_audience=1),
        description="进阶赋能型功能",
    )


class PromotedObject(BaseModel):
    pixel_id: Optional[str] = Field(None, description="Facebook Pixel ID")
    custom_event_type: Optional[
        Literal[
            "PURCHASE",
            "ADD_TO_CART",
            "ADD_TO_WISHLIST",
            "LEAD",
            "COMPLETE_REGISTRATION",
            "ADD_PAYMENT_INFO",
            "INITIATE_CHECKOUT",
            "START_TRIAL",
            "DONATE",
            "SEARCH",
            "VIEW_CONTENT",
            "SUBSCRIBE",
        ]
    ] = Field(None, description="转化事件类型")
    custom_conversion_id: Optional[str] = Field(None, description="自定义转化 ID")
    application_id: Optional[str] = Field(
        None, description="应用ID，如 736796522803757"
    )
    object_store_url: Optional[str] = Field(
        None,
        description="应用商店链接，如 https://play.google.com/store/apps/details?id=xxx",
    )
    page_id: Optional[str] = Field(
        None, description="公共主页 ID，用于页面互动/消息目标"
    )
    product_set_id: Optional[str] = Field(None, description="产品集 ID，用于动态广告")
    product_catalog_id: Optional[str] = Field(None, description="产品目录 ID")
    event_id: Optional[str] = Field(None, description="事件 ID，用于活动推广")
    offer_id: Optional[str] = Field(None, description="优惠 ID，用于优惠广告")
    offline_conversion_data_set_id: Optional[str] = Field(
        None, description="线下转化数据集 ID"
    )


class SalesConfig(BaseModel):
    promoted_object: Optional[PromotedObject] = Field(
        None, description="销量/转化类推广对象配置"
    )


class EngagementConfig(BaseModel):
    subtype: Literal["MESSENGER_CHAT"] = Field(
        ..., description="互动子类型，当前仅支持 Messenger 聊天"
    )
    channel: Literal["MESSENGER"] = Field(
        "MESSENGER", description="互动渠道，当前仅支持 Messenger"
    )
    page_id: Optional[str] = Field(None, description="用于聊天互动的主页 ID")


class WelcomeMessageIceBreaker(BaseModel):
    title: str = Field(..., description="破冰问题文案")
    response: Optional[str] = Field(None, description="破冰问题响应")


class WelcomeMessageQuickReply(BaseModel):
    title: str = Field(..., description="快捷回复展示文案")
    content_type: Literal["text"] = Field("text", description="快捷回复类型")
    response_type: Literal["text"] = Field("text", description="快捷回复响应类型")


class WelcomeMessageTextMessage(BaseModel):
    text: str = Field(..., description="文本模式欢迎语")
    ice_breakers: list[WelcomeMessageIceBreaker] = Field(
        default_factory=list, description="破冰问题列表"
    )
    quick_replies: list[dict] = Field(default_factory=list, description="快捷回复列表")


class WelcomeMessageTextFormat(BaseModel):
    customer_action_type: Literal["ice_breakers", "quick_replies"] = Field(
        ..., description="文本模式用户动作类型"
    )
    message: WelcomeMessageTextMessage = Field(..., description="文本模式消息体")


class WelcomeMessageAttachment(BaseModel):
    type: Literal["template", "video"] = Field(..., description="附件类型")
    payload: dict = Field(..., description="附件载荷")


class WelcomeMessageMediaMessage(BaseModel):
    text: str = Field(..., description="媒体模式欢迎语")
    attachment: WelcomeMessageAttachment = Field(..., description="媒体附件")
    quick_replies: list[WelcomeMessageQuickReply] = Field(
        default_factory=list, description="媒体模式快捷回复"
    )


class WelcomeMessageImageFormat(BaseModel):
    customer_action_type: Literal["quick_replies"] = Field(
        "quick_replies", description="图片模式用户动作类型"
    )
    message: WelcomeMessageMediaMessage = Field(..., description="图片模式消息体")


class WelcomeMessageVideoFormat(BaseModel):
    customer_action_type: Literal["quick_replies"] = Field(
        "quick_replies", description="视频模式用户动作类型"
    )
    message: WelcomeMessageMediaMessage = Field(..., description="视频模式消息体")


class WelcomeMessageFollowUp(BaseModel):
    text: str = Field(..., description="自动跟进文案")


class WelcomeMessageReengagement(BaseModel):
    text: str = Field(..., description="再互动文案")
    include_products: bool = Field(False, description="是否包含商品信息")


class PageWelcomeMessageConfig(BaseModel):
    auto_follow_up: Optional[WelcomeMessageFollowUp] = Field(
        None, description="自动跟进文案"
    )
    reengagement: Optional[WelcomeMessageReengagement] = Field(
        None, description="再互动文案"
    )
    reengagement_disabled: bool = Field(False, description="是否禁用再互动")
    media_type: Literal["text", "image", "video"] = Field(
        ..., description="欢迎语媒体类型"
    )
    text_format: Optional[WelcomeMessageTextFormat] = Field(
        None, description="文本模式配置"
    )
    image_format: Optional[WelcomeMessageImageFormat] = Field(
        None, description="图片模式配置"
    )
    video_format: Optional[WelcomeMessageVideoFormat] = Field(
        None, description="视频模式配置"
    )
    type: Optional[str] = Field(
        "VISUAL_EDITOR", description="欢迎语编辑器类型，默认 VISUAL_EDITOR"
    )
    version: Optional[int] = Field(2, description="欢迎语配置版本，默认 2")
    landing_screen_type: Optional[str] = Field(
        "welcome_message", description="落地页类型，默认 welcome_message"
    )

    @model_validator(mode="after")
    def validate_media_config(self):
        config_map = {
            "text": self.text_format,
            "image": self.image_format,
            "video": self.video_format,
        }
        selected = config_map.get(self.media_type)
        if selected is None:
            raise ValueError(f"media_type={self.media_type} 时必须提供对应的格式配置")

        for media_type, config in config_map.items():
            if media_type != self.media_type and config is not None:
                raise ValueError(
                    f"media_type={self.media_type} 时不能同时提供 {media_type}_format"
                )
        return self


class ContextualMultiAds(BaseModel):
    enroll_status: Literal["OPT_IN", "OPT_OUT"] = Field(..., description="注册状态")


class CallToAction(BaseModel):
    type: Literal[
        "ORDER_NOW",
        "SUBSCRIBE",
        "LEARN_MORE",
        "DOWNLOAD",
        "BOOK_NOW",
        "SHOP_NOW",
        "LISTEN_NOW",
        "PLAY_GAME",
        "WATCH_MORE",
        "SIGN_UP",
        "INSTALL_APP",
        "NO_BUTTON",
        "APPLY_NOW",
        "BUY_TICKETS",
        "CONTACT_US",
        "GET_OFFER",
        "GET_QUOTE",
        "GET_SHOWTIMES",
        "REQUEST_TIME",
        "SEE_MENU",
        "MESSAGE_PAGE",
    ] = Field("PLAY_GAME", description="行动号召按钮类型")
    value: Optional[Dict] = Field(None)

    @model_validator(mode="after")
    def check_value(self):
        if self.type == "MESSAGE_PAGE":
            if self.value is None:
                raise ValueError("type=MESSAGE_PAGE 时，value 必填")
        else:
            if self.value is not None:
                raise ValueError("只有 type=MESSAGE_PAGE 时，才允许传 value")

        return self


class CreativeEnhancement(BaseModel):
    """创意增强开关:前端传 bool。多数项汇成 degrees_of_freedom_spec;
    add_music / website_destination_optimization 为透传项,下游分别落到
    asset_feed_spec.audios 与 destination_spec.website,不入本 spec。"""

    show_summary: bool = Field(True, description="显示摘要")
    inline_comment: bool = Field(True, description="相关评论")
    enhance_cta: bool = Field(True, description="增强行动号召")
    reveal_details_over_time: bool = Field(True, description="逐步显示详情")
    show_destination_blurbs: bool = Field(True, description="显示精选")
    text_optimizations: bool = Field(True, description="文案改进")
    text_transformation_types: bool = Field(
        True, description="文案优化(TEXT_LIQUIDITY 文案流动性,degrees_of_freedom_spec 顶层)"
    )
    image_animation: bool = Field(False, description="添加动画(图片)")
    image_brightness_and_contrast: bool = Field(False, description="调整亮度和对比度(图片)")
    image_templates: bool = Field(False, description="叠加文字(图片)")
    image_touchups: bool = Field(False, description="润色(图片)")
    image_replace: bool = Field(False, description="增强素材文案(图片)")
    detail_to_layout: bool = Field(False, description="为广告布局添加详情(视频)")
    video_auto_crop: bool = Field(False, description="视频润色(视频)")
    video_filtering: bool = Field(False, description="添加视频特效(视频)")
    add_music: bool = Field(
        True, description="添加音乐(图片随机配乐,下游走 asset_feed_spec.audios,不入本 spec)"
    )
    website_destination_optimization: bool = Field(
        True, description="网站位置优化(下游走 destination_spec.website)"
    )


class CreativeConfig(BaseModel):
    type: Optional[Literal["image", "video", "carousel"]] = Field(
        None, description="素材类型"
    )
    path: Optional[str] = Field(None, description="本地文件路径")
    image_hash: Optional[str] = Field(None, description="已上传的图片hash")
    picture: Optional[str] = Field(None, description="图片URL")
    title: Optional[str] = Field(None, description="广告标题 (对应 link_data.name)")
    body: Optional[str] = Field(None, description="广告正文 (对应 link_data.message)")
    description: Optional[str] = Field(
        None, description="广告描述 (对应 link_data.description)"
    )
    call_to_action: Optional[CallToAction] = Field(None, description="行动号召配置")
    page_welcome_message: Optional[PageWelcomeMessageConfig] = Field(
        None, description="聊天创建工具配置，会由下游转换为创意层 page_welcome_message"
    )
    video_id: Optional[str] = Field(None, description="已上传的视频ID")
    basename: Optional[str] = Field(
        None, description="素材文件名（不含后缀），用于创意历史还原"
    )
    img: Optional[str] = Field(None, description="素材缩略图base64，用于创意历史还原")
    post_id: Optional[str] = Field(None, description="引用原贴ID")
    enhancement: Optional[CreativeEnhancement] = Field(
        None, description="创意增强开关;缺省则不下发 degrees_of_freedom_spec,下游回退固定项"
    )
    degrees_of_freedom_spec: Optional[Dict] = Field(
        None, description="由 enhancement 汇总,前端无需传"
    )

    @model_validator(mode="after")
    def validate_post_id_mode(self):
        if not self.post_id:
            return self

        if any(
            value is not None
            for value in (
                self.type,
                self.path,
                self.image_hash,
                self.video_id,
                self.picture,
                self.title,
                self.body,
                self.description,
                self.call_to_action,
                self.page_welcome_message,
            )
        ):
            raise ValueError("传入 post_id 时，不能同时传其他 creative 字段")
        return self

    @model_validator(mode="after")
    def build_degrees_of_freedom_spec(self):
        if self.enhancement is None:
            return self

        e = self.enhancement
        # add_music / website_destination_optimization 是透传项,不汇进 features

        def _status(flag: bool) -> dict:
            return {"enroll_status": "OPT_IN" if flag else "OPT_OUT"}

        features = {
            "show_summary": _status(e.show_summary),
            "inline_comment": _status(e.inline_comment),
            "enhance_cta": _status(e.enhance_cta),
            "reveal_details_over_time": _status(e.reveal_details_over_time),
            "show_destination_blurbs": _status(e.show_destination_blurbs),
            "text_optimizations": {
                **_status(e.text_optimizations),
                "customizations": {"text_extraction": _status(e.text_optimizations)},
            },
        }
        # carousel 按图片处理(非视频)
        if self.type == "video":
            features.update(
                {
                    "ads_with_benefits": _status(e.detail_to_layout),
                    "video_auto_crop": _status(e.video_auto_crop),
                    "video_filtering": _status(e.video_filtering),
                }
            )
        else:
            features.update(
                {
                    "image_animation": _status(e.image_animation),
                    "image_brightness_and_contrast": _status(
                        e.image_brightness_and_contrast
                    ),
                    "image_templates": _status(e.image_templates),
                    "image_touchups": _status(e.image_touchups),
                    "replace_media_text": _status(e.image_replace),
                }
            )

        self.degrees_of_freedom_spec = {"creative_features_spec": features}
        if e.text_transformation_types:
            self.degrees_of_freedom_spec["text_transformation_types"] = ["TEXT_LIQUIDITY"]
        return self


class AdConfig(BaseModel):
    name: str = Field(..., description="广告名称")
    page_id: Optional[str] = Field(..., description="Facebook 公共主页 ID")
    link_url: Optional[str] = Field(None, description="目标链接")
    status: Literal["ACTIVE", "PAUSED", "DELETED", "ARCHIVED"] = Field(
        ..., description="广告状态"
    )
    creative: CreativeConfig = Field(..., description="素材创意")
    contextual_multi_ads: Optional[ContextualMultiAds] = Field(
        default_factory=lambda: ContextualMultiAds(enroll_status="OPT_IN"),
        description="多广告主广告配置",
    )
    target_account_name: Optional[str] = Field(
        None,
        description="指定该广告只分配到这个账户名下;为空=不限户,与 target_adset_name 一起为空时走随机均分",
    )
    target_adset_name: Optional[str] = Field(
        None,
        description="指定该广告只分配到这些广告组名下(按模板 adset.name 匹配);为空=不限组",
    )
    display_link: Optional[str] = Field(
        None,
        description="指定显示链接，分到object_story_spec下的link_caption",
    )
    by_tag: bool = Field(
        False,
        description="按标签分组分配:与其它 by_tag 广告标签集互相包含(含相等)时不进同一广告组",
    )


class AdSetConfig(BaseModel):
    name: str = Field(..., description="广告组名称")
    optimization_goal: (
        Literal[
            "OFFSITE_CONVERSIONS",
            "VALUE",
            "APP_INSTALLS",
            "LINK_CLICKS",
            "CONVERSATIONS",
        ]
        | None
    ) = Field(None, description="优化目标")
    destination_type: Optional[
        Literal[
            "APP",
            "WEBSITE",
            "PHONE_CALL",
            "MESSENGER",
            "WHATSAPP",
            "INSTAGRAM_DIRECT",
            "ON_AD",
            "FACEBOOK",
            "INSTAGRAM",
            "INSTAGRAM_PROFILE",
        ]
    ] = Field(None, description="目标类型")
    billing_event: (
        Literal[
            "IMPRESSIONS",
            "LINK_CLICKS",
            "APP_INSTALLS",
            "POST_ENGAGEMENT",
            "PAGE_LIKES",
            "THRUPLAY",
        ]
        | None
    ) = Field(None, description="计费事件")
    bid_strategy: Literal[
        "LOWEST_COST_WITHOUT_CAP",
        "LOWEST_COST_WITH_BID_CAP",
        "COST_CAP",
        "LOWEST_COST_WITH_MIN_ROAS",
    ] = Field(..., description="竞价策略")
    bid_amount: Optional[int] = Field(
        None,
        description="出价金额，单位：分；COST_CAP=单次成效费用目标 / LOWEST_COST_WITH_BID_CAP=竞价上限，这两种策略下必填",
    )
    targeting: TargetingConfig = Field(..., description="受众定向配置")
    is_dynamic_creative: bool = Field(
        False, description="动态素材，开启后由 FB 自动组合素材/文案（单图单文案也会包成 asset_feed_spec）"
    )
    brand_safety_content_filter_levels: list[
        Literal[
            "FACEBOOK_RELAXED",
            "FACEBOOK_STANDARD",
            "FACEBOOK_STRICT",
            "AN_RELAXED",
            "AN_STANDARD",
            "AN_STRICT",
        ]
    ] = Field(
        default=["FACEBOOK_RELAXED", "AN_RELAXED"],
        description="库存筛选(品牌安全)，默认扩展库存，与 FB 默认一致",
    )
    status: Literal["ACTIVE", "PAUSED", "DELETED", "ARCHIVED"] = Field(
        ..., description="广告组状态"
    )
    daily_budget: Optional[int] = Field(
        None, description="每日预算，单位：分 (如 10000 = $100.00)"
    )
    lifetime_budget: Optional[int] = Field(
        None, description="总预算，单位：分 (与 daily_budget 二选一)"
    )
    promoted_object: Optional[PromotedObject] = Field(
        None, description="推广对象 - Pixel和转化事件配置（转化优化时必需）"
    )
    sales_config: Optional[SalesConfig] = Field(None, description="销量目标的额外配置")
    engagement_config: Optional[EngagementConfig] = Field(
        None, description="互动目标的额外配置"
    )
    start_time: Optional[str] = Field(
        None, description="排期开始时间，ISO 8601格式，如 2024-01-15T10:00:00+0800"
    )
    end_time: Optional[str] = Field(
        None, description="排期结束时间，ISO 8601格式，如 2024-01-20T23:59:59+0800"
    )

    @model_validator(mode="after")
    def apply_objective_defaults(self):
        if (
            self.bid_strategy in ("COST_CAP", "LOWEST_COST_WITH_BID_CAP")
            and not self.bid_amount
        ):
            raise ValueError(f"bid_strategy={self.bid_strategy} 时 bid_amount 必填")

        if self.destination_type == "INSTAGRAM":
            self.destination_type = "INSTAGRAM_PROFILE"

        self.start_time = _normalize_schedule_time(self.start_time)
        self.end_time = _normalize_schedule_time(self.end_time)

        if (
            self.sales_config
            and self.sales_config.promoted_object
            and not self.promoted_object
        ):
            self.promoted_object = self.sales_config.promoted_object

        if self.engagement_config:
            if self.destination_type is None:
                self.destination_type = "MESSENGER"
            if self.optimization_goal is None:
                self.optimization_goal = "CONVERSATIONS"
            if self.billing_event is None:
                self.billing_event = "IMPRESSIONS"

            promoted_object_data = {}
            if self.promoted_object:
                promoted_object_data = self.promoted_object.model_dump(
                    exclude_none=True
                )
            if self.engagement_config.page_id:
                promoted_object_data["page_id"] = self.engagement_config.page_id
            self.promoted_object = PromotedObject(**promoted_object_data)
        return self


class CampaignBaseConfig(BaseModel):
    name: str = Field(..., description="广告系列名称")
    objective: Literal[
        "OUTCOME_SALES",
        "OUTCOME_TRAFFIC",
        "OUTCOME_LEADS",
        "OUTCOME_ENGAGEMENT",
        "OUTCOME_AWARENESS",
        "OUTCOME_APP_PROMOTION",
    ] = Field(..., description="广告目标")
    status: Literal["ACTIVE", "PAUSED", "DELETED", "ARCHIVED"] = Field(
        ..., description="广告系列状态"
    )
    is_adset_budget_sharing_enabled: bool = Field(
        ..., description="是否启用广告组预算共享 (CBO)，通常为 False"
    )
    bid_strategy: Optional[
        Literal[
            "LOWEST_COST_WITHOUT_CAP",
            "LOWEST_COST_WITH_BID_CAP",
            "COST_CAP",
            "LOWEST_COST_WITH_MIN_ROAS",
        ]
    ] = Field("LOWEST_COST_WITHOUT_CAP", description="竞价策略")
    special_ad_categories: list[
        Literal[
            "CREDIT",
            "EMPLOYMENT",
            "HOUSING",
            "ISSUES_ELECTIONS_POLITICS",
            "FINANCIAL_PRODUCTS_SERVICES",
            "ONLINE_GAMBLING_AND_GAMING",
        ]
    ] = Field(default=[], description="特殊广告类别，通常为空列表 []")
    special_ad_category_country: Optional[list[str]] = Field(
        None, description="特殊广告类别地区(国家代码列表)，仅 special_ad_categories 非空时下发"
    )
    buying_type: Optional[Literal["AUCTION", "RESERVED"]] = Field(
        default="AUCTION", description="购买类型: 竞拍(默认) 或 预定"
    )
    daily_budget: Optional[int] = Field(
        None,
        description="系列每日预算，单位：分 (如 50000 = $500.00/天), 设置了自动变成CBO系列预算",
    )
    lifetime_budget: Optional[int] = Field(
        None, description="系列总预算，单位：分 (与 daily_budget 二选一)"
    )
    auto_regulation_identity: bool = Field(
        default=False, description="自动广告主:投受限地区时复用本账户已验证广告主身份"
    )

    @model_validator(mode="after")
    def drop_country_without_categories(self):
        if not self.special_ad_categories:
            self.special_ad_category_country = None
        return self


class CampaignConfig(CampaignBaseConfig):
    adsets: list[AdSetConfig] = Field(..., description="广告组列表")

    @model_validator(mode="after")
    def validate_objective_params(self):
        _validate_adsets_for_objective(self.objective, self.adsets)
        return self


class CampaignFlowConfig(CampaignBaseConfig):
    adsets: Optional[list[AdSetConfig]] = Field(
        default_factory=list,
        description="兼容流程模式下的广告组列表",
    )

    @model_validator(mode="after")
    def validate_objective_params(self):
        _validate_adsets_for_objective(self.objective, self.adsets or [])
        return self


class AccountInfo(BaseModel):
    account_id: str = Field(..., description="广告账户ID, 格式: 'act_xxxxx'")
    account_name: str = Field(..., description="广告账户名称")
    person_id: str = Field(..., description="个号id")
    person_name: str = Field(..., description="个号名称")
    page_id: str = Field(..., description="公共主页ID")
    page_name: str = Field(..., description="公共主页名称")
    pixel_id: Optional[str] = Field(None, description="像素ID")
    pixel_name: Optional[str] = Field(None, description="像素名称")
    instagram_user_id: Optional[str] = Field(
        None, description="是否设置Instagram账户为公共主页"
    )


class AccountGroup(BaseModel):
    game_platform: str = Field(..., description="项目名称，如 '测试-批量上广告'")
    country: str = Field(..., description="投放地区，如 '印度'")
    agent_line: str = Field(..., description="任务线名称，如 'test01'")
    link_url: Optional[str] = Field(None, description="投放链接")
    account_ids: list[AccountInfo] = Field(..., description="广告账户信息列表")


class AdCreateConfig(BaseModel):
    account_groups: list[AccountGroup] = Field(
        ..., description="按项目/地区/任务线分组的账户配置列表"
    )
    ads: list[AdConfig] = Field(..., description="广告列表")
    campaigns: list[CampaignConfig] = Field(..., description="广告系列列表")
    ad_num: int = Field()
    adset_num: int = Field()
    campaign_num: int = Field()

    @model_validator(mode="after")
    def validate_page_welcome_messages(self):
        if any(
            campaign.objective == "OUTCOME_ENGAGEMENT" for campaign in self.campaigns
        ):
            for index, ad in enumerate(self.ads):
                if not ad.creative.page_welcome_message:
                    raise ValueError(
                        f"互动目标广告的 ads[{index}] 必须提供 creative.page_welcome_message"
                    )
        return self


class CampaignCreateRequest(BaseModel):
    account_groups: list[AccountGroup] = Field(
        ..., description="按项目/地区/任务线分组的账户配置列表"
    )
    campaigns: list[CampaignFlowConfig] = Field(..., description="广告系列列表")
    ads: Optional[list[AdConfig]] = Field(None, description="兼容旧流程的广告列表")
    ad_num: Optional[int] = Field(None, gt=0, description="兼容旧流程的每组广告数量")
    adset_num: Optional[int] = Field(None, gt=0, description="兼容旧流程的广告组数量")
    campaign_num: Optional[int] = Field(
        None, gt=0, description="兼容旧流程的广告系列数量"
    )

    @model_validator(mode="after")
    def validate_campaign_ads_dependency(self):
        if not self.ads:
            return self

        has_adsets = any(campaign.adsets for campaign in self.campaigns)
        if not has_adsets:
            raise ValueError("传入 ads 时，campaigns 下必须包含 adsets")
        if any(
            campaign.objective == "OUTCOME_ENGAGEMENT" for campaign in self.campaigns
        ):
            for index, ad in enumerate(self.ads):
                if not ad.creative.page_welcome_message:
                    raise ValueError(
                        f"互动目标广告的 ads[{index}] 必须提供 creative.page_welcome_message"
                    )
        return self


class AdSetCreateRequest(BaseModel):
    account_groups: list[AccountGroup] = Field(
        ..., description="按项目/地区/任务线分组的账户配置列表"
    )
    adsets: list[AdSetConfig] = Field(..., description="广告组列表")
    ads: Optional[list[AdConfig]] = Field(None, description="兼容旧流程的广告列表")
    ad_num: Optional[int] = Field(None, gt=0, description="兼容旧流程的每组广告数量")

    @model_validator(mode="after")
    def validate_engagement_ads_dependency(self):
        if not self.ads:
            return self

        if any(adset.engagement_config for adset in self.adsets):
            for index, ad in enumerate(self.ads):
                if not ad.creative.page_welcome_message:
                    raise ValueError(
                        f"互动目标广告的 ads[{index}] 必须提供 creative.page_welcome_message"
                    )
        return self


class AdsCreateRequest(BaseModel):
    account_groups: list[AccountGroup] = Field(
        ..., description="按项目/地区/任务线分组的账户配置列表"
    )
    ads: list[AdCreateConfig] = Field(..., description="广告列表")
    ad_num: int = Field(..., gt=0, description="每个账户创建的广告数量")


class SubtaskQuery(BaseModel):
    task_name: str = Field(..., description="项目名称")
    subtask_name: str = Field(..., description="任务线名称")


class SubtaskAccountQueryRequest(BaseModel):
    queries: list[SubtaskQuery] = Field(..., description="批量查询条件列表")
    real_name: Optional[str] = Field(None, description="选择过滤某个用户下的户或者部门")
    page: int = Field(default=1, ge=1, description="账户列表页码")
    page_size: int = Field(default=50, ge=1, le=200, description="每页账户数量")
    account_name: List[str] | None = Field(None, description="广告账户名称模糊搜索")
    account_id: List[str] | None = Field(None, description="广告账户ID模糊搜索")
    pixel_name_filter: str | None = Field(None, description="像素名称模糊搜索")
    person_name: str | None = Field(None, description="按关联个号精确过滤账户")
    status: str | None = Field(None, description="账户状态筛选")
    meta_only: bool = Field(
        default=False, description="只返回任务线配置信息, 跳过账户资产聚合"
    )


class OperateRequest(BaseModel):
    level: str = Field(..., description="广告对象层级: campaign / adset / ad")
    id: str = Field(..., description="FB 对象 ID")
    op_type: OpType = Field(
        ..., description="操作类型: budget / pause / start / delete"
    )
    name: Optional[str] = Field(None, description="广告对象名称")
    value: Optional[int] = Field(None, description="预算值（仅 budget 操作），单位：分")
    object_type: Optional[Literal["personal", "system"]] = Field(
        None, description="使用个号或者系统开发者操作"
    )
    personal_id: Optional[str] = Field(None, description="指定个号ID")


class SimpleAdConfig(BaseModel):
    """简化广告配置，page_id/link_url 由上层请求提供"""

    name: str = Field(..., description="广告名称（对应素材文件名）")
    status: Literal["ACTIVE", "PAUSED", "DELETED", "ARCHIVED"] = Field(
        ..., description="广告状态"
    )
    creative: CreativeConfig = Field(..., description="素材创意")
    contextual_multi_ads: Optional[ContextualMultiAds] = Field(
        default_factory=lambda: ContextualMultiAds(enroll_status="OPT_IN"),
        description="多广告主广告配置",
    )


class AdDeleteItem(BaseModel):
    id: str = Field(..., description="广告ID")
    name: Optional[str] = Field(None, description="广告名称")


class CreateAdsetOperation(BaseModel):
    """单个广告组下的创建操作"""

    adset_id: str = Field(..., description="广告组ID")
    campaign_name: Optional[str] = Field(None, description="系列名称（用于追踪标识）")
    adset_name: Optional[str] = Field(None, description="组名称（用于追踪标识）")
    page_id: Optional[str] = Field(
        None, description="本组使用的主页ID;缺省时回退到请求级 page_id"
    )
    ads: list[SimpleAdConfig] = Field(..., description="要创建的广告列表")


class CreateAdsRequest(BaseModel):
    """批量创建广告"""

    account_id: str = Field(..., description="广告账户ID, 格式: 'act_xxxxx'")
    page_id: str = Field(..., description="账户级默认主页ID(各 operation 未指定时使用)")
    link_url: str = Field(..., description="投放链接")
    object_type: Optional[Literal["personal", "system"]] = Field(
        None, description="使用个号或者系统开发者操作"
    )
    personal_id: Optional[str] = Field(None, description="指定个号ID")
    operations: list[CreateAdsetOperation] = Field(
        ..., description="按广告组分组的创建列表"
    )


class DeleteAdsRequest(BaseModel):
    """批量删除广告"""

    ads: list[AdDeleteItem] = Field(..., description="要删除的广告列表")
    object_type: Optional[Literal["personal", "system"]] = Field(
        None, description="使用个号或者系统开发者操作"
    )
    personal_id: Optional[str] = Field(
        None, description="指定个号ID（choose_dev 返回的 id）"
    )


class QueryAdStructureRequest(BaseModel):
    """查询广告结构树"""

    campaign_ids: Optional[list[str]] = Field(None, description="系列ID列表")
    adset_ids: Optional[list[str]] = Field(None, description="广告组ID列表")
    ad_ids: Optional[list[str]] = Field(None, description="广告ID列表")


class DeletePreviewRequest(BaseModel):
    """删除前预览: 由选中行解析出所属系列, 返回 账户>系列>组>广告 完整结构树"""

    level: str = Field(..., description="选中行所在层级: campaign / adset / ad")
    ids: list[str] = Field(..., description="选中的对象ID列表")


class ChooseDevRequest(BaseModel):
    """根据系列/组/广告 ID 查询可用开发者"""

    campaign_ids: Optional[list[str]] = Field(None, description="系列ID列表")
    adset_ids: Optional[list[str]] = Field(None, description="广告组ID列表")
    ad_ids: Optional[list[str]] = Field(None, description="广告ID列表")


def _validate_adsets_for_objective(objective: str, adsets: list[AdSetConfig]):
    for adset in adsets:
        if objective == "OUTCOME_ENGAGEMENT":
            if not adset.engagement_config:
                raise ValueError("互动目标广告组必须提供 engagement_config")
            if adset.sales_config:
                raise ValueError("互动目标广告组不能同时提供 sales_config")
            if adset.destination_type not in ENGAGEMENT_DESTINATION_TYPES:
                raise ValueError(
                    "互动目标广告组的 destination_type 必须为 "
                    f"{', '.join(sorted(ENGAGEMENT_DESTINATION_TYPES))} 之一"
                )
            if adset.optimization_goal not in ENGAGEMENT_OPTIMIZATION_GOALS:
                raise ValueError(
                    "互动目标广告组的 optimization_goal 必须为 "
                    f"{', '.join(sorted(ENGAGEMENT_OPTIMIZATION_GOALS))} 之一"
                )
            if not adset.promoted_object or not adset.promoted_object.page_id:
                raise ValueError(
                    "Messenger 聊天互动广告组必须提供 promoted_object.page_id"
                )
            forbidden_fields = [
                "pixel_id",
                "custom_event_type",
                "custom_conversion_id",
                "application_id",
                "object_store_url",
            ]
            if any(getattr(adset.promoted_object, field) for field in forbidden_fields):
                raise ValueError(
                    "互动目标广告组不能传 Pixel、转化事件或应用推广相关 promoted_object 字段"
                )
        else:
            if adset.engagement_config:
                raise ValueError("非互动目标广告组不能提供 engagement_config")
            if (
                adset.destination_type
                and adset.destination_type not in SALES_DESTINATION_TYPES
            ):
                raise ValueError(
                    "非互动目标广告组的 destination_type 必须为 "
                    f"{', '.join(sorted(SALES_DESTINATION_TYPES))} 之一"
                )
            if adset.optimization_goal is None:
                raise ValueError("非互动目标广告组必须提供 optimization_goal")
            if adset.billing_event is None:
                raise ValueError("非互动目标广告组必须提供 billing_event")
