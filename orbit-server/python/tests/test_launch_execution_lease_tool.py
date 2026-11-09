"""046真实工具的目标护栏；不连接SQL、不模拟实际迁移已通过。"""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

module = importlib.import_module("tools.launch_execution_lease_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("192.0.2.1", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", "13306", DATABASE),
        ("127.0.0.1", 13306.0, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306, None),
        ("127.0.0.1", 13306, 1),
    ],
)
def test_wrong_target_refused_before_any_http_or_database(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        module.run_execution_lease_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_only_exact_loopback_native_port_uuid_is_admitted_without_io():
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=Mock())
    module.guard_execution_lease_target(admin, DATABASE)
    admin.cursor.assert_not_called()


def test_actual_selected_database_must_match_before_fixture_or_http(monkeypatch):
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchall.return_value = (("orbit_py_it_" + "b" * 32,),)
    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=Mock(return_value=cursor), commit=Mock()
    )
    client = Mock()
    fixture = Mock(side_effect=AssertionError("不能构建其他数据库的资料"))
    monkeypatch.setattr(module, "create_protocol_plan", fixture)
    with pytest.raises(AssertionError):
        module.run_execution_lease_checks(client, admin, {}, "unused", None, DATABASE, [])
    cursor.execute.assert_called_once_with("SELECT DATABASE()", ())
    fixture.assert_not_called()
    assert not client.mock_calls


class AutocommitAdmin:
    """只模拟事务边界，不声称模拟MySQL约束、真实1644或并发。"""

    def __init__(self):
        self.persisted = ["original"]
        self.pending = None
        self.events = []

    def begin(self):
        assert self.pending is None
        self.events.append("begin")
        self.pending = []

    def write(self, value):
        self.events.append(value)
        if self.pending is None:
            self.persisted.append(value)  # autocommit=True时漏begin会泄漏部分写入。
        else:
            self.pending.append(value)

    def commit(self):
        self.events.append("commit")
        self.persisted.extend(self.pending or [])
        self.pending = None

    def rollback(self):
        self.events.append("rollback")
        self.pending = None


def test_autocommit_connection_does_not_commit_head_fact_audit_before_outbox_failure():
    admin = AutocommitAdmin()
    with pytest.raises(RuntimeError, match="outbox rejected"):
        with module.execution_lease_transaction(admin):
            admin.write("head")
            admin.write("fact")
            admin.write("audit")
            raise RuntimeError("outbox rejected")
    assert admin.persisted == ["original"]
    assert admin.events == ["begin", "head", "fact", "audit", "rollback"]


def test_autocommit_connection_success_commits_all_four_rows_after_outbox():
    admin = AutocommitAdmin()
    with module.execution_lease_transaction(admin):
        for row in ("head", "fact", "audit", "outbox"):
            admin.write(row)
    assert admin.persisted == ["original", "head", "fact", "audit", "outbox"]
    assert admin.events == ["begin", "head", "fact", "audit", "outbox", "commit"]
