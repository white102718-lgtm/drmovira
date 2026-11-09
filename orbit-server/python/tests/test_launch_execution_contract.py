"""execute纯完整清单协议；所有能力证据均为明确夹具，不证明平台写权限。"""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest
from test_launch_validation_contract import fixture as validation_fixture
from test_launch_validation_contract import uid

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation import build_compatibility_evidence, solve_allocation
from orbit_api.launch_dag import build_launch_dag
from orbit_api.launch_execution_contract import (
    iter_execution_nodes,
    iter_prepared_chunks,
    prepare_execution,
)
from orbit_api.launch_expansion import ad_slots
from orbit_api.launch_plan_source import PlanSource
from orbit_api.launch_validation_contract import freeze_validation
from orbit_api.launch_validation_store import ObservationReference


def fixture(*, activate=False, destination="WEBSITE", accounts=2, ad_copies=2):
    plan, args = validation_fixture(accounts=accounts, ad_copies=ad_copies)
    plan["activate_after_create"] = activate
    campaign = plan["campaigns"][0]
    campaign.update(
        objective="OUTCOME_SALES",
        buying_type="AUCTION",
        special_ad_categories=[],
        bid_strategy="LOWEST_COST_WITHOUT_CAP",
    )
    group = campaign["adsets"][0]
    group.update(
        name="真实冻结广告组",
        country_codes=["US"],
        age_min=18,
        age_max=65,
        placements="AUTO",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        metric_profile_id=uid(700),
    )
    args["channel_snapshot"]["type"] = "WEBSITE"
    group["ads"][0].update(
        name="真实冻结广告",
        body="真实文案",
        cta="LEARN_MORE",
        asset_type="IMAGE",
        url="https://example.org/landing",
    )
    args["channel_snapshot"]["type"] = destination
    if destination == "APP":
        campaign["objective"] = "OUTCOME_APP_PROMOTION"
        group["ads"][0]["url"] = None
        for binding in plan["identity_bindings"]:
            for item in binding["groups"]:
                item.update(
                    pixel_id=None,
                    conversion_event=None,
                    application_id="456789",
                    object_store_url="https://apps.example.org/app",
                )
    revisions = {asset: 4 for asset in plan["asset_ids"]}
    compatibility = build_compatibility_evidence(
        ad_slots(plan),
        plan["asset_ids"],
        capability_version=args["capability_version"],
        source_hash="e" * 64,
        verified=True,
        complete=True,
        evaluate=lambda _slot, _asset: True,
        material_revisions=revisions,
    )
    solution = solve_allocation(
        ad_slots(plan),
        plan["asset_ids"],
        compatibility,
        allow_repeat=True,
        seed=0,
        material_revisions=revisions,
    )
    args["allocation"]["input_hash"] = solution.input_hash
    graph = build_launch_dag(
        plan,
        plan_revision=7,
        allocation=solution,
        compatibility=compatibility,
        material_revisions=revisions,
    )
    args["total_dag_node_count"] = graph.total_dag_node_count
    validation = freeze_validation(plan, **args)
    payload = canonical(plan).encode()
    source = PlanSource(
        uid(900), args["plan_id"], 7, 8, hashlib.sha256(payload).hexdigest(), payload
    )
    metadata = {
        asset: {
            "id": asset,
            "revision": 4,
            "sha256": "f" * 64,
            "mime": "image/png",
            "size": 1234,
            "width": 1080,
            "height": 1080,
            "duration": None,
            "state": "READY",
            "physical_cleanup_state": "LIVE",
            "antivirus_status": "CLEAN",
            "execution_eligible": True,
            **plan["ownership"],
        }
        for asset in plan["asset_ids"]
    }
    references = tuple(
        [
            ObservationReference("ALLOCATION", args["allocation"]["id"], 7),
            ObservationReference("NAME_RESERVATION", args["name_reservation"]["id"], 7),
            ObservationReference("SCOPE", source.tenant_id, 9),
            ObservationReference("CAPABILITY", uid(500), 3),
            ObservationReference("POLICY", uid(501), 4),
            ObservationReference("CONFIGURATION", uid(700), 1),
        ]
        + [ObservationReference("ACCOUNT", identifier, 1) for identifier in plan["account_ids"]]
        + [ObservationReference("MATERIAL", identifier, 4) for identifier in plan["asset_ids"]]
    )
    inputs = {
        key: args[key]
        for key in (
            "allocation",
            "name_reservation",
            "capability_version",
            "policy_version",
            "scope_version",
            "channel_snapshot",
            "product_snapshot",
            "currency",
        )
    }
    inputs.update(
        validated_head_revision=8,
        compatibility=compatibility,
        material_revisions=revisions,
        material_metadata=metadata,
        resolved_metric_profiles={uid(700): resolved_profile()},
        observation_refs=references,
        request={"hash": validation.hash, "activate_ack": activate},
        now=validation.validated_at,
    )
    return source, validation, inputs


def resolved_profile():
    profile = {
        "id": uid(700),
        "version": "fixture-profile-v1",
        "source": "FIXTURE",
        "register_action_type": None,
        "purchase_action_type": "fixture_purchase",
        "value_action_type": "fixture_value",
        "attribution_windows": ["explicit-fixture-window"],
        "action_report_time": "conversion",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 7,
        "verified": True,
    }
    return {
        "profile": profile,
        "profile_source_hash": hashlib.sha256(canonical(profile).encode()).hexdigest(),
        "adapter_version": "fixture-explicit-attribution-v1",
        "bound_profile_version": profile["version"],
        "registry_revision": 1,
        "attribution_spec": [{"event_type": "CLICK_THROUGH", "window_days": 7}],
    }


def prepared(*, activate=False):
    source, validation, inputs = fixture(activate=activate)
    return prepare_execution(source, validation, **inputs)


def test_complete_chunks_actual_names_identity_assets_and_independent_full_hash():
    result = prepared()
    chunks = list(iter_prepared_chunks(result, chunk_bytes=1024))
    raw = b"".join(chunks)
    document = json.loads(raw)
    assert all(0 < len(chunk) <= 1024 for chunk in chunks)
    assert (
        hashlib.sha256(raw).hexdigest() == result.manifest_hash
        and len(raw) == result.manifest_bytes
    )
    assert hashlib.sha256(canonical(document).encode()).hexdigest() == result.manifest_hash
    assert (
        len(document["nodes"]) == result.dag.total_dag_node_count == document["dag"]["node_count"]
    )
    assert document["plan_revision"] == 7 and "head_revision" not in document
    assert document["source_payload_hash"] == result.source.payload_hash
    campaign = next(row for row in document["nodes"] if row["kind"] == "CAMPAIGN")
    group = next(row for row in document["nodes"] if row["kind"] == "ADSET")
    ad = next(row for row in document["nodes"] if row["kind"] == "AD")
    assert campaign["resolved_configuration"]["name"] == "渠道_真实投手_20261108_0001"
    assert group["resolved_configuration"]["name"] == "真实冻结广告组"
    assert ad["resolved_configuration"]["name"] == "真实冻结广告"
    assert ad["resolved_configuration"]["identity"]["page_id"] == "3000"
    assert ad["resolved_configuration"]["asset"]["sha256"] == "f" * 64
    assert ad["resolved_configuration"]["asset"]["revision"] == 4
    assert group["resolved_configuration"]["start_time"] == "2026-11-08T10:00:00.000Z"
    assert group["resolved_configuration"]["attribution_spec"] == [
        {"event_type": "CLICK_THROUGH", "window_days": 7}
    ]
    assert group["resolved_configuration"]["metric_profile_version"] == "fixture-profile-v1"
    assert campaign["resolved_configuration"]["budget"]["amount"] == "12.34"
    assert all(
        row["resolved_configuration"]["status"] == "PAUSED"
        for row in document["nodes"]
        if row["kind"] in {"CAMPAIGN", "ADSET", "AD"}
    )
    assert not any(row["kind"] == "ENABLE" for row in document["nodes"])
    assert (
        result.execution_authorized is False
        and not hasattr(result, "task_id")
        and not hasattr(result, "runtime_id")
    )


def test_activate_ack_is_required_but_publish_permission_is_not_granted():
    source, validation, inputs = fixture(activate=True)
    inputs["request"]["activate_ack"] = False
    with pytest.raises(OrbitError) as info:
        prepare_execution(source, validation, **inputs)
    assert info.value.pointer == "/activate_ack"
    inputs["request"]["activate_ack"] = True
    result = prepare_execution(source, validation, **inputs)
    nodes = list(iter_execution_nodes(result))
    assert any(
        row["kind"] == "ENABLE" and row["resolved_configuration"]["status"] == "ACTIVE"
        for row in nodes
    )
    assert any(
        row["kind"] == "VERIFY"
        and row["purpose"] == "ENABLE"
        and row["resolved_configuration"]["expected_configuration"]["status"] == "ACTIVE"
        for row in nodes
    )
    assert result.execution_authorized is False


def test_original_execute_ack_is_part_of_request_intent_even_when_no_activation():
    source, validation, inputs = fixture()
    first = prepare_execution(source, validation, **inputs)
    inputs["request"]["activate_ack"] = True
    second = prepare_execution(source, validation, **inputs)
    assert first.request_payload_hash != second.request_payload_hash
    assert first.manifest_hash == second.manifest_hash


def test_all_inputs_frozen_and_repeated_chunks_do_not_read_caller_mutations():
    source, validation, inputs = fixture()
    result = prepare_execution(source, validation, **inputs)
    before = b"".join(iter_prepared_chunks(result))
    inputs["allocation"]["items"].clear()
    inputs["name_reservation"]["items"][0]["name"] = "篡改"
    inputs["material_metadata"].clear()
    inputs["channel_snapshot"].clear()
    assert b"".join(iter_prepared_chunks(result)) == before
    with pytest.raises(FrozenInstanceError):
        result.manifest_hash = "x"


@pytest.mark.parametrize(
    "damage",
    [
        "head",
        "source_hash",
        "request_hash",
        "expired",
        "names",
        "allocation",
        "metadata_revision",
        "metadata_missing",
        "metadata_unknown_size",
        "metadata_owner",
        "references",
        "missing_policy",
        "unknown_request",
    ],
)
def test_missing_or_changed_sources_and_strict_execute_fields_fail_closed(damage):
    source, validation, inputs = fixture()
    if damage == "head":
        inputs["validated_head_revision"] = 9
    elif damage == "source_hash":
        source = replace(source, payload_hash="a" * 64)
    elif damage == "request_hash":
        inputs["request"]["hash"] = "a" * 64
    elif damage == "expired":
        inputs["now"] = validation.expires_at
    elif damage == "names":
        inputs["name_reservation"]["items"][0]["name"] += "变更"
    elif damage == "allocation":
        inputs["allocation"]["items"][0]["asset_revision"] = 9
    elif damage == "metadata_revision":
        next(iter(inputs["material_metadata"].values()))["revision"] = 9
    elif damage == "metadata_missing":
        inputs["material_metadata"] = {}
    elif damage == "metadata_unknown_size":
        next(iter(inputs["material_metadata"].values()))["size"] = None
    elif damage == "metadata_owner":
        next(iter(inputs["material_metadata"].values()))["owner_team_id"] = uid(999)
    elif damage == "references":
        inputs["observation_refs"] = ()
    elif damage == "missing_policy":
        inputs["observation_refs"] = tuple(
            row for row in inputs["observation_refs"] if row.kind != "POLICY"
        )
    else:
        inputs["request"]["verified"] = True
    with pytest.raises(OrbitError):
        prepare_execution(source, validation, **inputs)


def test_state_only_revalidation_keeps_stable_manifest_but_request_cas_is_bound():
    source, validation, inputs = fixture()
    first = prepare_execution(source, validation, **inputs)
    validation = replace(
        validation,
        validated_at=validation.validated_at + timedelta(seconds=10),
        expires_at=validation.expires_at + timedelta(seconds=10),
    )
    source = replace(source, head_revision=9)
    inputs["validated_head_revision"] = 9
    inputs["now"] += timedelta(seconds=10)
    second = prepare_execution(source, validation, **inputs)
    assert first.manifest_hash == second.manifest_hash
    assert first.request_payload_hash != second.request_payload_hash


def test_resolved_file_descriptor_never_serializes_ephemeral_url_or_boolean_authority():
    source, validation, inputs = fixture()
    for row in inputs["material_metadata"].values():
        row.update(
            download_url="https://fixture.invalid/temporary-only",
            verified=True,
            execution_eligible=True,
        )
    result = prepare_execution(source, validation, **inputs)
    raw = b"".join(iter_prepared_chunks(result))
    assert b"temporary-only" not in raw and b"execution_eligible" not in raw
    assert all("verified" not in row for row in json.loads(raw)["materials"].values())
    assert result.execution_authorized is False


def test_missing_required_resolved_group_or_ad_name_is_not_a_placeholder():
    source, validation, inputs = fixture()
    plan = source.payload()
    del plan["campaigns"][0]["adsets"][0]["name"]
    payload = canonical(plan).encode()
    source = replace(
        source, canonical_payload=payload, payload_hash=hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(OrbitError) as info:
        prepare_execution(source, validation, **inputs)
    assert info.value.pointer.endswith("/name")


@pytest.mark.parametrize("size", [0, True, 1024 * 1024 + 1])
def test_chunk_boundary_requires_safe_bounded_integer(size):
    with pytest.raises(ValueError):
        list(iter_prepared_chunks(prepared(), chunk_bytes=size))


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "unknown_field",
        "original_revision",
        "source_hash",
        "bound_version",
        "missing_spec",
        "spec_bool",
        "spec_extra",
        "unverified",
    ],
)
def test_metric_adapter_is_strict_and_never_guesses_target_parameters(damage):
    source, validation, inputs = fixture()
    row = inputs["resolved_metric_profiles"][uid(700)]
    if damage == "missing":
        inputs["resolved_metric_profiles"] = {}
    elif damage == "unknown_field":
        row["token"] = "forbidden"
    elif damage == "original_revision":
        row["profile"]["revision"] = 1
    elif damage == "source_hash":
        row["profile_source_hash"] = "a" * 64
    elif damage == "bound_version":
        row["bound_profile_version"] = "wrong-version"
    elif damage == "missing_spec":
        del row["attribution_spec"]
    elif damage == "spec_bool":
        row["attribution_spec"][0]["window_days"] = True
    elif damage == "spec_extra":
        row["attribution_spec"][0]["arbitrary"] = "no"
    else:
        row["profile"]["verified"] = False
    with pytest.raises(OrbitError) as info:
        prepare_execution(source, validation, **inputs)
    assert info.value.status == 503 and info.value.code == "EXECUTION_METRIC_ADAPTER_UNAVAILABLE"


def test_app_destination_freezes_explicit_application_not_pixel_or_website():
    source, validation, inputs = fixture(destination="APP")
    result = prepare_execution(source, validation, **inputs)
    node = next(row for row in iter_execution_nodes(result) if row["kind"] == "ADSET")
    assert node["resolved_configuration"]["identity"]["application_id"] == "456789"
    assert node["resolved_configuration"]["identity"]["pixel_id"] is None
    assert result.execution_authorized is False


def test_unknown_destination_dependency_fails_503():
    source, validation, inputs = fixture()
    inputs["channel_snapshot"].pop("type")
    with pytest.raises(OrbitError) as info:
        prepare_execution(source, validation, **inputs)
    assert info.value.status == 503 and info.value.code == "EXECUTION_DESTINATION_UNAVAILABLE"


def test_ten_thousand_ads_prepare_complete_streamed_commands_without_expanded_config_storage():
    source, validation, inputs = fixture(accounts=200, ad_copies=50)
    result = prepare_execution(source, validation, **inputs)
    assert result.dag.ad_count == 10000 and result.dag.total_dag_node_count <= 100000
    assert sum(row["kind"] == "AD" for row in iter_execution_nodes(result)) == 10000
    assert result.manifest_bytes > 1024 * 1024
    assert not hasattr(result, "resolved_nodes")
    assert isinstance(result.inputs_json, bytes) and isinstance(result.dag.nodes, tuple)


def test_complete_mapping_array_order_does_not_change_prepared_manifest():
    source, validation, inputs = fixture()
    original = prepare_execution(source, validation, **inputs)
    inputs["allocation"]["items"].reverse()
    inputs["name_reservation"]["items"].reverse()
    reordered = prepare_execution(source, validation, **inputs)
    assert reordered.manifest_hash == original.manifest_hash
    assert b"".join(iter_prepared_chunks(reordered)) == b"".join(iter_prepared_chunks(original))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state", "DELETED"),
        ("physical_cleanup_state", "UNKNOWN"),
        ("antivirus_status", None),
        ("execution_eligible", False),
    ],
)
def test_known_or_unknown_material_unavailability_cannot_be_frozen_as_executable(field, value):
    source, validation, inputs = fixture()
    next(iter(inputs["material_metadata"].values()))[field] = value
    with pytest.raises(OrbitError) as info:
        prepare_execution(source, validation, **inputs)
    assert info.value.status == 503
    assert info.value.code == "EXECUTION_MATERIAL_SOURCE_UNAVAILABLE"


def test_material_actual_owner_is_preserved_without_inventing_same_user_permission():
    source, validation, inputs = fixture()
    for row in inputs["material_metadata"].values():
        row["owner_user_id"] = uid(900)
    result = prepare_execution(source, validation, **inputs)
    assert {row["owner_user_id"] for row in json.loads(result.materials_json).values()} == {
        uid(900)
    }
    # 同团队并不授予权限；当前caller/目标投手交集由外部Provider核。
    assert result.execution_authorized is False


def test_mutable_source_bytes_are_rejected_before_freezing():
    source, validation, inputs = fixture()
    mutable = replace(source, canonical_payload=bytearray(source.canonical_payload))
    with pytest.raises(OrbitError):
        prepare_execution(mutable, validation, **inputs)
