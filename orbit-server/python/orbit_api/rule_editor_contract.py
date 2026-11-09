"""规则编辑辅助GET扩展合同；原Rule/MetricProfile对象不变。"""

from dataclasses import dataclass

from orbit_api.errors import OrbitError
from orbit_api.rule_contract import _text, identifier

PURPOSE = "RULE_EDITOR_CURSOR_V1"
SIZES = {20, 50, 100, 200}


def invalid(field):
    raise OrbitError(422, "FIELD_INVALID", "规则编辑候选参数无效", "/" + field)


@dataclass(frozen=True)
class EditorQuery:
    action: str
    rule_id: str | None
    kind: str | None = None
    owner_user_id: str | None = None
    owner_team_id: str | None = None
    q: str = ""
    page_size: int = 50
    cursor: str | None = None


def parse_editor_query(values, *, options=False):
    allowed = {"action", "rule_id"}
    if options:
        allowed |= {"kind", "owner_user_id", "owner_team_id", "q", "page_size", "cursor"}
    if not isinstance(values, dict) or set(values) - allowed:
        raise OrbitError(400, "UNKNOWN_FIELD", "规则辅助入口包含未定义参数")
    action = values.get("action")
    if action not in {"CREATE", "UPDATE"}:
        invalid("action")
    rule_id = values.get("rule_id")
    if action == "CREATE" and rule_id is not None or action == "UPDATE" and rule_id is None:
        invalid("rule_id")
    if rule_id is not None:
        rule_id = identifier(rule_id, "/rule_id")
    if not options:
        return EditorQuery(action, rule_id)
    kind = values.get("kind")
    if kind not in {"OWNER", "PROFILE"}:
        invalid("kind")
    user, team = values.get("owner_user_id"), values.get("owner_team_id")
    if kind == "OWNER" and (user is not None or team is not None):
        invalid("owner_user_id")
    if kind == "PROFILE":
        user, team = identifier(user, "/owner_user_id"), identifier(team, "/owner_team_id")
    q = values.get("q", "")
    q = _text(q, "/q", 100, trim=True) if q != "" else ""
    if kind == "PROFILE" and q:
        q = identifier(q, "/q")
    size = values.get("page_size", 50)
    if isinstance(size, str) and size in {"20", "50", "100", "200"}:
        size = int(size)
    if type(size) is not int or size not in SIZES:
        invalid("page_size")
    cursor = values.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
        invalid("cursor")
    return EditorQuery(action, rule_id, kind, user, team, q, size, cursor)
