"""动作能力不得从在线、身份或调用方布尔值推定。"""

from datetime import UTC, datetime, timedelta

import pytest

from orbit_api.errors import OrbitError


def test_missing_evidence_and_expired_are_not_verified():
    from orbit_api.agent_capability_contract import effective_state

    now = datetime.now(UTC)
    row = dict(
        state="VERIFIED",
        evidence_ref=None,
        verified_at=now,
        expires_at=now + timedelta(days=1),
        binding_revision=2,
        current_binding_revision=2,
        agent_revision=3,
        current_agent_revision=3,
        agent_state="READY",
        unbound_at=None,
        account_unbound_at=None,
        ownership_matches=1,
    )
    assert effective_state(row, now) == "UNVERIFIED"
    row["evidence_ref"] = "receipt:abc"
    assert effective_state(row, now) == "VERIFIED"
    row["expires_at"] = now
    assert effective_state(row, now) == "UNVERIFIED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_binding_revision", 3),
        ("current_agent_revision", 4),
        ("agent_state", "REVOKED"),
        ("ownership_matches", 0),
        ("unbound_at", datetime.now(UTC)),
    ],
)
def test_changed_context_never_inherits_capability(field, value):
    from orbit_api.agent_capability_contract import effective_state

    now = datetime.now(UTC)
    row = dict(
        state="VERIFIED",
        evidence_ref="receipt:abc",
        verified_at=now,
        expires_at=now + timedelta(days=1),
        binding_revision=2,
        current_binding_revision=2,
        agent_revision=3,
        current_agent_revision=3,
        agent_state="READY",
        unbound_at=None,
        account_unbound_at=None,
        ownership_matches=1,
    )
    row[field] = value
    assert effective_state(row, now) != "VERIFIED"


@pytest.mark.parametrize(
    "query", [{"q": "x"}, {"page_size": "201"}, {"page_size": True}, {"cursor": ""}]
)
def test_original_filters_reject_unknown_and_invalid(query):
    from orbit_api.agent_capability_contract import parse_filters

    with pytest.raises(OrbitError):
        parse_filters(query)


def test_receipt_needs_all_failure_modes_and_real_readback():
    from orbit_api.agent_capability_contract import AcceptanceEvidence

    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        AcceptanceEvidence("a" * 64, {}, now, now + timedelta(days=1))
    evidence = AcceptanceEvidence(
        "a" * 64,
        {k: "b" * 64 for k in ("success_readback", "explicit_failure", "unknown", "challenge")},
        now,
        now + timedelta(days=1),
    )
    assert evidence.source_sha256 == "a" * 64


@pytest.mark.asyncio
async def test_revoked_latest_does_not_fall_back_to_old_receipt(monkeypatch):
    import orbit_api.agent_capability_store as m

    captured = []

    async def rows(session, sql, values):
        captured.append(sql)
        return [{"state": "REVOKED", "agent_state": "READY"}]

    monkeypatch.setattr(m, "query_rows", rows)

    async def clock(session):
        return datetime.now(UTC)

    monkeypatch.setattr(m, "now_utc", clock)
    with pytest.raises(OrbitError) as error:
        await m.require_verified(
            None,
            tenant_id="00000000-0000-4000-8000-000000000001",
            agent_id="00000000-0000-4000-8000-000000000002",
            profile_binding_id="00000000-0000-4000-8000-000000000003",
            operation_kind="PAUSE",
            entity_type="CAMPAIGN",
            versions={k: "v1" for k in m.VERSIONS},
        )
    assert error.value.code == "CAPABILITY_UNVERIFIED"
    assert "c.state='VERIFIED'" not in captured[0]


def test_filters_defaults_and_all_page_sizes():
    from orbit_api.agent_capability_contract import parse_filters

    assert parse_filters({}) == (50, None)
    for size in (20, 50, 100, 200):
        assert parse_filters({"page_size": str(size), "cursor": "opaque"}) == (size, "opaque")


@pytest.mark.parametrize(
    "operation,entity",
    [("SET_BUDGET", "CAMPAIGN"), ("BUDGET_SET", "AD"), ("OTHER", "AD"), ("PAUSE", "ACCOUNT")],
)
def test_invalid_operation_entity_cannot_be_verified(operation, entity):
    from orbit_api.agent_capability_contract import VERSIONS, validate_target

    with pytest.raises(ValueError):
        validate_target(operation, entity, {k: "v1" for k in VERSIONS})


@pytest.mark.asyncio
async def test_no_record_is_closed_and_all_versions_bound(monkeypatch):
    import orbit_api.agent_capability_store as m

    captured = []

    async def rows(session, sql, values):
        captured.append((sql, values))
        return []

    monkeypatch.setattr(m, "query_rows", rows)

    async def clock(session):
        return datetime.now(UTC)

    monkeypatch.setattr(m, "now_utc", clock)
    versions = {k: "v1" for k in m.VERSIONS}
    uid = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(OrbitError) as error:
        await m.require_verified(
            None,
            tenant_id=uid,
            agent_id=uid,
            profile_binding_id=uid,
            operation_kind="PAUSE",
            entity_type="AD",
            versions=versions,
        )
    assert error.value.code == "CAPABILITY_UNVERIFIED"
    for key in versions:
        assert "c." + key + "=:" + key in captured[0][0]
        assert captured[0][1][key] == "v1"


@pytest.mark.asyncio
async def test_identity_boolean_cannot_publish_capability():
    from orbit_api.agent_capability_store import AgentCapabilityStore

    with pytest.raises(ValueError, match="ACCEPTANCE_EVIDENCE_REQUIRED"):
        await AgentCapabilityStore().publish(
            None,
            1,
            profile_binding_id="",
            operation_kind="PAUSE",
            entity_type="AD",
            versions={},
            evidence={"verified": True},
            request_id="",
        )
