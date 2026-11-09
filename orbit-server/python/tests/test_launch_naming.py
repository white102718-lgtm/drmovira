"""命名新模块纯边界：日期、全批占号、真实来源与失效；不冒充真实SQL验收。"""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api import launch_naming as naming
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


def uid(number):
    return str(UUID(int=number))


def prepared(count=2):
    return naming.NamingInput(
        uid(1),
        3,
        "a" * 64,
        date(2026, 11, 8),
        "b" * 64,
        {
            "channel": {"name": "渠道", "code": "CH"},
            "ownership": {"owner_user_id": uid(2)},
            "dependencies": {"channel": {"id": uid(3)}},
            "nickname": "昵称",
            "full_name": "真实姓名",
        },
        tuple((uid(4), uid(5), index) for index in range(1, count + 1)),
    )


@pytest.mark.parametrize(
    "last,count,expected",
    [
        (0, 2, [1, 2]),
        (9998, 3, [9999, 10000, 10001]),
        (naming.MAX_SEQUENCE - 1, 1, [naming.MAX_SEQUENCE]),
    ],
)
def test_decimal30_sequence_never_wraps_or_recycles(last, count, expected):
    assert list(naming.sequence_interval(Decimal(last), count)) == expected


@pytest.mark.parametrize("last,count", [(naming.MAX_SEQUENCE, 1), (-1, 1), (0, 0), (0, 10001)])
def test_empty_oversized_or_exhausted_whole_batch_rejected(last, count):
    with pytest.raises(OrbitError):
        naming.sequence_interval(last, count)


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 11, 7, 15, 59, 59), date(2026, 11, 7)),
        (datetime(2026, 11, 7, 16, 0, 0), date(2026, 11, 8)),
        (datetime(2026, 11, 7, 16, 0, 0, tzinfo=UTC), date(2026, 11, 8)),
    ],
)
async def test_database_utc_day_changes_at_shanghai_midnight(now, expected):
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: now))
    )
    assert await naming.database_day(session) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan_id", uid(9)),
        ("plan_revision", 4),
        ("naming_date", date(2026, 11, 9)),
        ("source_hash", "c" * 64),
    ],
)
def test_old_reservation_rejected_for_each_frozen_source_boundary(field, value):
    item = prepared()
    row = {
        "plan_id": item.plan_id,
        "plan_revision": item.revision,
        "naming_date": item.day,
        "source_hash": item.source_hash,
    }
    naming.assert_reservation_input(row, item)
    with pytest.raises(OrbitError) as failure:
        naming.assert_reservation_input(row | {field: value}, item)
    assert failure.value.code == "NAMING_PREVIEW_STALE"


@pytest.mark.parametrize(
    "changes", [{"revision": 4}, {"payload_hash": "c" * 64}, {"state": "SUBMITTED"}]
)
def test_locked_plan_cas_and_state_cannot_trust_old_unlocked_preview(changes):
    row = {"revision": 3, "payload_hash": "a" * 64, "state": "DRAFT"}
    with pytest.raises(OrbitError):
        naming.assert_plan_input(row | changes, prepared(), 3)


def test_naming_projection_does_not_mutate_saved_identity_or_claim_execution_verified():
    original = {
        "asset_ids": [uid(1)],
        "identity_bindings": [{"page_id": "page"}],
        "profile_binding_ids": [uid(3)],
        "account_ids": [uid(2)],
        "account_scope_snapshot_id": uid(4),
        "channel_id": uid(5),
        "campaigns": [{"adsets": [{"metric_profile_id": uid(8), "ads": [{"title": "原文"}]}]}],
    }
    result = naming.naming_projection(original)
    assert result["identity_bindings"] == [] and result["asset_ids"] == []
    assert result["account_scope_snapshot_id"] == uid(4)
    assert result["account_ids"] == [uid(2)] and result["channel_id"] == uid(5)
    assert original["identity_bindings"] == [{"page_id": "page"}]
    assert original["campaigns"][0]["adsets"][0]["metric_profile_id"] == uid(8)


def test_nfc_name_normalization_never_silently_truncates_or_substitutes_login():
    assert naming.normalized_name("  e\u0301  ") == "é"
    assert naming.normalized_name(None) == ""
    assert naming.normalized_name("😀" * 100) == "😀" * 100


class Writes:
    def __init__(self, last=0):
        self.calls = []
        self.last = last

    async def execute(self, sql, values=None):
        self.calls.append((str(sql), values))
        return SimpleNamespace(scalar_one=lambda: Decimal(self.last))


async def test_ten_thousand_names_inserted_in_bounded_batches_with_one_audit(monkeypatch):
    event = AsyncMock()
    monkeypatch.setattr(naming.access, "event", event)
    session = Writes(9998)
    current = BusinessContext(1, uid(100), "SUPER_ADMIN", uid(2), uid(3))
    row = await naming.LaunchNamingStore(None).create_reservation(
        session, current, prepared(10000), uid(8)
    )
    batches = [
        values for sql, values in session.calls if "INSERT INTO orbit_launch_name_item" in sql
    ]
    assert len(batches) == 50 and all(len(batch) == 200 for batch in batches)
    items = [item for batch in batches for item in batch]
    assert len({item["slot"] for item in items}) == 10000
    assert items[0]["name"].endswith("_9999") and items[-1]["name"].endswith("_19998")
    assert all(len(item["name"]) <= 200 for item in items)
    event.assert_awaited_once()
    assert row["source_hash"] == prepared().source_hash


async def test_overlong_real_names_reject_before_consuming_sequence_or_partial_item_insert(
    monkeypatch,
):
    event = AsyncMock()
    monkeypatch.setattr(naming.access, "event", event)
    source = prepared()
    source = replace(source, source=source.source | {"nickname": "😀" * 200})
    session = Writes()
    with pytest.raises(OrbitError) as failure:
        await naming.LaunchNamingStore(None).create_reservation(
            session, BusinessContext(1, uid(100), "USER", uid(2), uid(3)), source, uid(8)
        )
    assert failure.value.status == 422
    assert not any("UPDATE orbit_launch_name_sequence SET" in sql for sql, _ in session.calls)
    assert not any("INSERT INTO orbit_launch_name_item" in sql for sql, _ in session.calls)
    event.assert_not_awaited()


async def setup_replay(monkeypatch, source):
    current = BusinessContext(1, uid(100), "USER", uid(2), uid(3))
    context = AsyncMock(return_value=current)
    monkeypatch.setattr(naming.access, "context", context)
    monkeypatch.setattr(naming.access, "clock", AsyncMock())
    monkeypatch.setattr(naming, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(naming, "prepare_naming", AsyncMock(return_value=source))
    monkeypatch.setattr(
        naming,
        "capture_plan_source",
        AsyncMock(
            return_value=SimpleNamespace(
                plan_id=source.plan_id,
                payload_hash=source.payload_hash,
                source_revision=source.revision,
            )
        ),
    )
    row = {
        "id": source.plan_id,
        "revision": source.revision,
        "state": "DRAFT",
        "payload_hash": source.payload_hash,
    }
    monkeypatch.setattr(naming.LaunchStore, "row", AsyncMock(return_value=row))
    monkeypatch.setattr(naming, "database_day", AsyncMock(return_value=source.day))
    monkeypatch.setattr(naming.access, "replay", AsyncMock(return_value={"id": uid(9)}))
    return context


async def test_successful_key_replay_rechecks_locked_action_and_never_returns_stale_source(
    monkeypatch,
):
    source = prepared()
    context = await setup_replay(monkeypatch, source)
    store = naming.LaunchNamingStore(None)
    old = {
        "id": uid(9),
        "plan_id": source.plan_id,
        "plan_revision": source.revision,
        "naming_date": source.day,
        "source_hash": "old",
    }
    monkeypatch.setattr(store, "reservation", AsyncMock(return_value=old))
    result = AsyncMock()
    monkeypatch.setattr(store, "result", result)
    with pytest.raises(OrbitError) as failure:
        await store.reserve(
            object(), 1, "session", "csrf", "original-key", source.plan_id, 3, uid(8)
        )
    assert failure.value.code == "NAMING_PREVIEW_STALE"
    assert context.await_count == 2
    result.assert_not_awaited()


async def test_midnight_while_waiting_for_plan_lock_rejects_before_idempotency_or_counter(
    monkeypatch,
):
    source = prepared()
    await setup_replay(monkeypatch, source)
    monkeypatch.setattr(naming, "database_day", AsyncMock(return_value=date(2026, 11, 9)))
    with pytest.raises(OrbitError) as failure:
        await naming.LaunchNamingStore(None).reserve(
            object(), 1, "session", "csrf", "original-key", source.plan_id, 3, uid(8)
        )
    assert failure.value.code == "NAMING_DATE_CHANGED"
    naming.access.replay.assert_not_awaited()


async def test_uppercase_url_uuid_uses_canonical_same_intent_and_lookup(monkeypatch):
    source = replace(prepared(), plan_id="abcdef01-2345-4678-9abc-def012345678")
    await setup_replay(monkeypatch, source)
    store = naming.LaunchNamingStore(None)
    row = {
        "id": uid(9),
        "plan_id": source.plan_id,
        "plan_revision": source.revision,
        "naming_date": source.day,
        "source_hash": source.source_hash,
    }
    monkeypatch.setattr(store, "reservation", AsyncMock(return_value=row))
    monkeypatch.setattr(store, "result", AsyncMock(return_value={"id": uid(9)}))
    await store.reserve(
        object(), 1, "session", "csrf", "same-key", source.plan_id.upper(), 3, uid(8)
    )
    assert naming.LaunchStore.row.await_args_list[0].args[2] == source.plan_id
    assert naming.access.replay.await_args.args[4] == naming.access.digest([source.plan_id, 3])


@pytest.mark.parametrize(
    "identifier", ["{abcdef01-2345-4678-9abc-def012345678}", "abcdef01234546789abcdef012345678"]
)
async def test_noncanonical_uuid_syntax_never_reaches_sql(identifier):
    with pytest.raises(OrbitError) as failure:
        await naming.LaunchNamingStore(None).reserve(
            object(), 1, "session", "csrf", "same-key", identifier, 3, uid(8)
        )
    assert failure.value.status == 422


async def test_status_head_binds_names_to_actual_immutable_source_without_changing_cas(monkeypatch):
    before = replace(prepared(), revision=7)
    locked = {"revision": 7, "payload_hash": before.payload_hash, "state": "VALIDATED"}
    naming.assert_plan_input(locked, before, 7)
    capture = AsyncMock(
        return_value=SimpleNamespace(
            plan_id=before.plan_id, payload_hash=before.payload_hash, source_revision=3
        )
    )
    monkeypatch.setattr(naming, "capture_plan_source", capture)
    result = await naming.bind_naming_source("session", "current", locked, before)
    assert before.revision == 7 and result.revision == 3
    assert result.source_hash == before.source_hash and result.slots == before.slots
    capture.assert_awaited_once_with("session", "current", locked)
    naming.assert_reservation_input(
        {
            "plan_id": result.plan_id,
            "plan_revision": 3,
            "naming_date": result.day,
            "source_hash": result.source_hash,
        },
        result,
    )


@pytest.mark.parametrize("field,value", [("plan_id", uid(99)), ("payload_hash", "c" * 64)])
async def test_source_mismatch_never_rebinds_or_consumes_names(monkeypatch, field, value):
    before = prepared()
    source = {"plan_id": before.plan_id, "payload_hash": before.payload_hash, "source_revision": 1}
    monkeypatch.setattr(
        naming,
        "capture_plan_source",
        AsyncMock(return_value=SimpleNamespace(**(source | {field: value}))),
    )
    with pytest.raises(OrbitError) as failure:
        await naming.bind_naming_source("session", "current", {}, before)
    assert failure.value.code == "REVISION_CONFLICT" and before.revision == 3


@pytest.mark.parametrize("known_key", [True, False])
async def test_current_authorized_names_replay_before_old_cas_but_new_key_cannot_write(
    monkeypatch, known_key
):
    original = prepared()
    current_head = replace(original, revision=7)
    await setup_replay(monkeypatch, current_head)
    naming.capture_plan_source.return_value = SimpleNamespace(
        plan_id=original.plan_id, payload_hash=original.payload_hash, source_revision=3
    )
    naming.access.replay.return_value = {"id": uid(9)} if known_key else None
    store = naming.LaunchNamingStore(None)
    monkeypatch.setattr(
        store,
        "reservation",
        AsyncMock(
            return_value={
                "id": uid(9),
                "plan_id": original.plan_id,
                "plan_revision": 3,
                "naming_date": original.day,
                "source_hash": original.source_hash,
            }
        ),
    )
    monkeypatch.setattr(store, "result", AsyncMock(return_value={"id": uid(9)}))
    if known_key:
        assert await store.reserve(
            object(), 1, "session", "csrf", "known-key", original.plan_id, 3, uid(8)
        ) == {"id": uid(9)}
    else:
        with pytest.raises(OrbitError) as failure:
            await store.reserve(
                object(), 1, "session", "csrf", "new-key", original.plan_id, 3, uid(8)
            )
        assert failure.value.code == "REVISION_CONFLICT"
        store.result.assert_not_awaited()
