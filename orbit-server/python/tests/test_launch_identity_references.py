"""身份草稿引用边界；替身不代表真实发布或广告执行验收。"""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from test_launch_contract_expansion import parse, tree, uid

from orbit_api.errors import OrbitError


def binding():
    return {"account_id": uid(4), "page_id": "101", "groups": [], "ad_overrides": []}


def test_scope_identity_membership_is_deferred_until_scope_consumption():
    value = tree()
    value.update(account_ids=[], account_scope_snapshot_id=uid(99), identity_bindings=[binding()])
    assert parse(value)["identity_bindings"] == [binding()]


def test_explicit_identity_still_requires_selected_account():
    value = tree()
    value.update(account_ids=[uid(5)], identity_bindings=[binding()])
    with pytest.raises(OrbitError):
        parse(value)


@pytest.mark.parametrize("kind", ["PAGE", "PIXEL", "APPLICATION"])
async def test_resource_must_be_usable_in_current_account_inventory(kind):
    from orbit_api.launch_identity_references import validate_identity_resources

    value = tree()
    row = binding()
    row["groups"] = [
        {
            "adset_local_id": uid(11),
            "pixel_id": None,
            "conversion_event": None,
            "application_id": None,
            "object_store_url": None,
        }
    ]
    if kind != "PAGE":
        row["groups"][0]["pixel_id" if kind == "PIXEL" else "application_id"] = "202"
    inventory = {
        "account_id": uid(4),
        "resources": [
            {"kind": "PAGE", "external_id": "101", "usable": True},
            {"kind": kind, "external_id": "202", "usable": False},
        ],
    }
    if kind == "PAGE":
        row["page_id"] = "202"
    with pytest.raises(OrbitError) as caught:
        validate_identity_resources(value, row, 0, inventory)
    assert caught.value.status == 422
    assert caught.value.pointer.startswith("/identity_bindings/0/")


async def test_valid_resources_preserve_unverified_event_text_and_do_not_mutate():
    from orbit_api.launch_identity_references import validate_identity_resources

    value = tree()
    row = binding()
    row["groups"] = [
        {
            "adset_local_id": uid(11),
            "pixel_id": "202",
            "conversion_event": "PURCHASE",
            "application_id": None,
            "object_store_url": None,
        }
    ]
    inventory = {
        "account_id": uid(4),
        "resources": [
            {"kind": "PAGE", "external_id": "101", "usable": True},
            {"kind": "PIXEL", "external_id": "202", "usable": True},
        ],
    }
    before = deepcopy(row)
    validate_identity_resources(value, row, 0, inventory)
    assert row == before


async def test_scope_resolved_nonmember_is_rejected_before_identity_read():
    from orbit_api import launch_identity_references as refs

    value = tree()
    value.update(account_ids=[uid(5)], identity_bindings=[binding()])
    with pytest.raises(OrbitError) as caught:
        await refs.resolve_identity_dependencies(AsyncMock(), None, value, {})
    assert caught.value.status == 422


@pytest.mark.parametrize(
    "objective,fields",
    [
        (None, {"pixel_id": "202", "application_id": "303"}),
        ("OUTCOME_SALES", {"application_id": "303"}),
        ("OUTCOME_APP_PROMOTION", {"pixel_id": "202"}),
    ],
)
def test_identity_destination_mismatch_rejected(objective, fields):
    from orbit_api.launch_identity_references import validate_identity_resources

    value = tree()
    value["campaigns"][0]["objective"] = objective
    row = binding()
    row["groups"] = [
        {
            "adset_local_id": uid(11),
            "pixel_id": None,
            "conversion_event": None,
            "application_id": None,
            "object_store_url": None,
        }
        | fields
    ]
    inventory = {
        "account_id": uid(4),
        "resources": [
            {"kind": "PAGE", "external_id": "101", "usable": True},
            {"kind": "PIXEL", "external_id": "202", "usable": True},
            {"kind": "APPLICATION", "external_id": "303", "usable": True},
        ],
    }
    with pytest.raises(OrbitError) as caught:
        validate_identity_resources(value, row, 0, inventory)
    assert caught.value.pointer == "/identity_bindings/0/groups/0"


async def test_resolution_freezes_inventory_and_provenance_without_execution_authority(monkeypatch):
    from types import SimpleNamespace

    from orbit_api import launch_identity_references as refs

    current = SimpleNamespace(actor_id=8)
    value = tree()
    value["identity_bindings"] = [binding()]
    inventory = {
        "account_id": uid(4),
        "capability_version": "source-v1",
        "observed_at": "2026-11-01T00:00:00Z",
        "resources": [{"kind": "PAGE", "external_id": "101", "usable": True}],
    }
    reader = AsyncMock(return_value=inventory)
    monkeypatch.setattr(refs.IdentityPublicationReadmodel, "get", reader)
    prepared = {
        uid(4): {
            "probe": {"evidence_id": uid(81), "release_id": uid(82)},
            "configurations": [],
            "release": {},
        }
    }
    result = await refs.resolve_identity_dependencies(object(), current, value, prepared)
    assert result["identities"][uid(4)]["evidence_id"] == uid(81)
    assert result["identities"][uid(4)]["inventory_hash"]
    assert result["identities"][uid(4)]["capability_version"] == "source-v1"
    assert "execution_authority" not in result
    assert reader.await_args.kwargs["prepared_sources"] == prepared[uid(4)]


@pytest.fixture
def publication_graph(monkeypatch):
    from test_identity_publication_readmodel import graph

    return graph.__wrapped__(monkeypatch)


@pytest.mark.parametrize("changed", [False, True])
async def test_prelocked_readmodel_never_locks_additional_sources(
    publication_graph, monkeypatch, changed
):
    from orbit_api import identity_publication_readmodel as module

    data, session, account = publication_graph
    prepared = {
        "probe": deepcopy(data["probe"]),
        "configurations": [data["config"]],
        "release": data["release"],
    }
    source_lock = AsyncMock(side_effect=AssertionError("clock后不得追加来源锁"))
    monkeypatch.setattr(module, "lock_sources", source_lock)
    if changed:
        data["head"]["evidence_id"] = uid(500)
        with pytest.raises(OrbitError) as caught:
            await module.IdentityPublicationReadmodel().get(
                session, 1, account, prepared_sources=prepared
            )
        assert caught.value.code == "IDENTITY_PUBLICATION_SOURCE_RETRY"
        assert "history" not in data["events"]
    else:
        result = await module.IdentityPublicationReadmodel().get(
            session, 1, account, prepared_sources=prepared
        )
        assert result["account_id"] == account
        assert "validate-original" in data["events"]
    source_lock.assert_not_awaited()


async def test_prepare_discovers_all_before_locking_sources_in_order(monkeypatch):
    from types import SimpleNamespace

    from orbit_api import launch_identity_references as refs

    calls = []

    async def probe(session, query, parameters):
        calls.append(("probe", parameters["account"]))
        return {"evidence_id": uid(81), "release_id": uid(100 - int(parameters["account"][-1]))}

    async def sources(session, current, release):
        calls.append(("lock", release))
        return ([{"id": uid(88)}], {"id": release})

    monkeypatch.setattr(refs, "one", probe)
    monkeypatch.setattr(refs, "lock_sources", sources)
    result = await refs.prepare_identity_sources(
        object(), SimpleNamespace(tenant_id=uid(1)), [binding() | {"account_id": uid(5)}, binding()]
    )
    assert calls == [("probe", uid(4)), ("probe", uid(5)), ("lock", uid(95)), ("lock", uid(96))]
    assert set(result) == {uid(4), uid(5)}


async def test_adspower_binding_still_fails_closed_before_identity_inventory(monkeypatch):
    from types import SimpleNamespace

    from orbit_api import launch_references as refs

    monkeypatch.setattr(refs, "owner", AsyncMock(return_value=8))
    prepare = AsyncMock(side_effect=AssertionError("环境未接通时不得伪装身份能力"))
    monkeypatch.setattr(refs, "prepare_identity_sources", prepare)
    value = tree()
    value.update(identity_bindings=[binding()], profile_binding_ids=[uid(98)])
    with pytest.raises(OrbitError) as caught:
        await refs.validate_sources(object(), SimpleNamespace(), value, permission="launch.create")
    assert caught.value.status == 503
    assert caught.value.pointer == "/profile_binding_ids"
    prepare.assert_not_awaited()


@pytest.mark.parametrize("mutation", ["release-revoked", "raw-unavailable", "source-mismatch"])
async def test_prelocked_read_still_verifies_full_original_authority(publication_graph, mutation):
    from datetime import UTC, datetime

    from orbit_api import identity_publication_readmodel as module

    data, session, account = publication_graph
    prepared = {
        "probe": deepcopy(data["probe"]),
        "configurations": [data["config"]],
        "release": data["release"],
    }
    if mutation == "release-revoked":
        data["release"]["revoked_at"] = datetime.now(UTC)
    elif mutation == "raw-unavailable":
        data["raw"] = None
    else:
        data["evidence"]["source_config_id"] = uid(700)
    with pytest.raises(OrbitError) as caught:
        await module.IdentityPublicationReadmodel().get(
            session, 1, account, prepared_sources=prepared
        )
    assert caught.value.status == 503
    assert "validate-original" not in data["events"]


@pytest.mark.parametrize("changed", [False, True])
async def test_same_draft_body_refreezes_changed_identity_proof(monkeypatch, changed):
    from types import SimpleNamespace

    from test_launch_scope_consumption import current

    from orbit_api import launch_store as plans

    value = tree()
    value["identity_bindings"] = [binding()]
    previous = {"state": "DRAFT", "revision": 1, "payload_json": value}
    old = {"identities": {uid(4): {"evidence_id": uid(80)}}}
    new = deepcopy(old)
    if changed:
        new["identities"][uid(4)]["evidence_id"] = uid(81)
    for name, result in [
        ("successful_replay", None),
        ("context", current()),
        ("clock", 1),
        ("replay", None),
        ("remember", None),
    ]:
        monkeypatch.setattr(plans.access, name, AsyncMock(return_value=result))
    monkeypatch.setattr(plans, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(plans, "validate_sources", AsyncMock(return_value=new))
    monkeypatch.setattr(plans, "public_plan", lambda row: {"revision": 1})
    monkeypatch.setattr(
        "orbit_api.launch_plan_source.capture_plan_source",
        AsyncMock(return_value=SimpleNamespace(source_revision=1)),
    )
    store = plans.LaunchStore(None)
    store.row = AsyncMock(return_value=previous)
    store.persist = AsyncMock(return_value={"revision": 2})
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: old))
    )
    result = await store.save(session, 1, "session", "csrf", "new-key", value, uid(90), 1, uid(91))
    assert result["revision"] == (2 if changed else 1)
    assert store.persist.await_count == int(changed)
