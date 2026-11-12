"""Meta配置往返、组合约束和未接入能力护栏；不执行平台写入。"""

import json

import pytest
from test_launch_contract_expansion import ad, group, parse, tree, uid

from orbit_api.errors import OrbitError
from orbit_api.launch_meta_settings import require_meta_capabilities
from orbit_api.template_contract import parse_template, template_draft


def test_nested_settings_roundtrip_template_and_clone():
    value = tree()
    value["campaigns"][0]["meta_settings"] = {"advantage_campaign_budget": False}
    group(value)["meta_settings"] = {
        "audience_mode": "ADVANTAGE",
        "devices": {"operating_systems": ["IOS"], "ios_min_version": "15.2"},
    }
    ad(value)["meta_settings"] = {"format": "CAROUSEL", "carousel_asset_ids": [uid(80), uid(81)]}
    saved = parse(value)
    template = parse_template(
        json.dumps(
            {
                "name": "Meta",
                "description": "",
                "visibility": "PRIVATE",
                "recipient_user_ids": [],
                "campaigns": saved["campaigns"],
            }
        ).encode()
    )
    cloned = template_draft(template, saved["ownership"])
    assert group(cloned)["meta_settings"] == group(saved)["meta_settings"]
    assert ad(cloned)["meta_settings"] == ad(saved)["meta_settings"]
    assert ad(cloned)["local_id"] != ad(saved)["local_id"]
    assert "meta_settings" not in parse(tree())["campaigns"][0]


@pytest.mark.parametrize(
    "settings",
    [
        {
            "devices": {
                "operating_systems": ["IOS"],
                "ios_min_version": "18",
                "ios_max_version": "17",
            }
        },
        {"devices": {"android_models": ["Pixel"]}},
        {"excluded_country_codes": ["INVALID"]},
        {"excluded_custom_audience_ids": ["bad"]},
        {"genders": ["MALE", "MALE"]},
    ],
)
def test_invalid_nested_values(settings):
    value = tree()
    group(value)["meta_settings"] = settings
    with pytest.raises(OrbitError):
        parse(value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: group(v).update(placements="MANUAL"),
        lambda v: ad(v).update(
            meta_settings={"start_time": "2026-01-02T00:00:00Z", "end_time": "2026-01-01T00:00:00Z"}
        ),
        lambda v: ad(v).update(meta_settings={"format": "SINGLE", "carousel_asset_ids": [uid(80)]}),
        lambda v: v["campaigns"][0].update(
            bid_strategy="COST_CAP", meta_settings={"roas_goal": "2"}
        ),
    ],
)
def test_invalid_combinations(mutate):
    value = tree()
    mutate(value)
    with pytest.raises(OrbitError):
        parse(value)


def test_preflight_field_specific_and_legacy_unaffected():
    require_meta_capabilities(parse(tree()))
    value = tree()
    group(value)["meta_settings"] = {"audience_mode": "ADVANTAGE"}
    with pytest.raises(OrbitError) as error:
        require_meta_capabilities(parse(value))
    assert error.value.code == "META_CONFIGURATION_UNAVAILABLE"
    assert error.value.pointer == "/campaigns/0/adsets/0/meta_settings/audience_mode"


@pytest.mark.parametrize("value", [True, False, 1.0, "1"])
def test_attribution_requires_exact_integers(value):
    draft = tree()
    group(draft)["meta_settings"] = {"attribution_click_days": value}
    with pytest.raises(OrbitError):
        parse(draft)


@pytest.mark.parametrize(
    "settings",
    [
        {"unknown": True},
        {"devices": {"unknown": "x"}},
        {"manual_placements": {"facebook": ["UNKNOWN"]}},
        {"attribution_click_days": 2},
    ],
)
def test_new_schema_rejects_unknown_values(settings):
    draft = tree()
    group(draft)["meta_settings"] = settings
    with pytest.raises(OrbitError):
        parse(draft)


@pytest.mark.parametrize(
    "objective,event,goal",
    [
        ("OUTCOME_LEADS", "PURCHASE", "OFFSITE_CONVERSIONS"),
        ("OUTCOME_SALES", "LEAD", "OFFSITE_CONVERSIONS"),
        ("OUTCOME_SALES", "ADD_TO_CART", "VALUE"),
        ("OUTCOME_APP_PROMOTION", "PURCHASE", "APP_INSTALLS"),
    ],
)
def test_objective_event_goal_cross_validation(objective, event, goal):
    draft = tree()
    draft["campaigns"][0]["objective"] = objective
    group(draft).update(optimization_goal=goal, meta_settings={"conversion_event": event})
    with pytest.raises(OrbitError):
        parse(draft)


def test_single_campaign_goal_consistency_and_cbo_events():
    import copy

    draft = tree()
    c = draft["campaigns"][0]
    g = group(draft)
    g.update(
        optimization_goal="OFFSITE_CONVERSIONS", meta_settings={"conversion_event": "ADD_TO_CART"}
    )
    second = copy.deepcopy(g)
    second.update(local_id=uid(90), ads=[], optimization_goal="VALUE")
    second["meta_settings"]["conversion_event"] = "PURCHASE"
    c["adsets"].append(second)
    with pytest.raises(OrbitError):
        parse(draft)
    second["optimization_goal"] = "OFFSITE_CONVERSIONS"
    c["meta_settings"] = {"advantage_campaign_budget": True}
    with pytest.raises(OrbitError):
        parse(draft)
    c["meta_settings"]["advantage_campaign_budget"] = False
    parse(draft)


def test_identity_conversion_event_must_match_group():
    draft = tree()
    group(draft)["meta_settings"] = {"conversion_event": "ADD_TO_CART"}
    draft["identity_bindings"] = [
        {
            "account_id": draft["account_ids"][0],
            "page_id": "123",
            "groups": [
                {
                    "adset_local_id": group(draft)["local_id"],
                    "pixel_id": "123",
                    "conversion_event": "PURCHASE",
                    "application_id": None,
                    "object_store_url": None,
                }
            ],
            "ad_overrides": [],
        }
    ]
    with pytest.raises(OrbitError) as error:
        parse(draft)
    assert error.value.pointer == "/identity_bindings/0/groups/0/conversion_event"


def test_real_freeze_entrypoint_rejects_unmapped_control():
    from test_launch_validation_contract import fixture

    from orbit_api.launch_validation_contract import freeze_validation

    draft, args = fixture()
    group(draft)["meta_settings"] = {"audience_mode": "ADVANTAGE"}
    with pytest.raises(OrbitError) as error:
        freeze_validation(draft, **args)
    assert error.value.code == "META_CONFIGURATION_UNAVAILABLE"


@pytest.mark.asyncio
async def test_public_preflight_reports_field_before_missing_provider_without_writes(monkeypatch):
    from dataclasses import replace

    from test_launch_validation_store import Environment

    from orbit_api.directory_tokens import canonical

    env = Environment(monkeypatch)
    group(env.plan)["meta_settings"] = {"inventory_filter": "LIMITED"}
    env.source = replace(env.source, canonical_payload=canonical(env.plan).encode())
    env.store.provider = None
    with pytest.raises(OrbitError) as error:
        await env.prepare()
    assert error.value.code == "META_CONFIGURATION_UNAVAILABLE"
    assert error.value.pointer == "/campaigns/0/adsets/0/meta_settings/inventory_filter"
    assert not env.persisted and not env.events and env.input is None


def test_execute_entrypoint_cannot_bypass_new_configuration_guard():
    import hashlib
    from dataclasses import replace

    from test_launch_execution_contract import fixture

    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_execution_contract import prepare_execution

    source, validation, inputs = fixture()
    draft = source.payload()
    ad(draft)["meta_settings"] = {"format": "CAROUSEL"}
    payload = canonical(draft).encode()
    changed = replace(
        source, canonical_payload=payload, payload_hash=hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(OrbitError) as error:
        prepare_execution(changed, validation, **inputs)
    assert error.value.code == "META_CONFIGURATION_UNAVAILABLE"
    assert error.value.pointer == "/campaigns/0/adsets/0/ads/0/meta_settings/format"


@pytest.mark.parametrize(
    "level,settings,expected",
    [
        ("campaign", {"spending_limit": "10"}, "spending_limit"),
        ("campaign", {"advantage_campaign_budget": False}, "advantage_campaign_budget"),
        ("group", {"attribution_click_days": 7}, "attribution_click_days"),
        (
            "group",
            {"audience_network_inventory_filter": "STANDARD"},
            "audience_network_inventory_filter",
        ),
        ("group", {"devices": {"operating_systems": ["IOS"]}}, "devices/operating_systems"),
        ("ad", {"start_time": "2026-11-20T00:00:00Z"}, "start_time"),
    ],
)
def test_explicit_controls_never_silently_execute_even_defaults(level, settings, expected):
    draft = tree()
    target = {"campaign": draft["campaigns"][0], "group": group(draft), "ad": ad(draft)}[level]
    target["meta_settings"] = settings
    with pytest.raises(OrbitError) as error:
        require_meta_capabilities(parse(draft))
    assert error.value.code == "META_CONFIGURATION_UNAVAILABLE"
    assert error.value.pointer.endswith("/meta_settings/" + expected)


@pytest.mark.parametrize("objective", ["OUTCOME_SALES", "OUTCOME_LEADS"])
def test_website_goal_rejects_app_installs_only_for_new_meta_configuration(objective):
    draft = tree()
    draft["campaigns"][0]["objective"] = objective
    group(draft)["optimization_goal"] = "APP_INSTALLS"
    # 历史稀疏草稿保持原合同；新网站配置不能混入应用成效目标。
    assert group(parse(draft))["optimization_goal"] == "APP_INSTALLS"
    group(draft)["meta_settings"] = {"conversion_location": "WEBSITE"}
    with pytest.raises(OrbitError) as error:
        parse(draft)
    assert error.value.pointer == "/campaigns/0/adsets/0/optimization_goal"
    group(draft)["optimization_goal"] = "OFFSITE_CONVERSIONS"
    assert group(parse(draft))["optimization_goal"] == "OFFSITE_CONVERSIONS"
