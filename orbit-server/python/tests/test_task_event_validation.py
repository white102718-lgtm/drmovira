"""原TaskEvent存量校验纯测；未使用Task/Node枚举替换state原string合同。"""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.task_event_validation import (
    MAX_SAFE_INTEGER,
    validate_directory,
    validate_persisted_batch,
    validate_structure,
)

TENANT, TASK, EVENT, REQUEST, NODE = (str(UUID(int=i)) for i in range(1, 6))


def values():
    task = {"tenant_id": TENANT, "id": TASK, "revision": 3, "latest_sequence": 3}
    event = {
        "tenant_id": TENANT,
        "event_id": EVENT,
        "sequence": 1,
        "schema_version": 1,
        "task_id": TASK,
        "task_revision": 1,
        "node_id": None,
        "state": "QUEUED",
        "occurred_at": datetime(2026, 11, 8),
        "request_id": REQUEST,
    }
    directory = {
        key: event[key] for key in ("tenant_id", "task_id", "event_id", "sequence", "occurred_at")
    }
    directory["expires_at"] = event["occurred_at"] + timedelta(days=7)
    return task, event, directory


def fails(operation):
    with pytest.raises(OrbitError) as failure:
        operation()
    assert failure.value.status == 503
    assert failure.value.code == "TASK_EVENT_STATE_UNAVAILABLE"
    assert failure.value.pointer is None
    assert "sensitive-fixture" not in failure.value.message


@pytest.mark.parametrize("state", ["FUTURE_STATE", "PAUSED", "未" * 40, "🟢" * 40])
def test_valid_future_state_strings_are_not_restricted_to_task_node_enums(state):
    task, event, directory = values()
    event["state"] = state
    validate_structure(task, [event])
    validate_directory(task, [event], [directory])


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("sequence", 0),
        ("sequence", -1),
        ("sequence", True),
        ("sequence", 4),
        ("sequence", MAX_SAFE_INTEGER + 1),
        ("task_revision", 0),
        ("task_revision", 4),
        ("task_revision", True),
        ("task_revision", MAX_SAFE_INTEGER + 1),
        ("event_id", "sensitive-fixture"),
        ("request_id", "sensitive-fixture"),
        ("node_id", "sensitive-fixture"),
        ("node_id", 1),
        ("task_id", TENANT),
        ("tenant_id", TASK),
        ("state", ""),
        ("state", "x" * 41),
        ("state", "\ud800"),
        ("state", None),
        ("occurred_at", None),
        ("occurred_at", "sensitive-fixture"),
        ("occurred_at", datetime(2026, 11, 8, microsecond=1)),
        ("occurred_at", datetime(2026, 11, 8, tzinfo=timezone(timedelta(hours=8)))),
    ],
)
def test_corrupt_stored_field_is_safe_503_without_echoing_value(field, value):
    task, event, _ = values()
    event[field] = value
    fails(lambda: validate_structure(task, [event]))


def test_utc_aware_and_nullable_or_uuid_node_are_valid():
    task, event, directory = values()
    event["node_id"] = NODE
    event["occurred_at"] = event["occurred_at"].replace(tzinfo=UTC)
    validate_structure(task, [event])
    validate_directory(task, [event], [directory])


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", 2),
        ("sequence", True),
        ("tenant_id", TASK),
        ("task_id", TENANT),
        ("event_id", NODE),
        ("occurred_at", datetime(2026, 11, 8, microsecond=1000)),
        ("expires_at", datetime(2026, 11, 16)),
        ("expires_at", None),
    ],
)
def test_directory_matches_exact_event_identity_sequence_and_seven_day_time(field, value):
    task, event, directory = values()
    directory[field] = value
    fails(lambda: validate_directory(task, [event], [directory]))


def test_missing_duplicate_and_overflow_directory_are_rejected():
    task, event, directory = values()
    fails(lambda: validate_directory(task, [event], []))
    fails(lambda: validate_directory(task, [event], [directory, directory]))
    event["occurred_at"] = directory["occurred_at"] = datetime(9999, 12, 31)
    fails(lambda: validate_directory(task, [event], [directory]))


class Session:
    def __init__(self, directory):
        self.directory, self.calls = directory, []

    async def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        return SimpleNamespace(mappings=lambda: self.directory)


@pytest.mark.asyncio
async def test_entire_batch_structure_checked_before_any_directory_query():
    task, event, directory = values()
    session = Session([directory])
    with pytest.raises(OrbitError):
        await validate_persisted_batch(
            session,
            task,
            [
                event,
                event
                | {
                    "event_id": NODE,
                    "sequence": 2,
                    "schema_version": 2,
                },
            ],
        )
    assert session.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": True},
        {"revision": 0},
        {"latest_sequence": 0},
        {"latest_sequence": MAX_SAFE_INTEGER + 1},
        {"id": "invalid-fixture"},
    ],
)
def test_corrupt_task_header_is_not_used_to_authorize_event_bounds(changes):
    task, event, _ = values()
    fails(lambda: validate_structure(task | changes, [event]))


@pytest.mark.asyncio
async def test_two_hundred_rows_use_one_bounded_directory_query_without_n_plus_one():
    task, event, directory = values()
    task |= {"latest_sequence": 200, "revision": 200}
    events, cursors = [], []
    for index in range(1, 201):
        uid = str(UUID(int=1000 + index))
        events.append(event | {"event_id": uid, "sequence": index})
        cursors.append(directory | {"event_id": uid, "sequence": index})
    session = Session(cursors)
    await validate_persisted_batch(session, task, events)
    assert len(session.calls) == 1
    assert len(session.calls[0][1]["ids"]) == 200
    assert session.calls[0][1]["tenant"] == TENANT
    assert session.calls[0][1]["task"] == TASK
    assert "event_id IN" in str(session.calls[0][0])
    oversized = Session([])
    with pytest.raises(OrbitError):
        await validate_persisted_batch(oversized, task, events + [events[0]])
    assert oversized.calls == []


@pytest.mark.asyncio
async def test_empty_batch_has_no_extra_directory_query():
    task, _, _ = values()
    session = Session([])
    await validate_persisted_batch(session, task, [])
    assert session.calls == []
