"""任务命令必须显式选择发送或恢复，参数解析不能触发数据库/网络初始化。"""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "invitation_worker_cli", Path(__file__).parents[1] / "run_invitation_worker.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--send", "--recover"],
        ["--send", "--limit", "0"],
        ["--recover", "--limit", "101"],
        ["--send", "--cycles", "1"],
        ["--send", "--serve", "--cycles", "0"],
        ["--send", "--interval", "4"],
    ],
)
def test_explicit_mode_and_bounded_batch(argv):
    with pytest.raises(SystemExit):
        MODULE.arguments(argv)


def test_recovery_is_separate_from_send():
    options = MODULE.arguments(["--recover", "--limit", "100"])
    assert options.recover and not options.send and options.limit == 100


def test_controlled_serve_has_explicit_send_and_bounded_cycles():
    options = MODULE.arguments(["--recover", "--serve", "--cycles", "2", "--interval", "5"])
    assert options.serve and options.cycles == 2 and options.interval == 5 and not options.send
