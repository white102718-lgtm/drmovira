"""原指标分页纯测：严格过滤/真实签名Token/新事务快照及坏行失败关闭，无SQL运行。"""

import asyncio
import hashlib
import hmac
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import URL

import orbit_api.metric_profile_query as module
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError

NOW = datetime(2026, 11, 8, 13, 0, tzinfo=UTC)
TENANT, SUBJECT, TEAM = (str(UUID(int=value)) for value in (100, 101, 102))
CURRENT = BusinessContext(1, TENANT, "USER", SUBJECT, TEAM)


class FixtureCipher:
    active_key_id = "isolated-pure-key"

    def application_mac(self, purpose, value, key_id=None):
        assert purpose == module.CURSOR_PURPOSE
        assert key_id in {None, self.active_key_id}
        return hmac.new(b"unit-test-only-not-a-production-key", value, hashlib.sha256).hexdigest()


def row(number=1, *, source="FIXTURE"):
    identifier = str(UUID(int=number))
    profile = {
        "id": identifier,
        "version": "exact-string-1",
        "source": source,
        "register_action_type": None,
        "purchase_action_type": "observed-purchase",
        "value_action_type": None,
        "attribution_windows": ["opaque-window"],
        "action_report_time": "observed-report",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 28,
        "verified": True,
    }
    config_id = str(UUID(int=103)) if source == "META" else None
    config_revision = 2 if source == "META" else None
    proof = {
        "source_sha256": "a" * 64,
        "observed_at": "2026-11-01T00:00:00+00:00",
        "evidence_ref": "pure:fixed",
        "source_config_id": config_id,
        "source_config_revision": config_revision,
    }
    return {
        "id": identifier,
        "current_version": profile["version"],
        "payload_json": canonical(profile),
        "payload_hash": hashlib.sha256(canonical(profile).encode()).hexdigest(),
        "source": source,
        "authority_kind": "TRUSTED" if source == "META" else "ISOLATED_TEST",
        "source_config_id": config_id,
        "source_config_revision": config_revision,
        "source_sha256": "a" * 64,
        "observed_at": datetime(2026, 11, 1),
        "evidence_ref": "pure:fixed",
        "source_proof_json": canonical(proof),
        "config_id": config_id,
        "config_section": "META_BM" if source == "META" else None,
        "config_enabled": 1 if source == "META" else None,
        "config_revision": config_revision,
    }


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    scalar_one_or_none = scalar_one

    def mappings(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value


class Session:
    def __init__(
        self,
        rows=None,
        *,
        revision=1,
        scope=1,
        auth=1,
        active=False,
        host="127.0.0.1",
        port=13306,
        database=None,
    ):
        self.rows = [row()] if rows is None else rows
        self.revision, self.scope, self.auth, self.active = revision, scope, auth, active
        self.sql = []
        self.bind = SimpleNamespace(url=URL.create("mysql", host=host, port=port))
        self.database = database or "orbit_py_it_" + "a" * 32

    def in_transaction(self):
        return self.active

    @asynccontextmanager
    async def begin(self):
        assert not self.active
        self.active = True
        try:
            yield
        finally:
            self.active = False

    async def execute(self, statement, values=None):
        assert self.active
        sql = str(statement)
        self.sql.append(sql)
        if sql == "SELECT DATABASE()":
            return Result(self.database)
        if "FROM sys_identity_subject" in sql:
            assert sql.endswith("FOR SHARE")
            return Result(self.auth)
        if "FROM orbit_directory_clock" in sql:
            assert sql.endswith("FOR SHARE")
            return Result(self.scope)
        if "FROM orbit_metric_profile_clock" in sql:
            assert sql.endswith("FOR SHARE")
            return Result({"revision": self.revision, "now": NOW.replace(tzinfo=None)})
        assert "FROM orbit_metric_profile_head h" in sql and "FOR SHARE" not in sql
        assert "LEFT JOIN orbit_system_configuration" in sql
        assert any("FROM orbit_metric_profile_clock" in previous for previous in self.sql[:-1])
        rows = [item for item in self.rows if item["id"] > values["after"]]
        for field in ("q", "metric_profile_id"):
            if field in values:
                rows = [item for item in rows if item["id"] == values[field]]
        return Result(sorted(rows, key=lambda item: item["id"])[: values["limit"]])


@pytest.fixture
def query(monkeypatch):
    authorize = AsyncMock(
        side_effect=lambda _session, actor, _menu, _action: replace(CURRENT, actor_id=actor)
    )
    monkeypatch.setattr(module, "require_business_access", authorize)
    return module.MetricProfileQuery(
        DirectoryTokens(FixtureCipher()), isolated_fixture=True
    ), authorize


def page(query, session, raw=None, *, actor=1, authorization="Bearer isolated-unit-session"):
    return asyncio.run(query.page(session, actor, authorization, raw or {}))


@pytest.mark.parametrize(
    "field",
    ["status", "date_from", "date_to", "operator_user_id", "channel_id", "entity_type", "unknown"],
)
def test_undefined_filters_are_not_silently_ignored(field):
    with pytest.raises(OrbitError) as error:
        module.parse_metric_profile_filters({field: "present"})
    assert error.value.status == 400 and error.value.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize(
    "raw",
    [
        {"page_size": "1"},
        {"page_size": 20},
        {"page_size": True},
        {"page_size": "050"},
        {"q": "partial-name"},
        {"metric_profile_id": None},
        {"cursor": ""},
        {"cursor": "x" * 2049},
    ],
)
def test_strict_parameter_boundaries(raw):
    with pytest.raises(OrbitError) as error:
        module.parse_metric_profile_filters(raw)
    assert error.value.status == 422


@pytest.mark.parametrize("size", ["20", "50", "100", "200"])
def test_only_original_page_sizes_allowed(size):
    filters, cursor = module.parse_metric_profile_filters({"page_size": size})
    assert filters == {"page_size": int(size), "q": "", "metric_profile_id": ""} and cursor is None


def test_real_signed_keyset_two_pages_preserves_original_page_and_exact_fields(query):
    reader, authorize = query
    rows = [row(value) for value in range(1, 22)]
    first_session = Session(rows)
    first = page(reader, first_session, {"page_size": "20"})
    assert not first_session.active and len(first["items"]) == 20 and first["next_cursor"]
    assert set(first) == {"items", "next_cursor", "data_as_of", "scope_version"}
    assert len(first["items"][0]) == 12 and "adapter_version" not in first["items"][0]
    second = page(reader, Session(rows), {"page_size": "20", "cursor": first["next_cursor"]})
    assert [item["id"] for item in first["items"] + second["items"]] == [
        item["id"] for item in rows
    ]
    assert second["next_cursor"] is None and second["data_as_of"] == first["data_as_of"]
    assert authorize.await_args.args[1:] == (1, "monitor", "monitor.read")


def test_filter_ids_intersect_and_shared_profile_has_no_owner_scope_clause(query):
    reader, _ = query
    session = Session([row(1), row(2)])
    assert (
        page(reader, session, {"q": row(1)["id"], "metric_profile_id": row(2)["id"]})["items"] == []
    )
    assert "owner_user_id" not in session.sql[-1] and "LIKE" not in session.sql[-1]
    exact = page(reader, Session([row(1), row(2)]), {"q": row(2)["id"]})
    assert [item["id"] for item in exact["items"]] == [row(2)["id"]]


@pytest.mark.parametrize(
    "change", ["authorization", "actor", "auth", "scope", "size", "filter", "clock"]
)
def test_cursor_binds_current_session_actor_auth_scope_filters_size_and_clock(query, change):
    reader, _ = query
    rows = [row(number) for number in range(1, 22)]
    token = page(reader, Session(rows), {"page_size": "20"})["next_cursor"]
    session_args, request_args = {}, {}
    raw = {"page_size": "20", "cursor": token}
    if change in {"auth", "scope"}:
        session_args[change] = 2
    elif change == "clock":
        session_args["revision"] = 2
    elif change == "size":
        raw["page_size"] = "50"
    elif change == "filter":
        raw["q"] = row()["id"]
    elif change == "actor":
        request_args["actor"] = 2
    else:
        request_args["authorization"] = "Bearer different-unit-session"
    with pytest.raises(OrbitError) as error:
        page(reader, Session(rows, **session_args), raw, **request_args)
    assert error.value.status == 409
    assert error.value.code == ("METRIC_PROFILE_CHANGED" if change == "clock" else "SCOPE_CHANGED")


def test_bad_signature_rejected_without_listing(query):
    reader, _ = query
    token = page(reader, Session([row(number) for number in range(1, 22)]), {"page_size": "20"})[
        "next_cursor"
    ]
    session = Session()
    with pytest.raises(OrbitError) as error:
        page(
            reader,
            session,
            {"page_size": "20", "cursor": token[:-1] + ("a" if token[-1] != "a" else "b")},
        )
    assert error.value.status == 400 and not any(
        "FROM orbit_metric_profile_head" in sql for sql in session.sql
    )


def test_existing_rr_transaction_cannot_reuse_old_snapshot(query):
    reader, authorize = query
    session = Session(active=True)
    with pytest.raises(ValueError):
        page(reader, session)
    authorize.assert_not_awaited()
    assert session.sql == []


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, None),
        ("127.0.0.1", 3306, None),
        ("127.0.0.1", 13306, "production"),
    ],
)
def test_explicit_fixture_guard_applies_even_to_empty_result(query, host, port, database):
    reader, _ = query
    session = Session([], host=host, port=port, database=database)
    with pytest.raises(OrbitError) as error:
        page(reader, session)
    assert error.value.status == 503 and not any(
        "FROM orbit_metric_profile_head" in sql for sql in session.sql
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("payload_hash", "b" * 64),
        ("id", str(UUID(int=999))),
        ("current_version", "different"),
        ("source_sha256", "b" * 64),
        ("evidence_ref", "different"),
        ("source_proof_json", '{"bad":true}'),
        ("payload_json", '{"bad":true}'),
        ("authority_kind", "TRUSTED"),
    ],
)
def test_corrupt_profile_or_proof_fails_whole_page(query, field, value):
    reader, _ = query
    broken = row() | {field: value}
    with pytest.raises(OrbitError) as error:
        page(reader, Session([broken]))
    assert error.value.status == 503


def test_production_default_rejects_fixture_and_accepts_complete_current_meta(monkeypatch):
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=CURRENT))
    reader = module.MetricProfileQuery(DirectoryTokens(FixtureCipher()))
    with pytest.raises(OrbitError) as error:
        page(reader, Session())
    assert error.value.status == 503
    result = page(reader, Session([row(source="META")]))
    assert result["items"][0]["source"] == "META"
    assert "config_id" not in result["items"][0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("config_enabled", 0),
        ("config_revision", 3),
        ("config_section", "GPT"),
        ("source_config_id", None),
    ],
)
def test_meta_source_must_match_exact_enabled_configuration(field, value):
    broken = row(source="META") | {field: value}
    with pytest.raises(OrbitError) as error:
        module.validated_public_profile(broken, isolated_fixture=False, now=NOW)
    assert error.value.status == 503


def test_041_candidate_only_three_after_configuration_triggers_and_sorted_clock_updates():
    source = (
        Path(__file__).resolve().parents[2]
        / "docs/orbit/sql-drafts/041_metric_profile_configuration_clock_candidate.sql"
    ).read_text(encoding="utf-8-sig")
    assert source.count("CREATE TRIGGER ") == 3
    assert all(
        " AFTER " + action + " ON orbit_system_configuration" in source
        for action in ("INSERT", "UPDATE", "DELETE")
    )
    assert "ORDER BY tenant_id" in source and "ROW_COUNT()<>2" in source
    assert "METRIC_CLOCK_UNAVAILABLE" in source and "revision<9007199254740991" in source
    assert "INSERT INTO orbit_metric_profile_clock" not in source


@pytest.mark.parametrize(
    "micros,expected_second,expected_micros",
    [
        (499, 0, 0),
        (500, 0, 1000),
        (998499, 0, 998000),
        (998500, 0, 999000),
        (999499, 0, 999000),
        (999500, 1, 0),
    ],
)
def test_mysql_observation_milliseconds_round_half_up_including_second_carry(
    micros,
    expected_second,
    expected_micros,
):
    value = datetime(2026, 11, 1, microsecond=micros, tzinfo=UTC)
    assert module.mysql_millisecond_instant(value) == datetime(
        2026,
        11,
        1,
        second=expected_second,
        microsecond=expected_micros,
        tzinfo=UTC,
    )


def test_mysql_observation_rounding_carries_across_year_boundary():
    assert module.mysql_millisecond_instant(datetime(2026, 12, 31, 23, 59, 59, 999500)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )


def test_legitimate_raw_microsecond_proof_matches_rounded_database_column():
    import json

    value = row()
    proof = json.loads(value["source_proof_json"])
    proof["observed_at"] = "2026-11-01T00:00:00.999700+00:00"
    value["source_proof_json"] = canonical(proof)
    value["observed_at"] = datetime(2026, 11, 1, 0, 0, 1)
    assert (
        module.validated_public_profile(value, isolated_fixture=True, now=NOW)["id"] == value["id"]
    )


@pytest.mark.parametrize(
    "observed",
    [None, "2026-11-01", datetime(2026, 11, 1, microsecond=1), datetime(2026, 11, 1, second=1)],
)
def test_wrong_independent_database_observation_column_is_rejected(observed):
    with pytest.raises(OrbitError) as error:
        module.validated_public_profile(
            row() | {"observed_at": observed}, isolated_fixture=True, now=NOW
        )
    assert error.value.status == 503


def test_matching_future_database_and_proof_observation_still_fails_closed():
    import json
    from datetime import timedelta

    value = row()
    future = NOW + timedelta(milliseconds=1)
    proof = json.loads(value["source_proof_json"])
    proof["observed_at"] = future.isoformat()
    value.update(observed_at=future.replace(tzinfo=None), source_proof_json=canonical(proof))
    with pytest.raises(OrbitError) as error:
        module.validated_public_profile(value, isolated_fixture=True, now=NOW)
    assert error.value.status == 503


def test_observation_rounding_overflow_is_explicitly_unavailable():
    with pytest.raises(OrbitError) as error:
        module.mysql_millisecond_instant(datetime.max.replace(tzinfo=UTC))
    assert error.value.status == 503
