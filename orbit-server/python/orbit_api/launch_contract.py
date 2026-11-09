"""投放原合同严格DTO：仅确认草稿结构，不把结构合法等同平台可执行。"""

import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError

from orbit_api.channel_contract import https_url
from orbit_api.errors import OrbitError
from orbit_api.launch_countries import COUNTRY_CODES
from orbit_api.reference_contract import StrictInput, pointer, schema_error

MAX_CONFIG_BYTES = 5 * 1024 * 1024
MAX_NODES = 10000
MONEY = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$")


class PlanOwnership(StrictInput):
    owner_user_id: str
    owner_team_id: str


class Budget(StrictInput):
    owner: Literal["CAMPAIGN", "ADSET"]
    type: Literal["DAILY", "LIFETIME"]
    amount: str
    currency: str
    spend_cap: str | None


class AdConfig(StrictInput):
    local_id: str
    copies: int = Field(ge=1, le=50)
    # 默认None只表达原合同字段可省略；显式null仍被非nullable类型拒绝。
    name: str = None
    title: str = None
    body: str = None
    description: str = None
    url: str | None = None
    url_tags: str = None
    cta: str = None
    asset_type: Literal["ANY", "IMAGE", "VIDEO"] = None


class AdSetConfig(StrictInput):
    local_id: str
    copies: int = Field(ge=1, le=50)
    ads: list[AdConfig] = Field(max_length=MAX_NODES)
    name: str = None
    budget: Budget | None = None
    country_codes: list[str] = Field(default=None, min_length=1, max_length=50)
    age_min: int = Field(default=None, ge=18, le=65)
    age_max: int = Field(default=None, ge=18, le=65)
    locales: list[str] = Field(default=None, max_length=20)
    placements: Literal["AUTO"] = None
    optimization_goal: str = None
    billing_event: str = None
    metric_profile_id: str = None
    start_time: str = None
    end_time: str | None = None


class CampaignConfig(StrictInput):
    local_id: str
    copies: int = Field(ge=1, le=50)
    adsets: list[AdSetConfig] = Field(max_length=MAX_NODES)
    objective: Literal["OUTCOME_SALES", "OUTCOME_APP_PROMOTION"] = None
    buying_type: Literal["AUCTION"] = None
    special_ad_categories: list[str] = Field(default=None, max_length=10)
    budget: Budget | None = None
    bid_strategy: Literal["LOWEST_COST_WITHOUT_CAP"] = None


class GroupIdentity(StrictInput):
    adset_local_id: str
    pixel_id: str | None
    conversion_event: str | None
    application_id: str | None
    object_store_url: str | None


class AdIdentityOverride(StrictInput):
    ad_local_id: str
    page_id: str


class IdentityBinding(StrictInput):
    account_id: str
    page_id: str
    groups: list[GroupIdentity] = Field(max_length=MAX_NODES)
    ad_overrides: list[AdIdentityOverride] = Field(max_length=MAX_NODES)


class PlanWrite(StrictInput):
    name: str
    ownership: PlanOwnership
    account_ids: list[str] = Field(max_length=500)
    channel_id: str | None = None
    campaigns: list[CampaignConfig] = Field(max_length=MAX_NODES)
    identity_bindings: list[IdentityBinding] = Field(max_length=500)
    asset_ids: list[str] = Field(max_length=500)
    allow_repeat: bool
    activate_after_create: bool
    execution_mode: Literal["META_API", "ADSPOWER_UI"]
    account_scope_snapshot_id: str | None = None
    profile_binding_ids: list[str] = Field(default=None, max_length=500)
    workflow_version: str = None
    adapter_version: str = None


def fail(parts, message="字段值不符合投放合同"):
    raise OrbitError(422, "FIELD_VALIDATION_FAILED", message, pointer(parts))


def uuid_field(value, parts):
    try:
        normalized = str(UUID(value))
        if normalized != value.lower():
            raise ValueError
        return normalized
    except (ValueError, AttributeError, TypeError):
        fail(parts, "必须为有效UUID")


def text_field(value, parts, maximum, *, minimum=1, multiline=False):
    value = unicodedata.normalize("NFC", value).strip()
    if not minimum <= len(value) <= maximum:
        fail(parts, "文本码点数量超出允许范围")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        and not (multiline and char == "\n")
        for char in value
    ):
        fail(parts, "文本含不可见控制字符")
    return value


def unique_ids(values, parts):
    result = [uuid_field(value, (*parts, index)) for index, value in enumerate(values)]
    if len(result) != len(set(result)):
        fail(parts, "UUID数组不得重复")
    return result


def _money(value, parts):
    if len(value) > 28 or not MONEY.fullmatch(value):
        fail(parts, "金额必须为至多六位小数的十进制字符串")
    number = Decimal(value)
    if number <= 0 or number > Decimal("1000000"):
        fail(parts, "金额必须大于零且不超过一百万")


def _budget(value, parts, owner):
    if value is None:
        return
    if value["owner"] != owner:
        fail((*parts, "owner"), "预算拥有者与配置层级不一致")
    _money(value["amount"], (*parts, "amount"))
    if value["spend_cap"] is not None:
        _money(value["spend_cap"], (*parts, "spend_cap"))
    if not re.fullmatch(r"[A-Z]{3}", value["currency"]):
        fail((*parts, "currency"), "币种必须为三位大写代码")
    # 此处只检合同。币种存在性/真实minor unit/平台最小预算须另有版本化政策。


def _https(value, parts):
    try:
        return https_url(value)
    except OrbitError as error:
        code = "FIELD_VALIDATION_FAILED" if error.status == 422 else error.code
        raise OrbitError(error.status, code, error.message, pointer(parts)) from None


def _date(value, parts):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})", value):
        fail(parts, "时间必须为含时区偏移的RFC3339日期时间")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(parts, "日期时间无效")


def campaigns(value, prefix=("campaigns",)):
    """逐字段归一化，整棵树local_id唯一；草稿可缺业务必填，已填写值严格。"""
    seen, adsets, ads = set(), set(), set()
    for ci, campaign in enumerate(value):
        cp = (*prefix, ci)
        _node(campaign, cp, seen)
        _budget(campaign.get("budget"), (*cp, "budget"), "CAMPAIGN")
        if "special_ad_categories" in campaign:
            campaign["special_ad_categories"] = [
                text_field(item, (*cp, "special_ad_categories", i), 64)
                for i, item in enumerate(campaign["special_ad_categories"])
            ]
        for si, adset in enumerate(campaign["adsets"]):
            sp = (*cp, "adsets", si)
            _node(adset, sp, seen)
            adsets.add(adset["local_id"])
            _budget(adset.get("budget"), (*sp, "budget"), "ADSET")
            if campaign.get("budget") and adset.get("budget"):
                fail((*sp, "budget"), "系列预算与广告组预算不可并存")
            _texts(
                adset,
                sp,
                {"name": (1, 200), "optimization_goal": (1, 64), "billing_event": (1, 64)},
            )
            if "country_codes" in adset:
                countries = adset["country_codes"]
                for i, country in enumerate(countries):
                    if country not in COUNTRY_CODES:
                        fail((*sp, "country_codes", i), "必须为有效ISO二字母国家代码")
                if len(countries) != len(set(countries)):
                    fail((*sp, "country_codes"), "国家不得重复")
            for i, locale in enumerate(adset.get("locales", [])):
                if not re.fullmatch(r"[0-9]{1,64}", locale):
                    fail((*sp, "locales", i), "语言ID必须为数字字符串")
            if adset.get("age_min", 18) > adset.get("age_max", 65):
                fail((*sp, "age_max"), "年龄上限不得小于下限")
            if "metric_profile_id" in adset:
                adset["metric_profile_id"] = uuid_field(
                    adset["metric_profile_id"], (*sp, "metric_profile_id")
                )
            start = (
                _date(adset["start_time"], (*sp, "start_time")) if "start_time" in adset else None
            )
            end = _date(adset["end_time"], (*sp, "end_time")) if adset.get("end_time") else None
            if start and end and end <= start:
                fail((*sp, "end_time"), "结束时间必须晚于开始时间")
            for ai, ad in enumerate(adset["ads"]):
                ap = (*sp, "ads", ai)
                _node(ad, ap, seen)
                ads.add(ad["local_id"])
                _texts(
                    ad,
                    ap,
                    {
                        "name": (1, 200),
                        "title": (1, 100),
                        "body": (1, 2000),
                        "description": (0, 300),
                        "cta": (1, 64),
                        "url_tags": (0, 1024),
                    },
                )
                if ad.get("url") is not None:
                    ad["url"] = _https(ad["url"], (*ap, "url"))
                if ad.get("url_tags"):
                    tags = ad["url_tags"]
                    if tags.startswith("?") or any(
                        "=" not in item or not item.split("=", 1)[0] for item in tags.split("&")
                    ):
                        fail((*ap, "url_tags"), "链接参数须为key=value且不含问号前缀")
    return adsets, ads


def _node(value, parts, seen):
    value["local_id"] = uuid_field(value["local_id"], (*parts, "local_id"))
    if value["local_id"] in seen:
        fail((*parts, "local_id"), "整份配置的local_id必须唯一")
    seen.add(value["local_id"])


def _texts(value, parts, fields):
    for key, (minimum, maximum) in fields.items():
        if key in value:
            value[key] = text_field(
                value[key], (*parts, key), maximum, minimum=minimum, multiline=key == "body"
            )


def strict_json(raw):
    """独立5MiB上限与重复键拒绝，不能套用目录2MiB解析器。"""
    if not isinstance(raw, bytes):
        raise OrbitError(400, "INVALID_STRUCTURE", "请求必须为JSON字节正文", "/")
    if len(raw) > MAX_CONFIG_BYTES:
        raise OrbitError(413, "PAYLOAD_TOO_LARGE", "计划配置超过五MiB上限", "/")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeError, RecursionError):
        raise OrbitError(400, "INVALID_STRUCTURE", "JSON编码、结构或重复字段无效", "/") from None


def parse_model(raw, model):
    try:
        return model.model_validate(strict_json(raw)).model_dump(exclude_unset=True)
    except ValidationError as error:
        normalized = schema_error(error)
        if normalized.status == 422:
            normalized.code = "FIELD_VALIDATION_FAILED"
        raise normalized from None


def ensure_config_size(value):
    """NFC、默认字段或默认共享成员展开后仍必须满足最终配置大小上限。"""
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_CONFIG_BYTES:
        raise OrbitError(413, "PAYLOAD_TOO_LARGE", "规范配置超过五MiB上限", "/")


def parse_plan(raw):
    value = parse_model(raw, PlanWrite)
    value["name"] = text_field(value["name"], ("name",), 100, minimum=0)
    for key in ("owner_user_id", "owner_team_id"):
        value["ownership"][key] = uuid_field(value["ownership"][key], ("ownership", key))
    for key in ("account_ids", "asset_ids", "profile_binding_ids"):
        if key in value:
            value[key] = unique_ids(value[key], (key,))
    for key in ("channel_id", "account_scope_snapshot_id"):
        if value.get(key) is not None:
            value[key] = uuid_field(value[key], (key,))
    if value.get("account_scope_snapshot_id") and value["account_ids"]:
        fail(("account_ids",), "跨页选择快照与显式账户集合不可同时非空")
    value.setdefault("channel_id", None)
    for key in ("workflow_version", "adapter_version"):
        if key in value:
            value[key] = text_field(value[key], (key,), 64)
    group_ids, ad_ids = campaigns(value["campaigns"])
    binding_ids = set()
    for bi, binding in enumerate(value["identity_bindings"]):
        bp = ("identity_bindings", bi)
        binding["account_id"] = uuid_field(binding["account_id"], (*bp, "account_id"))
        if (
            binding["account_id"] not in value["account_ids"]
            or binding["account_id"] in binding_ids
        ):
            fail((*bp, "account_id"), "身份账户须为已选且不得重复")
        binding_ids.add(binding["account_id"])
        _numeric(binding["page_id"], (*bp, "page_id"))
        for key, ref_key, allowed in (
            ("groups", "adset_local_id", group_ids),
            ("ad_overrides", "ad_local_id", ad_ids),
        ):
            refs = set()
            for ri, item in enumerate(binding[key]):
                rp = (*bp, key, ri)
                item[ref_key] = uuid_field(item[ref_key], (*rp, ref_key))
                if item[ref_key] not in allowed or item[ref_key] in refs:
                    fail((*rp, ref_key), "身份引用须属于当前树且不得重复")
                refs.add(item[ref_key])
                for numeric in ("pixel_id", "application_id", "page_id"):
                    if item.get(numeric) is not None:
                        _numeric(item[numeric], (*rp, numeric))
                if item.get("conversion_event") is not None:
                    item["conversion_event"] = text_field(
                        item["conversion_event"], (*rp, "conversion_event"), 64
                    )
                if item.get("object_store_url") is not None:
                    item["object_store_url"] = _https(
                        item["object_store_url"], (*rp, "object_store_url")
                    )
    ensure_config_size(value)
    return value


def _numeric(value, parts):
    if not re.fullmatch(r"[0-9]{1,64}", value):
        fail(parts, "平台资源ID必须为数字字符串")


class AllocationRequest(StrictInput):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    allow_repeat: bool
    seed: int = Field(ge=0, le=2147483647)
    algorithm_version: Literal["allocation-v1"]


class ValidatePlan(StrictInput):
    allocation_id: str
    name_reservation_id: str


class ExecutePlan(StrictInput):
    hash: str
    activate_ack: bool


def parse_plan_action(raw, action):
    value = parse_model(
        raw,
        {"allocation": AllocationRequest, "validate": ValidatePlan, "execute": ExecutePlan}[action],
    )
    if action == "allocation":
        value["asset_ids"] = unique_ids(value["asset_ids"], ("asset_ids",))
    elif action == "validate":
        for key in ("allocation_id", "name_reservation_id"):
            value[key] = uuid_field(value[key], (key,))
    elif not re.fullmatch(r"[a-f0-9]{64}", value["hash"]):
        fail(("hash",), "预检摘要必须为64位小写十六进制")
    return value
