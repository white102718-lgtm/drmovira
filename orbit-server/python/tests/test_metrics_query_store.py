"""指标窄READ纯测试：内存SQL替身只证明边界，不是MySQL或可信来源验收。"""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_store import (
    LATEST_CELLS_SQL,
    PUBLICATION_BINDING_FIELDS,
    MetricCellBatch,
    MetricReadContext,
    MetricReadSourceProvider,
    MetricsQueryStore,
    PublicationValidationReceipt,
    literal_contains,
    numerator,
    publication_validation_binding,
)
from orbit_api.metrics_scope_access import MetricQueryScope

TENANT, OWNER, TEAM, PROFILE, ACCOUNT = (str(uuid4()) for _ in range(5))
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def query(**changes):
    return {
        "date_from": "2026-01-01",
        "date_to": "2026-01-02",
        "dataset": "AD",
        "metric_profile_id": PROFILE,
        "scope_snapshot_id": None,
        "channel_id": None,
        "operator_user_id": None,
        "q": "",
        "sort": "spend",
        "direction": "DESC",
        "cursor": None,
        "page_size": 20,
        "granularity": "SUMMARY",
        **changes,
    }


def head(**changes):
    return {
        "tenant_id": TENANT,
        "id": str(uuid4()),
        "generation": 10,
        "profile_id": PROFILE,
        "profile_version": "original-version-01",
        "profile_hash": "a" * 64,
        "authority_kind": "ISOLATED_TEST",
        "source_config_id": None,
        "source_config_revision": None,
        "source_proof_json": '{"kind":"PURE_SQL_REPLACEMENT_NOT_PLATFORM"}',
        "state": "PUBLISHED",
        "expected_cell_count": 1,
        "expected_cells_hash": "b" * 64,
        "captured_cells_hash": "b" * 64,
        "cell_count": 1,
        "fact_count": 1,
        "capture_sequence_max": 120,
        "manifest_hash": "c" * 64,
        "publisher_actor_id": 1,
        "request_id": str(uuid4()),
        "oldest_observed_at": NOW.replace(tzinfo=None),
        "created_at": NOW.replace(tzinfo=None),
        "published_at": NOW.replace(tzinfo=None),
        **changes,
    }


def scope(role="USER", managed=(), **changes):
    return MetricQueryScope(
        BusinessContext(1, TENANT, role, OWNER, TEAM),
        1,
        "d" * 64,
        managed,
        changes.pop("snapshot_id", None),
        changes.pop("snapshot_hash", None),
        changes.pop("member_count", None),
        **changes,
    )


def cell(source, **changes):
    return {
        "tenant_id": TENANT,
        "id": str(uuid4()),
        "publication_id": source["id"],
        "account_id": ACCOUNT,
        "account_snapshot_id": str(uuid4()),
        "business_date": date(2026, 1, 1),
        "profile_id": PROFILE,
        "profile_version": source["profile_version"],
        "breakdown_key": "TOTAL",
        "capture_sequence": 120,
        "timezone_name": "Asia/Shanghai",
        "owner_user_id": OWNER,
        "owner_team_id": TEAM,
        "currency": "USD",
        "empty_result": 0,
        **changes,
    }


def fact(selected, **changes):
    value = {
        key: selected[key]
        for key in (
            "tenant_id",
            "account_id",
            "account_snapshot_id",
            "business_date",
            "profile_id",
            "profile_version",
            "breakdown_key",
            "capture_sequence",
        )
    }
    return value | {
        "cell_id": selected["id"],
        "id": str(uuid4()),
        "ad_id": str(uuid4()),
        "adset_id": str(uuid4()),
        "campaign_id": str(uuid4()),
        "campaign_snapshot_id": str(uuid4()),
        "adset_snapshot_id": str(uuid4()),
        "ad_snapshot_id": str(uuid4()),
        "spend": Decimal("120.000000"),
        "impressions": Decimal("1000.000000"),
        "clicks": Decimal("12.000000"),
        "registrations": None,
        "purchases": Decimal("2.000000"),
        "purchase_value": Decimal("240.000000"),
        "is_deleted": 0,
        **changes,
    }


class RegisteredPureSource(MetricReadSourceProvider):
    """只有本纯测登记的完整头可回执；不是生产Provider或SQLfixture发行器。"""

    kind = "ISOLATED_TEST"

    def __init__(self, heads):
        self.registered = {item["id"]: publication_validation_binding(item) for item in heads}
        self.calls = []
        self.override = None

    async def verify_publications(self, session, current_scope, original_query, heads):
        self.calls.append(tuple(item["id"] for item in heads))
        if self.override is not None:
            return self.override(heads)
        result = []
        for item in heads:
            actual = publication_validation_binding(item)
            if self.registered.get(item["id"]) != actual:
                raise OrbitError(503, "TEST_SOURCE_NOT_REGISTERED", "纯测试登记不匹配")
            result.append(PublicationValidationReceipt(actual))
        return tuple(result)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def all(self):
        return self.value


class Session:
    def __init__(self, heads):
        self.transaction = object()
        self.sync_session = SimpleNamespace(get_transaction=lambda: self.transaction)
        self.heads = {item["id"]: item for item in heads}
        self.anchor = max(heads, key=lambda item: item["generation"])
        self.profile_revision = 1
        self.calls = []
        self.cell_pages = []
        self.fact_pages = []
        self.dimensions = []
        self.matching_ids = []

    def in_transaction(self):
        return self.transaction is not None

    async def execute(self, statement, values=None):
        sql = str(statement)
        self.calls.append((sql, dict(values or {})))
        if "FROM orbit_metric_profile_head h" in sql:
            return FakeResult(
                [
                    {
                        "id": PROFILE,
                        "current_version": self.anchor["profile_version"],
                        "revision": self.profile_revision,
                        "state": "ENABLED",
                        "payload_hash": "a" * 64,
                    }
                ]
            )
        if "SELECT p.* FROM orbit_metric_publication p" in sql:
            if "ids" in values:
                return FakeResult([self.heads[key] for key in values["ids"] if key in self.heads])
            return FakeResult([self.anchor])
        if "SELECT c.* FROM orbit_metric_capture_cell c" in sql:
            return FakeResult(self.cell_pages.pop(0) if self.cell_pages else [])
        if "SELECT f.* FROM orbit_metric_ad_fact_version f" in sql:
            return FakeResult(self.fact_pages.pop(0) if self.fact_pages else [])
        if "SELECT d.id,d.tenant_id,d.account_id,d.entity_kind" in sql:
            return FakeResult(
                [
                    {key: item[key] for key in ("id", "tenant_id", "account_id", "entity_kind")}
                    | {"name_length": len(item["name"])}
                    for item in self.dimensions
                ]
            )
        if "SELECT d.* FROM orbit_metric_entity_snapshot d" in sql:
            selected = self.dimensions
            if " LIKE :contains" in sql:
                selected = [item for item in selected if item["id"] in self.matching_ids]
            return FakeResult(selected)
        raise AssertionError("纯SQL替身遇到未登记查询")


@pytest.fixture
def setup(monkeypatch):
    async def build(*, heads=None, current_scope=None, body=None, clock=None):
        heads = heads or [head()]
        source = RegisteredPureSource(heads)
        session = Session(heads)
        authorization = AsyncMock(return_value=current_scope or scope())
        boundary = AsyncMock()
        monkeypatch.setattr("orbit_api.metrics_query_store.authorize_metric_scope", authorization)
        monkeypatch.setattr("orbit_api.metrics_query_store.fixture_boundary", boundary)
        store = MetricsQueryStore(source, clock=clock or (lambda: NOW))
        original = body or query()
        context = await store.select_source_anchor(session, 1, original)
        return store, session, source, context, authorization, boundary

    return build


@pytest.mark.parametrize("operation", range(4))
def test_default_no_provider_all_entries_503_zero_sql_and_no_auth(monkeypatch, operation):
    authorize = AsyncMock()
    monkeypatch.setattr("orbit_api.metrics_query_store.authorize_metric_scope", authorize)
    session = SimpleNamespace(execute=AsyncMock())
    store = MetricsQueryStore()

    async def run():
        if operation == 0:
            return await store.select_source_anchor(session, 1, query())
        if operation == 1:
            return await anext(store.iter_latest_cells(session, MetricReadContext()))
        if operation == 2:
            return await anext(
                store.iter_selected_facts(session, MetricReadContext(), MetricCellBatch())
            )
        return await store.select_matching_dimensions(
            session, MetricReadContext(), MetricCellBatch()
        )

    with pytest.raises(OrbitError) as result:
        asyncio.run(run())
    assert (result.value.status, result.value.code) == (503, "METRICS_DATA_UNVERIFIED")
    session.execute.assert_not_called()
    authorize.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", True),
        ("generation", 1.0),
        ("generation", 0),
        ("fact_count", -1),
        ("expected_cell_count", 2),
        ("captured_cells_hash", "e" * 64),
        ("manifest_hash", "A" * 64),
        ("profile_hash", None),
        ("state", "BUILDING"),
        ("source_config_id", str(uuid4())),
        ("source_config_revision", 1),
        ("profile_version", "x" * 65),
        ("published_at", "2026-01-01"),
        ("source_proof_json", []),
        ("source_proof_json", {"bad": float("nan")}),
        ("authority_kind", "TRUSTED"),
        ("created_at", None),
    ],
)
def test_full_head_binding_rejects_unverified_shapes(field, value):
    with pytest.raises(OrbitError) as result:
        publication_validation_binding(head(**{field: value}))
    assert result.value.status == 503


def test_proof_hash_is_full_canonical_object_and_binding_has_every_actual_head_field():
    original = head(source_proof_json='{"z":2,"a":1}')
    same = original | {"source_proof_json": {"a": 1, "z": 2}}
    assert publication_validation_binding(original) == publication_validation_binding(same)
    changed = original | {"source_proof_json": {"a": 1, "z": 3}}
    assert publication_validation_binding(original) != publication_validation_binding(changed)
    assert set(PUBLICATION_BINDING_FIELDS) == set(original) - {"source_proof_json"} | {
        "source_proof_hash"
    }


@pytest.mark.parametrize("mode", ["true", "list", "empty", "duplicate", "foreign", "bool-int"])
def test_provider_receipt_requires_exact_all_heads_and_strict_types(setup, mode):
    async def run():
        store, session, source, context, _, _ = await setup()
        expected = publication_validation_binding(session.anchor)

        def bad(heads):
            if mode == "true":
                return True
            if mode == "list":
                return [PublicationValidationReceipt(expected)]
            if mode == "empty":
                return ()
            if mode == "duplicate":
                return (
                    PublicationValidationReceipt(expected),
                    PublicationValidationReceipt(expected),
                )
            changed = list(expected)
            changed[1 if mode == "foreign" else 18] = str(uuid4()) if mode == "foreign" else True
            return (PublicationValidationReceipt(tuple(changed)),)

        source.override = bad
        await store._binding(session, context)

    with pytest.raises(OrbitError) as result:
        asyncio.run(run())
    assert result.value.status == 503


@pytest.mark.parametrize("field", PUBLICATION_BINDING_FIELDS)
def test_any_changed_head_receipt_field_is_rejected(setup, field):
    async def run():
        store, session, source, context, _, _ = await setup()
        changed = list(publication_validation_binding(session.anchor))
        index = PUBLICATION_BINDING_FIELDS.index(field)
        value = changed[index]
        changed[index] = (
            value + 1 if type(value) is int else ("changed" if value is not None else 1)
        )
        source.override = lambda _heads: (PublicationValidationReceipt(tuple(changed)),)
        await store._binding(session, context)

    with pytest.raises(OrbitError):
        asyncio.run(run())


@pytest.mark.parametrize(
    "mode",
    ["forged", "other-store", "other-session", "next-transaction", "ended", "provider-replaced"],
)
def test_private_handle_cannot_be_forged_or_reused_outside_exact_session_transaction(setup, mode):
    async def run():
        store, session, source, context, _, _ = await setup()
        calls = len(session.calls)
        target = store
        if mode == "forged":
            context = MetricReadContext()
        elif mode == "other-store":
            target = MetricsQueryStore(source)
        elif mode == "other-session":
            session = Session(list(session.heads.values()))
            calls = 0
        elif mode == "next-transaction":
            session.transaction = object()
        elif mode == "ended":
            session.transaction = None
        else:
            store.source_provider = RegisteredPureSource(list(session.heads.values()))
        with pytest.raises(OrbitError) as result:
            await target._binding(session, context)
        assert result.value.code == "METRICS_READ_CONTEXT_INVALID"
        assert len(session.calls) == calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "change", ["auth", "fingerprint", "scopehash", "managed", "membercount", "subject"]
)
def test_current_scope_is_rechecked_before_reading_frozen_source(setup, change):
    async def run():
        current_scope = scope(snapshot_id=str(uuid4()), snapshot_hash="e" * 64, member_count=501)
        store, session, _, context, authorize, _ = await setup(current_scope=current_scope)
        changes = {
            "auth": {"auth_version": 2},
            "fingerprint": {"auth_fingerprint": "f" * 64},
            "scopehash": {"snapshot_hash": "a" * 64},
            "managed": {"managed_team_ids": (str(uuid4()),)},
            "membercount": {"member_count": 500},
            "subject": {"current": BusinessContext(1, TENANT, "USER", str(uuid4()), TEAM)},
        }[change]
        authorize.return_value = replace(current_scope, **changes)
        calls = len(session.calls)
        with pytest.raises(OrbitError) as result:
            await store._binding(session, context)
        assert result.value.code == "METRICS_READ_CONTEXT_INVALID" and len(session.calls) == calls

    asyncio.run(run())


def test_original_query_mutation_cannot_change_bound_intent_and_profile_change_invalidates(setup):
    async def run():
        original = query()
        store, session, _, context, _, boundary = await setup(body=original)
        original["q"] = "different"
        assert (await store._binding(session, context)).query["q"] == ""
        boundary.assert_awaited_once_with(session)
        session.profile_revision += 1
        with pytest.raises(OrbitError) as result:
            await store._binding(session, context)
        assert result.value.code == "METRICS_SOURCE_CHANGED"

    asyncio.run(run())


@pytest.mark.parametrize(
    "role,managed",
    [("USER", ()), ("TEAM_ADMIN", ()), ("TEAM_ADMIN", (str(uuid4()),)), ("SUPER_ADMIN", ())],
)
def test_cell_candidates_keyset_historical_scope_and_partition_latest_are_not_q_filtered(
    setup, role, managed
):
    async def run():
        current_scope = scope(
            role, managed, snapshot_id=str(uuid4()), snapshot_hash="e" * 64, member_count=501
        )
        original = query(
            q="middle", channel_id="arbitrary-original-channel", operator_user_id=OWNER
        )
        store, session, _, context, _, _ = await setup(current_scope=current_scope, body=original)
        selected = cell(session.anchor)
        next_cell = cell(session.anchor, business_date=date(2026, 1, 2))
        session.cell_pages = [[selected], [next_cell], []]
        batches = [
            batch async for batch in store.iter_latest_cells(session, context, read_batch_size=1)
        ]
        assert len(batches) == 2
        cell_calls = [(sql, values) for sql, values in session.calls if "SELECT c.*" in sql]
        assert cell_calls[1][1]["after_account"] == ACCOUNT
        assert cell_calls[1][1]["after_day"] == date(2026, 1, 1)
        sql, values = cell_calls[0]
        assert "snapshot" in values and "member_count" not in values
        assert values["operator"] == OWNER and "q" not in values and "channel" not in values
        inner = sql.split("AND NOT EXISTS (")[1].split("AND ({visible})")[0]
        assert "newer.owner" not in inner and "OFFSET" not in sql
        assert "FOR SHARE" not in sql  # 不把窗口/聚合变成虚假当前锁读；固定同事务cutoff。
        assert ("managed" in values) == bool(role == "TEAM_ADMIN" and managed)
        if role == "SUPER_ADMIN":
            assert "AND (1=1)" in sql
        with pytest.raises(TypeError):
            batches[0].rows[0]["tenant_id"] = "forged"

    asyncio.run(run())


def test_old_publication_must_also_have_exact_registered_source_receipt(setup):
    async def run():
        anchor, old = head(generation=20), head(generation=10)
        store, session, source, context, _, _ = await setup(heads=[anchor, old])
        session.cell_pages = [[cell(old)]]
        source.registered.pop(old["id"])
        with pytest.raises(OrbitError) as result:
            await anext(store.iter_latest_cells(session, context))
        assert result.value.code == "TEST_SOURCE_NOT_REGISTERED"

    asyncio.run(run())


def test_raw_cell_rows_cannot_replace_store_issued_batch_and_facts_are_bounded(setup):
    async def run():
        store, session, _, context, _, _ = await setup(body=query(channel_id="raw-code"))
        selected = cell(session.anchor)
        session.cell_pages = [[selected]]
        batch = await anext(store.iter_latest_cells(session, context))
        batch._rows = ({"id": "forged-private-row"},)
        first, second = sorted([fact(selected), fact(selected)], key=lambda row: row["id"])
        session.fact_pages = [[first], [second], []]
        found = [
            result
            async for result in store.iter_selected_facts(
                session, context, batch, read_batch_size=1
            )
        ]
        assert len(found) == 2 and found[0].rows[0]["spend"] == "120"
        assert found[0].rows[0]["registrations"] is None
        calls = [(sql, values) for sql, values in session.calls if "SELECT f.*" in sql]
        assert calls[0][1]["ids"] == (selected["id"],) and calls[0][1]["channel"] == "raw-code"
        assert calls[1][1]["after_id"] == first["id"]
        assert "f.is_deleted=0" in calls[0][0]
        with pytest.raises(OrbitError):
            await anext(store.iter_selected_facts(session, context, MetricCellBatch()))

    asyncio.run(run())


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0.000000"), "0"),
        (Decimal("123.450000"), "123.45"),
        (None, None),
        (Decimal("1" * 28), "1" * 28),
    ],
)
def test_fixed_source_values_preserve_decimal_and_null_without_rounding(value, expected):
    assert numerator(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        1,
        "1",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0.0000001"),
        Decimal("1" * 29),
    ],
)
def test_fixed_source_float_noncanonical_or_overcontract_value_is_503(value):
    with pytest.raises(OrbitError) as result:
        numerator(value)
    assert result.value.status == 503


def test_dimension_contains_is_only_related_ids_and_missing_row_never_becomes_fake_empty(setup):
    async def run():
        store, session, _, context, _, _ = await setup(body=query(dataset="ACCOUNT", q="字面%_!"))
        selected = cell(session.anchor)
        session.cell_pages = [[selected]]
        batch = await anext(store.iter_latest_cells(session, context))
        identifier = selected["account_snapshot_id"]
        session.dimensions = [
            {
                "id": identifier,
                "tenant_id": TENANT,
                "account_id": ACCOUNT,
                "entity_kind": "ACCOUNT",
                "name": "前段字面%_!后段",
                "external_id": "000123",
            }
        ]
        session.matching_ids = [identifier]
        result = await store.select_matching_dimensions(session, context, batch)
        assert result[0]["external_id"] == "000123"
        matching = next((sql, values) for sql, values in session.calls if " LIKE :contains" in sql)
        assert matching[1]["contains"] == literal_contains("字面%_!")
        assert matching[1]["ids"] == (identifier,) and "LIKE :contains" in matching[0]
        session.dimensions = []
        with pytest.raises(OrbitError):
            await store.select_matching_dimensions(session, context, batch)

    asyncio.run(run())


def test_raw_dimensions_keep_old_nonmatching_long_name_for_whole_window_reduction(setup):
    async def run():
        store, session, _, context, _, _ = await setup(body=query(dataset="ACCOUNT", q="新名称"))
        selected = cell(session.anchor)
        session.cell_pages = [[selected]]
        batch = await anext(store.iter_latest_cells(session, context))
        session.dimensions = [
            {
                "id": selected["account_snapshot_id"],
                "tenant_id": TENANT,
                "account_id": ACCOUNT,
                "entity_kind": "ACCOUNT",
                "name": "旧" * 10000,
                "external_id": "001",
            }
        ]
        session.matching_ids = []
        before = len(session.calls)
        result = await store.select_dimensions(session, context, batch)
        assert len(result) == 1 and len(result[0]["name"]) == 10000
        assert not any("LIKE :contains" in sql for sql, _ in session.calls[before:])
        assert result[0]["external_id"] == "001"

    asyncio.run(run())


def test_unmatched_full_raw_name_is_preserved_but_no_truncated_projection_is_published(setup):
    async def run():
        store, session, _, context, _, _ = await setup(body=query(dataset="ACCOUNT", q="other"))
        selected = cell(session.anchor)
        session.cell_pages = [[selected]]
        batch = await anext(store.iter_latest_cells(session, context))
        identifier = selected["account_snapshot_id"]
        session.dimensions = [
            {
                "id": identifier,
                "tenant_id": TENANT,
                "account_id": ACCOUNT,
                "entity_kind": "ACCOUNT",
                "name": "名" * 10000,
                "external_id": "001",
            }
        ]
        assert await store.select_matching_dimensions(session, context, batch) == ()
        session.matching_ids = [identifier]
        result = await store.select_matching_dimensions(session, context, batch)
        assert len(result) == 1 and len(result[0]["name"]) == 10000
        # 原始层不替最终DTO截名或拒旧名称；最终最新名称上限由结果投影验证。

    asyncio.run(run())


@pytest.mark.parametrize(
    "timezone,code",
    [
        ("America/Los_Angeles", "FIELD_VALIDATION_FAILED"),
        ("not/an/iana", "METRICS_DATA_UNVERIFIED"),
    ],
)
def test_future_date_uses_actual_cell_iana_today_not_shanghai_or_utc(setup, timezone, code):
    async def run():
        store, session, _, context, _, _ = await setup(
            body=query(date_from="2026-11-09", date_to="2026-11-09"),
            clock=lambda: datetime(2026, 11, 9, 0, 30, tzinfo=UTC),
        )
        session.cell_pages = [
            [cell(session.anchor, business_date=date(2026, 11, 9), timezone_name=timezone)]
        ]
        with pytest.raises(OrbitError) as result:
            await anext(store.iter_latest_cells(session, context))
        assert result.value.code == code

    asyncio.run(run())


def test_source_sql_has_no_write_or_offset_and_newer_antijoin_ignores_owner_and_q():
    source = __import__("inspect").getsource(
        __import__("orbit_api.metrics_query_store", fromlist=[""])
    )
    assert all(
        word not in source for word in ("INSERT INTO", "UPDATE orbit_", "DELETE FROM", "OFFSET")
    )
    newer = LATEST_CELLS_SQL.split("AND NOT EXISTS (")[1].split("AND ({visible})")[0]
    assert "owner_user_id" not in newer and "channel" not in newer and " LIKE " not in newer
    assert "newer.capture_sequence>c.capture_sequence" in newer


@pytest.mark.parametrize("size", [True, 0, -1, 201, 1.0, "20"])
def test_invalid_internal_batch_bound_cannot_trigger_unbounded_reads(setup, size):
    async def run():
        store, session, _, context, _, _ = await setup()
        before = len(session.calls)
        with pytest.raises(ValueError):
            await anext(store.iter_latest_cells(session, context, read_batch_size=size))
        assert len(session.calls) == before

    asyncio.run(run())


def test_receipt_unhashable_identifier_is_safe_503_not_type_error(setup):
    async def run():
        store, session, source, context, _, _ = await setup()
        value = list(publication_validation_binding(session.anchor))
        value[1] = []
        source.override = lambda _heads: (PublicationValidationReceipt(tuple(value)),)
        with pytest.raises(OrbitError) as result:
            await store._binding(session, context)
        assert result.value.status == 503

    asyncio.run(run())


def test_source_callback_cannot_commit_and_continue_with_old_capability(setup):
    async def run():
        store, session, source, context, _, _ = await setup()

        def changed_transaction(heads):
            session.transaction = object()
            return tuple(
                PublicationValidationReceipt(publication_validation_binding(item)) for item in heads
            )

        source.override = changed_transaction
        with pytest.raises(OrbitError) as result:
            await store._binding(session, context)
        assert result.value.code == "METRICS_READ_CONTEXT_INVALID"

    asyncio.run(run())


def test_fact_dimension_read_rechecks_origin_publication_not_only_latest_anchor(setup):
    async def run():
        anchor, old = head(generation=20), head(generation=10)
        store, session, source, context, _, _ = await setup(heads=[anchor, old])
        selected = cell(old)
        session.cell_pages = [[selected]]
        cell_batch = await anext(store.iter_latest_cells(session, context))
        session.fact_pages = [[fact(selected)]]
        fact_batch = await anext(store.iter_selected_facts(session, context, cell_batch))
        source.registered.pop(old["id"])
        with pytest.raises(OrbitError) as result:
            await store.select_matching_dimensions(session, context, fact_batch)
        assert result.value.code == "TEST_SOURCE_NOT_REGISTERED"

    asyncio.run(run())


def test_permission_revocation_is_propagated_before_any_frozen_read(setup):
    async def run():
        store, session, _, context, authorize, _ = await setup()
        before = len(session.calls)
        authorize.side_effect = OrbitError(403, "PERMISSION_DENIED", "当前动作不可用")
        with pytest.raises(OrbitError) as result:
            await anext(store.iter_latest_cells(session, context))
        assert result.value.status == 403 and len(session.calls) == before

    asyncio.run(run())


@pytest.mark.parametrize(
    "q,external", [("中文中段", None), ("000123", "000123"), ("123" * 30, None)]
)
def test_only_real_ascii_numeric_id_adds_exact_external_predicate(setup, q, external):
    async def run():
        store, session, _, context, _, _ = await setup(body=query(dataset="ACCOUNT", q=q))
        selected = cell(session.anchor)
        session.cell_pages = [[selected]]
        batch = await anext(store.iter_latest_cells(session, context))
        identifier = selected["account_snapshot_id"]
        session.dimensions = [
            {
                "id": identifier,
                "tenant_id": TENANT,
                "account_id": ACCOUNT,
                "entity_kind": "ACCOUNT",
                "name": "actual original name",
                "external_id": "000123",
            }
        ]
        await store.select_matching_dimensions(session, context, batch)
        sql, values = next(
            (sql, values) for sql, values in session.calls if " LIKE :contains" in sql
        )
        assert values.get("external_id") == external
        assert ("d.external_id=:external_id" in sql) == (external is not None)

    asyncio.run(run())
