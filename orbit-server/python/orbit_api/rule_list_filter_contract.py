"""规则列表已引用对象的最小只读候选；不是编辑/人员/指标目录。"""

from dataclasses import dataclass

from pydantic import Field

from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput
from orbit_api.rule_contract import MAX_SAFE, _utc, identifier

KINDS = frozenset({"OPERATOR", "METRIC_PROFILE", "CHANNEL"})
SIZES = frozenset({20, 50, 100, 200})
PURPOSE = "RULE_CURSOR_V1"
DOMAIN = "RULE_LIST_FILTER_OPTIONS_V1"


@dataclass(frozen=True)
class RuleListFilterQuery:
    kind: str
    page_size: int = 50
    cursor: str | None = None


class RuleListFilterItem(StrictInput):
    id: str
    label: str | None = Field(max_length=255)


class RuleListFilterPage(StrictInput):
    items: list[RuleListFilterItem] = Field(max_length=200)
    next_cursor: str | None = Field(min_length=1, max_length=2048)
    data_as_of: str
    scope_version: int = Field(ge=1, le=MAX_SAFE)


def parse_list_filter_query(values):
    if type(values) is not dict or set(values) - {"kind", "page_size", "cursor"}:
        raise OrbitError(400, "UNKNOWN_FIELD", "规则列表候选包含未定义参数")
    kind = values.get("kind")
    if type(kind) is not str or kind not in KINDS:
        raise OrbitError(422, "FIELD_INVALID", "请选择规则列表候选类型", "/kind")
    size = values.get("page_size", 50)
    if type(size) is str and size in {"20", "50", "100", "200"}:
        size = int(size)
    if type(size) is not int or size not in SIZES:
        raise OrbitError(422, "FIELD_INVALID", "请选择合法每页数量", "/page_size")
    cursor = values.get("cursor")
    if cursor is not None and (type(cursor) is not str or not 1 <= len(cursor) <= 2048):
        raise OrbitError(422, "FIELD_INVALID", "候选游标不合法", "/cursor")
    return RuleListFilterQuery(kind, size, cursor)


def unavailable():
    raise OrbitError(503, "RULE_LIST_FILTER_UNAVAILABLE", "规则列表筛选资料暂不可用")


def response_page(value):
    try:
        result = RuleListFilterPage.model_validate(value)
        _utc(result.data_as_of, "/data_as_of")
        previous = ""
        for item in result.items:
            if identifier(item.id, "/items/id") != item.id or item.id <= previous:
                unavailable()
            previous = item.id
            if item.label is not None:
                # 原标签不trim/回退猜名称；坏持久文本整体503。
                item.label.encode("utf-8", errors="strict")
        return result.model_dump()
    except (ValueError, TypeError, UnicodeError, OrbitError):
        unavailable()
