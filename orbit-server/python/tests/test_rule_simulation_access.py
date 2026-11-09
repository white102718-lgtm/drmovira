"""有界Rule授权流纯测：真实SessionTransaction/RowMapping，无SQL或来源权威验收。"""

import asyncio
import copy
import hashlib
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_rule_editor_definition import result, sample, uid

import orbit_api.rule_simulation_access as core
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError


class Fixture:
    def __init__(self, monkeypatch, count=401):
        self.head, self.version, self.manifest = sample()
        self.ids = [uid(100 + index) for index in range(count)]
        self.manifest["member_count"] = count
        self.manifest["member_ids_hash"] = hashlib.sha256(canonical(self.ids).encode()).hexdigest()
        self.profile = SimpleNamespace(
            version=self.version["metric_profile_version"],
            profile_hash=self.version["metric_profile_hash"],
            source_proof_json=b"{}",
        )
        self.version["profile_proof_hash"] = hashlib.sha256(b"{}").hexdigest()
        self.current = SimpleNamespace(
            tenant_id=self.head["tenant_id"],
            actor_id=91,
            subject_id=uid(10),
            team_id=uid(11),
            data_role="SUPER_ADMIN",
        )
        self.access = SimpleNamespace(current=self.current, managed_team_ids=())
        self.owner = SimpleNamespace(current=self.current, managed_team_ids=())
        self.calls = []
        self.rows = [
            {
                "account_id": identifier,
                "id": identifier,
                "frozen_owner_user_id": uid(77),
                "frozen_owner_team_id": uid(78),
                "frozen_currency": "EUR",
                "frozen_revision": 1,
                "owner_user_id": self.current.subject_id,
                "owner_team_id": self.current.team_id,
                "currency": "USD",
                "revision": 9,
                "timezone_id": "America/New_York",
            }
            for identifier in self.ids
        ]
        self.authorize = AsyncMock(return_value=self.access)
        self.owner_scope = AsyncMock(return_value=self.owner)
        self.profile_lock = AsyncMock(return_value=self.profile)
        self.revalidate = AsyncMock()
        monkeypatch.setattr(core, "authorize_rule", self.authorize)
        monkeypatch.setattr(core, "owner_scope", self.owner_scope)
        monkeypatch.setattr(core, "lock_rule_profile", self.profile_lock)
        monkeypatch.setattr(core, "account_clock", AsyncMock())
        monkeypatch.setattr(core, "assert_owner", lambda *args: None)
        monkeypatch.setattr(
            core,
            "require_rule_visible",
            lambda access, head: (
                None if head else (_ for _ in ()).throw(OrbitError(404, "NOT_FOUND", "无"))
            ),
        )
        monkeypatch.setattr(core, "revalidate_owner", self.revalidate)

    async def execute(self, statement, params):
        statement = str(statement)
        self.calls.append((statement, params))
        if "FROM orbit_rule_head" in statement:
            return result([copy.deepcopy(self.head)])
        if "FROM orbit_rule_version" in statement:
            return result([copy.deepcopy(self.version)])
        if "FROM orbit_rule_scope_manifest" in statement:
            return result([copy.deepcopy(self.manifest)])
        if "FROM orbit_rule_clock" in statement:
            return result([{"revision": 7}])
        if "FROM orbit_rule_scope_member" in statement:
            selected = [row for row in self.rows if row["account_id"] > params["after"]][
                : params["limit"]
            ]
            return result(copy.deepcopy(selected))
        raise AssertionError("unexpected_query")

    async def open(self, session, facade):
        session.execute = self.execute
        return await facade.open(session, 91, self.head["id"], self.head["revision"])


@pytest.mark.asyncio
@pytest.mark.parametrize("size,count", [(200, 401), (1000, 1001), (200, 1)])
async def test_current_original_permission_bounded_keyset_complete_hash_and_frozen_inputs(
    monkeypatch, size, count
):
    fixture = Fixture(monkeypatch, count)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        fixture.authorize.assert_awaited_once_with(session, 91, "rules.read")
        assert fixture.profile_lock.await_args.kwargs == {
            "expected_version": fixture.version["metric_profile_version"]
        }
        assert fixture.owner_scope.await_args.kwargs == {}
        batches = []
        async for batch in facade.iter_account_batches(session, ticket, batch_size=size):
            facade.assert_batch(session, ticket, batch)
            batches.append(batch)
            with pytest.raises(FrozenInstanceError):
                batch.accounts[0].currency = "JPY"
            with pytest.raises(ValueError):
                facade.assert_batch(session, ticket, replace(batch, accounts=()))
        summary = await facade.finish(session, ticket)
        facade.assert_summary(session, ticket, summary)
        assert summary.count == count and summary.member_hash == fixture.manifest["member_ids_hash"]
        assert [item.account_id for batch in batches for item in batch.accounts] == fixture.ids
        assert all(len(batch.accounts) <= size for batch in batches)
        assert batches[0].accounts[0].timezone_name == "America/New_York"
        assert (
            batches[0].accounts[0].currency == "USD"
        )  # 历史EUR/owner只是审计，不额外收窄当前交集。
        with pytest.raises(ValueError):
            facade.assert_summary(session, ticket, replace(summary, count=0))
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)
        for sql, params in fixture.calls:
            if "FROM orbit_rule_scope_member" in sql:
                assert "LIMIT :limit FOR SHARE OF m,a" in sql and params["limit"] == size
                assert "OFFSET" not in sql
        reads = [sql for sql, _ in fixture.calls]
        assert all(sql.startswith("SELECT") for sql in reads)
        assert next(
            i for i, sql in enumerate(reads) if "FROM orbit_rule_scope_manifest" in sql
        ) < next(i for i, sql in enumerate(reads) if "FROM orbit_rule_clock" in sql)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timezone,currency,error",
    [
        (None, None, "TIMEZONE_INVALID"),
        ("not/a-zone", "USD", "TIMEZONE_INVALID"),
        ("Asia/Shanghai", None, None),
    ],
)
async def test_unknown_timezone_and_currency_remain_unknown_without_utc_or_usd(
    monkeypatch, timezone, currency, error
):
    fixture = Fixture(monkeypatch, 1)
    fixture.rows[0].update(timezone_id=timezone, currency=currency)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        batches = [batch async for batch in facade.iter_account_batches(session, ticket)]
        account = batches[0].accounts[0]
        assert (account.timezone_name, account.currency, account.timezone_error) == (
            timezone,
            currency,
            error,
        )
        summary = await facade.finish(session, ticket)
        assert summary.timezone_invalid_count == int(error is not None)
        assert summary.currency_unknown_count == int(currency is None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["count", "hash", "missing", "owner", "currency", "frozen_revision"]
)
async def test_full_stream_corruption_and_either_current_scope_rejection_has_no_summary(
    monkeypatch, kind
):
    fixture = Fixture(monkeypatch, 201)
    if kind == "count":
        fixture.manifest["member_count"] += 1
    elif kind == "hash":
        fixture.manifest["member_ids_hash"] = "f" * 64
    elif kind == "missing":
        fixture.rows[-1]["id"] = None
    elif kind == "owner":
        fixture.owner.current = SimpleNamespace(subject_id=uid(800), data_role="USER")
    elif kind == "currency":
        fixture.rows[-1]["currency"] = "usd"
    else:
        fixture.rows[-1]["frozen_revision"] = True
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        with pytest.raises(OrbitError):
            async for _ in facade.iter_account_batches(session, ticket):
                pass
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)


@pytest.mark.asyncio
async def test_no_early_finish_repeated_or_concurrent_consumption_and_early_close(monkeypatch):
    fixture = Fixture(monkeypatch, 401)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)
        stream = facade.iter_account_batches(session, ticket)
        batch = await anext(stream)
        facade.assert_batch(session, ticket, batch)
        with pytest.raises(ValueError, match="ALREADY_CONSUMED"):
            await anext(facade.iter_account_batches(session, ticket))
        await stream.aclose()
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)


@pytest.mark.asyncio
async def test_cancellation_or_finish_auth_failure_never_produces_summary(monkeypatch):
    fixture = Fixture(monkeypatch, 401)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        stream = facade.iter_account_batches(session, ticket)
        await anext(stream)
        with pytest.raises(asyncio.CancelledError):
            await stream.athrow(asyncio.CancelledError())
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)
    fixture = Fixture(monkeypatch, 1)
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        _ = [batch async for batch in facade.iter_account_batches(session, ticket)]
        fixture.revalidate.side_effect = OrbitError(403, "PERMISSION_DENIED", "无")
        with pytest.raises(OrbitError):
            await facade.finish(session, ticket)
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)


@pytest.mark.asyncio
async def test_actual_transaction_session_and_issuer_ticket_cannot_be_reused(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session:
        async with session.begin():
            ticket = await fixture.open(session, facade)
            with pytest.raises(ValueError):
                await anext(core.RuleSimulationAccessFacade().iter_account_batches(session, ticket))
            async with AsyncSession() as other, other.begin():
                with pytest.raises(ValueError):
                    await anext(facade.iter_account_batches(other, ticket))
        async with session.begin():
            with pytest.raises(ValueError):
                await anext(facade.iter_account_batches(session, ticket))


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [True, 0, 1, 201, 1001, "200"])
async def test_only_two_internal_batch_bounds_allowed(monkeypatch, size):
    fixture = Fixture(monkeypatch, 1)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        with pytest.raises(ValueError):
            await anext(facade.iter_account_batches(session, ticket, batch_size=size))


@pytest.mark.asyncio
async def test_original_profile_version_drift_is_not_silently_rebound_and_history_not_supported(
    monkeypatch,
):
    fixture = Fixture(monkeypatch, 1)
    fixture.profile_lock.side_effect = OrbitError(409, "METRIC_PROFILE_VERSION_CHANGED", "变更")
    async with AsyncSession() as session, session.begin():
        with pytest.raises(OrbitError) as error:
            await fixture.open(session, core.RuleSimulationAccessFacade())
        assert error.value.code == "METRIC_PROFILE_VERSION_CHANGED"
        assert not any("orbit_account" in sql for sql, _ in fixture.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_at", ["open", "finish"])
async def test_current_head_cas_is_verified_before_ticket_and_before_summary(
    monkeypatch, changed_at
):
    fixture = Fixture(monkeypatch, 1)
    facade = core.RuleSimulationAccessFacade()
    original = fixture.execute

    async def execute(statement, params):
        if (
            changed_at == "open"
            and "FROM orbit_rule_head" in str(statement)
            and "FOR SHARE" in str(statement)
        ):
            fixture.head["revision"] += 1
        return await original(statement, params)

    async with AsyncSession() as session, session.begin():
        if changed_at == "open":
            session.execute = execute
            with pytest.raises(OrbitError) as error:
                await facade.open(session, 91, fixture.head["id"], 3)
            assert error.value.code == "RULE_SOURCE_CHANGED"
        else:
            ticket = await fixture.open(session, facade)
            _ = [batch async for batch in facade.iter_account_batches(session, ticket)]
            fixture.version["payload_hash"] = "0" * 64
            with pytest.raises(OrbitError) as error:
                await facade.finish(session, ticket)
            assert error.value.code == "RULE_SOURCE_CHANGED"


@pytest.mark.asyncio
async def test_concurrent_finish_is_rejected_and_cancellation_latches_failure(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    facade = core.RuleSimulationAccessFacade()
    entered, release = asyncio.Event(), asyncio.Event()

    async def revalidate(*args):
        entered.set()
        await release.wait()

    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        _ = [batch async for batch in facade.iter_account_batches(session, ticket)]
        fixture.revalidate.side_effect = revalidate
        task = asyncio.create_task(facade.finish(session, ticket))
        try:
            await entered.wait()
            with pytest.raises(ValueError, match="FINISH_IN_PROGRESS"):
                await facade.finish(session, ticket)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(ValueError):
                await facade.finish(session, ticket)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task


@pytest.mark.asyncio
async def test_ticket_and_batch_are_not_retained_by_facade_after_caller_releases_them(monkeypatch):
    import gc
    import weakref

    fixture = Fixture(monkeypatch, 1)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        batches = [batch async for batch in facade.iter_account_batches(session, ticket)]
        summary = await facade.finish(session, ticket)
        witness = weakref.ref(ticket)
        del summary, batches, ticket
        gc.collect()
        assert witness() is None


@pytest.mark.asyncio
async def test_explicit_old_batch_cannot_be_reused_after_advancing_stream(monkeypatch):
    fixture = Fixture(monkeypatch, 401)
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        stream = facade.iter_account_batches(session, ticket)
        old = await anext(stream)
        current = await anext(stream)
        with pytest.raises(ValueError):
            facade.assert_batch(session, ticket, old)
        facade.assert_batch(session, ticket, current)
        await stream.aclose()


@pytest.mark.asyncio
async def test_current_member_duplicates_reject_even_if_manifest_count_matches(monkeypatch):
    fixture = Fixture(monkeypatch, 2)
    fixture.rows[1]["account_id"] = fixture.rows[0]["account_id"]
    facade = core.RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        with pytest.raises(OrbitError):
            async for _ in facade.iter_account_batches(session, ticket):
                pass
        with pytest.raises(ValueError):
            await facade.finish(session, ticket)
