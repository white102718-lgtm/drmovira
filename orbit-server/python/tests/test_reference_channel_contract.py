"""引用目录与渠道的纯合同验证；不将这些单测冒充MySQL或浏览器验收。"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.channel_contract import https_url, parse_channel
from orbit_api.errors import OrbitError
from orbit_api.reference_access import assert_write_ownership, readable, scope_clause
from orbit_api.reference_contract import normalize_row, ownership, parse_import

TEAM = "10000000-0000-4000-8000-000000000001"
USER = "10000000-0000-4000-8000-000000000002"
PRODUCT = "10000000-0000-4000-8000-000000000003"
AGENT = "10000000-0000-4000-8000-000000000004"


def row(kind="PRODUCT"):
    return {
        "id": PRODUCT,
        "name": " 产品é ",
        "kind": kind,
        "availability": "AVAILABLE",
        "owner_team_id": TEAM,
        "data_owner_user_ids": [USER],
        "source_key": "origin-1",
        **({"allowed_agent_ids": [AGENT]} if kind == "PRODUCT" else {}),
    }


def channel():
    return {
        "code": "CH_001",
        "name": " 渠道一 ",
        "ownership": {"owner_team_id": TEAM, "data_owner_user_ids": [USER]},
        "type": "WEBSITE",
        "media": "META",
        "url": "https://example.com/path?a=1&b=%E4%B8%AD",
        "status": "ENABLED",
    }


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode()


def test_reference_normalizes_nfc_but_never_rebuilds_id():
    value = row()
    value["name"] = "  Cafe\u0301  "
    result = normalize_row(value, "PRODUCT")
    assert result["name"] == "Café"
    assert result["id"] == PRODUCT


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "bad"),
        ("name", 42),
        ("source_key", ""),
        ("name", "a\n"),
        ("availability", "ENABLED"),
        ("data_owner_user_ids", []),
        ("data_owner_user_ids", [USER, USER]),
        ("allowed_agent_ids", []),
        ("owner_team_id", "other-tenant"),
    ],
)
def test_reference_row_field_errors(field, value):
    item = row()
    item[field] = value
    with pytest.raises(OrbitError) as failure:
        normalize_row(item, "PRODUCT")
    assert failure.value.status == 422


def test_product_requires_agents_and_nonproduct_rejects_agents():
    value = row()
    del value["allowed_agent_ids"]
    with pytest.raises(OrbitError):
        normalize_row(value, "PRODUCT")
    value = row("VENDOR")
    value["allowed_agent_ids"] = [AGENT]
    with pytest.raises(OrbitError):
        normalize_row(value, "VENDOR")


@pytest.mark.parametrize("count", [0, 501])
def test_import_count_boundaries(count):
    with pytest.raises(OrbitError) as failure:
        parse_import(
            raw(
                {
                    "kind": "VENDOR",
                    "source": "source",
                    "reason": "reason",
                    "base_catalog_revision": 0,
                    "items": [row("VENDOR")] * count,
                }
            )
        )
    assert failure.value.status == 422


def test_import_unknown_fields_and_bool_revision_rejected():
    value = {
        "kind": "VENDOR",
        "source": "source",
        "reason": "reason",
        "base_catalog_revision": 0,
        "items": [row("VENDOR")],
    }
    assert parse_import(raw(value)).base_catalog_revision == 0
    with pytest.raises(OrbitError):
        parse_import(raw({**value, "tenant_id": TEAM}))
    with pytest.raises(OrbitError):
        parse_import(raw({**value, "base_catalog_revision": True}))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com:65536",
        "https://localhost",
        "https://127.0.0.1",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]",
        "https://example.com:0/path",
        "https://example.com/%0A",
        "https://example.com/%xx",
        "https://example.com/\\evil",
        "javascript:alert(1)",
    ],
)
def test_channel_rejects_unsafe_link(url):
    with pytest.raises(OrbitError) as failure:
        https_url(url)
    assert failure.value.status == 422


def test_channel_preserves_valid_https_parameters_without_injection():
    item = channel()
    result = parse_channel(raw(item))
    assert result["url"] == item["url"]
    assert result["name"] == "渠道一"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com:8443/path?a=1#/landing",
        "https://example.com/#fragment",
        "https://[2606:4700:4700::1111]/landing",
    ],
)
def test_channel_allows_contract_https_ports_spa_fragments_and_public_ipv6(value):
    assert https_url(value) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", "bad space"),
        ("code", "x" * 65),
        ("status", "ARCHIVED"),
        ("type", "网站"),
        ("media", "FACEBOOK"),
        ("name", None),
        ("product_id", "not-a-uuid"),
    ],
)
def test_channel_rejects_bad_fields(field, value):
    item = channel()
    item[field] = value
    with pytest.raises(OrbitError):
        parse_channel(raw(item))


def test_channel_structure_and_ownership_are_strict():
    item = channel()
    item["tenant_id"] = TEAM
    with pytest.raises(OrbitError) as failure:
        parse_channel(raw(item))
    assert failure.value.status == 400
    with pytest.raises(OrbitError):
        ownership({"owner_team_id": TEAM, "data_owner_user_ids": [USER], "scope": "ALL"})


def test_assignment_archive_require_reason_and_keep_ownership_distinct():
    assert parse_channel(raw({"reason": " 停止新增引用 "}), "archive") == {"reason": "停止新增引用"}
    assert (
        parse_channel(raw({"ownership": channel()["ownership"], "reason": "转交"}), "owners")[
            "ownership"
        ]
        == channel()["ownership"]
    )
    with pytest.raises(OrbitError):
        parse_channel(raw({"reason": ""}), "archive")


def test_data_scope_union_is_still_bounded_by_explicit_ownership():
    ctx = BusinessContext(1, TEAM, "USER", USER, TEAM)
    value = {"owner_team_id": TEAM, "data_owner_user_ids": [USER]}
    assert readable(ctx, [], value)
    hidden = deepcopy(value)
    hidden["data_owner_user_ids"] = [AGENT]
    assert not readable(ctx, [], hidden)
    assert not readable(replace(ctx, data_role="TEAM_ADMIN"), [], hidden)
    assert readable(replace(ctx, data_role="TEAM_ADMIN"), [TEAM], hidden)
    assert readable(replace(ctx, data_role="SUPER_ADMIN"), [], hidden)
    predicate = scope_clause(ctx, "r", "orbit_reference_owner", "reference_id")
    assert "o.user_id=:subject" in predicate and "o.tenant_id=r.tenant_id" in predicate


def test_user_maintenance_action_cannot_expand_ownership():
    context = BusinessContext(1, TEAM, "USER", USER, TEAM)
    own = {"owner_team_id": TEAM, "data_owner_user_ids": [USER]}
    assert_write_ownership(context, [], own)
    shared = {"owner_team_id": TEAM, "data_owner_user_ids": sorted([USER, AGENT])}
    assert_write_ownership(context, [], shared, previous=shared)
    with pytest.raises(OrbitError) as failure:
        assert_write_ownership(context, [], shared)
    assert failure.value.status == 403


def test_manager_own_scope_is_not_whole_team_scope():
    context = BusinessContext(1, TEAM, "TEAM_ADMIN", USER, TEAM)
    own = {"owner_team_id": TEAM, "data_owner_user_ids": [USER]}
    others = {"owner_team_id": TEAM, "data_owner_user_ids": [AGENT]}
    assert_write_ownership(context, [], own)
    with pytest.raises(OrbitError):
        assert_write_ownership(context, [], others)
    assert_write_ownership(context, [TEAM], others)


@pytest.mark.parametrize(
    "field,value,status,path",
    [
        ("name", 42, 400, "/name"),
        ("name", None, 400, "/name"),
        ("ownership", [], 400, "/ownership"),
        ("code", "bad code", 422, "/code"),
        ("product_id", "wrong", 400, "/product_id"),
        ("media", "FACEBOOK", 422, "/media"),
        ("bad/~field", "unknown", 400, "/bad~1~0field"),
    ],
)
def test_channel_exact_structure_boundary_and_pointer(field, value, status, path):
    payload = channel()
    payload[field] = value
    with pytest.raises(OrbitError) as failure:
        parse_channel(raw(payload))
    assert failure.value.status == status and failure.value.pointer == path
    if field == "bad/~field":
        assert failure.value.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize(
    "changes,status,path",
    [
        ({"kind": 1}, 400, "/kind"),
        ({"source": False}, 400, "/source"),
        ({"base_catalog_revision": True}, 400, "/base_catalog_revision"),
        ({"base_catalog_revision": -1}, 422, "/base_catalog_revision"),
        ({"items": {}}, 400, "/items"),
        ({"items": []}, 422, "/items"),
        ({"items": ["wrong"]}, 400, "/items/0"),
        ({"items": [row("VENDOR") | {"name": 42}]}, 400, "/items/0/name"),
        (
            {"items": [row("VENDOR") | {"data_owner_user_ids": [42]}]},
            400,
            "/items/0/data_owner_user_ids/0",
        ),
        ({"items": [row("VENDOR") | {"bad/~field": "unknown"}]}, 400, "/items/0/bad~1~0field"),
    ],
)
def test_import_exact_structure_boundary_and_pointer(changes, status, path):
    value = {
        "kind": "VENDOR",
        "source": "source",
        "reason": "reason",
        "base_catalog_revision": 0,
        "items": [row("VENDOR")],
    }
    with pytest.raises(OrbitError) as failure:
        parse_import(raw(value | changes))
    assert failure.value.status == status and failure.value.pointer == path


def test_business_row_value_errors_are_deferred_to_preview_not_structure():
    item = row("VENDOR")
    item["name"] = ""
    item["availability"] = "INVALID"
    value = {
        "kind": "VENDOR",
        "source": "source",
        "reason": "reason",
        "base_catalog_revision": 0,
        "items": [item],
    }
    assert parse_import(raw(value)).items == [item]
    with pytest.raises(OrbitError) as failure:
        normalize_row(item, "VENDOR")
    assert failure.value.status == 422


@pytest.mark.parametrize("kind", ["PRODUCT", "BUSINESS_AGENT"])
def test_retired_imports_cannot_be_created(kind):
    with pytest.raises(OrbitError) as failure:
        parse_import(
            raw(
                {
                    "kind": kind,
                    "source": "source",
                    "reason": "reason",
                    "base_catalog_revision": 0,
                    "items": [row(kind)],
                }
            )
        )
    assert failure.value.code == "REFERENCE_KIND_RETIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["PRODUCT", "BUSINESS_AGENT"])
async def test_retired_catalog_cannot_be_listed(kind):
    from orbit_api.reference_store import ReferenceStore

    with pytest.raises(OrbitError) as failure:
        await ReferenceStore(None).list(None, 1, kind, {"page_size": 20})
    assert failure.value.code == "REFERENCE_KIND_RETIRED"
