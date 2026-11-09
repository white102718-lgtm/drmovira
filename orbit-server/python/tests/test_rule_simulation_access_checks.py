"""有界授权真实工具护栏纯测；不运行数据库/HTTP。"""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rule_simulation_access_checks")
DATABASE = "orbit_py_it_" + "b" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306.0, DATABASE),
    ],
)
def test_invalid_target_precedes_imported_fixtures_sql_http_and_engine(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        core.run_rule_simulation_access_checks(client, admin, {}, "", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls
    with pytest.raises(ValueError):
        core.engine_url(admin, database)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_engine_values_are_only_owned_admin_memory_with_exact_target(as_bytes):
    user, password = "fixture-user", "fixture-inmemory-not-env"
    admin = SimpleNamespace(
        host="127.0.0.1",
        port=13306,
        user=user.encode() if as_bytes else user,
        password=password.encode() if as_bytes else password,
    )
    url = core.engine_url(admin, DATABASE)
    assert (url.drivername, url.host, url.port, url.database) == (
        "mysql+asyncmy",
        "127.0.0.1",
        13306,
        DATABASE,
    )
    assert url.username == user and url.password == password


def test_invalid_connection_values_do_not_fall_back_to_other_config():
    admin = SimpleNamespace(host="127.0.0.1", port=13306, user="fixture", password=None)
    with pytest.raises(ValueError):
        core.engine_url(admin, DATABASE)


def test_actual_selected_database_is_checked_before_fixture_or_mutation():
    commands = []

    class Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, command, params=()):
            commands.append((command, params))

        def fetchall(self):
            return (("foreign",),)

    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=Cursor, commit=Mock(), rollback=Mock()
    )
    client = Mock()
    with pytest.raises(ValueError, match="ACTUAL_DATABASE"):
        core.run_rule_simulation_access_checks(client, admin, {}, "", None, DATABASE, [])
    assert commands == [("SELECT DATABASE()", ())]
    assert not client.mock_calls


def test_fixed_case_names_and_native_id_do_not_reuse_rule_scope_options_range():
    assert (
        len(core.RULE_SIMULATION_ACCESS_CASES) == len(set(core.RULE_SIMULATION_ACCESS_CASES)) == 8
    )
    assert core.NATIVE_ACTOR == 990670
    assert not 990631 <= core.NATIVE_ACTOR <= 990654
