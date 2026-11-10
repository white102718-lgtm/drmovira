"""Meta v24账户展示观测；账单应付不是可用余额，缺失值不补零。"""

import re
from decimal import Decimal

from orbit_api.account_details_contract import iso, observed_fields

# Meta Marketing API currency offsets，不使用ISO小数位推断Meta金额单位。
# https://developers.facebook.com/docs/marketing-api/currencies/
WHOLE_CURRENCIES = frozenset("CLP COP CRC HUF IDR ISK JPY KRW PYG TWD VND".split())
CENT_CURRENCIES = frozenset(
    "AED ARS AUD BDT BOB BRL CAD CHF CNY CZK DKK DZD EGP EUR GBP GTQ HKD HNL "
    "ILS INR KES LKR MOP MXN MYR NGN NIO NOK NZD PEN PHP PKR PLN QAR RON SAR "
    "SEK SGD THB TRY UAH USD UYU ZAR".split()
)
OPTIONAL_FIELDS = (
    "business_name",
    "business{id,name}",
    "is_prepay_account",
    "funding_source_details",
    "disable_reason",
)


def display_text(value):
    if (
        isinstance(value, str)
        and value.strip()
        and len(value) <= 2000
        and not any(ord(c) < 32 for c in value)
    ):
        return value
    return None


def observations(value, observed_at, *, principal=None):
    """仅允许明确展示字段进入观测，过滤付款原始信息及其他敏感响应。"""
    stamp = iso(observed_at)
    currency = value["currency"]
    result = {}

    def text(field, label, code=None):
        label = display_text(label)
        result[field] = dict(
            value=label,
            code=code,
            status="SYNCED" if label is not None else "UNKNOWN",
            reason_code=None if label is not None else "NOT_PROVIDED",
            source="META_GRAPH_METADATA",
            observed_at=stamp,
        )

    text(
        "personal_profile",
        principal.get("name") if isinstance(principal, dict) else None,
        principal.get("id") if isinstance(principal, dict) else None,
    )
    text("business_entity", value.get("business_name"))
    prepay = value.get("is_prepay_account")
    text(
        "payment_type",
        "预付" if prepay is True else "后付" if prepay is False else None,
        "PREPAY" if prepay is True else "POSTPAY" if prepay is False else None,
    )
    funding = value.get("funding_source_details")
    # 只保留Meta用于展示的脱敏说明，不保存卡号、券、原始付款对象或信用额度。
    text("payment_method", funding.get("display_string") if isinstance(funding, dict) else None)
    reason = value.get("disable_reason")
    text(
        "blocked_reason",
        f"Meta 停用原因代码 {reason}"
        if type(reason) is int and reason > 0
        else "无停用原因"
        if reason == 0 and type(reason) is int
        else None,
        str(reason) if type(reason) is int and 0 <= reason < 100000 else None,
    )
    divisor = 1 if currency in WHOLE_CURRENCIES else 100 if currency in CENT_CURRENCIES else None
    for field, source, kind in [
        ("payable", "balance_minor", "BILL"),
        ("lifetime_spend", "amount_spent_minor", "SPEND"),
    ]:
        raw = value.get(source)
        amount = None
        if divisor is not None and isinstance(raw, str) and re.fullmatch(r"[0-9]{1,23}", raw):
            number = Decimal(raw) / divisor
            if number < Decimal("1000000000000000000000"):
                amount = format(number, "f")
        result[field] = dict(
            amount=amount,
            currency=currency,
            kind=kind,
            status="SYNCED" if amount is not None else "UNKNOWN",
            source="META_GRAPH_METADATA",
            business_date=None,
            observed_at=stamp,
        )
    return observed_fields(result, currency)


def business_managers(value):
    """仅返回账户Graph对象直接关联的BM；没有返回不能断言零个BM。"""
    business = value.get("business")
    if (
        isinstance(business, dict)
        and isinstance(business.get("id"), str)
        and re.fullmatch(r"[0-9]{1,64}", business["id"])
        and display_text(business.get("name"))
        and len(business["name"]) <= 255
    ):
        return [{"external_id": business["id"], "name": business["name"]}]
    return None
