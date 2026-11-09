"""规则账户picker/冻结技术扩展；原Scope五字段和成员三字段保持不变。"""

from dataclasses import dataclass

from orbit_api.account_details_contract import filters
from orbit_api.account_scope_contract import MAX_BODY, ScopeSelection, parse_scope
from orbit_api.configuration import _parse_json
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_contract import _text, identifier
from orbit_api.rule_editor_contract import SIZES, parse_editor_query

PURPOSE = "RULE_EDITOR_SCOPE_CURSOR_V1"
FILTER_FIELDS = {"q", "status", "auth_status", "operator_user_id", "vendor_id"}


def invalid(field):
    raise OrbitError(422, "FIELD_INVALID", "规则账户选择参数无效", "/" + field)


@dataclass(frozen=True)
class ScopeContext:
    action: str
    rule_id: str | None
    owner_user_id: str
    owner_team_id: str

    @property
    def ownership(self):
        return {"owner_user_id": self.owner_user_id, "owner_team_id": self.owner_team_id}


@dataclass(frozen=True)
class ScopeQuery:
    context: ScopeContext | None
    query: dict
    page_size: int = 50
    cursor: str | None = None


@dataclass(frozen=True)
class ScopeWrite:
    context: ScopeContext
    selection: ScopeSelection
    canonical: str


def context(values):
    parsed = parse_editor_query(
        {key: values[key] for key in ("action", "rule_id") if key in values}
    )
    return ScopeContext(
        parsed.action,
        parsed.rule_id,
        identifier(values.get("owner_user_id"), "/owner_user_id"),
        identifier(values.get("owner_team_id"), "/owner_team_id"),
    )


def parse_scope_query(values, *, members=False):
    allowed = (
        {"q", "page_size", "cursor"}
        if members
        else FILTER_FIELDS
        | {"action", "rule_id", "owner_user_id", "owner_team_id", "page_size", "cursor"}
    )
    if not isinstance(values, dict) or set(values) - allowed:
        raise OrbitError(400, "UNKNOWN_FIELD", "规则账户入口包含未定义参数")
    size = values.get("page_size", 50)
    if isinstance(size, str) and size in {"20", "50", "100", "200"}:
        size = int(size)
    if type(size) is not int or size not in SIZES:
        invalid("page_size")
    cursor = values.get("cursor")
    if cursor is not None and (type(cursor) is not str or not 1 <= len(cursor) <= 2048):
        invalid("cursor")
    if members:
        q = values.get("q", "")
        q = _text(q, "/q", 100, trim=True) if q != "" else ""
        return ScopeQuery(None, {"q": q}, size, cursor)
    return ScopeQuery(
        context(values),
        filters({key: val for key, val in values.items() if key in FILTER_FIELDS}),
        size,
        cursor,
    )


def parse_scope_write(raw):
    if len(raw) > MAX_BODY:
        raise OrbitError(413, "BODY_TOO_LARGE", "规则账户冻结请求超过正文上限")
    value = _parse_json(raw)
    if not isinstance(value, dict) or set(value) != {"action", "rule_id", "ownership", "selection"}:
        invalid("")
    ownership = value["ownership"]
    if not isinstance(ownership, dict) or set(ownership) != {"owner_user_id", "owner_team_id"}:
        invalid("ownership")
    current = context({"action": value["action"], "rule_id": value["rule_id"]} | ownership)
    selection = parse_scope(canonical(value["selection"]).encode())
    normalized = {
        "action": current.action,
        "rule_id": current.rule_id,
        "ownership": current.ownership,
        "selection": _parse_json(selection.canonical.encode()),
    }
    return ScopeWrite(current, selection, canonical(normalized))
