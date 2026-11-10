"""历史指标为独立wrapper，不扩原13字段。"""

import json

import pytest

from orbit_api.errors import OrbitError
from orbit_api.metrics_contract import parse_metric_query


def query():
    return {
        "date_from": "2026-11-01",
        "date_to": "2026-11-02",
        "dataset": "ACCOUNT",
        "metric_profile_id": "00000000-0000-4000-8000-000000000001",
        "scope_snapshot_id": None,
        "channel_id": None,
        "operator_user_id": None,
        "q": "",
        "sort": "spend",
        "direction": "DESC",
        "cursor": None,
        "page_size": 50,
        "granularity": "SUMMARY",
    }


def test_history_wrapper_preserves_original_contract_and_hash_distinction():
    from orbit_api.metrics_contract import parse_history_metric_query, parse_internal_metric_query
    from orbit_api.metrics_query_store import metric_query_hash

    original = query()
    parsed = parse_history_metric_query(
        json.dumps({"query": original, "metric_profile_version": "archived.v1"}).encode()
    )
    assert parsed["_history_profile_version"] == "archived.v1"
    assert parse_internal_metric_query(json.dumps(parsed).encode()) == parsed
    assert parse_internal_metric_query(json.dumps(original).encode()) == parse_metric_query(
        json.dumps(original).encode()
    )
    with pytest.raises(OrbitError):
        parse_metric_query(json.dumps(parsed).encode())
    assert metric_query_hash(parsed) != metric_query_hash(original)
    assert metric_query_hash(parsed) != metric_query_hash(
        parsed | {"_history_profile_version": "archived.v2"}
    )


@pytest.mark.parametrize("version", [None, "", True, "x" * 65])
def test_invalid_history_version_is_never_inferred(version):
    from orbit_api.metrics_contract import parse_history_metric_query

    with pytest.raises(OrbitError):
        parse_history_metric_query(
            json.dumps({"query": query(), "metric_profile_version": version}).encode()
        )


def test_historical_source_resolves_explicit_version_without_current_head(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import orbit_api.metrics_query_store as module
    from orbit_api.metrics_contract import parse_history_metric_query

    response = {
        "id": query()["metric_profile_id"],
        "current_version": "archived.v1",
        "revision": 7,
        "payload_hash": "a" * 64,
    }
    reader = AsyncMock(return_value=[response])
    monkeypatch.setattr(module, "rows", reader)
    scope = SimpleNamespace(
        current=SimpleNamespace(
            tenant_id="tenant", subject_id="owner", actor_id=3, data_role="USER"
        )
    )
    parsed = parse_history_metric_query(
        json.dumps({"query": query(), "metric_profile_version": "archived.v1"}).encode()
    )
    result = asyncio.run(module.MetricsQueryStore()._profile(None, scope, parsed))
    assert result == (response["id"], "archived.v1", 7, "a" * 64)
    sql = reader.call_args.args[1]
    params = reader.call_args.args[2]
    assert "h.current_version" not in sql and "h.state='ENABLED'" not in sql
    assert "orbit_meta_metric_publication_receipt" in sql
    assert "hc.owner_user_id=:subject" in sql
    assert params["version"] == "archived.v1"
    assert params["subject"] == "owner"
