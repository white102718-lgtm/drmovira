"""独立预期集合结构与常量内存完整流纯测；无发行或MySQL来源验收。"""

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_result_contract import (
    ExpectedEntityMembership,
    ExpectedStreamVerifier,
    ExpectedUnitManifest,
    ExpectedUnitReceipt,
    QuerySourceIdentity,
    require_expected_provider,
)

TENANT, ACTOR, PROFILE, PUBLICATION = (str(uuid4()) for _ in range(4))


def source(**changes):
    return QuerySourceIdentity(
        **{
            "tenant_id": TENANT,
            "publication_id": PUBLICATION,
            "generation": 12,
            "profile_id": PROFILE,
            "profile_version": "observed-v001",
            "profile_hash": "a" * 64,
            "authority_kind": "ISOLATED_TEST",
            **changes,
        }
    )


def unit(**changes):
    return ExpectedUnitReceipt(
        **{
            "tenant_id": TENANT,
            "account_id": str(uuid4()),
            "business_date": date(2026, 1, 1),
            "profile_id": PROFILE,
            "profile_version": "observed-v001",
            "owner_user_id": ACTOR,
            "owner_team_id": str(uuid4()),
            "currency": "USD",
            "timezone_name": "America/New_York",
            "account_snapshot_id": str(uuid4()),
            "attribution_version": 1,
            "entity_count": 0,
            "entity_hash": hashlib.sha256(b"").hexdigest(),
            **changes,
        }
    )


def member(selected, **changes):
    return ExpectedEntityMembership(
        **{
            "tenant_id": TENANT,
            "account_id": selected.account_id,
            "business_date": selected.business_date,
            "profile_id": PROFILE,
            "profile_version": "observed-v001",
            "dataset": "AD",
            "entity_id": str(uuid4()),
            "entity_snapshot_id": str(uuid4()),
            "name_capture_sequence": 120,
            "name_observed_at": datetime(2026, 1, 1, 12, tzinfo=UTC),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"name_capture_sequence": 0},
        {"name_capture_sequence": True},
        {"name_capture_sequence": 1.0},
        {"name_capture_sequence": 9007199254740992},
        {"name_observed_at": None},
        {"name_observed_at": "2026-01-01T12:00:00Z"},
        {"name_observed_at": datetime(2026, 1, 1)},
        {"name_observed_at": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))},
    ],
)
def test_expected_name_evidence_rejects_guessed_or_non_utc_values(changes):
    with pytest.raises(OrbitError) as error:
        member(unit(), **changes)
    assert error.value.status == 503


def test_expected_name_evidence_is_required_and_bound_into_complete_member_root():
    selected = unit()
    original = member(selected)
    changed = replace(original, name_capture_sequence=121)
    moved = replace(
        original, name_observed_at=original.name_observed_at + timedelta(microseconds=1)
    )
    assert len({stream_hash([item]) for item in (original, changed, moved)}) == 3
    with pytest.raises(TypeError):
        ExpectedEntityMembership(*original.record()[:8])


def stream_hash(items):
    return hashlib.sha256(
        b"".join(canonical(item.record()).encode() + b"\n" for item in items)
    ).hexdigest()


def manifest(units=(), memberships=(), **changes):
    return ExpectedUnitManifest(
        **{
            "source": source(),
            "actor_id": 1,
            "subject_id": ACTOR,
            "auth_version": 1,
            "auth_fingerprint": "b" * 64,
            "query_hash": "c" * 64,
            "dataset": "AD",
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 1, 31),
            "scope_snapshot_id": None,
            "scope_hash": None,
            "scope_count": None,
            "unit_count": len(units),
            "unit_hash": stream_hash(units),
            "membership_count": len(memberships),
            "membership_hash": stream_hash(memberships),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "a" * 32),
        ("publication_id", str(uuid4()).upper()),
        ("profile_id", None),
        ("generation", True),
        ("generation", 0),
        ("generation", 1.0),
        ("generation", 9007199254740992),
        ("profile_version", ""),
        ("profile_version", "x" * 65),
        ("profile_version", "\ud800"),
        ("profile_hash", "A" * 64),
        ("authority_kind", "LABEL_ONLY"),
    ],
)
def test_source_identity_strict_shape_is_not_authority(field, value):
    with pytest.raises(OrbitError) as result:
        source(**{field: value})
    assert result.value.status == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_id": True},
        {"auth_version": 0},
        {"subject_id": "not-uuid"},
        {"scope_hash": "d" * 64},
        {"scope_count": 0},
        {"scope_snapshot_id": str(uuid4())},
        {"scope_snapshot_id": str(uuid4()), "scope_hash": "d" * 64, "scope_count": 50001},
        {"unit_count": -1},
        {"membership_count": True},
        {"unit_hash": "bad"},
        {"date_from": datetime(2026, 1, 1)},
        {"date_to": date(2025, 1, 1)},
        {"date_to": date(2026, 4, 4)},
        {"dataset": "ASSET"},
        {"source": {}},
    ],
)
def test_manifest_binds_complete_source_scope_and_original_93_days(changes):
    with pytest.raises(OrbitError):
        manifest(**changes)


def test_null_scope_has_no_50k_query_limit_and_known_scope_preserves_zero():
    unlimited = manifest(unit_count=4_650_000, membership_count=10_000_000)
    assert unlimited.scope_count is None and unlimited.unit_count == 4_650_000
    zero = manifest(scope_snapshot_id=str(uuid4()), scope_hash="d" * 64, scope_count=0)
    assert zero.scope_count == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"business_date": "2026-01-01"},
        {"business_date": datetime(2026, 1, 1)},
        {"account_id": "act_123"},
        {"owner_user_id": "user-1"},
        {"currency": "US"},
        {"timezone_name": "UTC+8"},
        {"attribution_version": True},
        {"entity_count": -1},
        {"entity_hash": "x" * 64},
        {"profile_version": None},
    ],
)
def test_expected_unit_requires_real_frozen_fields_not_current_defaults(changes):
    with pytest.raises(OrbitError):
        unit(**changes)


def test_nullable_frozen_owners_remain_null_and_dst_zone_is_preserved():
    selected = unit(owner_user_id=None, owner_team_id=None)
    assert selected.owner_user_id is selected.owner_team_id is None
    assert selected.timezone_name == "America/New_York"
    with pytest.raises(FrozenInstanceError):
        selected.currency = "EUR"


@pytest.mark.parametrize(
    "changes",
    [
        {"entity_id": "12345"},
        {"dataset": "LAUNCH"},
        {"entity_snapshot_id": None},
        {"profile_version": ""},
    ],
)
def test_entity_membership_does_not_replace_internal_entity_with_external_id(changes):
    with pytest.raises(OrbitError):
        member(unit(), **changes)


@pytest.mark.parametrize("provider", [None, True, {"kind": "TRUSTED"}, object()])
def test_missing_expected_provider_is_explicit_503_without_io(provider):
    with pytest.raises(OrbitError) as result:
        require_expected_provider(provider)
    assert result.value.code == "METRICS_DATA_UNVERIFIED"


def test_complete_unit_stream_is_chunk_independent_and_200_bounded():
    selected = sorted([unit() for _ in range(401)], key=lambda item: item.key())
    expected = manifest(selected)
    verifier = ExpectedStreamVerifier(expected)
    verifier.add(tuple(selected[:200]))
    verifier.add(tuple(selected[200:400]))
    verifier.add(tuple(selected[400:]))
    assert verifier.finish() == 401
    assert set(vars(verifier)) == {
        "manifest",
        "memberships",
        "unit",
        "_count",
        "_last",
        "_digest",
        "_finished",
    }
    with pytest.raises(OrbitError):
        verifier.finish()


def test_empty_expected_set_verifies_empty_root_without_fake_units():
    assert ExpectedStreamVerifier(manifest()).finish() == 0
    with pytest.raises(OrbitError):
        ExpectedStreamVerifier(manifest()).add((unit(),))


@pytest.mark.parametrize(
    "failure", ["missing", "extra", "duplicate", "unordered", "wrong-root", "oversize", "list"]
)
def test_expected_stream_rejects_incomplete_or_changed_full_roster(failure):
    selected = sorted([unit() for _ in range(2)], key=lambda item: item.key())
    expected = manifest(selected)
    verifier = ExpectedStreamVerifier(expected)
    with pytest.raises(OrbitError):
        if failure == "missing":
            verifier.add((selected[0],))
            verifier.finish()
        elif failure == "extra":
            verifier.add(tuple(selected) + (unit(),))
        elif failure == "duplicate":
            verifier.add((selected[0], selected[0]))
        elif failure == "unordered":
            verifier.add(tuple(reversed(selected)))
        elif failure == "wrong-root":
            ExpectedStreamVerifier(replace(expected, unit_hash="f" * 64)).add(tuple(selected))
            changed = ExpectedStreamVerifier(replace(expected, unit_hash="f" * 64))
            changed.add(tuple(selected))
            changed.finish()
        elif failure == "oversize":
            verifier.add(tuple(unit() for _ in range(201)))
        else:
            verifier.add(selected)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": str(uuid4())},
        {"profile_id": str(uuid4())},
        {"profile_version": "other"},
        {"business_date": date(2026, 2, 1)},
    ],
)
def test_wrong_unit_context_rejects_atomically_without_half_batch(changes):
    selected = sorted([unit() for _ in range(2)], key=lambda item: item.key())
    verifier = ExpectedStreamVerifier(manifest(selected))
    with pytest.raises(OrbitError):
        verifier.add((selected[0], replace(selected[1], **changes)))
    assert verifier._count == 0
    verifier.add(tuple(selected))
    assert verifier.finish() == 2


def test_membership_stream_rejects_duplicate_entity_with_different_snapshot():
    selected = unit()
    records = sorted([member(selected) for _ in range(201)], key=lambda item: item.key())
    verifier = ExpectedStreamVerifier(manifest((selected,), records), memberships=True)
    verifier.add(tuple(records[:200]))
    verifier.add(tuple(records[200:]))
    assert verifier.finish() == 201
    other_snapshot = replace(records[0], entity_snapshot_id=str(uuid4()))
    broken = ExpectedStreamVerifier(
        manifest((selected,), (records[0], other_snapshot)), memberships=True
    )
    with pytest.raises(OrbitError):
        broken.add((records[0], other_snapshot))


def test_each_unit_membership_root_and_count_are_verified_separately():
    selected = unit()
    records = sorted([member(selected) for _ in range(3)], key=lambda item: item.key())
    selected = replace(selected, entity_count=3, entity_hash=stream_hash(records))
    expected = manifest((selected,), records)
    verifier = ExpectedStreamVerifier(expected, memberships=True, unit=selected)
    verifier.add(tuple(records))
    assert verifier.finish() == 3
    bad = ExpectedStreamVerifier(
        expected, memberships=True, unit=replace(selected, entity_hash="f" * 64)
    )
    bad.add(tuple(records))
    with pytest.raises(OrbitError):
        bad.finish()
    wrong_account = replace(records[0], account_id=str(uuid4()))
    with pytest.raises(OrbitError):
        ExpectedStreamVerifier(expected, memberships=True, unit=selected).add((wrong_account,))
