"""配置源/CAS分离的纯边界；SQL排序、索引和锁仍需独立真实数据库验证。"""

import hashlib
import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import MAX_CONFIG_BYTES
from orbit_api.launch_plan_source import capture_plan_source


def uid(value):
    return str(UUID(int=value))


def fixture():
    payload = {"name": "原配置", "ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)}}
    encoded = canonical(payload).encode()
    head = {
        "id": uid(4),
        "revision": 3,
        "payload_hash": hashlib.sha256(encoded).hexdigest(),
        "payload_json": payload,
        **payload["ownership"],
    }
    metadata = {"revision": 1, "payload_hash": head["payload_hash"], "storage_bytes": len(encoded)}
    return BusinessContext(1, uid(1), "USER", uid(2), uid(3)), head, metadata, payload


class Session:
    def __init__(self, *rows, transaction=True):
        self.rows, self.calls, self.transaction = list(rows), [], transaction

    def in_transaction(self):
        return self.transaction

    async def execute(self, sql, params):
        self.calls.append((str(sql), dict(params)))
        row = self.rows.pop(0)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))


@pytest.mark.asyncio
async def test_state_only_head_preserves_original_configuration_and_immutable_work_copy():
    current, head, metadata, payload = fixture()
    session = Session(metadata, {"payload_json": json.dumps(payload, ensure_ascii=False)})
    source = await capture_plan_source(session, current, head)
    assert (source.source_revision, source.head_revision) == (1, 3)
    assert source.plan_id == head["id"] and source.tenant_id == current.tenant_id
    changed = source.payload()
    changed["ownership"]["owner_user_id"] = uid(99)
    payload["name"] = "调用方修改"
    assert source.payload()["name"] == "原配置"
    assert source.payload()["ownership"]["owner_user_id"] == uid(2)
    with pytest.raises(FrozenInstanceError):
        source.head_revision = 4
    assert len(session.calls) == 2
    assert "ORDER BY revision DESC LIMIT 1 FOR SHARE" in session.calls[0][0]
    assert "payload_json FROM" not in session.calls[0][0]
    assert session.calls[1][1]["revision"] == 1
    assert all(call[1]["tenant"] == current.tenant_id for call in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 0},
        {"revision": True},
        {"revision": 4},
        {"revision": 9007199254740992},
        {"payload_hash": "0" * 64},
        {"storage_bytes": 0},
        {"storage_bytes": True},
        {"storage_bytes": 2 * MAX_CONFIG_BYTES + 1},
    ],
)
async def test_latest_configuration_corruption_never_falls_back_or_fetches_large_body(changes):
    current, head, metadata, _ = fixture()
    session = Session(metadata | changes)
    with pytest.raises(OrbitError) as error:
        await capture_plan_source(session, current, head)
    assert (error.value.status, error.value.code) == (503, "LAUNCH_SOURCE_STATE_UNAVAILABLE")
    assert len(session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"id": "invalid"},
        {"revision": True},
        {"revision": 0},
        {"payload_hash": None},
        {"owner_user_id": uid(99)},
        {"payload_json": "invalid"},
        {"payload_json": []},
    ],
)
async def test_invalid_head_rejected_before_sql(changes):
    current, head, _, _ = fixture()
    session = Session()
    with pytest.raises(OrbitError) as error:
        await capture_plan_source(session, current, head | changes)
    assert error.value.status == 503 and session.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "not-json",
        {"name": "different"},
        {"ownership": {"owner_user_id": uid(99), "owner_team_id": uid(3)}},
        {"name": float("nan")},
        {"name": "\ud800"},
        {"name": "x" * MAX_CONFIG_BYTES},
    ],
)
async def test_source_payload_mismatch_or_corruption_has_safe_uniform_error(payload):
    current, head, metadata, _ = fixture()
    session = Session(metadata, {"payload_json": payload})
    with pytest.raises(OrbitError) as error:
        await capture_plan_source(session, current, head)
    assert (error.value.status, error.value.code) == (503, "LAUNCH_SOURCE_STATE_UNAVAILABLE")
    assert len(session.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["metadata", "payload"])
async def test_missing_source_never_invents_version(missing):
    current, head, metadata, _ = fixture()
    session = Session(None) if missing == "metadata" else Session(metadata, None)
    with pytest.raises(OrbitError):
        await capture_plan_source(session, current, head)


@pytest.mark.asyncio
async def test_no_implicit_authorization_or_transaction():
    current, head, _, _ = fixture()
    for ctx, session in [(None, Session()), (current, Session(transaction=False))]:
        with pytest.raises(ValueError):
            await capture_plan_source(session, ctx, head)
        assert session.calls == []
