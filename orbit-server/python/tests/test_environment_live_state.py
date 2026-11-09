"""设备登记读回按服务端时钟衰减，停止Worker不会永久显示在线。"""

from datetime import UTC, datetime, timedelta

import pytest

from orbit_api.execution_agent_contract import public_agent


@pytest.mark.parametrize(
    "age,state,expected",
    [
        (0, "SUSPECT", "SUSPECT"),
        (15, "READY", "READY"),
        (45, "READY", "SUSPECT"),
        (90, "READY", "OFFLINE"),
        (150, "SUSPECT", "OFFLINE"),
        (0, "REVOKED", "REVOKED"),
    ],
)
def test_live_state_decays_and_requires_recovery(age, state, expected):
    now = datetime(2026, 11, 9, tzinfo=UTC)
    row = {
        "id": "device",
        "name": "machine",
        "endpoint": "http://127.0.0.1:50325",
        "probe_interval": 15,
        "revision": 3,
        "state": state,
        "last_heartbeat": now - timedelta(seconds=age),
    }
    assert public_agent(row, now=now)["state"] == expected
    assert public_agent(row, now=now)["revision"] == 3
