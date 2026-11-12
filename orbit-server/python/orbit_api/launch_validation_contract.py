"""预检纯冻结协议：摘要承诺输入，不证明权限、平台能力或生产来源。

完整执行树逐节点编码，不物化复制笛卡尔积。仅返回不可变摘要和计数，
调用者仍须在同一生产受理边界核验权威来源、CAS和当前动作权限。
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field

from orbit_api.errors import OrbitError
from orbit_api.launch_contract import (
    MAX_CONFIG_BYTES,
    fail,
    parse_model,
    parse_plan,
    parse_plan_action,
    text_field,
    uuid_field,
)
from orbit_api.launch_expansion import SHANGHAI, Counts, budget_totals, expanded_counts
from orbit_api.reference_contract import StrictInput

SAFE_INTEGER = 9007199254740991
SCHEMA_VERSION = 1
TTL = timedelta(minutes=15)
# 原始10000条slot/name的严格上限可容纳于此内部解析预算；不限制展开树字节数。
REFERENCE_BYTES = 16 * 1024 * 1024
SET_FIELDS = {
    "account_ids",
    "asset_ids",
    "profile_binding_ids",
    "country_codes",
    "locales",
    "special_ad_categories",
}


class AllocationItem(StrictInput):
    slot_key: str = Field(min_length=1, max_length=512)
    account_id: str
    asset_id: str
    asset_revision: int = Field(ge=1, le=SAFE_INTEGER)


class Allocation(StrictInput):
    id: str
    plan_id: str
    plan_revision: int = Field(ge=1, le=SAFE_INTEGER)
    state: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
    task_id: str | None
    algorithm_version: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=0, le=2147483647)
    items: list[AllocationItem] = Field(max_length=10000)
    warnings: list[str] = Field(max_length=100)
    input_hash: str = Field(min_length=64, max_length=64)


class NameItem(StrictInput):
    slot_key: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=200)
    sequence: str = Field(min_length=1, max_length=30, pattern=r"^[0-9]+$")


class NameReservation(StrictInput):
    id: str
    plan_revision: int = Field(ge=1, le=SAFE_INTEGER)
    naming_date: str
    items: list[NameItem] = Field(min_length=1, max_length=10000)


@dataclass(frozen=True)
class FrozenValidation:
    """不携带可变输入或authority标记，不能凭此对象发广告或创建Task。"""

    hash: str
    source_revision: int
    counts: Counts
    budget_totals: tuple[tuple[str, str], ...]
    scope_version: int
    total_dag_node_count: int
    validated_at: datetime
    expires_at: datetime
    naming_date: date


def parse_validation_action(raw, action):
    if action not in {"validate", "execute"}:
        raise ValueError("仅接受原validate/execute请求")
    return parse_plan_action(raw, action)


def _bounded_json(value, limit):
    """先有界编码再解析；禁止先deepcopy或一次序列化任意大的输入。"""
    if isinstance(value, bytes):
        if len(value) > limit:
            raise OrbitError(413, "PAYLOAD_TOO_LARGE", "冻结输入超过解析字节上限", "/")
        return value
    result, size = bytearray(), 0
    try:
        for token in json.JSONEncoder(
            ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).iterencode(value):
            encoded = token.encode("utf-8")
            size += len(encoded)
            if size > limit:
                raise OrbitError(413, "PAYLOAD_TOO_LARGE", "冻结输入超过解析字节上限", "/")
            result.extend(encoded)
        return bytes(result)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise OrbitError(400, "INVALID_STRUCTURE", "冻结输入必须为合法JSON", "/") from None


def _positive(value, field, maximum=SAFE_INTEGER, minimum=1):
    if type(value) is not int or not minimum <= value <= maximum:
        fail((field,), "必须为允许范围内的安全整数")
    return value


def _text(value, parts, maximum, *, minimum=1):
    if not isinstance(value, str):
        fail(parts, "必须为文本")
    return text_field(value, parts, maximum, minimum=minimum)


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("冻结时钟必须为调用者提供的可信aware datetime")
    value = value.astimezone(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def utc_milliseconds(value):
    return _time(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _decimal(value):
    # 只处理已经由原计划/Money合同验证过的十进制字符串；不用浮点。
    result = format(Decimal(value), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _tokens(value, field=None, *, normalize=True):
    """确定性JSON token流。树数组保持原语义序，仅明确的集合规范排序。"""
    if isinstance(value, dict):
        yield "{"
        for index, key in enumerate(sorted(value)):
            if index:
                yield ","
            yield json.dumps(key, ensure_ascii=False)
            yield ":"
            yield from _tokens(
                value[key],
                key,
                normalize=normalize and key not in {"channel_snapshot", "product_snapshot"},
            )
        yield "}"
    elif isinstance(value, (list, tuple)) or (normalize and field == "expanded_tree"):
        if normalize and field in SET_FIELDS:
            value = sorted(value)
        elif normalize and field == "identity_bindings":
            value = sorted(value, key=lambda row: row["account_id"])
        elif normalize and field == "groups":
            value = sorted(value, key=lambda row: row["adset_local_id"])
        elif normalize and field == "ad_overrides":
            value = sorted(value, key=lambda row: row["ad_local_id"])
        yield "["
        for index, item in enumerate(value):
            if index:
                yield ","
            yield from _tokens(item, normalize=normalize)
        yield "]"
    else:
        if normalize and field in {"amount", "spend_cap"} and value is not None:
            value = _decimal(value)
        elif normalize and field in {"start_time", "end_time"} and value is not None:
            value = utc_milliseconds(datetime.fromisoformat(value.replace("Z", "+00:00")))
        yield json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _mapping(items, field):
    result = {}
    for index, row in enumerate(items):
        key = row["slot_key"]
        if key in result:
            fail((field, "items", index, "slot_key"), "slot不得重复")
        result[key] = row
    return result


def _tree(plan, names, allocation):
    """每次只构造一个浅节点；配置子值来自已解析的私有5MiB输入。"""
    identities = {row["account_id"]: row for row in plan["identity_bindings"]}
    for account in sorted(plan["account_ids"]):
        if account not in identities:
            fail(("identity_bindings",), "每个执行账户必须有完整身份映射")
        identity = identities[account]
        groups = {row["adset_local_id"]: row for row in identity["groups"]}
        overrides = {row["ad_local_id"]: row["page_id"] for row in identity["ad_overrides"]}
        for campaign in plan["campaigns"]:
            for ci in range(1, campaign["copies"] + 1):
                prefix = f"{account}/{campaign['local_id']}/{ci}"
                if prefix not in names:
                    fail(("name_reservation_id",), "名称保留必须覆盖所有展开系列")
                yield {
                    "kind": "CAMPAIGN",
                    "key": prefix,
                    "name": names[prefix]["name"],
                    "name_sequence": names[prefix]["sequence"],
                    "configuration": {
                        k: v for k, v in campaign.items() if k not in {"adsets", "copies"}
                    },
                }
                for group in campaign["adsets"]:
                    if not group["ads"] or group["local_id"] not in groups:
                        fail(("identity_bindings",), "每个广告组必须有广告及resolved identity")
                    for si in range(1, group["copies"] + 1):
                        group_key = f"{prefix}/{group['local_id']}/{si}"
                        resolved = {"page_id": identity["page_id"], **groups[group["local_id"]]}
                        yield {
                            "kind": "ADSET",
                            "key": group_key,
                            "identity": resolved,
                            "configuration": {
                                k: v for k, v in group.items() if k not in {"ads", "copies"}
                            },
                        }
                        for ad in group["ads"]:
                            for ai in range(1, ad["copies"] + 1):
                                key = f"{group_key}/{ad['local_id']}/{ai}"
                                if (
                                    key not in allocation
                                    or allocation[key]["account_id"] != account
                                ):
                                    fail(("allocation_id",), "分配必须覆盖所有广告且账户一致")
                                yield {
                                    "kind": "AD",
                                    "key": key,
                                    "identity": {
                                        **resolved,
                                        "page_id": overrides.get(
                                            ad["local_id"], identity["page_id"]
                                        ),
                                    },
                                    "asset": {
                                        k: allocation[key][k]
                                        for k in ("asset_id", "asset_revision")
                                    },
                                    "configuration": {k: v for k, v in ad.items() if k != "copies"},
                                }


def freeze_validation(
    plan,
    *,
    plan_id,
    source_revision,
    allocation,
    name_reservation,
    capability_version,
    policy_version,
    scope_version,
    channel_snapshot,
    product_snapshot,
    currency,
    total_dag_node_count,
    validated_at,
):
    """冻结完整执行输入，绝不验证外部authority或推断平台可执行。

    allocation/name_reservation为原严格公开对象；source_revision为配置源，
    不接head_revision。最终名称、全部素材版本与逐账户identity进入完整树。
    """
    plan_id = uuid_field(plan_id, ("plan_id",))
    source_revision = _positive(source_revision, "source_revision")
    scope_version = _positive(scope_version, "scope_version")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        fail(("currency",), "须显式提供当前账户三位大写币种")
    _positive(total_dag_node_count, "total_dag_node_count", maximum=100000)
    now = _time(validated_at)
    value = parse_plan(_bounded_json(plan, MAX_CONFIG_BYTES))
    from orbit_api.launch_meta_settings import require_meta_capabilities

    require_meta_capabilities(value)
    counts = expanded_counts(value)
    if (
        not value["account_ids"]
        or not counts.ad_count
        or any(not row["adsets"] for row in value["campaigns"])
    ):
        fail(("campaigns",), "完整执行树不得为空")
    if total_dag_node_count < sum((counts.campaign_count, counts.adset_count, counts.ad_count)):
        fail(("total_dag_node_count",), "DAG计数不得少于完整三层业务节点")
    if not 1 <= len(value["asset_ids"]) <= min(500, counts.ad_count):
        fail(("asset_ids",), "素材池须为1至广告数量且不超过500个")
    if value.get("account_scope_snapshot_id"):
        fail(("account_scope_snapshot_id",), "冻结前必须消费范围快照为真实账户")
    alloc = parse_model(_bounded_json(allocation, REFERENCE_BYTES), Allocation)
    names = parse_model(_bounded_json(name_reservation, REFERENCE_BYTES), NameReservation)
    for field in ("id", "plan_id"):
        alloc[field] = uuid_field(alloc[field], ("allocation", field))
    if alloc["task_id"] is not None:
        alloc["task_id"] = uuid_field(alloc["task_id"], ("allocation", "task_id"))
    names["id"] = uuid_field(names["id"], ("name_reservation", "id"))
    if (
        alloc["plan_id"] != plan_id
        or alloc["plan_revision"] != source_revision
        or names["plan_revision"] != source_revision
    ):
        fail(("source_revision",), "名称/分配须绑定同一真实配置源版本")
    if alloc["state"] != "SUCCEEDED" or alloc["algorithm_version"] != "allocation-v1":
        fail(("allocation_id",), "必须提供完整已完成的allocation-v1分配")
    if not re.fullmatch(r"[a-f0-9]{64}", alloc["input_hash"]):
        fail(("allocation", "input_hash"), "分配输入摘要必须为小写SHA256")
    for index, warning in enumerate(alloc["warnings"]):
        text_field(warning, ("allocation", "warnings", index), 500)
    assets = set(value["asset_ids"])
    for row in alloc["items"]:
        for field in ("account_id", "asset_id"):
            row[field] = uuid_field(row[field], ("allocation", field))
        if row["asset_id"] not in assets:
            fail(("allocation_id",), "素材必须来自当前计划池")
    try:
        day = date.fromisoformat(names["naming_date"])
    except (ValueError, TypeError):
        fail(("name_reservation", "naming_date"), "必须为ISO业务日")
    if day.isoformat() != names["naming_date"] or day != now.astimezone(SHANGHAI).date():
        fail(("name_reservation_id",), "名称保留必须属于当前上海业务日")
    for index, row in enumerate(names["items"]):
        row["name"] = text_field(row["name"], ("name_reservation", "items", index, "name"), 200)
    allocations, reservations = (
        _mapping(alloc["items"], "allocation"),
        _mapping(names["items"], "name_reservation"),
    )
    if len(allocations) != counts.ad_count or len(reservations) != counts.campaign_count:
        fail(("allocation_id",), "完整分配和名称数量须与展开树完全一致")
    if any(int(row["sequence"]) < 1 for row in names["items"]) or len(
        {int(row["sequence"]) for row in names["items"]}
    ) != len(reservations):
        fail(("name_reservation_id",), "保留序号不得重复")
    usage = Counter(row["asset_id"] for row in alloc["items"])
    if not value["allow_repeat"] and (
        len(value["asset_ids"]) != counts.ad_count or max(usage.values()) > 1
    ):
        fail(("allow_repeat",), "不重复分配必须一广告一素材且池大小相等")
    revisions = {}
    for row in alloc["items"]:
        if revisions.setdefault(row["asset_id"], row["asset_revision"]) != row["asset_revision"]:
            fail(("allocation_id",), "同一素材不得混用版本")
    try:
        totals = budget_totals(value)
    except OrbitError as error:
        if error.status == 422:
            error.code = "FIELD_VALIDATION_FAILED"
        raise
    if any(row["currency"] != currency for row in totals):
        fail(("currency",), "预算币种必须与当前账户冻结币种一致")
    # 快照仅承诺调用方输入，不解析verified或据其授予authority。
    snapshots = {}
    for key, snapshot in (
        ("channel_snapshot", channel_snapshot),
        ("product_snapshot", product_snapshot),
    ):
        if not isinstance(snapshot, dict) or not snapshot:
            fail((key,), "必须显式提供非空冻结快照")
        snapshots[key] = json.loads(_bounded_json(snapshot, MAX_CONFIG_BYTES))
    document = {
        "schema_version": SCHEMA_VERSION,
        # 原canonical字段名保留plan_revision；其值为配置源，不是状态CAS头。
        "plan_revision": source_revision,
        "plan_id": plan_id,
        "plan": value,
        "allocation": {
            k: v for k, v in alloc.items() if k not in {"items", "warnings", "task_id", "state"}
        },
        "name_reservation": {k: v for k, v in names.items() if k != "items"},
        "capability_version": _text(capability_version, ("capability_version",), 64),
        "policy_version": _text(policy_version, ("policy_version",), 64),
        "scope_version": scope_version,
        **snapshots,
        "currency": currency,
        "activate_after_create": value["activate_after_create"],
        "expanded_tree": _tree(value, reservations, allocations),
    }
    digest = hashlib.sha256()
    for token in _tokens(document):
        digest.update(token.encode("utf-8"))
    return FrozenValidation(
        digest.hexdigest(),
        source_revision,
        counts,
        tuple((row["currency"], _decimal(row["amount"])) for row in totals),
        scope_version,
        total_dag_node_count,
        now,
        now + TTL,
        day,
    )


def is_current(record, now):
    """到期等号即失效；上海午夜即使未满15分钟也失效，未来记录不可用。"""
    now = _time(now)
    return (
        record.validated_at <= now < record.expires_at
        and now.astimezone(SHANGHAI).date() == record.naming_date
    )


def validation_response(
    record=None,
    *,
    errors=(),
    counts=None,
    totals=None,
    scope_version=None,
    total_dag_node_count=None,
):
    """只序列化十字段。空errors并不证明外部授权，store才可选择发布结果。"""
    if len(errors) > 1000:
        fail(("errors",), "字段错误不得超过1000项")
    result_errors = []
    for index, error in enumerate(errors):
        if not isinstance(error, dict) or set(error) != {"path", "code", "message", "constraint"}:
            fail(("errors", index), "必须为原四字段FieldError")
        item = {
            key: _text(error[key], ("errors", index, key), maximum, minimum=minimum)
            for key, maximum, minimum in (
                ("path", 255, 1),
                ("code", 64, 1),
                ("message", 1000, 1),
                ("constraint", 500, 0),
            )
        }
        if not item["path"].startswith("/"):
            fail(("errors", index, "path"), "字段路径必须为JSON pointer")
        result_errors.append(item)
    if record is not None:
        if any(
            value is not None for value in (counts, totals, scope_version, total_dag_node_count)
        ):
            raise ValueError("冻结记录与独立汇总不可混用")
        counts, totals, scope_version, total_dag_node_count = (
            record.counts,
            record.budget_totals,
            record.scope_version,
            record.total_dag_node_count,
        )
    elif not result_errors:
        raise ValueError("成功响应必须有冻结记录；不能以空errors伪造hash")
    if not isinstance(counts, Counts):
        raise ValueError("须提供真实Counts汇总")
    for field in ("campaign_count", "adset_count", "ad_count"):
        _positive(getattr(counts, field), field, maximum=2147483647, minimum=0)
    scope_version = _positive(scope_version, "scope_version")
    _positive(total_dag_node_count, "total_dag_node_count", maximum=2147483647, minimum=0)
    if not isinstance(totals, (tuple, list)) or len(totals) > 100:
        fail(("budget_totals",), "必须提供至多100项真实Money汇总")
    money, currencies = [], set()
    for index, pair in enumerate(totals):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            fail(("budget_totals", index), "汇总须为币种/Decimal金额对")
        currency, amount = pair
        if (
            not isinstance(currency, str)
            or not re.fullmatch(r"[A-Z]{3}", currency)
            or currency in currencies
        ):
            fail(("budget_totals", index, "currency"), "币种必须唯一且为三位大写代码")
        if (
            not isinstance(amount, str)
            or len(amount) > 28
            or not re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]{1,6})?", amount)
        ):
            fail(("budget_totals", index, "amount"), "金额必须为原Money十进制字符串")
        currencies.add(currency)
        money.append({"currency": currency, "amount": _decimal(amount)})
    return {
        "valid": not result_errors,
        "hash": None if result_errors else record.hash,
        "expires_at": None if result_errors else utc_milliseconds(record.expires_at),
        "errors": result_errors,
        "campaign_count": counts.campaign_count,
        "adset_count": counts.adset_count,
        "ad_count": counts.ad_count,
        "budget_totals": money,
        "scope_version": scope_version,
        "total_dag_node_count": total_dag_node_count,
    }
