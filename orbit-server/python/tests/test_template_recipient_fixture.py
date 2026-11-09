"""真实专项控制身份的若依账号长度回归；不扩表规避夹具错误。"""

import importlib.util
import re
import sys
from pathlib import Path


def test_recipient_fixture_username_fits_native_30_character_account_contract(monkeypatch):
    tools = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "template_recipient_fixture_test", tools / "template_recipient_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    values = [module.fixture_username() for _ in range(21)]
    assert len(set(values)) == 21
    assert all(len(value) == 29 and re.fullmatch(r"[a-z0-9_]+", value) for value in values)
