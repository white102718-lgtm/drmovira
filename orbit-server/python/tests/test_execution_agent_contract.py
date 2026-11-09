"""执行机登记输入合同；不代表设备证书、心跳或执行能力验收。"""

import json

import pytest

from orbit_api.errors import OrbitError


def body(**changes):
    return {
        "name": "Mac执行机",
        "endpoint": "http://localhost:50325",
        "probe_interval": 15,
    } | changes


def parse(value):
    from orbit_api.execution_agent_contract import parse_agent

    return parse_agent(json.dumps(value).encode())


def test_original_agent_write_fields_and_canonical_loopback():
    assert parse(body()) == body(endpoint="http://127.0.0.1:50325")


@pytest.mark.parametrize(
    "changes",
    [
        {"probe_interval": True},
        {"probe_interval": 9},
        {"probe_interval": 301},
        {"probe_interval": "15"},
        {"name": ""},
        {"name": "a" * 81},
        {"api_key": "secret"},
        {"state": "READY"},
        {"last_heartbeat": "2026-11-09T00:00:00Z"},
        {"owner_user_id": "not-an-original-field"},
        {"device_certificate": "secret"},
    ],
)
def test_invalid_or_authority_injecting_fields_are_rejected(changes):
    with pytest.raises(OrbitError) as failure:
        parse(body(**changes))
    expected = (
        400
        if (set(changes) - set(body()) or type(changes.get("probe_interval", 15)) is not int)
        else 422
    )
    assert failure.value.status == expected
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://local.adspower.net:50325",
        "http://127.1:50325",
        "http://127.0.0.1:22",
        "http://127.0.0.1:50325?api_key=secret",
        "http://u:secret@localhost:50325",
        "https://localhost:50325",
        "http://[::1]:50325",
        "http://localhost:50325/status",
    ],
)
def test_endpoint_matches_execution_machine_strict_rule(endpoint):
    from orbit_agent.adspower_status import ProbeError, canonical_endpoint

    with pytest.raises(ProbeError):
        canonical_endpoint(endpoint)
    with pytest.raises(OrbitError) as failure:
        parse(body(endpoint=endpoint))
    assert failure.value.pointer == "/endpoint"


def test_reason_only_and_no_unknown_fields():
    from orbit_api.execution_agent_contract import parse_agent

    assert parse_agent(b'{"reason":"decommission"}', "revoke") == {"reason": "decommission"}
    with pytest.raises(OrbitError):
        parse_agent(b'{"reason":"decommission","api_key":"secret"}', "revoke")


def test_public_shape_never_exposes_internal_scope_or_certificate_metadata():
    from orbit_api.execution_agent_contract import public_agent

    row = body(endpoint="http://127.0.0.1:50325") | {
        "id": "00000000-0000-0000-0000-000000000001",
        "revision": 1,
        "state": "OFFLINE",
        "last_heartbeat": None,
        "tenant_id": "private",
        "owner_user_id": "private",
        "owner_team_id": "private",
    }
    result = public_agent(row)
    assert set(result) == {
        "id",
        "revision",
        "name",
        "endpoint",
        "probe_interval",
        "state",
        "last_heartbeat",
    }
    assert result["state"] == "OFFLINE" and result["last_heartbeat"] is None


@pytest.mark.parametrize(
    "age,expected",
    [(0, "READY"), (44.999, "READY"), (45, "SUSPECT"), (89.999, "SUSPECT"), (90, "OFFLINE")],
)
def test_heartbeat_uses_server_received_time_thresholds(age, expected):
    from datetime import UTC, datetime, timedelta

    from orbit_api.execution_agent_contract import heartbeat_state

    now = datetime.now(UTC)
    assert (
        heartbeat_state(revoked=False, received_at=now - timedelta(seconds=age), now=now)
        == expected
    )
    assert heartbeat_state(revoked=True, received_at=now, now=now) == "REVOKED"
    assert heartbeat_state(revoked=False, received_at=None, now=now) == "OFFLINE"


def test_future_or_naive_time_never_marks_agent_ready():
    from datetime import UTC, datetime, timedelta

    from orbit_api.execution_agent_contract import heartbeat_state

    now = datetime.now(UTC)
    for received in (now + timedelta(seconds=1), datetime.now()):
        with pytest.raises(ValueError):
            heartbeat_state(revoked=False, received_at=received, now=now)


def test_registration_date_uses_beijing_inclusive_day_boundaries():
    from orbit_api.execution_agent_contract import parse_agent_filters

    filters, cursor = parse_agent_filters({"date_from": "2026-11-09", "date_to": "2026-11-09"})
    assert filters["date_from"] == "2026-11-08 16:00:00"
    assert filters["date_to"] == "2026-11-09 16:00:00"
    assert cursor is None


@pytest.mark.parametrize(
    "query",
    [
        {"date_from": "2026-11-10", "date_to": "2026-11-09"},
        {"date_to": "9999-12-31"},
        {"date_from": "bad"},
        {"page_size": "500"},
        {"status": "ONLINE"},
        {"api_key": "secret"},
    ],
)
def test_agent_query_rejects_invalid_or_secret_fields(query):
    from orbit_api.execution_agent_contract import parse_agent_filters

    with pytest.raises(OrbitError):
        parse_agent_filters(query)


def test_unsupported_linked_filters_remain_in_parsed_contract_for_explicit_failure():
    from orbit_api.execution_agent_contract import parse_agent_filters

    filters, _ = parse_agent_filters({"channel_id": "campaign-source", "entity_type": "AD"})
    assert filters["channel_id"] == "campaign-source" and filters["entity_type"] == "AD"
