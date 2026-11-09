"""已完成真实发行票据的配置投影纯测；不授予指标发行资格。"""

from dataclasses import FrozenInstanceError, replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_rule_simulation_access import Fixture

from orbit_api.errors import OrbitError
from orbit_api.rule_profile_references import RuleProfileBinding
from orbit_api.rule_simulation_access import RuleSimulationAccessFacade


def binding(fixture):
    return RuleProfileBinding(
        fixture.head["metric_profile_id"],
        fixture.profile.version,
        1,
        1,
        b"{}",
        fixture.profile.profile_hash,
        "FIXTURE",
        None,
        None,
        b"{}",
    )


@pytest.mark.asyncio
async def test_only_complete_original_summary_returns_same_immutable_binding_without_sql(
    monkeypatch,
):
    fixture = Fixture(monkeypatch, 1)
    profile = binding(fixture)
    fixture.profile_lock.return_value = profile
    facade = RuleSimulationAccessFacade()
    async with AsyncSession() as session:
        async with session.begin():
            ticket = await fixture.open(session, facade)
            with pytest.raises(ValueError):
                facade.verified_profile(session, ticket, None)
            async for _ in facade.iter_account_batches(session, ticket):
                pass
            summary = await facade.finish(session, ticket)
            calls = len(fixture.calls)
            assert facade.verified_profile(session, ticket, summary) is profile
            assert len(fixture.calls) == calls
            with pytest.raises(FrozenInstanceError):
                profile.source_config_id = "invented"
            with pytest.raises(ValueError):
                facade.verified_profile(session, ticket, replace(summary, count=0))
            async with AsyncSession() as other, other.begin():
                with pytest.raises(ValueError):
                    facade.verified_profile(other, ticket, summary)
        async with session.begin():
            with pytest.raises(ValueError):
                facade.verified_profile(session, ticket, summary)


@pytest.mark.asyncio
async def test_untyped_profile_substitute_is_not_promoted_to_verified_binding(monkeypatch):
    fixture = Fixture(monkeypatch, 1)
    facade = RuleSimulationAccessFacade()
    async with AsyncSession() as session, session.begin():
        ticket = await fixture.open(session, facade)
        async for _ in facade.iter_account_batches(session, ticket):
            pass
        summary = await facade.finish(session, ticket)
        with pytest.raises(OrbitError) as error:
            facade.verified_profile(session, ticket, summary)
        assert error.value.code == "RULE_SIMULATION_ACCESS_UNAVAILABLE"
