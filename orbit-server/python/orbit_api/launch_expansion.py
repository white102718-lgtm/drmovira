"""计划纯展开/预算/命名：不查询平台，不签发预检凭证，不分配广告任务。"""

import copy
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from orbit_api.errors import OrbitError

SHANGHAI = ZoneInfo("Asia/Shanghai")
LAYER_LIMIT = 10000


@dataclass(frozen=True)
class Counts:
    campaign_count: int
    adset_count: int
    ad_count: int


@dataclass(frozen=True, order=True)
class Slot:
    """严格按合同元组排序；复制编号从1开始，各层不得脱离自己的父分支。"""

    account_id: str
    campaign_id: str
    campaign_copy: int
    adset_id: str
    adset_copy: int
    ad_id: str
    ad_copy: int
    asset_type: str = "ANY"

    @property
    def key(self):
        return "/".join(
            str(value)
            for value in (
                self.account_id,
                self.campaign_id,
                self.campaign_copy,
                self.adset_id,
                self.adset_copy,
                self.ad_id,
                self.ad_copy,
            )
        )


def expanded_counts(plan):
    """先做整数乘法保护，绝不先实例化可能百万级的复制笛卡尔积。"""
    campaign_count = adset_count = ad_count = 0
    count = len(plan["account_ids"])
    for campaign in plan["campaigns"]:
        multiplier = count * campaign["copies"]
        campaign_count += multiplier
        for adset in campaign["adsets"]:
            adset_multiplier = multiplier * adset["copies"]
            adset_count += adset_multiplier
            ad_count += adset_multiplier * sum(ad["copies"] for ad in adset["ads"])
    if max(campaign_count, adset_count, ad_count) > LAYER_LIMIT:
        raise OrbitError(422, "PLAN_NODE_LIMIT", "每层展开节点及广告不得超过一万", "/campaigns")
    return Counts(campaign_count, adset_count, ad_count)


def ad_slots(plan):
    expanded_counts(plan)
    slots = []
    for account in sorted(plan["account_ids"]):
        for campaign in sorted(plan["campaigns"], key=lambda row: row["local_id"]):
            for ci in range(1, campaign["copies"] + 1):
                for adset in sorted(campaign["adsets"], key=lambda row: row["local_id"]):
                    for si in range(1, adset["copies"] + 1):
                        for ad in sorted(adset["ads"], key=lambda row: row["local_id"]):
                            slots.extend(
                                Slot(
                                    account,
                                    campaign["local_id"],
                                    ci,
                                    adset["local_id"],
                                    si,
                                    ad["local_id"],
                                    ai,
                                    ad.get("asset_type", "ANY"),
                                )
                                for ai in range(1, ad["copies"] + 1)
                            )
    return slots


def campaign_slots(plan):
    expanded_counts(plan)
    return [
        (account, campaign["local_id"], index)
        for account in sorted(plan["account_ids"])
        for campaign in sorted(plan["campaigns"], key=lambda row: row["local_id"])
        for index in range(1, campaign["copies"] + 1)
    ]


def budget_totals(plan):
    """按真实预算拥有者的副本计费，绝不乘广告副本或跨币种换算相加。"""
    expanded_counts(plan)
    totals = {}
    account_count = len(plan["account_ids"])

    def add(budget, multiplier):
        currency = budget["currency"]
        totals[currency] = totals.get(currency, Decimal(0)) + Decimal(budget["amount"]) * multiplier

    for campaign in plan["campaigns"]:
        factor = account_count * campaign["copies"]
        if campaign.get("budget"):
            add(campaign["budget"], factor)
        for adset in campaign["adsets"]:
            if adset.get("budget"):
                if campaign.get("budget"):
                    raise OrbitError(422, "FIELD_INVALID", "系列与广告组预算不可并存", "/campaigns")
                add(adset["budget"], factor * adset["copies"])
    return [
        {"amount": format(amount, "f"), "currency": currency}
        for currency, amount in sorted(totals.items())
    ]


def naming_date(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("命名时钟必须含可信时区")
    return now.astimezone(SHANGHAI).date()


def campaign_name(*, channel_name, channel_code, nickname, full_name, day, sequence):
    """只生成真实已占用序号的文本；调用方负责事务占号、日期版本和幂等。"""
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("序号必须为正整数")
    if len(str(sequence)) > 30:
        raise OrbitError(409, "NAME_SEQUENCE_EXHAUSTED", "当日命名序列已超出合同上限")
    label = channel_name.strip() or channel_code.strip()
    owner = nickname.strip() or full_name.strip()
    if not label or not owner:
        raise OrbitError(409, "NAMING_SOURCE_UNAVAILABLE", "渠道或负责人命名来源不可用")
    name = f"{label}_{owner}_{day:%Y%m%d}_{sequence:04d}"
    if len(name) > 200:
        raise OrbitError(422, "FIELD_INVALID", "自动生成系列名称超过二百码点", "/campaigns")
    return name


def clone_campaigns(campaigns):
    """模板加载/树克隆深复制并给每个层级新UUID，保留原树兄弟顺序。"""
    result = copy.deepcopy(campaigns)
    for campaign in result:
        campaign["local_id"] = str(uuid4())
        for adset in campaign["adsets"]:
            adset["local_id"] = str(uuid4())
            for ad in adset["ads"]:
                ad["local_id"] = str(uuid4())
    return result
