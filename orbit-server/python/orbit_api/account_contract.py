"""账户导入合同：外部ID始终为字符串，先检查原始上限再逐项规范化和去重。"""

import re
from dataclasses import dataclass

from orbit_api.configuration import _parse_json
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid

MAX_INPUT = 20000
MAX_TOKENS = 500
ROW_STATES = frozenset(
    {
        "WAITING",
        "FETCHING",
        "SUCCEEDED",
        "ALREADY_EXISTS",
        "DUPLICATE",
        "INVALID",
        "FORBIDDEN",
        "OWNERSHIP_CONFLICT",
        "FAILED",
    }
)
TERMINAL = ROW_STATES - {"WAITING", "FETCHING"}
_TOKENS = re.compile(r"[^\s,，;；]+")
_DIGITS = re.compile(r"[0-9]{1,32}\Z")


@dataclass(frozen=True)
class AccountImport:
    vendor_id: str | None
    account_ids_text: str
    owner_user_id: str
    owner_team_id: str


def parse_import(raw):
    """独立扩展POST账户批次；不改变原ImportRequest的三个属性。"""
    if len(raw) > 100000:
        raise OrbitError(413, "BODY_TOO_LARGE", "账户导入请求正文超过上限")
    value = _parse_json(raw)
    required = {"account_ids_text", "owner_user_id", "owner_team_id"}
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or set(value) - required - {"vendor_id"}
    ):
        raise OrbitError(400, "INVALID_STRUCTURE", "请提供户商、原始ID文本与目标拥有者和团队")
    if not isinstance(value["account_ids_text"], str):
        raise OrbitError(
            400, "INVALID_STRUCTURE", "账户ID原始输入必须为字符串", "/account_ids_text"
        )
    tokenize(value["account_ids_text"])
    return AccountImport(
        _uuid(value["vendor_id"], "/vendor_id") if value.get("vendor_id") is not None else None,
        value["account_ids_text"],
        _uuid(value["owner_user_id"], "/owner_user_id"),
        _uuid(value["owner_team_id"], "/owner_team_id"),
    )


def tokenize(value):
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_INPUT:
        raise OrbitError(
            422, "IMPORT_TEXT_LIMIT", "原始输入必须为1至20000个Unicode字符", "/account_ids_text"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise OrbitError(
            422, "IMPORT_TEXT_INVALID", "原始输入包含无效Unicode字符", "/account_ids_text"
        ) from None
    matches = list(_TOKENS.finditer(value))
    if not matches:
        raise OrbitError(422, "IMPORT_EMPTY", "请输入至少一个账户ID", "/account_ids_text")
    if len(matches) > MAX_TOKENS:
        raise OrbitError(
            422, "IMPORT_TOO_MANY_TOKENS", "原始非空项最多500条，重复项也计数", "/account_ids_text"
        )
    # 一次扫描位置，CRLF作为一行，不随每个token重复扫描整段文本。
    positions, line, column, previous = {}, 1, 1, ""
    starts = {match.start() for match in matches}
    for offset, character in enumerate(value):
        if offset in starts:
            positions[offset] = (line, column)
        if character == "\r":
            line, column = line + 1, 1
        elif character == "\n":
            if previous != "\r":
                line += 1
            column = 1
        else:
            column += 1
        previous = character
    rows, seen = [], {}
    for index, match in enumerate(matches):
        raw = match.group()
        normalized = raw[4:] if raw.startswith("act_") else raw
        valid = bool(_DIGITS.fullmatch(normalized))
        duplicate = seen.get(normalized) if valid else None
        state = "INVALID" if not valid else "DUPLICATE" if duplicate is not None else "WAITING"
        if valid and duplicate is None:
            seen[normalized] = index
        row_line, row_column = positions[match.start()]
        rows.append(
            {
                "token_index": index,
                "line_no": row_line,
                "column": row_column,
                "raw_display": raw[:128],
                "normalized_id": normalized if valid else None,
                "duplicate_of": duplicate,
                "state": state,
            }
        )
    return rows


def batch_summary(states, *, started=True):
    """DUPLICATE不算失败，ALREADY_EXISTS算成功；还有未终态时绝不显示完成。"""
    states = list(states)
    if not states or len(states) > MAX_TOKENS or any(value not in ROW_STATES for value in states):
        raise ValueError("导入状态集合无效")
    success = sum(value in {"SUCCEEDED", "ALREADY_EXISTS"} for value in states)
    duplicate = states.count("DUPLICATE")
    failed = sum(
        value in {"INVALID", "FORBIDDEN", "OWNERSHIP_CONFLICT", "FAILED"} for value in states
    )
    if any(value not in TERMINAL for value in states):
        state = "RUNNING" if started else "QUEUED"
    else:
        state = "PARTIAL_SUCCESS" if success and failed else "FAILED" if failed else "SUCCEEDED"
    return {
        "state": state,
        "total": len(states),
        "success_count": success,
        "failed_count": failed,
        "duplicate_count": duplicate,
    }
