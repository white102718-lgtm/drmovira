"""指标来源原合同及内部状态机纯测；不运行SQL或平台采集。"""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import URL

import orbit_api.metric_profile_store as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.metric_profile_contract import MetricSourceProof, publication


def fixture(source="FIXTURE"):
    proof = MetricSourceProof(
        "a" * 64,
        datetime(2026, 11, 1, tzinfo=UTC),
        "receipt:fixed",
        str(uuid4()) if source == "META" else None,
        1 if source == "META" else None,
    )
    profile = {
        "id": str(uuid4()),
        "version": "release-2026.11",
        "source": source,
        "register_action_type": None,
        "purchase_action_type": "purchase-observed",
        "value_action_type": None,
        "attribution_windows": ["opaque-window-not-auto-converted"],
        "action_report_time": "observed-report-time",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 28,
        "verified": True,
    }
    prepared = publication(
        profile, "explicit-adapter-A", [{"event_type": "EXPLICIT", "window_days": 7}], proof
    )
    return profile, proof, prepared


class Authority(module.MetricProfileAuthority):
    kind = "ISOLATED_TEST"

    def __init__(self, value):
        self.value = value

    async def capture(self, *args):
        return self.value

    async def revalidate(self, *args):
        return self.value.proof


class Database:
    def __init__(self, host="127.0.0.1", port=13306, name=None):
        self.bind = SimpleNamespace(url=URL.create("mysql", host=host, port=port))
        self.name = name or "orbit_py_it_" + "a" * 32
        self.writes = []

    def in_transaction(self):
        return True

    async def execute(self, statement, params=None):
        if str(statement) == "SELECT UTC_TIMESTAMP(3)":
            return SimpleNamespace(scalar_one=lambda: datetime(2026, 11, 8, tzinfo=UTC))
        if str(statement) == "SELECT DATABASE()":
            return SimpleNamespace(scalar_one=lambda: self.name)
        self.writes.append((str(statement), params))
        return SimpleNamespace(rowcount=1)


@pytest.mark.parametrize("connection", [False, True])
@pytest.mark.parametrize(
    "host,port,name,valid",
    [
        ("127.0.0.1", 13306, "orbit_py_it_" + "b" * 32, True),
        ("localhost", 13306, None, False),
        ("127.0.0.1", 3306, None, False),
        ("127.0.0.1", 13306, "business", False),
    ],
)
def test_owned_connection_keeps_same_exact_fixture_boundary(connection, host, port, name, valid):
    database = Database(host, port, name)
    if connection:
        database.bind = SimpleNamespace(engine=database.bind)
    if valid:
        asyncio.run(module.fixture_boundary(database))
        assert database.writes == []
    else:
        with pytest.raises(OrbitError):
            asyncio.run(module.fixture_boundary(database))


def context():
    return BusinessContext(1, str(uuid4()), "SUPER_ADMIN", str(uuid4()), str(uuid4()))


def test_original_profile_and_explicit_mapping_remain_separate_without_guessing():
    profile, _, prepared = fixture()
    assert prepared.profile() == profile
    assert json.loads(prepared.attribution_json) == [{"event_type": "EXPLICIT", "window_days": 7}]
    assert "registry_revision" not in profile and "adapter_version" not in profile
    assert profile["attribution_windows"] == ["opaque-window-not-auto-converted"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 1),
        ("version", ""),
        ("version", "v" * 65),
        ("maturity_days", True),
        ("maturity_days", 0),
        ("maturity_days", 91),
        ("verified", 1),
        ("source", "UNKNOWN"),
        ("attribution_windows", []),
        ("timezone_policy", "UTC"),
        ("breakdown", "COUNTRY"),
        ("register_action_type", ""),
        ("internal_revision", 1),
    ],
)
def test_original_profile_strict_fields_never_inherit_defaults(field, value):
    profile, proof, _ = fixture()
    profile[field] = value
    with pytest.raises(OrbitError):
        publication(profile, "adapter", [{"event_type": "EXPLICIT", "window_days": 7}], proof)


@pytest.mark.parametrize(
    "mapping",
    [
        [],
        [{"window_days": 7}],
        [{"event_type": "X", "window_days": True}],
        [{"event_type": "X", "window_days": 7, "token": "not-allowed"}],
    ],
)
def test_mapping_requires_explicit_strict_attribution_spec(mapping):
    profile, proof, _ = fixture()
    with pytest.raises(OrbitError):
        publication(profile, "adapter", mapping, proof)


@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "bad"},
        {"observed_at": datetime(2026, 1, 1)},
        {"evidence_ref": "https://unsafe.example/token"},
        {"source_config_id": str(uuid4())},
    ],
)
def test_source_proof_is_explicit_bounded_utc_and_no_transport(change):
    profile, proof, _ = fixture()
    with pytest.raises(OrbitError):
        publication(
            profile, "adapter", [{"event_type": "X", "window_days": 7}], replace(proof, **change)
        )


def test_missing_authority_is_zero_database_work():
    _, _, prepared = fixture()
    database = Database()
    with pytest.raises(OrbitError) as error:
        asyncio.run(
            module.MetricProfileStore().publish(database, context(), prepared, 0, str(uuid4()))
        )
    assert error.value.code == "METRIC_PROFILE_AUTHORITY_UNAVAILABLE" and not database.writes


@pytest.mark.parametrize(
    "host,port,name",
    [
        ("localhost", 13306, None),
        ("127.0.0.1", 3306, None),
        ("192.0.2.1", 13306, None),
        ("127.0.0.1", 13306, "business"),
    ],
)
def test_fixture_boundary_is_exact_host_port_and_uuid_database(host, port, name):
    with pytest.raises(OrbitError):
        asyncio.run(module.fixture_boundary(Database(host, port, name)))


def test_prepare_does_not_use_session_and_rejects_authority_wrong_version():
    profile, _, prepared = fixture()
    store = module.MetricProfileStore(Authority(prepared))
    assert (
        asyncio.run(store.prepare(profile["id"], profile["version"], prepared.adapter_version))
        == prepared
    )
    with pytest.raises(OrbitError):
        asyncio.run(store.prepare(profile["id"], "different", prepared.adapter_version))


def test_forged_publication_bytes_cannot_skip_strict_contract():
    _, _, prepared = fixture()
    with pytest.raises(OrbitError):
        module.checked_prepared(replace(prepared, attribution_json=b"[]"))
    with pytest.raises(OrbitError):
        module.checked_prepared(replace(prepared, profile_json=prepared.profile_json + b" "))


@pytest.mark.parametrize(
    "state", ["new", "duplicate", "disabled", "immutable-conflict", "stale-new"]
)
def test_publish_is_atomic_intent_and_exact_version_not_old_head_alias(monkeypatch, state):
    profile, _, prepared = fixture()
    current, database = context(), Database()
    store = module.MetricProfileStore(Authority(prepared))
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))

    async def read(session, sql, params):
        if "clock" in sql:
            return {"revision": 5}
        if "FROM orbit_metric_profile_head" in sql:
            return (
                None
                if state == "new"
                else {
                    "current_version": profile["version"],
                    "revision": 3,
                    "state": "DISABLED" if state == "disabled" else "ENABLED",
                }
            )
        if "FROM orbit_metric_profile_version" in sql:
            return (
                None
                if state in {"new", "stale-new"}
                else {
                    "payload_hash": "f" * 64
                    if state == "immutable-conflict"
                    else prepared.profile_hash,
                    "source_proof_json": module.proof_document(prepared.proof),
                }
            )
        if "FROM orbit_metric_profile_adapter" in sql:
            return (
                None
                if state in {"new", "stale-new"}
                else {
                    "profile_hash": prepared.profile_hash,
                    "mapping_hash": prepared.attribution_hash,
                    "revoked_at": None,
                    "source_proof_json": module.proof_document(prepared.proof),
                }
            )
        raise AssertionError("不允许其他SQL")

    monkeypatch.setattr(module, "one", read)
    if state in {"disabled", "immutable-conflict", "stale-new"}:
        with pytest.raises(OrbitError):
            asyncio.run(store.publish(database, current, prepared, 0, str(uuid4())))
        assert not database.writes
    else:
        result = asyncio.run(store.publish(database, current, prepared, 0, str(uuid4())))
        assert result["version"] == profile["version"]
        if state == "duplicate":
            assert not database.writes and result["revision"] == 3
        else:
            assert result["revision"] == 1
            operations = [sql for sql, _ in database.writes]
            assert operations[0].startswith("INSERT INTO orbit_metric_profile_version")
            assert sum("INSERT INTO orbit_metric_profile_audit" in sql for sql in operations) == 1
            assert sum("INSERT INTO orbit_metric_profile_outbox" in sql for sql in operations) == 1
            assert sum("UPDATE orbit_metric_profile_clock" in sql for sql in operations) == 1


@pytest.mark.parametrize("fault", ["none", "source", "revoked", "hash", "mapping", "proof"])
def test_exact_read_keeps_explicit_profile_mapping_and_rejects_changed_sources(monkeypatch, fault):
    profile, _, prepared = fixture()
    current, database = context(), Database()
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))
    row = {
        "current_version": profile["version"],
        "state": "ENABLED",
        "source": "FIXTURE",
        "payload_json": prepared.profile_json.decode(),
        "payload_hash": prepared.profile_hash,
        "profile_hash": prepared.profile_hash,
        "mapping_json": prepared.attribution_json.decode(),
        "mapping_hash": prepared.attribution_hash,
        "registry_revision": 6,
        "revoked_at": None,
        "source_config_id": None,
        "source_config_revision": None,
        "source_connection_id": None,
        "source_connection_revision": None,
        "version_proof": module.proof_document(prepared.proof),
        "adapter_proof": module.proof_document(prepared.proof),
    }
    if fault == "source":
        row["current_version"] = "different"
    elif fault == "revoked":
        row["revoked_at"] = datetime.now(UTC)
    elif fault == "hash":
        row["payload_hash"] = "f" * 64
    elif fault == "mapping":
        row["mapping_hash"] = "e" * 64
    elif fault == "proof":
        row["adapter_proof"] = "{}"

    async def exact_one(session, sql, params):
        if "FROM orbit_user_scope" in sql:
            return {
                key: getattr(current, key)
                for key in ("actor_id", "tenant_id", "data_role", "subject_id", "team_id")
            }
        if "clock" in sql:
            return {"revision": 6}
        return row

    monkeypatch.setattr(module, "one", exact_one)

    async def read():
        return await module.MetricProfileStore().lock_exact(
            database, current, current, profile["id"], profile["version"], prepared.adapter_version
        )

    if fault == "none":
        result = asyncio.run(read())
        assert result["profile"] == profile and result["registry_revision"] == 6
        assert result["attribution_spec"] == json.loads(prepared.attribution_json)
    else:
        with pytest.raises(OrbitError):
            asyncio.run(read())


@pytest.mark.parametrize("limit", [True, 1, 201])
def test_candidate_foundation_rejects_unknown_page_size_before_list_sql(monkeypatch, limit):
    current, database = context(), Database()
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))
    with pytest.raises(OrbitError):
        asyncio.run(module.MetricProfileStore().candidate_page(database, current, limit=limit))
    assert not database.writes


@pytest.mark.parametrize(
    "fault", ["changed-proof", "future-time", "meta-in-fixture", "fixture-in-trusted"]
)
def test_publication_source_changes_cannot_reach_clock_or_business_writes(monkeypatch, fault):
    profile, proof, prepared = fixture("META" if fault == "meta-in-fixture" else "FIXTURE")
    current, database = context(), Database()
    authority = Authority(prepared)
    if fault == "fixture-in-trusted":
        authority.kind = "TRUSTED"
    if fault == "changed-proof":
        authority.revalidate = AsyncMock(return_value=replace(proof, source_sha256="b" * 64))
    if fault == "future-time":
        prepared = replace(
            prepared, proof=replace(proof, observed_at=datetime(2030, 1, 1, tzinfo=UTC))
        )
        authority.value = prepared
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))
    store = module.MetricProfileStore(authority)
    store._clock = AsyncMock(side_effect=AssertionError("不得锁目录或持久写"))
    with pytest.raises(OrbitError):
        asyncio.run(store.publish(database, current, prepared, 0, str(uuid4())))
    store._clock.assert_not_awaited()
    assert not database.writes


@pytest.mark.parametrize("binding", [False, True])
def test_revoke_updates_only_state_and_keeps_immutable_payload(monkeypatch, binding):
    current, database = context(), Database()
    identifier = str(uuid4())
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))

    async def read(session, sql, params):
        if "clock" in sql:
            return {"revision": 5}
        if "head" in sql:
            return {"revision": 3, "state": "ENABLED"}
        if "adapter" in sql:
            return {"revoked_at": None}
        raise AssertionError("不能读取其他表")

    monkeypatch.setattr(module, "one", read)
    store = module.MetricProfileStore()
    if binding:
        result = asyncio.run(
            store.revoke_binding(
                database, current, identifier, "version-A", "adapter-A", 3, str(uuid4())
            )
        )
    else:
        result = asyncio.run(store.revoke(database, current, identifier, 3, str(uuid4())))
    assert result["revision"] == 4
    writes = [sql for sql, _ in database.writes]
    assert all("UPDATE orbit_metric_profile_version" not in sql for sql in writes)
    assert all("payload_json=" not in sql and "mapping_json=" not in sql for sql in writes)
    assert sum("INSERT INTO orbit_metric_profile_audit" in sql for sql in writes) == 1
    assert sum("INSERT INTO orbit_metric_profile_outbox" in sql for sql in writes) == 1


def test_meta_read_uses_source_then_registry_then_exact_head_and_rejects_revoked_config(
    monkeypatch,
):
    profile, proof, prepared = fixture("META")
    current, database = context(), Database()
    events = []
    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=current))
    monkeypatch.setattr(module, "require_system_access", AsyncMock(return_value=current))

    async def read(session, sql, params):
        if "FROM orbit_user_scope" in sql:
            return {
                key: getattr(current, key)
                for key in ("actor_id", "tenant_id", "data_role", "subject_id", "team_id")
            }
        if "FROM orbit_metric_profile_version" in sql and "JOIN" not in sql:
            events.append("source-metadata")
            return {
                "source": "META",
                "source_config_id": proof.source_config_id,
                "source_config_revision": 1,
                "source_proof_json": module.proof_document(proof),
                "source_connection_id": None,
                "source_connection_revision": None,
            }
        if "orbit_system_configuration" in sql:
            events.append("source-config-lock")
            return {"revision": 2, "enabled": True, "section": "META_BM"}
        raise AssertionError("来源变更时不能读取目录/头")

    monkeypatch.setattr(module, "one", read)
    with pytest.raises(OrbitError) as error:
        asyncio.run(
            module.MetricProfileStore().lock_exact(
                database,
                current,
                current,
                profile["id"],
                profile["version"],
                prepared.adapter_version,
            )
        )
    assert error.value.code == "METRIC_PROFILE_SOURCE_CHANGED"
    assert events == ["source-metadata", "source-config-lock"]


def test_candidate_original_filters_are_not_silently_accepted():
    with pytest.raises(TypeError):
        module.MetricProfileStore().candidate_page(
            Database(), context(), status="ANY_GUESSED_STATE"
        )


@pytest.mark.parametrize(
    "field", ["missing", "actor_id", "tenant_id", "data_role", "subject_id", "team_id"]
)
def test_target_owner_is_checked_against_live_identity_without_any_extra_menu_action(
    monkeypatch, field
):
    current = context()
    owner_context = replace(current, actor_id=2, subject_id=str(uuid4()))
    record = {
        key: getattr(owner_context, key)
        for key in ("actor_id", "tenant_id", "data_role", "subject_id", "team_id")
    }
    if field == "missing":
        record = None
    elif field == "actor_id":
        record[field] = 3
    elif field == "data_role":
        record[field] = "USER"
    else:
        record[field] = str(uuid4())
    queries = []

    async def live(session, sql, params):
        queries.append(sql)
        assert params == {"owner": 2}
        return record

    monkeypatch.setattr(module, "one", live)
    with pytest.raises(OrbitError) as error:
        asyncio.run(module.MetricProfileStore()._current_owner(Database(), owner_context))
    assert error.value.code == "METRIC_PROFILE_UNAVAILABLE"
    sql = queries[0]
    for guard in (
        "u.status='0'",
        "u.del_flag='0'",
        "i.auth_version>=1",
        "t.enabled=1",
        "b.enabled=1",
        "b.invited=0",
        "bt.enabled=1",
        "s.enabled=1",
        "FOR SHARE",
    ):
        assert guard in sql
    assert "sys_role" not in sql and "sys_menu" not in sql


def test_target_with_no_launch_read_is_allowed_when_current_identity_matches(monkeypatch):
    owner_context = context()
    row = {
        key: getattr(owner_context, key)
        for key in ("actor_id", "tenant_id", "data_role", "subject_id", "team_id")
    }
    monkeypatch.setattr(module, "one", AsyncMock(return_value=row))
    permission = AsyncMock(side_effect=AssertionError("目标不能额外要求任何菜单动作"))
    monkeypatch.setattr(module, "require_business_access", permission)
    asyncio.run(module.MetricProfileStore()._current_owner(Database(), owner_context))
    permission.assert_not_awaited()


def test_launch_create_is_rechecked_as_exact_caller_action_without_read_substitution(monkeypatch):
    current = context()
    authorize = AsyncMock(return_value=current)
    monkeypatch.setattr(module, "require_business_access", authorize)
    monkeypatch.setattr(
        module, "one", AsyncMock(side_effect=OrbitError(404, "OWNER_CHECK_SENTINEL", "定点结束"))
    )
    with pytest.raises(OrbitError) as error:
        asyncio.run(
            module.MetricProfileStore().lock_exact(
                Database(),
                current,
                current,
                str(uuid4()),
                "explicit",
                "adapter",
                permission="launch.create",
            )
        )
    assert error.value.code == "OWNER_CHECK_SENTINEL"
    assert authorize.await_count == 1
    assert authorize.await_args.args[1:] == (
        current.actor_id,
        "launch",
        "launch.create",
    )


def test_candidate_sql_has_exact_hash_and_append_only_guards():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "docs/orbit/sql-drafts/040_metric_profile_registry_candidate.sql"
    ).read_text(encoding="utf-8")
    assert source.count("CREATE TABLE ") == 6 and source.count("CREATE TRIGGER ") == 6
    for name in (
        "metric_version_immutable_update",
        "metric_version_immutable_delete",
        "metric_adapter_immutable_update",
        "metric_adapter_immutable_delete",
        "metric_audit_immutable_update",
        "metric_audit_immutable_delete",
    ):
        assert "CREATE TRIGGER " + name + " BEFORE " in source
    for field in ("payload_hash", "source_sha256", "profile_hash", "mapping_hash"):
        assert (
            "CHAR_LENGTH(" + field + ")=64 AND NOT REGEXP_LIKE(" + field + ",'[^0-9a-f]','c')"
            in source
        )
        assert field + " CHAR(64) NOT NULL" in source
    assert source.count("ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs") == 6
    assert source.count("COLLATE utf8mb4_bin") == 4
    assert "CAST(" not in source and "SHA2(" not in source
