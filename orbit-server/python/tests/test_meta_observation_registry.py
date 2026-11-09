"""原始观察登记纯协议；SQL/session替身不是实际MySQL原子性或Meta权限验收。"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

import orbit_api.meta_bound_observation as binding
import orbit_api.meta_observation_registry as module
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import (
    MetaAccountObservation,
    MetaIdentityObservation,
    MetaLaunchObservation,
    MetaLaunchReadConfiguration,
)


def uid():
    return str(uuid4())


def bound_fixture(name="页" * 4096, *, at=None):
    account_id, subject, team, tenant = uid(), uid(), uid(), uid()
    now = at or datetime(2026, 11, 9, 8, tzinfo=UTC)
    config = MetaLaunchReadConfiguration(uid(), 7, "00123", "v23.0", "never-persist-this-token")
    source = binding.MetaSourceSnapshot(
        tenant,
        23,
        subject,
        team,
        "USER",
        9,
        "accounts.sync",
        11,
        now,
        (binding.MetaAccountBinding(account_id, 5, "001", subject, team),),
        config,
        "",
        binding._ISSUER,
    )
    source = replace(source, binding_sha256=binding.binding_hash(source))
    data = {
        "name": None,
        "currency": "USD",
        "timezone_name": "UTC",
        "account_status": 0,
        "capabilities": ["RAW_ONLY"],
        "user_tasks": None,
    }
    resource = MetaIdentityObservation("PAGE", "009", name)
    unknown = ["name", "user_tasks"] + (["PAGE:009:name"] if name is None else [])
    account = MetaAccountObservation(
        "001", ("owned_ad_accounts",), canonical(data).encode(), (resource,), tuple(sorted(unknown))
    )
    observed = MetaLaunchObservation(
        config.source_config_id, 7, "00123", "v23.0", now, now, (account,), "", 6, 20000
    )
    # 独立完整JSON对照，不用待测流式根函数建立expected。
    document = {
        "source_config_id": config.source_config_id,
        "source_config_revision": 7,
        "business_id": "00123",
        "api_version": "v23.0",
        "started_at": now.isoformat(),
        "observed_at": now.isoformat(),
        "accounts": [
            dict(
                external_id="001",
                bm_edges=account.bm_edges,
                metadata=data,
                resources=[resource.__dict__],
                unknown_fields=account.unknown_fields,
            )
        ],
    }
    observed = replace(observed, evidence_sha256=module.digest(document))
    return binding.BoundMetaObservation(
        source, observed, module.digest([source.binding_sha256, observed.evidence_sha256])
    )


class Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.value)

    def first(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, prepared):
        self.prepared, self.calls, self.events = prepared, [], []
        source = prepared.bound.source
        self.context = BusinessContext(
            source.actor_id, source.tenant_id, source.data_role, source.subject_id, source.team_id
        )
        self.accounts = [
            dict(
                id=row.account_id,
                revision=row.revision,
                external_id=row.external_id,
                owner_user_id=row.owner_user_id,
                owner_team_id=row.owner_team_id,
                unbound_at=None,
            )
            for row in prepared.accounts
        ]
        self.configs = [
            dict(
                id=source.configuration.source_config_id,
                revision=7,
                settings_json={"businessId": "00123", "graphVersion": "v23.0"},
                secrets_json={"accessToken": "encrypted"},
            )
        ]
        self.ledger_results, self.reservation = [], None
        self.clock, self.auth_version, self.active = 11, 9, True
        self.head = None
        self.now = datetime(2026, 11, 9, 9)
        self.managed = []
        self.raw_accounts = [dict(row.__dict__) for row in prepared.accounts]
        self.raw_resources = [dict(row.__dict__) for row in prepared.resources]

    def in_transaction(self):
        return self.active

    async def execute(self, statement, values=None):
        sql = str(statement)
        self.calls.append((sql, values))
        if sql.startswith("SELECT") and "orbit_meta_raw_idempotency" in sql:
            self.events.append("ledger_current" if "FOR UPDATE" in sql else "ledger_probe")
            return Result(self.ledger_results.pop(0) if self.ledger_results else self.reservation)
        if sql.startswith("SELECT") and "orbit_system_configuration" in sql:
            self.events.append("sources")
            assert "ORDER BY id LIMIT 2 FOR SHARE" in sql
            return Result(self.configs)
        if sql.startswith("SELECT") and "orbit_ad_account" in sql:
            self.events.append("accounts")
            assert "FOR SHARE" in sql
            return Result(self.accounts)
        if sql.startswith("SELECT account_id FROM orbit_meta_raw_account"):
            return Result([{"account_id": row["account_id"]} for row in self.raw_accounts])
        if sql.startswith("SELECT") and "FROM orbit_meta_raw_account" in sql:
            return Result(self.raw_accounts)
        if sql.startswith("SELECT") and "FROM orbit_meta_raw_resource" in sql:
            after = (values["after_account"], values["after_kind"], values["after_external"])
            return Result(
                [
                    row
                    for row in self.raw_resources
                    if (row["account_id"], row["kind"], row["external_id"]) > after
                ][:200]
            )
        if sql.startswith("SELECT") and "orbit_meta_raw_head" in sql:
            return Result(self.head)
        if "SELECT auth_version" in sql:
            return Result(self.auth_version)
        if sql == "SELECT UTC_TIMESTAMP(6)":
            return Result(self.now)
        if sql.startswith("INSERT INTO orbit_meta_raw_idempotency"):
            if self.reservation is None:
                self.reservation = dict(
                    intent_hash=values["intent"],
                    registry_id=values["registry"],
                    receipt_json=json.loads(values["receipt"]),
                )
            return Result(None)
        if sql.startswith("INSERT INTO orbit_meta_raw_"):
            assert "never-persist-this-token" not in repr(values)
            return Result(None)
        raise AssertionError("未知或非原始登记SQL")


@pytest.fixture
def prepared():
    return module.MetaObservationRegistry().prepare(bound_fixture())


def install_context(monkeypatch, session):
    async def access(selected, actor, menu, permission):
        assert selected is session and (actor, menu, permission) == (
            23,
            "accounts",
            "accounts.sync",
        )
        session.events.append("authorize")
        return session.context

    async def clock(selected, current):
        assert selected is session
        session.events.append("clock_dueguard")
        return session.clock

    async def managed(selected, current):
        assert selected is session
        session.events.append("managed_current_lock")
        return session.managed

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "clock", clock)
    monkeypatch.setattr(module, "managed_teams", managed)


def successful_ledger(session):
    prepared = session.prepared
    identifier = uid()
    session.head = dict(
        bound_sha256=prepared.bound.binding_sha256,
        intent_hash=prepared.intent_hash,
        account_count=len(prepared.accounts),
        resource_count=len(prepared.resources),
        observed_at=prepared.bound.observation.observed_at.replace(tzinfo=None),
    )
    return dict(
        intent_hash=prepared.intent_hash,
        registry_id=identifier,
        receipt_json=module.MetaObservationRegistry.receipt(prepared, identifier),
    )


async def register(session, prepared):
    return await module.MetaObservationRegistry().register(
        session, 23, prepared, key="fixed-key-for-raw-observation", request_id=uid()
    )


def test_prepare_full_oracle_and_names_do_not_truncate_or_invent_authority(prepared):
    assert (
        module.stream_digest(prepared.bound.observation)
        == prepared.bound.observation.evidence_sha256
    )
    assert len(prepared.resources[0].name) == 4096
    assert json.loads(prepared.accounts[0].metadata_json)["name"] is None
    assert json.loads(prepared.accounts[0].metadata_json)["account_status"] == 0
    assert "never-persist-this-token" not in repr(prepared)
    assert not prepared.bound.execution_authorized


def test_unknown_resource_name_remains_null():
    prepared = module.MetaObservationRegistry().prepare(bound_fixture(None))
    assert prepared.resources[0].name is None
    assert "PAGE:009:name" in json.loads(prepared.accounts[0].unknown_json)


@pytest.mark.parametrize(
    "part", ["issuer", "binding", "observation", "combined", "source", "resource"]
)
def test_malformed_or_replaced_roots_never_become_prepared(part):
    bound = bound_fixture()
    if part == "issuer":
        bound = replace(bound, source=replace(bound.source, _issuer=object()))
    elif part == "binding":
        bound = replace(bound, source=replace(bound.source, binding_sha256="0" * 64))
    elif part == "observation":
        bound = replace(bound, observation=replace(bound.observation, evidence_sha256="0" * 64))
    elif part == "combined":
        bound = replace(bound, binding_sha256="0" * 64)
    elif part == "source":
        bound = replace(bound, observation=replace(bound.observation, source_config_revision=8))
    else:
        account = bound.observation.accounts[0]
        changed = replace(account.resources[0], name="换内容但保留旧根")
        bound = replace(
            bound,
            observation=replace(
                bound.observation, accounts=(replace(account, resources=(changed,)),)
            ),
        )
    with pytest.raises(OrbitError) as failure:
        module.MetaObservationRegistry().prepare(bound)
    assert failure.value.code == "META_RAW_OBSERVATION_INVALID"


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_count", True),
        ("response_bytes", 0),
        ("request_count", 2501),
        ("response_bytes", module.MAX_BYTES + 1),
        ("observed_at", datetime(2026, 11, 8, tzinfo=UTC)),
        ("observed_at", datetime(2026, 11, 9, 8)),
    ],
)
def test_typed_counts_and_observation_window_invalid_before_sql(field, value):
    bound = bound_fixture()
    with pytest.raises(OrbitError):
        module.MetaObservationRegistry().prepare(
            replace(bound, observation=replace(bound.observation, **{field: value}))
        )


def test_batch_row_and_byte_limits_are_real_not_only_row_count():
    values = [{"x": index} for index in range(201)]
    assert [len(batch) for batch in module.row_batches(values)] == [100, 100, 1]
    rows = [{"x": "中" * 40000} for _ in range(5)]
    batches = list(module.row_batches(rows))
    assert len(batches) == 3
    assert all(
        sum(len(canonical(row).encode()) for row in batch) <= module.BATCH_BYTES
        for batch in batches
    )
    with pytest.raises(OrbitError):
        list(module.row_batches([{"x": "a" * module.BATCH_BYTES}]))


@pytest.mark.asyncio
async def test_new_registration_rechecks_current_source_clock_scope_cas_then_only_raw_tables(
    monkeypatch, prepared
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    result = await register(session, prepared)
    assert (
        result["execution_authorized"] is False
        and result["account_count"] == result["resource_count"] == 1
    )
    assert (
        session.events.index("sources")
        < session.events.index("clock_dueguard")
        < session.events.index("accounts")
    )
    assert session.events.index("managed_current_lock") < session.events.index("accounts")
    inserted = [sql.split("(")[0] for sql, _ in session.calls if sql.startswith("INSERT")]
    assert len(inserted) == 6
    assert all("orbit_meta_raw_" in sql for sql in inserted)
    assert not any(
        sql.startswith("UPDATE orbit_account") or "orbit_account_identity" in sql
        for sql, _ in session.calls
    )
    assert not any("COMMIT" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["clock", "account_revision", "source_revision", "source_disabled", "auth", "owner", "unbound"],
)
async def test_new_key_fails_closed_on_final_cas_changes(monkeypatch, prepared, change):
    session = Session(prepared)
    install_context(monkeypatch, session)
    if change == "clock":
        session.clock += 1
    if change == "account_revision":
        session.accounts[0]["revision"] += 1
    if change == "source_revision":
        session.configs[0]["revision"] += 1
    if change == "source_disabled":
        session.configs = []
    if change == "auth":
        session.auth_version += 1
    if change == "owner":
        session.accounts[0]["owner_team_id"] = uid()
    if change == "unbound":
        session.accounts[0]["unbound_at"] = session.now
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "META_RAW_SOURCE_CHANGED"
    assert not any(sql.startswith("INSERT INTO orbit_meta_raw_head") for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_successful_key_does_not_rebind_when_source_clock_auth_versions_change(
    monkeypatch, prepared
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [old]
    session.configs, session.clock, session.auth_version = [], 300, 50
    session.accounts[0]["revision"] = 20
    assert await register(session, prepared) == old["receipt_json"]
    assert "sources" not in session.events
    assert not any(sql.startswith("INSERT") for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_source_cas_failure_after_probe_miss_rechecks_concurrent_success(
    monkeypatch, prepared
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [None, old]
    session.configs = []
    assert await register(session, prepared) == old["receipt_json"]


@pytest.mark.asyncio
async def test_successful_key_still_requires_current_scope_not_old_rr_managed_view(
    monkeypatch, prepared
):
    session = Session(prepared)
    session.context = replace(session.context, data_role="TEAM_ADMIN", subject_id=uid())
    session.ledger_results = [successful_ledger(session)]
    install_context(monkeypatch, session)
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert (failure.value.status, failure.value.code) == (404, "NOT_FOUND")
    assert "managed_current_lock" in session.events


@pytest.mark.asyncio
async def test_same_key_different_root_conflicts_after_current_scope(monkeypatch, prepared):
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session) | {"intent_hash": "0" * 64}
    session.ledger_results = [old]
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "IDEMPOTENCY_CONFLICT" and "accounts" in session.events


@pytest.mark.asyncio
async def test_corrupt_successful_receipt_or_missing_head_is_not_returned(monkeypatch, prepared):
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [old]
    session.head = None
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "META_RAW_OBSERVATION_INVALID"


@pytest.mark.asyncio
async def test_scope_or_permission_revoked_even_successful_ledger_is_denied(monkeypatch, prepared):
    session = Session(prepared)

    async def denied(*args):
        raise OrbitError(403, "PERMISSION_DENIED", "同步已撤销")

    monkeypatch.setattr(module, "require_business_access", denied)
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.status == 403 and session.calls == []


@pytest.mark.asyncio
async def test_external_transaction_and_untampered_prepared_rows_required(monkeypatch, prepared):
    session = Session(prepared)
    session.active = False
    with pytest.raises(ValueError):
        await register(session, prepared)
    session.active = True
    altered = replace(prepared, resources=(replace(prepared.resources[0], name="误改"),))
    with pytest.raises(OrbitError):
        await register(session, altered)
    assert session.calls == []


def test_candidate_has_six_tables_complete_nonnullable_ledger_and_no_forward_fk_cycle():
    path = (
        Path(__file__).resolve().parents[2]
        / "docs/orbit/sql-drafts/045_meta_observation_registry_candidate.sql"
    )
    sql = path.read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE ") == 6
    ledger = sql.split("CREATE TABLE orbit_meta_raw_idempotency (")[1].split("CREATE TABLE")[0]
    assert "registry_id CHAR(36) NOT NULL" in ledger and "receipt_json JSON NOT NULL" in ledger
    assert "REFERENCES orbit_meta_raw_head" not in ledger
    assert "VARCHAR(4096) NULL" in sql
    assert "DATETIME(3)" not in sql and "DATETIME(6)" in sql
    assert sql.count("CREATE TRIGGER ") == 12
    assert "(NEW.receipt_json<=>OLD.receipt_json)" in sql
    assert "(OLD.state='PENDING' AND NEW.state='DONE')" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("microseconds", [123499, 123500, 999999])
async def test_original_microsecond_proof_and_receipt_roundtrip_never_rounds_sql_precision(
    monkeypatch, microseconds
):
    at = datetime(2026, 11, 9, 8, 59, 59, microseconds, tzinfo=UTC)
    prepared = module.MetaObservationRegistry().prepare(bound_fixture(at=at))
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [old]
    receipt = await register(session, prepared)
    assert receipt["observed_at"] == at.isoformat().replace("+00:00", "Z")
    assert session.head["observed_at"].microsecond == microseconds
    assert prepared.bound.observation.observed_at + timedelta(microseconds=1) > at


@pytest.mark.asyncio
@pytest.mark.parametrize("microseconds", [123499, 123500, 999999])
async def test_new_registration_writes_original_microseconds_as_datetime_six(
    monkeypatch, microseconds
):
    at = datetime(2026, 11, 9, 8, 59, 59, microseconds, tzinfo=UTC)
    prepared = module.MetaObservationRegistry().prepare(bound_fixture(at=at))
    session = Session(prepared)
    install_context(monkeypatch, session)
    await register(session, prepared)
    head = next(
        values for sql, values in session.calls if sql.startswith("INSERT INTO orbit_meta_raw_head")
    )
    assert head["captured"] == head["started"] == head["observed"] == at.replace(tzinfo=None)


def test_known_token_returned_as_resource_name_is_rejected_not_persisted_or_redacted():
    with pytest.raises(OrbitError) as failure:
        module.MetaObservationRegistry().prepare(bound_fixture("never-persist-this-token"))
    assert failure.value.code == "META_RAW_OBSERVATION_INVALID"
    assert "never-persist-this-token" not in str(failure.value)


@pytest.mark.asyncio
async def test_current_dueguard_applies_to_successful_historical_receipt(monkeypatch, prepared):
    session = Session(prepared)
    install_context(monkeypatch, session)
    session.ledger_results = [successful_ledger(session)]

    async def due(*args):
        raise OrbitError(503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "到期投影未追平")

    monkeypatch.setattr(module, "clock", due)
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
    assert not any(sql.startswith("INSERT") for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_complete_ledger_reservation_is_used_without_null_building_state(
    monkeypatch, prepared
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    await register(session, prepared)
    sql, values = next(
        (sql, values)
        for sql, values in session.calls
        if sql.startswith("INSERT INTO orbit_meta_raw_idempotency")
    )
    assert "ON DUPLICATE KEY UPDATE key_hash=key_hash" in sql
    assert (
        values["registry"]
        and values["intent"]
        and json.loads(values["receipt"])["execution_authorized"] is False
    )
    assert all(
        len(batch) <= 100
        and sum(len(canonical(row).encode()) for row in batch) <= module.BATCH_BYTES
        for _, batch in session.calls
        if isinstance(batch, list)
    )
    reserve_at = next(
        index
        for index, (sql, _) in enumerate(session.calls)
        if sql.startswith("INSERT INTO orbit_meta_raw_idempotency")
    )
    locked_keys = [
        index
        for index, (sql, _) in enumerate(session.calls)
        if "FROM orbit_meta_raw_idempotency" in sql and "FOR UPDATE" in sql
    ]
    assert locked_keys and all(index > reserve_at for index in locked_keys)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage", ["missing_account", "metadata", "missing_resource", "resource", "extra_resource"]
)
async def test_historical_replay_checks_actual_details_even_if_head_and_stored_hashes_look_valid(
    monkeypatch, prepared, damage
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    session.ledger_results = [successful_ledger(session)]
    if damage == "missing_account":
        session.raw_accounts = []
    elif damage == "metadata":
        value = json.loads(session.raw_accounts[0]["metadata_json"])
        value["name"] = "损坏正文保留旧hash"
        session.raw_accounts[0]["metadata_json"] = json.dumps(value)
    elif damage == "missing_resource":
        session.raw_resources = []
    elif damage == "resource":
        session.raw_resources[0]["name"] = "损坏资源保留旧hash"
    else:
        session.raw_resources.append(session.raw_resources[0] | {"external_id": "999"})
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "META_RAW_OBSERVATION_INVALID"


@pytest.mark.asyncio
async def test_mysql_json_presentation_whitespace_does_not_invalidate_canonical_details(
    monkeypatch, prepared
):
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [old]
    for row in session.raw_accounts:
        for field in ("metadata_json", "edges_json", "unknown_json"):
            row[field] = json.dumps(json.loads(row[field]), ensure_ascii=False, indent=2)
    assert await register(session, prepared) == old["receipt_json"]


@pytest.mark.asyncio
async def test_replay_verifies_every_resource_across_keyset_pages_not_a_sample(monkeypatch):
    original = bound_fixture("页")
    observed = original.observation
    account = observed.accounts[0]
    resources = tuple(MetaIdentityObservation("PAGE", f"{index:06d}", "页") for index in range(201))
    account = replace(account, resources=resources)
    observed = replace(observed, accounts=(account,))
    document = dict(
        source_config_id=observed.source_config_id,
        source_config_revision=observed.source_config_revision,
        business_id=observed.business_id,
        api_version=observed.api_version,
        started_at=observed.started_at.isoformat(),
        observed_at=observed.observed_at.isoformat(),
        accounts=[
            dict(
                external_id=account.external_id,
                bm_edges=account.bm_edges,
                metadata=json.loads(account.metadata_json),
                resources=[row.__dict__ for row in resources],
                unknown_fields=account.unknown_fields,
            )
        ],
    )
    observed = replace(observed, evidence_sha256=module.digest(document))
    bound = replace(
        original,
        observation=observed,
        binding_sha256=module.digest([original.source.binding_sha256, observed.evidence_sha256]),
    )
    prepared = module.MetaObservationRegistry().prepare(bound)
    session = Session(prepared)
    install_context(monkeypatch, session)
    old = successful_ledger(session)
    session.ledger_results = [old]
    assert await register(session, prepared) == old["receipt_json"]
    queries = [values for sql, values in session.calls if "FROM orbit_meta_raw_resource" in sql]
    assert len(queries) == 2 and queries[1]["after_external"] == "000199"
    session.calls.clear()
    session.ledger_results = [old]
    session.raw_resources[-1]["name"] = "第二页最后一项损坏"
    with pytest.raises(OrbitError) as failure:
        await register(session, prepared)
    assert failure.value.code == "META_RAW_OBSERVATION_INVALID"
