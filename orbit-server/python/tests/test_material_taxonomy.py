"""标签分类查询真实HTTP参数解析边界；SQL/权限计数由真实集成专项另验。"""

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_taxonomy import parse_taxonomy_filters


def test_taxonomy_original_query_defaults_and_literal_unicode_search():
    assert parse_taxonomy_filters({}) == {"q": "", "status": "", "page_size": 50}
    assert parse_taxonomy_filters(
        {"q": "  标签_%  ", "status": "DISABLED", "page_size": "200"}
    ) == {"q": "标签_%", "status": "DISABLED", "page_size": 200}


@pytest.mark.parametrize("size", ["20", "50", "100", "200"])
def test_taxonomy_all_original_page_sizes(size):
    assert parse_taxonomy_filters({"page_size": size})["page_size"] == int(size)


@pytest.mark.parametrize(
    "value",
    [
        {"status": ""},
        {"status": "READY"},
        {"page_size": "1"},
        {"page_size": "020"},
        {"q": "字" * 101},
    ],
)
def test_taxonomy_invalid_fields_rejected(value):
    with pytest.raises(OrbitError) as error:
        parse_taxonomy_filters(value)
    assert error.value.status == 422


@pytest.mark.parametrize(
    "field",
    ["date_from", "date_to", "operator_user_id", "channel_id", "metric_profile_id", "entity_type"],
)
def test_taxonomy_undefined_fact_filter_is_explicit_not_ignored(field):
    with pytest.raises(OrbitError) as error:
        parse_taxonomy_filters({field: "2026-01-01"})
    assert error.value.status == 422 and error.value.code == "FILTER_UNSUPPORTED"


def test_taxonomy_unknown_query_is_structural_error():
    with pytest.raises(OrbitError) as error:
        parse_taxonomy_filters({"unexpected": "x"})
    assert error.value.status == 400 and error.value.code == "UNKNOWN_FIELD"


def test_taxonomy_read_model_handles_immutable_sql_rows_and_cursor_binds_actor(monkeypatch):
    import asyncio
    from types import MappingProxyType
    from uuid import uuid4

    from orbit_api import material_library as module
    from orbit_api.authorization import BusinessContext

    identifier = str(uuid4())
    claims = {}

    class Tokens:
        def issue(self, purpose, value):
            claims["next"] = value
            return "fixture-signed-cursor"

        def verify(self, purpose, token):
            return claims["next"]

    class Library(module.MaterialLibrary):
        async def context(self, session, actor, permission="assets.read"):
            return BusinessContext(actor, "tenant", "USER", "subject", "team")

        async def scope_version(self, session, context):
            return 1

        async def taxonomy_counts(self, session, actor, kind, identifiers):
            return dict.fromkeys(identifiers, 3)

    async def one(*args, **kwargs):
        return {"revision": 1}

    async def rows(session, sql, params):
        if "orbit_business_team_manager" in sql:
            return []
        assert params["q"] == "字_%" and params["status"] == "ENABLED"
        return [
            MappingProxyType(
                {
                    "id": identifier,
                    "name": "字_%",
                    "group_name": "组",
                    "state": "ENABLED",
                    "revision": 1,
                }
            )
        ] * 21

    monkeypatch.setattr(module, "one", one)
    monkeypatch.setattr(module, "rows", rows)
    library = Library(Tokens())
    filters = {"q": "字_%", "status": "ENABLED", "page_size": 20}
    first = asyncio.run(library.taxonomy_list(None, 1, "TAG", filters=filters))
    assert len(first["items"]) == 20 and first["items"][0]["visible_asset_count"] == 3
    with pytest.raises(OrbitError) as error:
        asyncio.run(library.taxonomy_list(None, 2, "TAG", first["next_cursor"], filters))
    assert error.value.code == "CURSOR_STALE"


@pytest.mark.parametrize("cursor", ["", "x" * 2049])
def test_taxonomy_explicit_cursor_must_have_original_length(cursor):
    with pytest.raises(OrbitError) as error:
        parse_taxonomy_filters({"cursor": cursor})
    assert error.value.status == 422 and error.value.pointer == "/cursor"
