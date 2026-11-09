"""容量夹具的目标闸门；不连接MySQL、不启动服务。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tools.reference_channel_capacity_checks import guard_target, public_ids


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "production"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, None),
    ],
)
def test_wrong_target_rejects_before_database(host, port, database):
    connection = SimpleNamespace(host=host, port=port, cursor=MagicMock())
    with pytest.raises(ValueError):
        guard_target(connection, database)
    connection.cursor.assert_not_called()


def test_actual_selected_database_must_match_uuid():
    database = "orbit_py_it_" + "a" * 32
    connection = MagicMock(host="127.0.0.1", port=13306)
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("orbit_py_it_" + "b" * 32,)
    with pytest.raises(ValueError):
        guard_target(connection, database)
    cursor.execute.assert_called_once_with("SELECT DATABASE()")


def test_exact_isolated_database_is_accepted():
    database = "orbit_py_it_" + "a" * 32
    connection = MagicMock(host="127.0.0.1", port=13306)
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (database,)
    guard_target(connection, database)


def test_original_channel_and_reference_envelopes_are_distinct():
    assert public_ids([{"id": "channel"}], "channels") == ["channel"]
    assert public_ids([{"value": {"id": "reference"}}], "references") == ["reference"]
