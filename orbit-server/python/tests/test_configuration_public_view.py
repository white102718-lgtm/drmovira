"""配置公开DTO必须区分未配置、已清除与无需凭据，不回显存储值。"""

import datetime as dt
import json

import pytest

from orbit_api.configuration_store import _public


@pytest.mark.parametrize(
    "section,secrets,expected",
    [
        ("AI_GPT", {}, {"apiKey": {"configured": False, "hint": "未配置"}}),
        (
            "AI_GPT",
            {"apiKey": "fixture-ciphertext", "unknown": "fixture-unknown"},
            {"apiKey": {"configured": True, "hint": "已配置（不回显）"}},
        ),
        ("RISK", {}, {}),
    ],
)
def test_absent_secret_slots_stay_visible_and_never_leak(section, secrets, expected):
    view = _public(
        {
            "id": "fixture",
            "section": section,
            "name": "配置",
            "enabled": False,
            "revision": 1,
            "settings_json": "{}",
            "secrets_json": json.dumps(secrets),
            "verification_status": "UNTESTED",
            "verified_at": None,
            "updated_at": dt.datetime(2026, 11, 7),
        }
    )
    assert view["secrets"] == expected
    assert "fixture-ciphertext" not in json.dumps(view)
    assert "fixture-unknown" not in json.dumps(view)
