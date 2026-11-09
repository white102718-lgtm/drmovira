"""C1纯合同/事务边界；Transport是受控协议，不代表真实Meta或SQL验收。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_meta_identity_facts_observation import Transport, selected
from test_meta_identity_facts_observation import bound as bound

import orbit_api.identity_publication_store as module
import orbit_api.meta_identity_principal_binding as principal
from orbit_api.errors import OrbitError
from orbit_api.meta_observation_registry import digest


class Authority(module.IdentityCapabilityAuthority):
    kind = "ISOLATED_TEST"

    def __init__(self, qualification):
        self.qualification = qualification
        self.captures = 0

    async def capture(self, match, account_id):
        self.captures += 1
        return self.qualification

    async def revalidate(self, session, current, prepared):
        raise AssertionError("纯合同测试不能假装实际数据库来源复核")


@pytest.fixture
async def packet(bound):
    source = principal.PrincipalBindingSource(
        bound, "00042", (), bound.source.captured_at, "", principal._ISSUER
    )
    source = replace(source, source_sha256=principal.source_hash(source))
    match = await principal.observe_identity_principal(
        source, [selected(bound)], transport=Transport()
    )
    account_id = bound.source.accounts[0].account_id
    q = module.IdentityQualification(
        str(uuid4()),
        3,
        "b" * 64,
        "real-version-text",
        bound.binding_sha256,
        match.evidence_sha256,
        account_id,
        tuple(
            module.IdentityDecision(row.kind, row.external_id, False, "NOT_VERIFIED")
            for row in bound.observation.accounts[0].resources
        ),
        max(match.facts.observed_at, bound.observation.observed_at),
    )
    return match, q


async def prepare(packet, **changes):
    match, q = packet
    authority = Authority(replace(q, **changes))
    return await module.IdentityPublicationStore(authority).prepare(
        match, q.account_id, registry_id=str(uuid4()), expected_revision=0
    )


async def test_no_authority_fails_before_consuming_observation(packet):
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationStore().prepare(
            None, None, registry_id=None, expected_revision=0
        )
    assert (failure.value.status, failure.value.code) == (
        503,
        "IDENTITY_PUBLICATION_AUTHORITY_UNAVAILABLE",
    )


async def test_full_inventory_not_selected_subset_and_exact_original_schema(packet):
    prepared = await prepare(packet)
    value = module.IdentityPublicationStore.check(prepared)
    assert set(value) == {"account_id", "resources", "capability_version", "observed_at"}
    assert len(prepared.match.facts.resources) == 1
    assert len(value["resources"]) == 3
    assert all(
        set(r) == {"kind", "external_id", "name", "usable", "reason_code"}
        for r in value["resources"]
    )
    assert all(r["usable"] is False for r in value["resources"])
    assert prepared.raw.bound is prepared.match.source.bound
    assert "fixture-hidden-secret" not in repr(prepared)
    assert "fixture-hidden-secret" not in prepared.payload_json


@pytest.mark.parametrize("microsecond", [123499, 123500, 999999, 0])
def test_floor_millisecond_never_rounds_or_crosses_second(microsecond):
    value = datetime(2026, 11, 9, 23, 59, 59, microsecond, tzinfo=UTC)
    projected = module.floor_ms(value)
    assert projected.microsecond == microsecond // 1000 * 1000
    assert projected.second == 59 and projected.day == 9
    assert projected <= value < projected + timedelta(milliseconds=1)


@pytest.mark.parametrize("value", [datetime(2026, 11, 9), "2026-11-09T00:00:00Z", None])
def test_projection_requires_original_aware_utc(value):
    with pytest.raises(OrbitError):
        module.floor_ms(value)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "bool-int"])
async def test_complete_decision_set_is_mandatory(packet, mutation):
    match, q = packet
    decisions = q.decisions
    if mutation == "missing":
        decisions = decisions[:-1]
    elif mutation == "duplicate":
        decisions = decisions[:-1] + decisions[:1]
    elif mutation == "foreign":
        decisions = decisions[:-1] + (replace(decisions[-1], external_id="00009999"),)
    else:
        decisions = (replace(decisions[0], usable=1),) + decisions[1:]
    with pytest.raises(OrbitError) as failure:
        await prepare((match, q), decisions=decisions)
    assert failure.value.status == 503


@pytest.mark.parametrize(
    "change",
    [
        {"raw_bound_hash": "0" * 64},
        {"principal_hash": "0" * 64},
        {"release_source_hash": "arbitrary"},
        {"release_revision": True},
        {"capability_version": ""},
        {"observed_at": datetime(2000, 1, 1, tzinfo=UTC)},
    ],
)
async def test_unbound_or_invalid_qualification_fails_closed(packet, change):
    with pytest.raises(OrbitError):
        await prepare(packet, **change)


async def test_immutable_prepared_rejects_mutation_and_does_not_trust_retained_hash(packet):
    prepared = await prepare(packet)
    for altered in (
        replace(prepared, payload_json=prepared.payload_json.replace("NOT_VERIFIED", "GRANTED")),
        replace(prepared, intent_hash="0" * 64),
        replace(prepared, expected_revision=2),
        replace(prepared, _issuer=object()),
    ):
        with pytest.raises(OrbitError):
            module.IdentityPublicationStore.check(altered)
    facts = replace(prepared.match.facts, principal_reason="altered-body-same-hash")
    with pytest.raises(OrbitError):
        module.check_match(replace(prepared.match, facts=facts))


async def test_microseconds_and_independent_release_are_inside_full_intent(packet):
    prepared = await prepare(packet)
    match, q = packet
    document = module.intent_document(
        match, q, prepared.registry_id, 0, module.json_value(prepared.payload_json)
    )
    assert document["projection_version"] == "UTC_FLOOR_MS_V1"
    assert document["raw_observed_at"] == q.observed_at.isoformat()
    assert digest(document) == prepared.intent_hash
    for change in (
        {"observed_at": q.observed_at + timedelta(microseconds=1)},
        {"release_id": str(uuid4())},
        {"release_revision": 4},
    ):
        altered = replace(q, **change)
        _, value = module.publication_payload(match, altered)
        assert (
            digest(module.intent_document(match, altered, prepared.registry_id, 0, value))
            != prepared.intent_hash
        )


def release():
    return dict(
        revoked_at=None,
        revision=3,
        capability_version="v",
        source_hash="b" * 64,
        source_config_id="config",
        source_config_revision=7,
        business_id="00123",
        graph_version="v25.0",
        action_scope="ACCOUNT_IDENTITIES_READ",
        issuer="actual-issuer",
        source_kind="META_AUTHORITY",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"revoked_at": datetime.now(UTC)},
        {"revision": 4},
        {"source_hash": "0" * 64},
        {"source_kind": "ISOLATED_PROTOCOL"},
        {"action_scope": "ADS_WRITE"},
        {"issuer": ""},
        {"source_config_revision": 8},
        {"graph_version": "v26.0"},
    ],
)
def test_trusted_label_cannot_replace_actual_release(change):
    with pytest.raises(OrbitError) as failure:
        module.valid_release(
            release() | change,
            {"id": "config", "revision": 7},
            kind="TRUSTED",
            version="v",
            revision=3,
            source_hash="b" * 64,
            business="00123",
            graph="v25.0",
        )
    assert failure.value.code == "IDENTITY_PUBLICATION_RELEASE_UNAVAILABLE"


def test_valid_independent_release_and_isolated_kind_are_separate():
    for kind, source in (("TRUSTED", "META_AUTHORITY"), ("ISOLATED_TEST", "ISOLATED_PROTOCOL")):
        module.valid_release(
            release() | {"source_kind": source},
            {"id": "config", "revision": 7},
            kind=kind,
            version="v",
            revision=3,
            source_hash="b" * 64,
            business="00123",
            graph="v25.0",
        )


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("example.com", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_preview"),
    ],
)
async def test_isolated_provider_never_works_on_preview_or_external_db(host, port, database):
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            url=SimpleNamespace(host=host, port=port, database=database)
        )
    )
    with pytest.raises(OrbitError):
        await module.authority_database(session, "ISOLATED_TEST")


@pytest.mark.parametrize("connection_bound", [False, True])
@pytest.mark.parametrize("database_matches", [False, True])
async def test_isolated_database_guard_accepts_real_bind_shape_but_always_checks_selected_database(
    connection_bound, database_matches
):
    database = "orbit_py_it_" + "a" * 32
    engine = SimpleNamespace(url=SimpleNamespace(host="127.0.0.1", port=13306, database=database))
    bind = SimpleNamespace(engine=engine) if connection_bound else engine
    queries = []

    async def execute(statement):
        queries.append(str(statement))
        return SimpleNamespace(scalar_one=lambda: database if database_matches else "orbit_preview")

    session = SimpleNamespace(get_bind=lambda: bind, execute=execute)
    if database_matches:
        await module.authority_database(session, "ISOLATED_TEST")
    else:
        with pytest.raises(OrbitError):
            await module.authority_database(session, "ISOLATED_TEST")
    assert queries == ["SELECT DATABASE()"]


async def test_register_requires_outer_transaction_before_sql(packet):
    prepared = await prepare(packet)
    with pytest.raises(ValueError):
        await module.IdentityPublicationStore().register(
            SimpleNamespace(in_transaction=lambda: False),
            23,
            prepared,
            key="immutable-key-123456",
            request_id=str(uuid4()),
        )


async def test_reboot_probe_requires_current_action_before_looking_up_key(monkeypatch):
    events = []

    async def access(*args):
        events.append("current-sync")
        raise OrbitError(403, "PERMISSION_DENIED", "动作已撤销")

    async def one(*args):
        raise AssertionError("不得在当前授权前探测成功键")

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "one", one)
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationStore().successful_replay(
            SimpleNamespace(in_transaction=lambda: True),
            23,
            key="immutable-key-123456",
            intent_hash="b" * 64,
        )
    assert failure.value.status == 403 and events == ["current-sync"]
