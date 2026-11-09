"""跨页选择原合同及唯一SQL构造纯测试，不替代50k真实容量与权限验收。"""

import json
from uuid import UUID

import pytest

from orbit_api.account_scope_contract import parse_scope
from orbit_api.account_selection import selection_sql
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"
FILTER = {"q": "", "status": None, "auth_status": None, "operator_user_id": None, "vendor_id": None}


def parse(value):
    return parse_scope(json.dumps(value).encode())


def test_ids_preserve_full_members_and_canonical_set_order():
    second = str(UUID(int=2))
    first = parse({"mode": "IDS", "account_ids": [ID, second], "filter": None})
    other = parse({"mode": "IDS", "account_ids": [second, ID], "filter": None})
    assert first.account_ids == tuple(sorted([ID, second]))
    assert first.canonical == other.canonical


def test_exact_50000_is_accepted_and_raw_50001_not_deduplicated_down():
    ids = [str(UUID(int=index)) for index in range(1, 50001)]
    assert len(parse({"mode": "IDS", "account_ids": ids, "filter": None}).account_ids) == 50000
    with pytest.raises(OrbitError):
        parse({"mode": "IDS", "account_ids": ids + [ids[0]], "filter": None})


@pytest.mark.parametrize(
    "value",
    [
        {"mode": "IDS", "account_ids": [], "filter": None},
        {"mode": "IDS", "account_ids": [ID], "filter": FILTER},
        {"mode": "FILTER", "account_ids": [ID], "filter": FILTER},
        {"mode": "FILTER", "account_ids": [], "filter": None},
        {"mode": "FILTER", "account_ids": [], "filter": {}},
        {"mode": "IDS", "account_ids": [None], "filter": None},
        {"mode": "IDS", "account_ids": [ID, ID], "filter": None},
        {"mode": "FILTER", "account_ids": [], "filter": FILTER | {"status": "active"}},
        {"mode": "FILTER", "account_ids": [], "filter": FILTER | {"vendor_id": 12}},
        {"mode": "FILTER", "account_ids": [], "filter": FILTER | {"date_from": "2026-01-01"}},
    ],
)
def test_invalid_original_mode_matrix_and_fields_are_rejected(value):
    with pytest.raises(OrbitError):
        parse(value)


def test_duplicate_json_keys_are_not_silently_overwritten():
    with pytest.raises(OrbitError):
        parse_scope(b'{"mode":"IDS","mode":"FILTER","account_ids":[],"filter":null}')


@pytest.mark.parametrize("query", ["00123", "act_00123"])
def test_original_numeric_search_keeps_leading_zero(query):
    value = parse({"mode": "FILTER", "account_ids": [], "filter": FILTER | {"q": query}})
    clauses, params = selection_sql(value.query)
    assert clauses == ["a.external_id=:external"]
    assert params == {"external": "00123"}


def test_non_ascii_digits_and_sql_wildcards_follow_original_literal_prefix_search():
    for query in ("１２３", "prefix!%_"):
        value = parse({"mode": "FILTER", "account_ids": [], "filter": FILTER | {"q": query}})
        clauses, params = selection_sql(value.query)
        assert clauses == ["a.name_prefix LIKE :search ESCAPE '!'"]
        assert params == {
            "search": query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        }
