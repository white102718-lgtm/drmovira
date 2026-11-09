"""原账户动作结构、幂等头、当地日边界纯测试；不计到期执行验收。"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from starlette.datastructures import Headers

from orbit_api.account_actions_contract import (
    next_business_midnight,
    parse_assignment,
    parse_reason,
    validate_effective,
    write_headers,
)
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"


def data():
    return {
        "operator_user_id": ID,
        "owner_team_id": ID,
        "vendor_id": None,
        "effective_from": "2026-11-09T00:00:00+08:00",
        "reason": "明确分配原因",
    }


def test_original_assignment_preserves_nullable_vendor_and_normalizes_utc_boundary():
    value = parse_assignment(json.dumps(data()).encode())
    assert value.vendor_id is None
    assert value.effective_from == "2026-11-08T16:00:00.000Z"
    assert parse_reason('{"reason":"明确原因"}'.encode()) == "明确原因"


def test_fractional_microseconds_cannot_be_truncated_into_exact_business_midnight():
    value = parse_assignment(
        json.dumps(data() | {"effective_from": "2026-11-09T00:00:00.000001+08:00"}).encode()
    )
    with pytest.raises(OrbitError) as failure:
        validate_effective(
            value.effective_from, "Asia/Shanghai", datetime(2026, 11, 8, 6, tzinfo=UTC)
        )
    assert failure.value.code == "ASSIGNMENT_EFFECTIVE_INVALID"


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": ""},
        {"reason": "r" * 1001},
        {"reason": 1},
        {"operator_user_id": None},
        {"owner_team_id": "invalid"},
        {"vendor_id": 1},
        {"effective_from": "2026-11-09"},
        {"effective_from": "2026-11-09T00:00:00"},
        {"extra": "not-allowed"},
    ],
)
def test_invalid_original_assignment_fields_reject(changes):
    with pytest.raises(OrbitError):
        parse_assignment(json.dumps(data() | changes).encode())


@pytest.mark.parametrize("body", [b'{"reason":"","token":"fixture"}', b'{"reason":null}', b"[]"])
def test_reason_rejects_unknown_fields_and_wrong_types(body):
    with pytest.raises(OrbitError):
        parse_reason(body)


@pytest.mark.parametrize(
    "now,hours",
    [
        (datetime(2026, 3, 8, 5, tzinfo=UTC), 23),
        (datetime(2026, 11, 1, 4, tzinfo=UTC), 25),
    ],
)
def test_next_local_day_uses_iana_dst_instead_of_24_hours(now, hours):
    effective = next_business_midnight("America/New_York", now)
    assert effective - now == timedelta(hours=hours)
    assert validate_effective(effective.isoformat(), "America/New_York", now) == effective
    with pytest.raises(OrbitError):
        validate_effective((effective + timedelta(seconds=1)).isoformat(), "America/New_York", now)


def test_nonexistent_midnight_does_not_silently_guess_offset_or_wall_time():
    with pytest.raises(OrbitError) as failure:
        next_business_midnight("Pacific/Apia", datetime(2011, 12, 29, 12, tzinfo=UTC))
    assert failure.value.code == "BUSINESS_MIDNIGHT_UNAVAILABLE"


def test_strict_if_match_and_duplicate_headers_are_not_coerced():
    original = {
        "x-csrf-token": "fixture-csrf-token",
        "idempotency-key": "fixture-key-00001",
        "if-match": '"1"',
    }
    assert write_headers(Headers(original)) == ("fixture-csrf-token", "fixture-key-00001", 1)
    for revision in ("1", '"0"', '"01"', 'W/"1"', '"9007199254740992"'):
        with pytest.raises(OrbitError):
            write_headers(Headers(original | {"if-match": revision}))
    duplicate = Headers(
        raw=[(key.encode(), value.encode()) for key, value in original.items()]
        + [(b"if-match", b'"2"')]
    )
    with pytest.raises(OrbitError):
        write_headers(duplicate)
