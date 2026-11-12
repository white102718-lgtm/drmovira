"""Meta显式配置合同；缺省不回填历史草稿，平台能力另行预检。"""

from typing import Literal

from pydantic import Field, field_validator

from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, pointer


class CampaignMetaSettings(StrictInput):
    spending_limit: str | None = None
    advantage_campaign_budget: bool = False
    bid_amount: str | None = None
    roas_goal: str | None = None


class DeviceSettings(StrictInput):
    platforms: list[Literal["MOBILE", "DESKTOP"]] = Field(default_factory=list, max_length=2)
    operating_systems: list[Literal["ANDROID", "IOS"]] = Field(default_factory=list, max_length=2)
    android_models: list[str] = Field(default_factory=list, max_length=100)
    excluded_android_models: list[str] = Field(default_factory=list, max_length=100)
    excluded_ios_models: list[str] = Field(default_factory=list, max_length=100)
    ios_models: list[str] = Field(default_factory=list, max_length=100)
    android_min_version: str | None = None
    android_max_version: str | None = None
    ios_min_version: str | None = None
    ios_max_version: str | None = None


class ManualPlacements(StrictInput):
    facebook: list[
        Literal[
            "FEED",
            "STORY",
            "REELS",
            "RIGHT_COLUMN",
            "MARKETPLACE",
            "VIDEO_FEEDS",
            "SEARCH",
            "INSTREAM_VIDEO",
            "PROFILE_FEED",
            "REELS_OVERLAY",
        ]
    ] = Field(default_factory=list, max_length=10)
    instagram: list[
        Literal[
            "STREAM",
            "STORY",
            "REELS",
            "EXPLORE",
            "EXPLORE_HOME",
            "PROFILE_FEED",
            "SEARCH",
            "PROFILE_REELS",
        ]
    ] = Field(default_factory=list, max_length=8)
    messenger: list[Literal["INBOX", "STORY", "SPONSORED_MESSAGES"]] = Field(
        default_factory=list, max_length=3
    )
    audience_network: list[Literal["CLASSIC", "REWARDED_VIDEO", "INSTREAM_VIDEO"]] = Field(
        default_factory=list, max_length=3
    )
    threads: list[Literal["FEED"]] = Field(default_factory=list, max_length=1)


class AdSetMetaSettings(StrictInput):
    conversion_location: Literal["WEBSITE", "APP"] = "WEBSITE"
    conversion_event: (
        Literal["ADD_TO_CART", "PURCHASE", "COMPLETE_REGISTRATION", "LEAD", "SUBSCRIBE"] | None
    ) = None
    attribution_click_days: Literal[1, 7] = 7
    attribution_view_days: Literal[0, 1] = 1
    audience_mode: Literal["ORIGINAL", "ADVANTAGE"] = "ORIGINAL"
    excluded_country_codes: list[str] = Field(default_factory=list, max_length=50)
    genders: list[Literal["MALE", "FEMALE"]] = Field(default_factory=list, max_length=2)
    excluded_custom_audience_ids: list[str] = Field(default_factory=list, max_length=100)
    manual_placements: ManualPlacements = Field(default_factory=ManualPlacements)
    inventory_filter: Literal["FULL", "STANDARD", "LIMITED"] = "STANDARD"
    audience_network_inventory_filter: Literal["FULL", "STANDARD", "LIMITED"] = "STANDARD"
    devices: DeviceSettings = Field(default_factory=DeviceSettings)

    @field_validator("attribution_click_days", "attribution_view_days", mode="before")
    @classmethod
    def exact_days(cls, value):
        """Literal数值仍需拒绝布尔与浮点，避免Pydantic相等值强制转换。"""
        if type(value) is not int:
            raise ValueError("归因天数必须为整数")
        return value


class AdMetaSettings(StrictInput):
    format: Literal["SINGLE", "CAROUSEL"] = "SINGLE"
    start_time: str | None = None
    end_time: str | None = None
    carousel_asset_ids: list[str] = Field(default_factory=list, max_length=10)


def require_meta_capabilities(plan):
    """现有适配器未证明支持新控制：逐字段拒绝，默认值也不冒充已映射。"""

    def unavailable(parts):
        raise OrbitError(
            503,
            "META_CONFIGURATION_UNAVAILABLE",
            "该Meta配置尚未接入执行能力，请保留草稿等待能力核验",
            pointer(parts),
        )

    def check(settings, parts):
        for key, value in settings.items():
            if isinstance(value, dict):
                check(value, (*parts, key))
            elif value is not None and value != []:
                unavailable((*parts, key))

    for ci, campaign in enumerate(plan["campaigns"]):
        cp = ("campaigns", ci)
        if campaign.get("objective") == "OUTCOME_LEADS":
            unavailable((*cp, "objective"))
        if campaign.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP") != "LOWEST_COST_WITHOUT_CAP":
            unavailable((*cp, "bid_strategy"))
        check(campaign.get("meta_settings") or {}, (*cp, "meta_settings"))
        for si, group in enumerate(campaign["adsets"]):
            sp = (*cp, "adsets", si)
            if group.get("placements") == "MANUAL":
                unavailable((*sp, "placements"))
            check(group.get("meta_settings") or {}, (*sp, "meta_settings"))
            for ai, ad in enumerate(group["ads"]):
                check(ad.get("meta_settings") or {}, (*sp, "ads", ai, "meta_settings"))


def validate_meta_campaign(campaign, cp):
    """已填写配置必须自洽；预算、资源等尚未填写可保留为草稿。"""
    from orbit_api.launch_contract import _money, fail

    meta = campaign.get("meta_settings") or {}
    mp = (*cp, "meta_settings")
    for key in ("spending_limit", "bid_amount", "roas_goal"):
        if meta.get(key) is not None:
            _money(meta[key], (*mp, key))
    strategy = campaign.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP")
    if meta.get("bid_amount") is not None and strategy not in {
        "COST_CAP",
        "LOWEST_COST_WITH_BID_CAP",
    }:
        fail((*mp, "bid_amount"), "费用目标或竞价上限仅适用于对应竞价策略")
    if meta.get("roas_goal") is not None and strategy != "LOWEST_COST_WITH_MIN_ROAS":
        fail((*mp, "roas_goal"), "ROAS目标仅适用于最低ROAS竞价策略")
    if "advantage_campaign_budget" in meta:
        cbo = meta["advantage_campaign_budget"]
        if not cbo and campaign.get("budget"):
            fail((*mp, "advantage_campaign_budget"), "关闭系列预算时预算应配置在广告组")
        if cbo:
            for si, group in enumerate(campaign["adsets"]):
                if group.get("budget"):
                    fail((*cp, "adsets", si, "budget"), "开启系列预算时不可同时设置广告组预算")
    goals = set()
    events = set()
    for si, group in enumerate(campaign["adsets"]):
        sp = (*cp, "adsets", si)
        validate_meta_group(campaign, group, sp)
        if group.get("optimization_goal"):
            goals.add(group["optimization_goal"])
        event = (group.get("meta_settings") or {}).get("conversion_event")
        if event:
            events.add(event)
    # 保留旧草稿原合同；新配置开始填写后复核整个系列。
    if meta or any(g.get("meta_settings") for g in campaign["adsets"]):
        if len(goals) > 1:
            fail((*cp, "adsets"), "同系列的成效目标必须一致")
        if (meta.get("advantage_campaign_budget") or campaign.get("budget")) and len(events) > 1:
            fail((*cp, "adsets"), "系列预算下转化事件必须一致")


def _unique(values, path):
    from orbit_api.launch_contract import fail

    if len(values) != len(set(values)):
        fail(path, "选项不得重复")


def validate_meta_group(campaign, group, sp):
    import re

    from orbit_api.launch_contract import _numeric, fail, text_field
    from orbit_api.launch_countries import COUNTRY_CODES

    meta = group.get("meta_settings") or {}
    mp = (*sp, "meta_settings")
    objective = campaign.get("objective")
    location = meta.get("conversion_location")
    event = meta.get("conversion_event")
    if objective == "OUTCOME_APP_PROMOTION" and location == "WEBSITE":
        fail((*mp, "conversion_location"), "应用推广须使用应用转化位置")
    if objective in {"OUTCOME_SALES", "OUTCOME_LEADS"} and location == "APP":
        fail((*mp, "conversion_location"), "当前系列目标须使用网站转化位置")
    if (location == "APP" or objective == "OUTCOME_APP_PROMOTION") and event:
        fail((*mp, "conversion_event"), "应用目标不可套用网站转化事件")
    if event == "PURCHASE" and objective and objective != "OUTCOME_SALES":
        fail((*mp, "conversion_event"), "购物事件仅适用于销售目标")
    if event == "LEAD" and objective and objective != "OUTCOME_LEADS":
        fail((*mp, "conversion_event"), "潜在客户事件仅适用于潜在客户目标")
    if meta and group.get("optimization_goal") == "VALUE" and event != "PURCHASE":
        fail((*sp, "optimization_goal"), "价值优化仅适用于购物事件")
    if (
        meta
        and objective == "OUTCOME_APP_PROMOTION"
        and group.get("optimization_goal") not in {None, "APP_INSTALLS"}
    ):
        fail((*sp, "optimization_goal"), "应用推广当前仅支持应用安装成效目标")
    if (
        meta
        and objective in {"OUTCOME_SALES", "OUTCOME_LEADS"}
        and group.get("optimization_goal") not in {None, "OFFSITE_CONVERSIONS", "VALUE"}
    ):
        fail((*sp, "optimization_goal"), "网站转化仅支持最大转化或价值成效目标")
    for key in ("excluded_country_codes", "genders", "excluded_custom_audience_ids"):
        _unique(meta.get(key, []), (*mp, key))
    for i, country in enumerate(meta.get("excluded_country_codes", [])):
        if country not in COUNTRY_CODES:
            fail((*mp, "excluded_country_codes", i), "必须为有效ISO二字母国家代码")
        if country in group.get("country_codes", []):
            fail((*mp, "excluded_country_codes", i), "包含与排除地区不能重叠")
    for i, identifier in enumerate(meta.get("excluded_custom_audience_ids", [])):
        _numeric(identifier, (*mp, "excluded_custom_audience_ids", i))
    placements = meta.get("manual_placements") or {}
    for platform, values in placements.items():
        _unique(values, (*mp, "manual_placements", platform))
    selected = any(placements.values())
    if group.get("placements") == "MANUAL" and not selected:
        fail((*mp, "manual_placements"), "手动版位至少选择一项")
    if group.get("placements", "AUTO") == "AUTO" and selected:
        fail((*mp, "manual_placements"), "自动版位不可同时配置手动版位")
    devices = meta.get("devices") or {}
    dp = (*mp, "devices")
    for key, values in devices.items():
        if isinstance(values, list):
            for i, value in enumerate(values):
                values[i] = text_field(value, (*dp, key, i), 100)
            _unique(values, (*dp, key))
    systems = devices.get("operating_systems", [])
    if devices.get("platforms") == ["DESKTOP"] and (
        systems or any(devices.get(k) for k in devices if k != "platforms")
    ):
        fail(dp, "仅桌面设备不可配置移动操作系统或型号")
    for os in ("android", "ios"):
        model_keys = (f"{os}_models", f"excluded_{os}_models")
        if set(devices.get(model_keys[0], [])) & set(devices.get(model_keys[1], [])):
            fail((*dp, model_keys[1]), "包含与排除型号不能重叠")
        version_keys = (f"{os}_min_version", f"{os}_max_version")
        if any(devices.get(k) for k in (*model_keys, *version_keys)) and os.upper() not in systems:
            fail((*dp, "operating_systems"), "型号和版本限制须选择对应操作系统")
        parsed = []
        for key in version_keys:
            value = devices.get(key)
            if value is None:
                parsed.append(None)
                continue
            if not re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){0,2}", value):
                fail((*dp, key), "版本须为至多三段数字，例如17.2.1")
            parts = [int(p) for p in value.split(".")]
            parsed.append(tuple(parts + [0] * (3 - len(parts))))
        if all(v is not None for v in parsed) and parsed[0] > parsed[1]:
            fail((*dp, version_keys[1]), "版本上限不得小于下限")


def validate_meta_ad(ad, ap):
    from orbit_api.launch_contract import _date, fail, unique_ids

    meta = ad.get("meta_settings") or {}
    mp = (*ap, "meta_settings")
    start = _date(meta["start_time"], (*mp, "start_time")) if meta.get("start_time") else None
    end = _date(meta["end_time"], (*mp, "end_time")) if meta.get("end_time") else None
    if start and end and end <= start:
        fail((*mp, "end_time"), "广告结束时间必须晚于开始时间")
    if "carousel_asset_ids" in meta:
        meta["carousel_asset_ids"] = unique_ids(
            meta["carousel_asset_ids"], (*mp, "carousel_asset_ids")
        )
    if meta.get("carousel_asset_ids") and meta.get("format", "SINGLE") != "CAROUSEL":
        fail((*mp, "carousel_asset_ids"), "单图片或视频格式不能配置轮播素材")
    if meta.get("carousel_asset_ids") and len(meta["carousel_asset_ids"]) < 2:
        fail((*mp, "carousel_asset_ids"), "轮播至少需要两个素材")


def validate_meta_identities(plan):
    """组级事件与每个账户身份绑定一致；不制造像素、应用或账户资源。"""
    from orbit_api.launch_contract import fail

    groups = {
        group["local_id"]: (campaign, group)
        for campaign in plan["campaigns"]
        for group in campaign["adsets"]
    }
    for bi, binding in enumerate(plan["identity_bindings"]):
        cbo_events = {}
        for gi, identity in enumerate(binding["groups"]):
            campaign, group = groups[identity["adset_local_id"]]
            meta = group.get("meta_settings") or {}
            if not meta and not campaign.get("meta_settings"):
                continue
            ip = ("identity_bindings", bi, "groups", gi)
            selected = meta.get("conversion_event")
            actual = identity.get("conversion_event")
            if selected and actual and selected != actual:
                fail((*ip, "conversion_event"), "身份转化事件须与广告组设置一致")
            objective = campaign.get("objective")
            if objective == "OUTCOME_APP_PROMOTION" and (actual or identity.get("pixel_id")):
                fail(ip, "应用推广不可配置网站像素或事件")
            if objective in {"OUTCOME_SALES", "OUTCOME_LEADS"} and (
                identity.get("application_id") or identity.get("object_store_url")
            ):
                fail(ip, "网站转化不可配置应用资源")
            event = actual or selected
            if event == "PURCHASE" and objective and objective != "OUTCOME_SALES":
                fail((*ip, "conversion_event"), "购物事件仅适用于销售目标")
            if event == "LEAD" and objective and objective != "OUTCOME_LEADS":
                fail((*ip, "conversion_event"), "潜在客户事件仅适用于潜在客户目标")
            if (campaign.get("meta_settings") or {}).get(
                "advantage_campaign_budget"
            ) or campaign.get("budget"):
                previous = cbo_events.get(campaign["local_id"])
                if event:
                    cbo_events[campaign["local_id"]] = event
                if previous and event and previous != event:
                    fail((*ip, "conversion_event"), "系列预算下转化事件必须一致")
