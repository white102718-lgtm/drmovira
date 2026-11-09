"""规则作用账户的远程筛选候选；不改变原Rule/Scope或授予人员/户商写权。"""

import re
from dataclasses import dataclass

from orbit_api.errors import OrbitError
from orbit_api.rule_contract import _text
from orbit_api.rule_editor_contract import SIZES
from orbit_api.rule_editor_scope_contract import ScopeContext, context

PURPOSE = "RULE_SCOPE_OPTIONS_CURSOR_V1"
KINDS = frozenset({"OPERATOR", "VENDOR"})
OPERATOR_FIELDS = frozenset({"id", "name", "team_id", "team_name", "active"})
VENDOR_FIELDS = frozenset({"id", "name", "alias", "availability"})
PAGE_FIELDS = frozenset({"items", "next_cursor", "data_as_of", "scope_version"})
_UUID_TEXT = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


@dataclass(frozen=True)
class ScopeOptionsQuery:
    context: ScopeContext
    kind: str
    q: str = ""
    page_size: int = 50
    cursor: str | None = None

    @property
    def exact_id(self):
        return self.q.lower() if _UUID_TEXT.fullmatch(self.q) else None


def invalid(field):
    raise OrbitError(422, "FIELD_INVALID", "规则筛选候选参数无效", "/" + field)


def parse_scope_options_query(values):
    allowed = {
        "kind",
        "action",
        "rule_id",
        "owner_user_id",
        "owner_team_id",
        "q",
        "page_size",
        "cursor",
    }
    if not isinstance(values, dict) or set(values) - allowed:
        raise OrbitError(400, "UNKNOWN_FIELD", "规则筛选候选包含未定义参数")
    kind = values.get("kind")
    if type(kind) is not str or kind not in KINDS:
        invalid("kind")
    current = context(values)
    q = values.get("q", "")
    if type(q) is not str:
        invalid("q")
    q = _text(q, "/q", 100, trim=True) if q != "" else ""
    size = values.get("page_size", 50)
    if isinstance(size, str) and size in {"20", "50", "100", "200"}:
        size = int(size)
    if type(size) is not int or size not in SIZES:
        invalid("page_size")
    cursor = values.get("cursor")
    if cursor is not None and (type(cursor) is not str or not 1 <= len(cursor) <= 2048):
        invalid("cursor")
    return ScopeOptionsQuery(current, kind, q, size, cursor)
