"""真实父票据/事务与RowMapping，SQL/独立authority皆纯替身，不是Meta发行。"""

import copy
import json
from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_metrics_query_store import head
from test_rule_editor_definition import result, uid
from test_rule_simulation_access import Fixture
from test_rule_simulation_expected_units import clock_execute, consume

import orbit_api.rule_metric_publication_access as core
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_store import (
    PublicationValidationReceipt,
    publication_validation_binding,
)
from orbit_api.rule_profile_references import RuleProfileBinding
from orbit_api.rule_simulation_access import RuleSimulationAccessFacade
from orbit_api.rule_simulation_expected_units import RuleSimulationExpectedUnits


class RegisteredPureAuthority(core.RulePublicationAuthority):
    """仅测试：预先登记独立tuple，而非收到头后即算hash返回成功。"""

    def __init__(self, heads):
        self.registered = {row["id"]: publication_validation_binding(row) for row in heads}
        self.calls = []
        self.transform = lambda rows: rows

    async def verify_publications(self, session, binding, heads):
        self.calls.append((binding, heads))
        receipts = tuple(PublicationValidationReceipt(self.registered[row["id"]]) for row in heads)
        return self.transform(receipts)


class Setup:
    def __init__(self, monkeypatch):
        self.fixture = Fixture(monkeypatch, 1)
        f = self.fixture
        self.profile = RuleProfileBinding(
            f.head["metric_profile_id"],
            f.version["metric_profile_version"],
            1,
            1,
            b"{}",
            f.version["metric_profile_hash"],
            "META",
            uid(800),
            3,
            b"{}",
        )
        f.profile_lock.return_value = self.profile
        self.access = RuleSimulationAccessFacade()
        self.calendar = RuleSimulationExpectedUnits(self.access)
        self.anchor = head(
            tenant_id=f.current.tenant_id,
            profile_id=self.profile.profile_id,
            profile_version=self.profile.version,
            profile_hash=self.profile.profile_hash,
            authority_kind="TRUSTED",
            source_config_id=self.profile.source_config_id,
            source_config_revision=3,
            id=uid(900),
            generation=10,
            capture_sequence_max=120,
        )
        self.old = self.anchor | {"id": uid(899), "generation": 9, "capture_sequence_max": 110}
        self.heads = [self.old, self.anchor]
        self.authority = RegisteredPureAuthority(self.heads)
        self.sql = []

    async def prepare(self, session):
        ticket = await self.fixture.open(session, self.access)
        clock_execute(session, self.fixture)
        _, _, summary = await consume(session, self.access, self.calendar, ticket)

        async def execute(statement, params):
            sql = str(statement)
            self.sql.append((sql, params))
            if "ORDER BY p.generation DESC" in sql:
                return result([copy.deepcopy(self.anchor)])
            if "p.id IN" in sql:
                return result(
                    [
                        copy.deepcopy(row)
                        for row in sorted(self.heads, key=lambda r: r["id"])
                        if row["id"] in params["ids"]
                    ]
                )
            raise AssertionError("unexpected_SQL")

        session.execute = execute
        return ticket, summary

    def reader(self, authority=True):
        return core.RuleMetricPublicationAccess(
            self.access, self.calendar, self.authority if authority else None
        )


@pytest.mark.asyncio
async def test_actual_parent_calendar_and_independent_registered_receipts_freeze_cutoff(
    monkeypatch,
):
    s = Setup(monkeypatch)
    reader = s.reader()
    async with AsyncSession() as session, session.begin():
        parent, calendar = await s.prepare(session)
        ticket = await reader.open(session, parent, calendar)
        assert ticket.generation == 10 and ticket.capture_sequence_max == 120
        assert ticket.binding.profile_id == json.loads(parent.rule_json)["metric_profile_id"]
        batch = await reader.verify_heads(session, ticket, (s.anchor["id"], s.old["id"]))
        reader.assert_batch(session, ticket, batch)
        assert batch.publications == tuple(publication_validation_binding(row) for row in s.heads)
        assert len(s.authority.calls) == 2
        assert all(
            "orbit_metric_publication" in sql and sql.startswith("SELECT") for sql, _ in s.sql
        )
        assert not any("orbit_system_configuration" in sql for sql, _ in s.sql)
        assert "LIMIT 1 FOR SHARE" in s.sql[0][0]
        assert ticket.binding.calendar_root == calendar.calendar_root
        with pytest.raises(TypeError):
            s.authority.calls[0][1][0]["id"] = uid(999)
        with pytest.raises(ValueError):
            reader.assert_batch(session, ticket, replace(batch, publications=()))
        with pytest.raises(ValueError):
            await reader.verify_heads(session, replace(ticket, generation=100), (s.old["id"],))


@pytest.mark.asyncio
async def test_no_authority_before_sql_even_with_forged_parents(monkeypatch):
    s = Setup(monkeypatch)
    async with AsyncSession() as session, session.begin():

        async def forbidden(*args):
            raise AssertionError("SQL_before_default_failure")

        session.execute = forbidden
        with pytest.raises(OrbitError) as error:
            await s.reader(False).open(session, object(), object())
        assert error.value.status == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["calendar", "ticket", "facade"])
async def test_forged_parent_or_other_issuer_cannot_reach_sql(monkeypatch, kind):
    s = Setup(monkeypatch)
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        reader = s.reader()
        if kind == "calendar":
            summary = replace(summary, calendar_root="f" * 64)
        elif kind == "ticket":
            parent = replace(parent, revision=88)
        else:
            reader = core.RuleMetricPublicationAccess(
                RuleSimulationAccessFacade(), s.calendar, s.authority
            )
        with pytest.raises(ValueError):
            await reader.open(session, parent, summary)
        assert s.sql == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,config,revision",
    [("FIXTURE", None, None), ("META", None, None), ("META", uid(800), True)],
)
async def test_no_unlocked_fixture_source_or_bad_config_is_accepted(
    monkeypatch, source, config, revision
):
    s = Setup(monkeypatch)
    s.fixture.profile_lock.return_value = replace(
        s.profile, source=source, source_config_id=config, source_config_revision=revision
    )
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        with pytest.raises(OrbitError):
            await s.reader().open(session, parent, summary)
        assert s.sql == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", uid(777)),
        ("profile_id", uid(777)),
        ("profile_version", "new"),
        ("profile_hash", "f" * 64),
        ("source_config_id", uid(777)),
        ("source_config_revision", 4),
        ("authority_kind", "ISOLATED_TEST"),
        ("state", "SEALED"),
        ("cell_count", 2),
        ("captured_cells_hash", "f" * 64),
        ("generation", True),
    ],
)
async def test_bad_latest_head_fails_not_silent_fallback_or_partial_authority(
    monkeypatch, field, value
):
    s = Setup(monkeypatch)
    s.anchor[field] = value
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        with pytest.raises(OrbitError) as error:
            await s.reader().open(session, parent, summary)
        assert error.value.code == "RULE_PUBLICATION_SOURCE_UNAVAILABLE"
        assert len(s.sql) == 1 and not s.authority.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "duplicate", "bool", "changed", "non_tuple"])
async def test_independent_receipt_exact_set_type_and_all_columns(monkeypatch, kind):
    s = Setup(monkeypatch)

    def transform(rows):
        if kind == "missing":
            return ()
        if kind == "duplicate":
            return rows + rows
        if kind == "non_tuple":
            return list(rows)
        values = list(rows[0].binding)
        values[2 if kind == "bool" else 17] = True if kind == "bool" else "f" * 64
        return (PublicationValidationReceipt(tuple(values)),)

    s.authority.transform = transform
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        with pytest.raises(OrbitError):
            await s.reader().open(session, parent, summary)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ids", [(), tuple(uid(1000 + i) for i in range(201)), (uid(899), uid(899)), [uid(899)]]
)
async def test_one_to_two_hundred_ids_no_duplicate_or_unbounded_query(monkeypatch, ids):
    s = Setup(monkeypatch)
    reader = s.reader()
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        ticket = await reader.open(session, parent, summary)
        count = len(s.sql)
        with pytest.raises(ValueError):
            await reader.verify_heads(session, ticket, ids)
        assert len(s.sql) == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [("generation", 11), ("capture_sequence_max", 121), ("source_config_revision", 4)],
)
async def test_selected_head_cannot_cross_anchor_cutoff_or_same_source(monkeypatch, field, value):
    s = Setup(monkeypatch)
    reader = s.reader()
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        ticket = await reader.open(session, parent, summary)
        s.old[field] = value
        with pytest.raises(OrbitError):
            await reader.verify_heads(session, ticket, (s.old["id"],))


@pytest.mark.asyncio
async def test_missing_requested_head_and_cross_transaction_fail_closed(monkeypatch):
    s = Setup(monkeypatch)
    reader = s.reader()
    async with AsyncSession() as session:
        async with session.begin():
            parent, summary = await s.prepare(session)
            ticket = await reader.open(session, parent, summary)
            with pytest.raises(OrbitError):
                await reader.verify_heads(session, ticket, (uid(999),))
        async with session.begin():
            with pytest.raises(ValueError):
                await reader.verify_heads(session, ticket, (s.old["id"],))


@pytest.mark.asyncio
async def test_full_two_hundred_headers_are_bounded_and_exact(monkeypatch):
    s = Setup(monkeypatch)
    s.heads = [s.old | {"id": uid(1000 + i)} for i in range(200)]
    s.authority = RegisteredPureAuthority([s.anchor, *s.heads])
    reader = s.reader()
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)
        ticket = await reader.open(session, parent, summary)
        batch = await reader.verify_heads(
            session, ticket, tuple(row["id"] for row in reversed(s.heads))
        )
        reader.assert_batch(session, ticket, batch)
        assert len(batch.publications) == 200
        assert len(s.authority.calls[-1][1]) == 200
        assert len(s.sql) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("badkind", [True, [], None])
async def test_bad_authority_kind_fails_safe_before_sql(monkeypatch, badkind):
    s = Setup(monkeypatch)
    s.authority.kind = badkind
    async with AsyncSession() as session, session.begin():
        with pytest.raises(OrbitError):
            await s.reader().open(session, object(), object())
        assert s.sql == []


@pytest.mark.asyncio
async def test_no_published_anchor_never_produces_read_ticket(monkeypatch):
    s = Setup(monkeypatch)
    async with AsyncSession() as session, session.begin():
        parent, summary = await s.prepare(session)

        async def no_heads(*args):
            return result([])

        session.execute = no_heads
        with pytest.raises(OrbitError):
            await s.reader().open(session, parent, summary)
        assert s.authority.calls == []
