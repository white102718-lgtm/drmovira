"""日历预期纯测：真实父facade批次/SessionTransaction，SQL返回替身，非来源/采集证明。"""

import asyncio
import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_rule_editor_definition import result
from test_rule_simulation_access import Fixture

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_simulation_access import RuleSimulationAccessFacade
from orbit_api.rule_simulation_expected_units import RuleSimulationExpectedUnits

NOW = datetime(2026, 11, 9, 0, 30, 0, 123499)


def set_window(fixture, window):
    import json

    body = json.loads(fixture.version["payload_json"])
    body["window"] = window
    fixture.version["payload_json"] = canonical(body)
    fixture.version["payload_hash"] = hashlib.sha256(canonical(body).encode()).hexdigest()


def clock_execute(session, fixture, *, value=NOW, error=None):
    counter = []

    async def execute(statement, params=None):
        if str(statement) == "SELECT UTC_TIMESTAMP(6) AS evaluated_at":
            counter.append(1)
            if error is not None:
                raise error
            return result([{"evaluated_at": value}])
        return await fixture.execute(statement, params)

    session.execute = execute
    return counter


async def consume(session, access, calendar, ticket, *, size=200):
    values, sizes = [], []
    async for parent_batch in access.iter_account_batches(session, ticket, batch_size=size):
        async for batch in calendar.iter_units(session, ticket, parent_batch):
            calendar.assert_batch(session, ticket, batch)
            values.extend(batch.units)
            sizes.append(len(batch.units))
            with pytest.raises(FrozenInstanceError):
                batch.units[0].currency = "USD"
            with pytest.raises(ValueError):
                calendar.assert_batch(session, ticket, replace(batch, units=()))
    parent_summary = await access.finish(session, ticket)
    summary = calendar.finish(session, ticket, parent_summary)
    calendar.assert_summary(session, ticket, summary)
    return values, sizes, summary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "window,days,last",
    [
        ("TODAY", 1, "2026-11-08"),
        ("YESTERDAY", 1, "2026-11-07"),
        ("LAST_3D", 3, "2026-11-08"),
        ("LAST_7D", 7, "2026-11-08"),
    ],
)
async def test_original_four_windows_real_parent_batch_common_sql_utc_and_timezone(
    monkeypatch, window, days, last
):
    fixture = Fixture(monkeypatch, 1)
    set_window(fixture, window)
    fixture.rows[0]["timezone_id"] = "America/Los_Angeles"
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock = clock_execute(session, fixture)
        values, sizes, summary = await consume(session, access, calendar, ticket)
        assert clock == [1]
        assert summary.evaluated_at == NOW.replace(tzinfo=UTC)
        assert len(values) == days == summary.resolved_unit_count
        assert values[-1].business_date.isoformat() == last
        assert all(
            unit.status == "RESOLVED"
            and unit.currency == "USD"
            and unit.timezone_name == "America/Los_Angeles"
            for unit in values
        )
        assert sizes == [days] and summary.account_count == 1 and summary.calendar_complete
        assert summary.unresolved_account_count == 0
        with pytest.raises(ValueError):
            calendar.assert_summary(session, ticket, replace(summary, calendar_complete=False))


@pytest.mark.asyncio
async def test_thousand_accounts_split_and_same_tx_clock_and_root_invariance(
    monkeypatch,
):
    fixture = Fixture(monkeypatch, 1001)
    set_window(fixture, "LAST_3D")
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        counter = clock_execute(session, fixture)
        values, sizes, summary = await consume(session, access, calendar, ticket, size=1000)
        assert len(values) == 3003 and max(sizes) == 200 and min(sizes) >= 1
        assert [(unit.account_id, unit.business_date) for unit in values] == sorted(
            (unit.account_id, unit.business_date) for unit in values
        )
        assert summary.account_count == 1001 and summary.calendar_complete
        # 第二个原父票据同事务，只复用calendar实例SQL时刻，不重新取时。
        next_ticket = await access.open(session, 91, fixture.head["id"], fixture.head["revision"])
        again, _, next_summary = await consume(session, access, calendar, next_ticket, size=200)
        assert counter == [1] and values == again
        assert next_summary.calendar_root == summary.calendar_root


@pytest.mark.asyncio
async def test_unresolved_sentinel_preserves_all_accounts_no_fake_date_or_currency(monkeypatch):
    fixture = Fixture(monkeypatch, 3)
    set_window(fixture, "TODAY")
    fixture.rows[0].update(timezone_id=None, currency=None)
    fixture.rows[1]["timezone_id"] = "invalid/zone"
    fixture.rows[2]["timezone_id"] = "Asia/Shanghai"
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock_execute(session, fixture)
        values, _, summary = await consume(session, access, calendar, ticket)
        assert len(values) == 3 and summary.account_count == 3
        assert summary.unresolved_account_count == 2 and summary.resolved_unit_count == 1
        assert summary.calendar_complete is False
        for unit in values[:2]:
            assert unit.status == "UNRESOLVED_WINDOW" and unit.business_date is None
            assert unit.reason_code == "TIMEZONE_INVALID"
        assert values[0].timezone_name is None and values[0].currency is None
        assert values[1].timezone_name == "invalid/zone"
        assert values[2].business_date.isoformat() == "2026-11-09"


@pytest.mark.asyncio
async def test_skipped_parent_batch_or_repeated_batch_cannot_issue_calendar_summary(monkeypatch):
    fixture = Fixture(monkeypatch, 401)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock_execute(session, fixture)
        index = 0
        async for parent in access.iter_account_batches(session, ticket):
            if index != 1:
                _ = [unit async for unit in calendar.iter_units(session, ticket, parent)]
            index += 1
        complete = await access.finish(session, ticket)
        with pytest.raises(ValueError, match="COMPLETE_ACCOUNTS"):
            calendar.finish(session, ticket, complete)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["close", "cancel", "parent_advance"])
async def test_partial_calendar_iteration_latches_failure_without_summary(monkeypatch, method):
    fixture = Fixture(monkeypatch, 401)
    set_window(fixture, "LAST_7D")
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock_execute(session, fixture)
        parent_stream = access.iter_account_batches(session, ticket)
        parent = await anext(parent_stream)
        stream = calendar.iter_units(session, ticket, parent)
        await anext(stream)
        if method == "close":
            await stream.aclose()
        elif method == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await stream.athrow(asyncio.CancelledError())
        else:
            await anext(parent_stream)
            with pytest.raises(ValueError):
                await anext(stream)
        await parent_stream.aclose()
        with pytest.raises(ValueError):
            await anext(calendar.iter_units(session, ticket, parent))


@pytest.mark.asyncio
async def test_forged_parent_batch_zero_sql_and_cross_facade_cannot_consume(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        counter = clock_execute(session, fixture)
        stream = access.iter_account_batches(session, ticket)
        parent = await anext(stream)
        with pytest.raises(ValueError):
            await anext(calendar.iter_units(session, ticket, replace(parent, accounts=())))
        with pytest.raises(ValueError):
            await anext(
                RuleSimulationExpectedUnits(RuleSimulationAccessFacade()).iter_units(
                    session, ticket, parent
                )
            )
        assert counter == []
        await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "badvalue", "cancel", "sqlerror"])
async def test_bad_or_cancelled_sql_reference_never_retries_new_time_same_transaction(
    monkeypatch, failure
):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        first = await fixture.open(session, access)
        counter = clock_execute(
            session,
            fixture,
            value=None if failure is None else "invalid" if failure == "badvalue" else NOW,
            error=asyncio.CancelledError()
            if failure == "cancel"
            else RuntimeError("pure")
            if failure == "sqlerror"
            else None,
        )
        parent_stream = access.iter_account_batches(session, first)
        parent = await anext(parent_stream)
        with pytest.raises((OrbitError, asyncio.CancelledError, RuntimeError)):
            await anext(calendar.iter_units(session, first, parent))
        await parent_stream.aclose()
        second = await access.open(session, 91, fixture.head["id"], fixture.head["revision"])
        parent_stream = access.iter_account_batches(session, second)
        parent = await anext(parent_stream)
        with pytest.raises(OrbitError):
            await anext(calendar.iter_units(session, second, parent))
        assert counter == [1]
        await parent_stream.aclose()


@pytest.mark.asyncio
async def test_calendar_summary_rejects_new_actual_transaction_and_repeat_finish(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session:
        async with session.begin():
            ticket = await fixture.open(session, access)
            clock_execute(session, fixture)
            _, _, summary = await consume(session, access, calendar, ticket)
            with pytest.raises(ValueError):
                calendar.finish(session, ticket, summary._parent_summary)
        async with session.begin():
            with pytest.raises(ValueError):
                calendar.assert_summary(session, ticket, summary)


def test_missing_authorization_facade_never_accepts_plain_provider_label():
    with pytest.raises(ValueError):
        RuleSimulationExpectedUnits(None)
    with pytest.raises(ValueError):
        RuleSimulationExpectedUnits("TRUSTED")


@pytest.mark.asyncio
async def test_repeated_or_concurrent_calendar_stream_does_not_return_another_complete_proof(
    monkeypatch,
):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock_execute(session, fixture)
        parent_stream = access.iter_account_batches(session, ticket)
        parent = await anext(parent_stream)
        first = calendar.iter_units(session, ticket, parent)
        await anext(first)
        with pytest.raises(ValueError, match="IN_PROGRESS"):
            await anext(calendar.iter_units(session, ticket, parent))
        with pytest.raises(StopAsyncIteration):
            await anext(first)
        with pytest.raises(ValueError, match="ACCOUNT_ORDER"):
            await anext(calendar.iter_units(session, ticket, parent))
        with pytest.raises(StopAsyncIteration):
            await anext(parent_stream)
        complete = await access.finish(session, ticket)
        with pytest.raises(ValueError):
            calendar.finish(session, ticket, complete)


@pytest.mark.asyncio
async def test_no_calendar_consumption_or_forged_parent_summary_never_finishes(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        counter = clock_execute(session, fixture)
        _ = [batch async for batch in access.iter_account_batches(session, ticket)]
        complete = await access.finish(session, ticket)
        with pytest.raises(ValueError):
            calendar.finish(session, ticket, complete)
        with pytest.raises(ValueError):
            calendar.finish(session, ticket, replace(complete, count=0))
        assert counter == []


@pytest.mark.asyncio
async def test_early_root_cannot_be_issued_before_last_calendar_batch_reaches_eof(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    access = RuleSimulationAccessFacade()
    calendar = RuleSimulationExpectedUnits(access)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, access)
        clock_execute(session, fixture)
        parents = access.iter_account_batches(session, ticket)
        parent = await anext(parents)
        units = calendar.iter_units(session, ticket, parent)
        await anext(units)
        with pytest.raises(StopAsyncIteration):
            await anext(parents)
        complete = await access.finish(session, ticket)
        with pytest.raises(ValueError, match="COMPLETE_STREAM"):
            calendar.finish(session, ticket, complete)
        # 父流已经推进/封存，未EOF的子流也不能再悄悄追认。
        with pytest.raises(ValueError):
            await anext(units)


@pytest.mark.asyncio
async def test_metadata_is_in_calendar_root_and_same_transaction_is_not_a_new_time_source(
    monkeypatch,
):
    async def calculation(currency, timezone):
        fixture = Fixture(monkeypatch, 1)
        fixture.rows[0].update(currency=currency, timezone_id=timezone)
        access = RuleSimulationAccessFacade()
        calendar = RuleSimulationExpectedUnits(access)
        async with AsyncSession() as session, session.begin():
            ticket = await fixture.open(session, access)
            clock_execute(session, fixture)
            _, _, summary = await consume(session, access, calendar, ticket)
            return summary.calendar_root

    base = await calculation("USD", "Asia/Shanghai")
    assert base != await calculation("EUR", "Asia/Shanghai")
    assert base != await calculation("USD", "America/Los_Angeles")
