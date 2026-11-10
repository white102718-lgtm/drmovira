"""连接指标来源合同：真实证明和配置版本，不以verified字面授信。"""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.metric_profile_contract import MetricSourceProof, check_proof


def test_connection_proof_supports_login_without_bm_config():
    proof = MetricSourceProof(
        "a" * 64,
        datetime.now(UTC),
        "meta:account",
        None,
        None,
        source_connection_id=str(uuid4()),
        source_connection_revision=2,
    )
    assert check_proof(proof, "META") == proof


def test_connection_proof_rejects_two_sources_or_partial_revision():
    proof = MetricSourceProof(
        "a" * 64,
        datetime.now(UTC),
        "meta:account",
        None,
        None,
        source_connection_id=str(uuid4()),
        source_connection_revision=2,
    )
    for bad in (
        replace(proof, source_config_id=str(uuid4()), source_config_revision=1),
        replace(proof, source_connection_revision=None),
    ):
        with pytest.raises(OrbitError):
            check_proof(bad, "META")


def test_old_proof_document_remains_byte_compatible():
    import json

    from orbit_api.metric_profile_contract import parse_source_proof
    from orbit_api.metric_profile_store import proof_document

    proof = MetricSourceProof("a" * 64, datetime.now(UTC), "meta:account", str(uuid4()), 1)
    document = json.loads(proof_document(proof))
    assert "source_connection_id" not in document
    assert parse_source_proof(document, "META") == proof


def settings():
    return {
        "profileVersion": "2026.11",
        "registerActionType": "offsite_conversion.fb_pixel_complete_registration",
        "purchaseActionType": "offsite_conversion.fb_pixel_purchase",
        "valueActionType": "offsite_conversion.fb_pixel_purchase",
        "intervalMinutes": 15,
        "lookbackDays": 7,
    }


def test_profile_mapping_reuses_saved_fields_and_requires_explicit_window():
    from orbit_api.meta_metric_profile_source import profile_from_settings

    identifier = str(uuid4())
    profile, mapping = profile_from_settings(
        identifier, settings(), ["7d_click", "1d_view"], "conversion", 28, "v24.0"
    )
    assert profile["id"] == identifier
    assert profile["version"] == "2026.11"
    assert profile["purchase_action_type"] == settings()["purchaseActionType"]
    assert mapping == [
        {"event_type": "CLICK_THROUGH", "window_days": 7},
        {"event_type": "VIEW_THROUGH", "window_days": 1},
    ]
    for windows in ([], ["28d_click"], ["7d_click", "7d_click"]):
        with pytest.raises(OrbitError):
            profile_from_settings(identifier, settings(), windows, "conversion", 28, "v24.0")


def test_profile_mapping_never_defaults_missing_business_fields():
    from orbit_api.meta_metric_profile_source import profile_from_settings

    for field in ("profileVersion", "registerActionType", "purchaseActionType", "valueActionType"):
        invalid = settings()
        invalid.pop(field)
        with pytest.raises(OrbitError):
            profile_from_settings(str(uuid4()), invalid, ["1d_click"], "impression", 28, "v24.0")
    with pytest.raises(OrbitError):
        profile_from_settings(str(uuid4()), settings(), ["1d_click"], "default", 28, "v24.0")


def test_publication_request_rejects_unknown_fields_and_never_accepts_proof():
    from orbit_api.meta_metric_profile_source import parse_selection

    request = {
        "configuration_id": str(uuid4()),
        "configuration_revision": 1,
        "connection_id": str(uuid4()),
        "connection_revision": 2,
        "account_id": "100000000000001",
        "attribution_windows": ["7d_click"],
        "action_report_time": "conversion",
        "maturity_days": 28,
        "expected_revision": 0,
    }
    assert parse_selection(request)["account_id"] == request["account_id"]
    for extra in ("proof", "verified", "tenant_id", "actor_id"):
        with pytest.raises(OrbitError):
            parse_selection(request | {extra: True})
    for field, value in [
        ("connection_revision", True),
        ("expected_revision", -1),
        ("account_id", "act_123"),
    ]:
        with pytest.raises(OrbitError):
            parse_selection(request | {field: value})


@pytest.mark.parametrize(
    "fault", ["none", "incomplete", "wrong_account", "wrong_source", "no_receipt", "config_changed"]
)
def test_authority_requires_actual_complete_account_and_revalidates_snapshot(monkeypatch, fault):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import orbit_api.meta_metric_profile_source as module
    from orbit_api.meta_read_contract import MetaReadConfiguration, ReadPage

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    selected = {
        "configuration_id": str(uuid4()),
        "configuration_revision": 1,
        "connection_id": str(uuid4()),
        "connection_revision": 2,
        "account_id": "123",
        "attribution_windows": ["7d_click"],
        "action_report_time": "conversion",
        "maturity_days": 28,
    }
    current = SimpleNamespace(tenant_id=str(uuid4()), actor_id=1)
    config = MetaReadConfiguration(selected["connection_id"], 2, "v24.0", "private-test-token")
    page = ReadPage(
        ({"account_id": "123"},),
        None,
        True,
        config.fingerprint,
        "b" * 64,
        "c" * 64,
        datetime.now(UTC),
    )
    if fault == "incomplete":
        page = replace(page, complete=False)
    if fault == "wrong_account":
        page = replace(page, items=({"account_id": "456"},))
    if fault == "wrong_source":
        page = replace(page, source_fingerprint="d" * 64)
    if fault == "no_receipt":
        page = {"account_id": "123"}
    adapter = SimpleNamespace(account_page=AsyncMock(return_value=page))
    row = {"id": selected["configuration_id"], "revision": 1, "settings_json": settings()}
    monkeypatch.setattr(module, "publisher", AsyncMock(return_value=current))
    monkeypatch.setattr(
        module, "load_connection", AsyncMock(return_value=SimpleNamespace(configuration=config))
    )
    verify = AsyncMock()
    monkeypatch.setattr(module, "validate_current_source", verify)
    authority = module.MetaMetricProfileAuthority(
        Session, None, 1, selected, "v24.0", adapter_factory=lambda config: adapter
    )
    authority.configuration = AsyncMock(return_value=row)

    async def run():
        prepared = await authority.capture(row["id"], "2026.11", module.ADAPTER_VERSION)
        if fault == "config_changed":
            row["settings_json"] = settings() | {"purchaseActionType": "changed"}
        await authority.revalidate(Session(), current, prepared)
        return prepared

    if fault == "none":
        prepared = asyncio.run(run())
        assert prepared.proof.source_config_id is None
        assert prepared.proof.source_connection_id == selected["connection_id"]
        assert prepared.profile()["verified"] is True
        verify.assert_awaited_once()
    else:
        with pytest.raises(OrbitError):
            asyncio.run(run())
    adapter.account_page.assert_awaited_once_with("123")


def test_history_candidate_visibility_requires_published_receipt_and_frozen_owner():
    from types import SimpleNamespace

    from orbit_api.metric_profile_query import history_source_clause

    own = history_source_clause(SimpleNamespace(data_role="USER"))
    assert "PUBLISHED" in own and "orbit_meta_metric_publication_receipt" in own
    assert "hc.owner_user_id=:subject" in own and "team_manager" not in own
    team = history_source_clause(SimpleNamespace(data_role="TEAM_ADMIN"))
    assert "tm.manager_user_id=:actor" in team and "tm.enabled=1" in team
    assert "mc.status='ACTIVE'" not in own


@pytest.mark.parametrize(
    "current_revision,connection_matches,allowed",
    [(2, True, True), (3, True, True), (1, True, False), (3, False, False)],
)
def test_collection_reauthorization_continuity_keeps_original_mapping(
    monkeypatch, current_revision, connection_matches, allowed
):
    import asyncio
    from unittest.mock import AsyncMock

    import orbit_api.meta_account_sources as sources
    import orbit_api.metric_profile_store as store

    proof = MetricSourceProof(
        "a" * 64, datetime.now(UTC), "receipt:original", None, None, str(uuid4()), 2
    )
    current_id = proof.source_connection_id if connection_matches else str(uuid4())
    loader = AsyncMock(return_value={"kind": "LOGIN"})
    monkeypatch.setattr(sources, "connection_row", loader)

    async def verify():
        await store.validate_collection_source(
            None, str(uuid4()), proof, current_id, current_revision
        )

    if allowed:
        asyncio.run(verify())
        loader.assert_awaited_once()
    else:
        with pytest.raises(OrbitError):
            asyncio.run(verify())
        loader.assert_not_awaited()
