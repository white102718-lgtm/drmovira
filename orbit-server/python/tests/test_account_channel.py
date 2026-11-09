"""账户当前渠道合同与规则过滤；真实事务另由HTTP专项验证。"""

import json
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.rule_list_filter_contract import parse_list_filter_query
from orbit_api.rule_store import parse_rule_query


def test_rule_channel_is_a_real_filter():
    channel = str(UUID(int=42))
    assert parse_rule_query({"channel_id": channel}).channel_id == channel
    assert parse_list_filter_query({"kind": "CHANNEL"}).kind == "CHANNEL"


def test_current_channel_accepts_binding_and_explicit_clear():
    from orbit_api.account_channel import parse_write

    channel = str(UUID(int=42))
    assert parse_write(json.dumps({"channel_id": channel, "reason": "明确改绑"}).encode()) == {
        "channel_id": channel,
        "reason": "明确改绑",
    }
    assert parse_write(b'{"channel_id":null,"reason":"clear"}')["channel_id"] is None


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"channel_id": "bad", "reason": "test"},
        {"channel_id": None, "reason": ""},
        {"channel_id": None, "reason": "ok", "tenant_id": "x"},
        {"channel_id": 12, "reason": "ok"},
    ],
)
def test_invalid_write(value):
    from orbit_api.account_channel import parse_write

    with pytest.raises(OrbitError):
        parse_write(json.dumps(value).encode())


@pytest.mark.asyncio
async def test_successful_key_replay_survives_channel_disable(monkeypatch):
    """停用仅禁止新关联，不能把已提交成功的网络恢复变为422。"""
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import orbit_api.account_channel as core
    from orbit_api.directory_tokens import canonical

    channel = str(UUID(int=42))
    account = str(UUID(int=2))
    value = {"channel_id": channel, "reason": "恢复原请求"}
    result = {"account_id": account, "channel_id": channel, "revision": 2, "csrf_token": None}
    digest = hashlib.sha256(canonical([account, 1, value]).encode()).hexdigest()

    class Rows:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                Rows({"status": "DISABLED", "value_json": {"ownership": {}}}),
                Rows({"payload_hash": digest, "response_json": result}),
            ]
        )
    )
    current = SimpleNamespace(tenant_id=str(UUID(int=3)), actor_id=1, subject_id=str(UUID(int=4)))
    store = core.AccountChannelStore(None)
    store.account = AsyncMock(return_value=(current, [], {"id": account, "revision": 9}))
    monkeypatch.setattr(core, "verify_csrf", lambda *a: None)
    monkeypatch.setattr(core, "readable", lambda *a: True)
    assert (
        await store.write(session, 1, account, 1, "key", "auth", "csrf", value, str(UUID(int=5)))
        == result
    )
    assert session.execute.call_count == 2
