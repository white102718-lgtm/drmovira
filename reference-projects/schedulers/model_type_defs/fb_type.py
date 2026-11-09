from typing import Literal, TypedDict, List


class ContextualMultiAds(TypedDict):
    enroll_status: Literal["OPT_IN", "OPT_OUT"]


class TargetingAutomation(TypedDict, total=False):
    advantage_audience: int  # 赋能型受众选项，1 表示开启


class CreativeConfig(TypedDict, total=False):
    type: Literal[
        "image",  # 图片广告
        "video",  # 视频广告
        "carousel",  # 轮播广告
    ]
    # 素材来源（三选一）
    path: str  # 方式1: 本地文件路径
    image_hash: str  # 方式2: 已上传的图片hash
    picture: str  # 方式3: 图片URL

    title: str  # 广告标题
    body: str  # 广告正文
    page_welcome_message: "PageWelcomeMessageConfig | str"  # 聊天欢迎模板，直接透传到创意


class PageWelcomeMessageAutoFollowUp(TypedDict, total=False):
    text: str


class PageWelcomeMessageReengagement(TypedDict, total=False):
    text: str
    include_products: bool


class PageWelcomeMessageIceBreaker(TypedDict, total=False):
    title: str
    response: str | None


class PageWelcomeMessageQuickReply(TypedDict, total=False):
    title: str
    content_type: str
    payload: str
    response_type: str


class PageWelcomeMessageTextMessage(TypedDict, total=False):
    text: str
    ice_breakers: List[PageWelcomeMessageIceBreaker]
    quick_replies: List[PageWelcomeMessageQuickReply]


class PageWelcomeMessageTextFormat(TypedDict, total=False):
    customer_action_type: str
    message: PageWelcomeMessageTextMessage


class PageWelcomeMessageConfig(TypedDict, total=False):
    auto_follow_up: PageWelcomeMessageAutoFollowUp
    reengagement: PageWelcomeMessageReengagement
    reengagement_disabled: bool
    type: str
    version: int
    landing_screen_type: str
    media_type: str
    text_format: PageWelcomeMessageTextFormat


class _AdConfigRequired(TypedDict):
    name: str
    status: Literal[
        "ACTIVE",  # Campaign.Status.active - 启用
        "PAUSED",  # Campaign.Status.paused - 暂停
        "DELETED",  # Campaign.Status.deleted - 已删除
        "ARCHIVED",  # Campaign.Status.archived - 已归档
    ]
    creative: CreativeConfig  # 素材创意
    contextual_multi_ads: ContextualMultiAds  # 多广告主广告
    page_id: str  # Facebook 公共主页 ID


class _AdConfigOptional(TypedDict, total=False):
    link_url: str  # 目标链接，互动系列可不传


class AdConfig(_AdConfigRequired, _AdConfigOptional):
    pass


class GeoLocations(TypedDict):
    countries: List[str]  # 国家代码列表，如 ["US", "CN", "JP"]


class _TargetingConfigRequired(TypedDict):
    geo_locations: GeoLocations  # 地理位置
    age_min: int  # 最小年龄 (18-65)
    age_max: int  # 最大年龄 (18-65)
    publisher_platforms: List[
        Literal[
            "facebook",
            "instagram",
            "audience_network",
            "messenger",
            "whatsapp",
            "threads",
        ]
    ]  # 发布平台


class _TargetingConfigOptional(TypedDict, total=False):
    device_platforms: List[Literal["mobile", "desktop"]]  # 设备平台
    user_os: List[
        Literal["Android", "iOS", "Android_ver_2.0_and_above", "iOS_ver_2.0_and_above"]
    ]  # 操作系统
    locales: List[int]  # 语言代码列表 (可选)，如 [6] 英语, [24] 中文, [28] 西班牙语
    genders: List[Literal[1, 2]]  # 性别定向，1=男 2=女，不传=不限
    targeting_automation: TargetingAutomation  # 广告自动化配置


class TargetingConfig(_TargetingConfigRequired, _TargetingConfigOptional):
    pass


class PromotedObject(TypedDict, total=False):
    pixel_id: str  # Facebook Pixel ID
    page_id: str  # Facebook 公共主页 ID
    custom_event_type: Literal[
        "PURCHASE",  # 购物
        "ADD_TO_CART",  # 加购
        "LEAD",  # 潜在客户
        "COMPLETE_REGISTRATION",  # 完成注册
        "ADD_PAYMENT_INFO",  # 添加支付信息
        "INITIATE_CHECKOUT",  # 发起结账
        "SEARCH",  # 搜索
        "VIEW_CONTENT",  # 查看内容
    ]


class _AdSetConfigRequired(TypedDict):
    name: str
    optimization_goal: Literal[
        "OFFSITE_CONVERSIONS",  # AdSet.OptimizationGoal.offsite_conversions - 转化量最大化（网站）
        "VALUE",  # AdSet.OptimizationGoal.value - 转化价值最大化（网站）
        "POST_ENGAGEMENT",  # AdSet.OptimizationGoal.post_engagement - 帖子互动
    ]  # 转化发生位置和成效目标
    billing_event: Literal[
        "IMPRESSIONS",  # AdSet.BillingEvent.impressions - 展示次数 (最常用)
        "LINK_CLICKS",  # AdSet.BillingEvent.link_clicks - 链接点击
        "APP_INSTALLS",  # AdSet.BillingEvent.app_installs - 应用安装
        "POST_ENGAGEMENT",  # AdSet.BillingEvent.post_engagement - 帖子互动
        "PAGE_LIKES",  # AdSet.BillingEvent.page_likes - 主页赞
        "THRUPLAY",  # AdSet.BillingEvent.thruplay - 视频播放
    ]
    bid_strategy: Literal[
        "LOWEST_COST_WITHOUT_CAP",  # AdSet.BidStrategy.lowest_cost_without_cap - 最低成本-无上限 (推荐)
        "LOWEST_COST_WITH_BID_CAP",  # AdSet.BidStrategy.lowest_cost_with_bid_cap - 最低成本-有竞价上限
        "COST_CAP",  # AdSet.BidStrategy.cost_cap - 成本上限
        "LOWEST_COST_WITH_MIN_ROAS",  # AdSet.BidStrategy.lowest_cost_with_min_roas - 最低成本-最低ROAS
    ]
    targeting: TargetingConfig  # 受众定向
    status: Literal[
        "ACTIVE",  # Campaign.Status.active - 启用
        "PAUSED",  # Campaign.Status.paused - 暂停
        "DELETED",  # Campaign.Status.deleted - 已删除
        "ARCHIVED",  # Campaign.Status.archived - 已归档
    ]
    ads: List[AdConfig]  # 广告列表


class _AdSetConfigOptional(TypedDict, total=False):
    bid_amount: int  # 出价金额，单位：分；COST_CAP=单次成效费用目标 / LOWEST_COST_WITH_BID_CAP=竞价上限
    daily_budget: int  # 广告组每日预算，单位：分 (如 10000 = $100.00)
    lifetime_budget: int  # 广告组总预算，单位：分 (与 daily_budget 二选一)
    promoted_object: PromotedObject  # 推广对象 - Pixel和转化事件配置（转化优化时必需）
    start_time: str  # 排期开始时间，ISO 8601格式，如 2024-01-15T10:00:00+0800
    end_time: str  # 排期结束时间，ISO 8601格式，如 2024-01-20T23:59:59+0800
    is_dynamic_creative: bool  # 动态素材，开启后创意走 asset_feed_spec


class AdSetConfig(_AdSetConfigRequired, _AdSetConfigOptional):
    pass


class _CampaignConfigRequired(TypedDict):
    name: str
    objective: Literal[
        "OUTCOME_SALES",  # Campaign.Objective.outcome_sales - 销量 (转化)
        "OUTCOME_TRAFFIC",  # Campaign.Objective.outcome_traffic - 流量
        "OUTCOME_LEADS",  # Campaign.Objective.outcome_leads - 潜在客户
        "OUTCOME_ENGAGEMENT",  # Campaign.Objective.outcome_engagement - 互动
        "OUTCOME_AWARENESS",  # Campaign.Objective.outcome_awareness - 认知度
        "OUTCOME_APP_PROMOTION",  # Campaign.Objective.outcome_app_promotion - 应用推广
    ]
    status: Literal[
        "ACTIVE",  # Campaign.Status.active - 启用
        "PAUSED",  # Campaign.Status.paused - 暂停
        "DELETED",  # Campaign.Status.deleted - 已删除
        "ARCHIVED",  # Campaign.Status.archived - 已归档
    ]
    adsets: List[AdSetConfig]  # 广告组列表
    is_adset_budget_sharing_enabled: bool  # 是否启用广告组预算共享 (CBO)，通常为 False


class _CampaignConfigOptional(TypedDict, total=False):
    campaign_type: Literal[
          "sales",  # 销量系列
          "engagement",  # 互动系列
    ]
    bid_strategy: Literal[
        "LOWEST_COST_WITHOUT_CAP",  # AdSet.BidStrategy.lowest_cost_without_cap - 最低成本-无上限 (推荐)
        "LOWEST_COST_WITH_BID_CAP",  # AdSet.BidStrategy.lowest_cost_with_bid_cap - 最低成本-有竞价上限
        "COST_CAP",  # AdSet.BidStrategy.cost_cap - 成本上限
        "LOWEST_COST_WITH_MIN_ROAS",  # AdSet.BidStrategy.lowest_cost_with_min_roas - 最低成本-最低ROAS
    ]
    daily_budget: int  # 系列每日预算，单位：分 (如 50000 = $500.00/天)
    lifetime_budget: int  # 系列总预算，单位：分 (与 daily_budget 二选一)
    special_ad_categories: List[
        Literal[
            "CREDIT",  # Campaign.SpecialAdCategories.credit - 信贷
            "EMPLOYMENT",  # Campaign.SpecialAdCategories.employment - 就业
            "HOUSING",  # Campaign.SpecialAdCategories.housing - 住房
            "ISSUES_ELECTIONS_POLITICS",  # Campaign.SpecialAdCategories.issues_elections_politics - 社会议题、选举或政治
            "FINANCIAL_PRODUCTS_SERVICES",  # Campaign.SpecialAdCategories.financial_products_services - 金融产品和服务
            "ONLINE_GAMBLING_AND_GAMING",  # Campaign.SpecialAdCategories.online_gambling_and_gaming - 在线赌博和游戏
        ]
    ]  # 特殊广告类别，通常为空列表 []
    special_ad_category_country: List[str]  # 特殊广告类别地区(国家代码列表)
    buying_type: Literal[
        "AUCTION",  # 竞拍 (默认，最常用)
        "RESERVED",  # 预定
    ]


class CampaignConfig(_CampaignConfigRequired, _CampaignConfigOptional):
    pass


class AccountConfigDict(TypedDict):
    account_id: str
    account_name: str
    page_id: str
    page_name: str
    pixel_id: str
    pixel_name: str
    game_platform: str
    country: str
    agent_line: str
    link_url: str | None
    campaigns: List[CampaignConfig]


class RecommendedCombinations:
    """推荐的配置组合（objective + buying_type + optimization_goal + billing_event + bid_strategy）"""

    # 销量/转化目标 - 竞拍
    SALES = {
        "objective": "OUTCOME_SALES",
        "buying_type": "AUCTION",
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }

    # 流量目标 - 竞拍
    TRAFFIC = {
        "objective": "OUTCOME_TRAFFIC",
        "buying_type": "AUCTION",
        "optimization_goal": "LINK_CLICKS",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }

    # 潜在客户目标 - 竞拍
    LEADS = {
        "objective": "OUTCOME_LEADS",
        "buying_type": "AUCTION",
        "optimization_goal": "LEAD_GENERATION",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }

    # 互动目标 - 竞拍
    ENGAGEMENT = {
        "objective": "OUTCOME_ENGAGEMENT",
        "buying_type": "AUCTION",
        "optimization_goal": "POST_ENGAGEMENT",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }
