"""原跨页账户ScopeRequest合同：先限制原输入数量，禁止静默去重或截断。"""

from dataclasses import dataclass

from orbit_api.account_details_contract import filters
from orbit_api.configuration import _parse_json
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid

MAX_MEMBERS = 50000
MAX_BODY = 2_500_000
FILTER_FIELDS = {"q", "status", "auth_status", "operator_user_id", "vendor_id"}


@dataclass(frozen=True)
class ScopeSelection:
    mode: str
    account_ids: tuple[str, ...]
    query: dict | None
    canonical: str


def invalid(pointer):
    raise OrbitError(422, "FIELD_INVALID", "账户范围选择不符合原合同", pointer)


def parse_scope(raw):
    if len(raw) > MAX_BODY:
        raise OrbitError(413, "BODY_TOO_LARGE", "账户范围请求超过正文上限")
    value = _parse_json(raw)
    if not isinstance(value, dict) or set(value) != {"mode", "account_ids", "filter"}:
        invalid("/")
    if value["mode"] not in ("IDS", "FILTER"):
        invalid("/mode")
    ids = value["account_ids"]
    if not isinstance(ids, list) or len(ids) > MAX_MEMBERS:
        invalid("/account_ids")
    parsed, seen = [], set()
    for index, item in enumerate(ids):
        pointer = f"/account_ids/{index}"
        if not isinstance(item, str):
            invalid(pointer)
        identifier = _uuid(item, pointer)
        if identifier in seen:
            raise OrbitError(422, "DUPLICATE_VALUE", "不能重复选择同一账户", pointer)
        seen.add(identifier)
        parsed.append(identifier)
    if value["mode"] == "IDS":
        if not parsed or value["filter"] is not None:
            invalid("/account_ids")
        query = None
    else:
        original = value["filter"]
        if parsed or not isinstance(original, dict) or set(original) != FILTER_FIELDS:
            invalid("/filter")
        if not isinstance(original["q"], str):
            invalid("/filter/q")
        for field in FILTER_FIELDS - {"q"}:
            if original[field] is not None and not isinstance(original[field], str):
                invalid("/filter/" + field)
        # 复用原账户目录字段/值/名称搜索规范；日期仅影响消耗，不参与成员筛选。
        query = filters({key: val for key, val in original.items() if val is not None})
    normalized = {"mode": value["mode"], "account_ids": sorted(parsed), "filter": value["filter"]}
    if query is not None:
        normalized["filter"] = {
            "q": query["q"],
            "status": query.get("account_status"),
            "auth_status": query.get("auth_status"),
            "operator_user_id": query.get("owner_user_id"),
            "vendor_id": query.get("vendor_id"),
        }
    return ScopeSelection(value["mode"], tuple(sorted(parsed)), query, canonical(normalized))
