"""候选工具纯护栏，不运行数据库/HTTP或证明063实际通过。"""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rule_simulation_schema_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_target_guard_is_before_any_imported_fixture_sql_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError, match="ISOLATED_UUID"):
        core.run_rule_simulation_schema_checks(client, admin, {}, "", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_valid_target_requires_exact_integer_port():
    core.guard_target(SimpleNamespace(host="127.0.0.1", port=13306), DATABASE)
    with pytest.raises(ValueError):
        core.guard_target(SimpleNamespace(host="127.0.0.1", port=13306.0), DATABASE)


def test_raw_hash_preserves_bytes_and_semantic_comparison_preserves_array_order():
    first = {"a": [1, 2], "name": "中文"}
    raw = json.dumps(first, ensure_ascii=False, indent=2).encode()
    compact = json.dumps(first, ensure_ascii=False, separators=(",", ":")).encode()
    assert core.raw_hash(raw) != core.raw_hash(compact)
    assert core.same_response(raw, first)
    assert core.same_response(raw, {"name": "中文", "a": [1, 2]})
    assert not core.same_response(raw, {**first, "a": [2, 1]})
    assert not core.same_response(raw, {**first, "name": "另一份合法JSON"})
    with pytest.raises(ValueError):
        core.raw_hash(bytearray(raw))


def test_semantic_comparison_rejects_invalid_utf8_and_duplicate_json_keys():
    from orbit_api.errors import OrbitError

    for raw in (b"\xff{}", b'{"a":1,"a":2}'):
        with pytest.raises(OrbitError):
            core.same_response(raw, {"a": 2})


def test_candidate_is_fixed_draft_not_migration_and_cases_are_exact_eight():
    assert (
        core.CANDIDATE
        == Path(__file__).parents[2] / "docs/orbit/sql-drafts/063_rule_simulation_candidate.sql"
    )
    content = core.candidate_bytes()
    assert content.count(b"CREATE TABLE ") == 8
    assert content.count(b"CREATE TRIGGER ") == 24
    assert (
        len(core.RULE_SIMULATION_SCHEMA_CASES) == len(set(core.RULE_SIMULATION_SCHEMA_CASES)) == 8
    )
    assert len(core.TABLES) == len(set(core.TABLES)) == 8


@pytest.mark.parametrize(
    "mode", ["foreign_database", "without_multi", "without_strict", "without_fk", "already_exists"]
)
def test_actual_selected_database_session_and_existing_table_gates_precede_candidate(
    monkeypatch, mode
):
    from pymysql.constants import CLIENT

    commands = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, values=()):
            commands.append((statement, values))
            self.statement = statement

        def fetchall(self):
            if self.statement == "SELECT DATABASE()":
                return (("foreign" if mode == "foreign_database" else DATABASE,),)
            if self.statement.startswith("SELECT @@SESSION.sql_mode"):
                return (
                    (
                        "NO_ENGINE_SUBSTITUTION"
                        if mode == "without_strict"
                        else "STRICT_TRANS_TABLES",
                        0 if mode == "without_fk" else 1,
                    ),
                )
            if "information_schema.TABLES" in self.statement:
                return ((1 if mode == "already_exists" else 0,),)
            raise AssertionError("unexpected_sql")

    admin = SimpleNamespace(
        host="127.0.0.1",
        port=13306,
        cursor=Cursor,
        client_flag=0 if mode == "without_multi" else CLIENT.MULTI_STATEMENTS,
    )
    candidate = Mock(side_effect=AssertionError("candidate_read_before_guard"))
    monkeypatch.setattr(core, "candidate_bytes", candidate)
    client = Mock()
    with pytest.raises(ValueError):
        core.run_rule_simulation_schema_checks(client, admin, {}, "", None, DATABASE, [])
    candidate.assert_not_called()
    assert not client.mock_calls
    assert all(
        not command.startswith(("CREATE", "INSERT", "UPDATE", "DROP")) for command, _ in commands
    )
    for command, params in commands:
        if "information_schema.TABLES" in command:
            assert params == (DATABASE, *core.TABLES)
            assert "TABLE_SCHEMA=%s" in command and command.count("%s") == 9
