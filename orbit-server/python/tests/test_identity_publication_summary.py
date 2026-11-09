"""055完整性/MAC及批量协议纯测；不计真实SQL、Meta或百万资源容量。"""

import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

import pytest

import orbit_api.identity_publication_summary as module
from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError


def uid():
    return str(uuid4())


def cipher(active="old", *, old=True):
    keys = {"new": base64.b64encode(b"n" * 32).decode()}
    if old:
        keys["old"] = base64.b64encode(b"o" * 32).decode()
    return CredentialCipher(active, keys)


@pytest.fixture
def claim():
    result = {k: "a" * 64 for k in module.HASH_FIELDS}
    result.update({k: uid() for k in module.UUID_FIELDS})
    result.update({k: 1 for k in module.NUMBER_FIELDS})
    result.update(
        resource_count=0,
        capability_version="original-version",
        principal_id="0007",
        observed_at=datetime(2026, 11, 9, 0, 0, 0, 123000, tzinfo=UTC),
        raw_observed_at=datetime(2026, 11, 9, 0, 0, 0, 123500, tzinfo=UTC),
        raw_credential_expires_at=None,
        authority_kind="TRUSTED",
        projection_version=module.PROJECTION,
        key_id="old",
    )
    return result


def sign(value, key=None):
    result = deepcopy(value)
    result["mac"] = (key or cipher()).application_mac(
        module.PURPOSE, canonical(module.seal_claims(value)).encode(), value["key_id"]
    )
    return result


def test_original_microseconds_and_explicit_floor_remain_distinct(claim):
    first = module.seal_claims(claim)
    assert first["raw_observed_at"].endswith(".123500Z")
    assert first["observed_at"].endswith(".123Z")
    altered = deepcopy(claim)
    altered["raw_observed_at"] = altered["raw_observed_at"].replace(microsecond=123499)
    assert module.seal_claims(altered) != first
    assert module.seal_claims(altered)["observed_at"] == first["observed_at"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revision", True),
        ("revision", 0),
        ("account_revision", 9007199254740992),
        ("resource_count", True),
        ("resource_count", -1),
        ("resource_count", 5001),
        ("capability_version", ""),
        ("capability_version", "x" * 65),
        ("capability_version", "\ud800"),
        ("principal_id", "7x"),
        ("key_id", "new/key"),
        ("payload_hash", "A" * 64),
        ("authority_kind", "READ_VERIFIED"),
        ("projection_version", "ROUND_MS"),
    ],
)
def test_typed_claim_bounds_reject_untrusted_variants(claim, field, value):
    claim[field] = value
    with pytest.raises(OrbitError) as caught:
        module.seal_claims(claim)
    assert caught.value.code == "IDENTITY_SUMMARY_INVALID"


def test_rounded_projection_and_invalid_expiry_are_not_signable(claim):
    claim["observed_at"] += timedelta(milliseconds=1)
    with pytest.raises(OrbitError):
        module.seal_claims(claim)
    claim["observed_at"] -= timedelta(milliseconds=1)
    claim["raw_credential_expires_at"] = claim["raw_observed_at"]
    with pytest.raises(OrbitError):
        module.seal_claims(claim)


def test_explicit_old_key_verifies_after_rotation_but_not_retirement(claim):
    sealed = sign(claim)
    assert module.check_mac(cipher("new"), sealed)
    assert not module.check_mac(cipher("new", old=False), sealed)
    assert not module.check_mac(None, sealed)
    assert sealed["key_id"] == "old"  # 验证不会替换key或重新签旧回执。


@pytest.mark.parametrize("field", module.CLAIM_FIELDS)
def test_every_source_binding_is_mac_authenticated(claim, field):
    sealed = sign(claim)
    if field in module.UUID_FIELDS:
        sealed[field] = uid()
    elif field in module.HASH_FIELDS:
        sealed[field] = "b" * 64
    elif field in module.NUMBER_FIELDS or field == "resource_count":
        sealed[field] += 1
    elif field == "raw_credential_expires_at":
        sealed[field] = claim["raw_observed_at"] + timedelta(days=1)
    elif field in {"observed_at", "raw_observed_at"}:
        sealed[field] += timedelta(seconds=1)
    elif field == "authority_kind":
        sealed[field] = "ISOLATED_TEST"
    else:
        sealed[field] += "x"
    assert not module.check_mac(cipher(), sealed)


@pytest.mark.parametrize("count", [0, 5000])
def test_valid_complete_inventory_extremes_are_signable(claim, count):
    claim["resource_count"] = count
    assert module.check_mac(cipher(), sign(claim))


@pytest.mark.parametrize("field", module.CLAIM_FIELDS)
def test_current_comparison_rejects_even_newly_signed_different_binding(claim, field):
    altered = deepcopy(claim)
    if field in module.UUID_FIELDS:
        altered[field] = uid()
    elif field in module.HASH_FIELDS:
        altered[field] = "b" * 64
    elif field in module.NUMBER_FIELDS or field == "resource_count":
        altered[field] += 1
    elif field == "raw_credential_expires_at":
        altered[field] = claim["raw_observed_at"] + timedelta(days=1)
    elif field in {"observed_at", "raw_observed_at"}:
        altered["observed_at"] += timedelta(seconds=1)
        altered["raw_observed_at"] += timedelta(seconds=1)
    elif field == "authority_kind":
        altered[field] = "ISOLATED_TEST"
    elif field == "projection_version":
        altered[field] = "INVALID"
        assert not module.matches_current_seal(cipher(), claim, altered)
        return
    elif field == "key_id":
        altered[field] = "new"
    elif field == "principal_id":
        altered[field] = "0008"
    else:
        altered[field] += "x"
    assert not module.matches_current_seal(cipher("new"), claim, sign(altered, cipher("new")))


@pytest.mark.parametrize(
    "value",
    [
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "ABCDEF01-2345-6789-abcd-0123456789ab",
        "{abcdef01-2345-6789-abcd-0123456789ab}",
        "urn:uuid:abcdef01-2345-6789-abcd-0123456789ab",
        "abcdef0123456789abcd0123456789ab",
        "abcdef01-2345-6789-abcd-0123456789ab\n",
        "abcdef01-2345-6789-abcd-0123456789a１",
        None,
        1,
    ],
)
def test_fast_uuid_validation_preserves_original_canonical_rule(claim, value):
    try:
        module.uuid_value(value)
        valid = True
    except (OrbitError, ValueError, TypeError):
        valid = False
    claim["account_id"] = value
    if valid:
        assert module.seal_claims(claim)["account_id"] == value
    else:
        with pytest.raises(OrbitError):
            module.seal_claims(claim)


def test_combined_mac_keeps_rotation_retirement_and_corruption_checks(claim):
    sealed = sign(claim)
    assert module.matches_current_seal(cipher("new"), claim, sealed)
    assert not module.matches_current_seal(cipher("new", old=False), claim, sealed)
    sealed["mac"] = "z" * 43
    assert not module.matches_current_seal(cipher(), claim, sealed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", True),
        ("revision", 1.0),
        ("resource_count", False),
        ("resource_count", 0.0),
        ("account_id", None),
        ("payload_hash", 1),
        ("capability_version", "\ud800"),
        ("observed_at", None),
        ("raw_observed_at", "2026-11-09T00:00:00.123500Z"),
        ("raw_credential_expires_at", False),
    ],
)
def test_current_equality_cannot_inherit_seal_constraints_with_wrong_type(claim, field, value):
    sealed = sign(claim)
    claim[field] = value
    assert not module.matches_current_seal(cipher(), claim, sealed)


@pytest.mark.parametrize("naive", [True, False])
def test_current_timestamp_equality_preserves_original_utc_normalization(claim, naive):
    from datetime import timezone

    sealed = sign(claim)
    for field in ("observed_at", "raw_observed_at"):
        claim[field] = (
            claim[field].replace(tzinfo=None)
            if naive
            else claim[field].astimezone(timezone(timedelta(hours=8)))
        )
    assert module.seal_claims(claim) == module.seal_claims(sealed)
    assert module.matches_current_seal(cipher(), claim, sealed)


def test_summary_unknown_never_uses_zero_as_missing_inventory():
    assert module.unknown() == dict(
        identity_status="UNKNOWN", identity_count=None, identity_observed_at=None
    )
    assert module.unknown("UNSYNCED")["identity_count"] is None


@pytest.mark.parametrize("values", [[uid()] * 2, [uid()] * 201, {}, [None]])
def test_candidate_batch_is_explicit_unique_and_bounded(values):
    with pytest.raises(OrbitError):
        module.identifiers(values)


class Session:
    def __init__(self, at):
        self.tx = object()
        self.sync_session = SimpleNamespace(get_transaction=lambda: self.tx)
        self.now = at

    async def execute(self, statement):
        assert str(statement) == "SELECT UTC_TIMESTAMP(6)"
        return SimpleNamespace(scalar_one=lambda: self.now)


@pytest.fixture
def graph(claim, monkeypatch):
    current = SimpleNamespace(actor_id=7, tenant_id=claim["tenant_id"])
    session = Session(claim["raw_observed_at"] + timedelta(seconds=1))
    account = dict(
        id=claim["account_id"],
        revision=claim["account_revision"],
        account_status="ACTIVE",
        auth_status="AUTHORIZED",
        unbound_at=None,
    )
    config = dict(
        id=claim["source_config_id"],
        revision=claim["source_config_revision"],
        settings_json={"systemUserId": "0007", "businessId": "42", "graphVersion": "v25.0"},
        secrets_json={"accessToken": "encrypted-not-logged"},
    )
    release = dict(
        id=claim["release_id"],
        revision=claim["release_revision"],
        capability_version=claim["capability_version"],
        source_hash=claim["release_source_hash"],
        source_config_id=config["id"],
        source_config_revision=config["revision"],
        business_id="42",
        graph_version="v25.0",
        action_scope="ACCOUNT_IDENTITIES_READ",
        issuer="controlled-source",
        source_kind="META_AUTHORITY",
        revoked_at=None,
    )
    head = dict(
        account_id=account["id"],
        revision=1,
        evidence_id=claim["evidence_id"],
        capability_version=claim["capability_version"],
        resource_count=0,
        observed_at=claim["observed_at"],
        provenance_frozen=1,
    )
    proof = {k: v for k, v in claim.items() if k not in {"key_id", "revision"}}
    proof["identity_revision"] = 1
    item = dict(
        account_id=account["id"],
        account_revision=1,
        capability_version=claim["capability_version"],
        source_config_id=config["id"],
        source_config_revision=1,
        observed_at=claim["observed_at"],
        payload_hash=claim["payload_hash"],
        complete=1,
        verified=1,
        revoked_at=None,
        credential_expires_at=None,
    )
    raw = dict(
        bound_sha256=claim["bound_sha256"],
        source_config_id=config["id"],
        source_config_revision=config["revision"],
    )
    model = module.IdentityPublicationSummary(cipher())
    ticket = module.SummaryTicket(
        session,
        session.tx,
        current,
        "accounts.read",
        (account["id"],),
        MappingProxyType({account["id"]: (1, claim["evidence_id"], claim["release_id"])}),
        (MappingProxyType(config),),
        MappingProxyType({release["id"]: release}),
        module._ISSUER,
    )
    data = dict(
        account=account,
        config=config,
        release=release,
        head=head,
        proof=proof,
        item=item,
        raw=raw,
        seal=sign(claim),
        current=current,
        model=model,
        ticket=ticket,
        session=session,
        clock_calls=0,
        authority_calls=0,
    )

    async def access(*args):
        return current

    async def clock(*args):
        data["clock_calls"] += 1

    async def accounts(*args):
        return [account]

    async def authority(*args):
        data["authority_calls"] += 1

    async def metadata(*args):
        eid = claim["evidence_id"]
        return (
            {account["id"]: head} if data["head"] else {},
            {eid: item},
            {eid: proof},
            {eid: data["seal"]} if data["seal"] else {},
            {claim["registry_id"]: raw},
        )

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "clock", clock)
    monkeypatch.setattr(module, "current_accounts", accounts)
    monkeypatch.setattr(module, "authority_database", authority)
    monkeypatch.setattr(model, "_metadata", metadata)
    return data


@pytest.mark.asyncio
async def test_batch_resolve_uses_verified_seal_not_resource_scan(graph):
    result = await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    value = result[graph["account"]["id"]]
    assert value["identity_status"] == "SYNCED"
    assert value["identity_count"] == 0
    assert graph["clock_calls"] == graph["authority_calls"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["no_seal", "bad_mac", "unfrozen", "revoked", "source", "head"])
async def test_each_incomplete_or_changed_binding_stays_unknown(graph, change):
    if change == "no_seal":
        graph["seal"] = None
    elif change == "bad_mac":
        graph["seal"]["resource_count"] += 1
    elif change == "unfrozen":
        graph["head"]["provenance_frozen"] = 0
    elif change == "revoked":
        graph["release"]["revoked_at"] = graph["session"].now
    elif change == "source":
        graph["config"]["revision"] += 1
    elif change == "head":
        graph["head"]["revision"] += 1
    result = await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    assert result[graph["account"]["id"]] == module.unknown()


@pytest.mark.asyncio
async def test_absent_head_is_unsynced_with_null_count(graph):
    graph["head"] = None
    result = await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    assert result[graph["account"]["id"]] == module.unknown("UNSYNCED")


@pytest.mark.asyncio
async def test_ticket_cannot_cross_actor_session_or_transaction(graph):
    model, session, ticket = graph["model"], graph["session"], graph["ticket"]
    for actual_session, actor in [(session, 8), (Session(session.now), 7)]:
        with pytest.raises(OrbitError):
            model.check_ticket(actual_session, actor, ticket, "accounts.read")
    session.tx = object()
    with pytest.raises(OrbitError):
        model.check_ticket(session, 7, ticket, "accounts.read")


@pytest.mark.asyncio
async def test_current_scope_failure_is_not_swallowed_into_unknown(graph, monkeypatch):
    async def inaccessible(*args):
        raise OrbitError(404, "ACCOUNT_NOT_FOUND", "账户不存在")

    monkeypatch.setattr(module, "current_accounts", inaccessible)
    with pytest.raises(OrbitError) as caught:
        await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    assert caught.value.status == 404


@pytest.mark.asyncio
async def test_metadata_queries_have_constant_batch_count_and_no_resources(graph, monkeypatch):
    calls = []

    async def batched(session, sql, values, ids=None):
        calls.append((sql, ids))
        assert "orbit_account_identity_resource" not in sql
        if "SELECT h.account_id" in sql:
            return [graph["head"]]
        if "SELECT * FROM orbit_account_identity_evidence" in sql:
            return [{"id": graph["head"]["evidence_id"]}]
        if "SELECT * FROM orbit_identity_publication_provenance" in sql:
            return [graph["proof"]]
        return []

    monkeypatch.setattr(module, "rows", batched)
    await module.IdentityPublicationSummary()._metadata(
        graph["session"], graph["current"], [uid() for _ in range(200)]
    )
    assert len(calls) == 5
    assert all("FOR SHARE" in sql for sql, _ in calls)


@pytest.mark.asyncio
async def test_prepare_orders_sources_before_clock_and_freezes_config_json(graph, monkeypatch):
    events = []
    row = dict(graph["config"])

    async def batched(session, sql, values, ids=None):
        assert "orbit_account_clock" not in sql
        if "SELECT h.account_id" in sql:
            events.append("probe")
            return [graph["head"] | {"release_id": graph["release"]["id"]}]
        if "orbit_system_configuration" in sql:
            events.append("config")
            return [row]
        assert "orbit_identity_capability_release" in sql
        events.append("release")
        assert list(ids) == [graph["release"]["id"]]
        return [graph["release"]]

    monkeypatch.setattr(module, "rows", batched)
    ticket = await graph["model"].prepare(graph["session"], 7, [graph["account"]["id"]])
    assert events == ["probe", "config", "release"]
    assert graph["clock_calls"] == 0
    original = ticket.configurations[0]["settings_json"]
    row["settings_json"]["systemUserId"] = "changed-after-capture"
    assert ticket.configurations[0]["settings_json"] == original
    assert "encrypted-not-logged" not in repr(ticket)


@pytest.mark.asyncio
async def test_resolve_cannot_sign_or_relock_new_head_sources(graph, monkeypatch):
    ticket = graph["ticket"]
    no_probe = module.SummaryTicket(
        ticket.session,
        ticket.transaction,
        ticket.current,
        ticket.permission,
        (),
        MappingProxyType({}),
        (),
        MappingProxyType({}),
        module._ISSUER,
    )

    async def no_source_or_resource_queries(*args, **kwargs):
        raise AssertionError("resolve不可新增来源或资源查询")

    monkeypatch.setattr(module, "rows", no_source_or_resource_queries)
    result = await graph["model"].resolve(graph["session"], 7, [graph["account"]], no_probe)
    assert result[graph["account"]["id"]] == module.unknown()


@pytest.mark.asyncio
async def test_revoked_current_read_action_propagates_before_cached_seal(graph, monkeypatch):
    async def revoked(*args):
        raise OrbitError(403, "PERMISSION_DENIED", "读取权限已撤回")

    monkeypatch.setattr(module, "require_business_access", revoked)
    with pytest.raises(OrbitError) as caught:
        await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    assert caught.value.status == 403


@pytest.mark.asyncio
async def test_no_signer_default_does_not_issue_summary_success(graph):
    graph["model"].cipher = None
    result = await graph["model"].resolve(graph["session"], 7, [graph["account"]], graph["ticket"])
    assert result[graph["account"]["id"]] == module.unknown()


def test_candidate_freezes_old_proof_without_forging_seals():
    candidate = (
        Path(__file__).parents[2]
        / "docs/orbit/sql-drafts/055_identity_inventory_summary_candidate.sql"
    )
    sql = candidate.read_text(encoding="utf-8")
    assert sql.count("CREATE TRIGGER ") == 13
    assert "provenance_frozen BOOLEAN NOT NULL DEFAULT 0" in sql
    assert "UPDATE orbit_account_identity_history h JOIN" in sql
    assert "INSERT INTO orbit_identity_inventory_seal" not in sql
    assert "DECLARE resource_rows CURSOR" in sql
    assert "FOR SHARE OF p,e,h" in sql
    assert "DELIMITER" not in sql
