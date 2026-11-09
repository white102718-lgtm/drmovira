"""容量配置工具的隔离/资源/部分失败护栏，不代替真实MySQL配置或压测。"""

import json

import pytest
from tools import configure_mysql_capacity_fixture as module


class Connection:
    host = "127.0.0.1"
    port = 13306

    def __init__(self, directory):
        self.directory = directory
        self.settings = [128 * 1024**2, 100 * 1024**2, 1, 128 * 1024**2, 1]
        self.active = 0
        self.calls = []
        self.last = ""
        self.fail_redo = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, values=None):
        self.calls.append((sql, values))
        self.last = sql
        if sql == "SET GLOBAL innodb_buffer_pool_size=%s":
            self.settings[0] = values[0]
        elif sql == "SET GLOBAL innodb_redo_log_capacity=%s":
            if self.fail_redo:
                raise RuntimeError("private-database-message")
            self.settings[1] = values[0]
        elif sql.startswith("SET"):
            pytest.fail("不能修改其它全局参数或持久性语义")

    def fetchone(self):
        if self.last == "SELECT @@datadir":
            return (str(self.directory),)
        if self.last.startswith("SELECT @@global"):
            return tuple(self.settings)
        if self.last.startswith("SELECT COUNT"):
            return (self.active,)
        if "resize_status_code" in self.last:
            return ("resize", "0")
        if "capacity_resized" in self.last:
            return ("redo", str(self.settings[1]))
        pytest.fail("未知读取")


@pytest.fixture
def connection(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA", tmp_path.resolve())
    return Connection(tmp_path)


def configured(connection, **kwargs):
    return module.configure(
        connection, available_memory=8 * module.TARGET, disk_free=16 * module.TARGET, **kwargs
    )


def test_readonly_default_never_changes_settings(connection):
    report = configured(connection)
    assert report["result"] == "READ_ONLY" and not report["applied_settings"]
    assert not any(sql.startswith("SET") for sql, _ in connection.calls)


@pytest.mark.parametrize("field,value", [("host", "localhost"), ("port", 3306)])
def test_foreign_target_rejected_before_any_sql(connection, field, value):
    setattr(connection, field, value)
    with pytest.raises(ValueError, match="OWNED_FIXTURE"):
        configured(connection, apply=True)
    assert connection.calls == []


def test_foreign_datadir_cannot_be_mutated(connection, tmp_path):
    connection.directory = tmp_path / "other-project"
    with pytest.raises(ValueError, match="OWNED_DATADIR"):
        configured(connection, apply=True)
    assert not any(sql.startswith("SET") for sql, _ in connection.calls)


@pytest.mark.parametrize("cause", ["memory", "disk", "transaction", "durability"])
def test_resource_active_transaction_or_durability_failure_never_mutates(connection, cause):
    memory, disk = 8 * module.TARGET, 16 * module.TARGET
    if cause == "memory":
        memory = module.TARGET
    elif cause == "disk":
        disk = module.TARGET
    elif cause == "transaction":
        connection.active = 1
    else:
        connection.settings[2] = 0
    with pytest.raises(ValueError):
        module.configure(connection, apply=True, available_memory=memory, disk_free=disk)
    assert not any(sql.startswith("SET") for sql, _ in connection.calls)


def test_explicit_apply_grows_only_two_settings_and_keeps_durable_commit(connection):
    report = configured(connection, apply=True)
    assert report["result"] == "APPLIED"
    assert report["after"]["buffer_pool_bytes"] == module.TARGET
    assert report["after"]["redo_capacity_bytes"] == module.TARGET
    assert report["after"]["flush_log_at_commit"] == 1
    assert len(report["applied_settings"]) == 2


def test_larger_existing_profile_is_never_shrunk(connection):
    connection.settings[:2] = [2 * module.TARGET, 2 * module.TARGET]
    report = configured(connection, apply=True)
    assert report["result"] == "APPLIED" and report["applied_settings"] == []
    assert report["after"]["buffer_pool_bytes"] == 2 * module.TARGET


def test_partial_failure_is_not_success_and_does_not_leak_database_message(connection):
    connection.fail_redo = True
    report = configured(connection, apply=True)
    assert report["result"] == "PARTIAL_FAILED"
    assert report["after"]["buffer_pool_bytes"] == module.TARGET
    assert report["after"]["redo_capacity_bytes"] < module.TARGET
    assert "private-database-message" not in json.dumps(report)
