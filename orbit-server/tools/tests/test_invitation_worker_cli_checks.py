"""CLI验收夹具边界单测；只检查引导隔离，不伪装数据库或HTTPS通过。"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "invitation_worker_checks", Path(__file__).parents[1] / "invitation_worker_cli_checks.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture_values():
    return {
        "ORBIT_PYTHON_DB_SOURCES": {
            "master": {
                "db_host": "127.0.0.1",
                "db_port": 13306,
                "db_database": "orbit_py_it_" + "a" * 32,
                "db_password": "fixture-secret-password",
            }
        }
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"db_host": "remote.example"},
        {"db_port": 13307},
        {"db_database": "orbit_preview"},
        {"db_database": "orbit_py_it_"},
    ],
)
def test_fixture_cannot_target_existing_preview_or_external_database(overrides):
    values = fixture_values()
    values["ORBIT_PYTHON_DB_SOURCES"]["master"].update(overrides)
    with pytest.raises(ValueError, match="独立测试数据库"):
        MODULE.invoke_worker_cli(values, ["--recover"])


def test_private_configuration_is_only_passed_in_stdin(monkeypatch):
    def run(command, **kwargs):
        assert "fixture-secret-password" not in repr(command)
        assert "fixture-secret-password" not in repr(kwargs["env"])
        assert json.loads(kwargs["input"]) == fixture_values()
        assert kwargs["timeout"] == 45 and kwargs["capture_output"]
        return SimpleNamespace(returncode=0, stdout='{"recovered_unknown":0}\n', stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.invoke_worker_cli(fixture_values(), ["--recover"]) == (
        0,
        [{"recovered_unknown": 0}],
    )


@pytest.mark.parametrize(
    "stdout,stderr",
    [("fixture-secret-password", ""), ('{"result":"FAILED"}', "fixture-secret-password")],
)
def test_unexpected_process_output_is_not_repeated_in_failure(monkeypatch, stdout, stderr):
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=stdout, stderr=stderr),
    )
    with pytest.raises(AssertionError) as error:
        MODULE.invoke_worker_cli(fixture_values(), ["--recover"])
    assert "fixture-secret" not in str(error.value)
