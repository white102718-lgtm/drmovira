"""当前读模型的独立来源/撤销边界协议；不计真实SQL或Meta验收。"""

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import orbit_api.identity_publication_readmodel as module
from orbit_api.errors import OrbitError


class LockedRow(Mapping):
    """真实SQLAlchemy RowMapping是Mapping，不承诺dict的|运算协议。"""

    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        return self.value[key]

    def __iter__(self):
        return iter(self.value)

    def __len__(self):
        return len(self.value)


@pytest.fixture
def graph(monkeypatch):
    account_id, evidence_id, config_id, release_id = (str(uuid4()) for _ in range(4))
    at = datetime(2026, 11, 9, 0, 0, 0, 123000, tzinfo=UTC)
    current = SimpleNamespace(tenant_id=str(uuid4()), actor_id=1)
    config = dict(
        id=config_id,
        revision=2,
        settings_json={"businessId": "42", "graphVersion": "v25.0", "systemUserId": "7"},
        secrets_json={"accessToken": "encrypted"},
    )
    release = dict(
        revoked_at=None,
        revision=3,
        capability_version="version",
        source_hash="a" * 64,
        source_config_id=config_id,
        source_config_revision=2,
        business_id="42",
        graph_version="v25.0",
        action_scope="ACCOUNT_IDENTITIES_READ",
        issuer="issuer",
        source_kind="META_AUTHORITY",
    )
    proof = dict(
        evidence_id=evidence_id,
        account_id=account_id,
        identity_revision=1,
        release_id=release_id,
        release_revision=3,
        release_source_hash="a" * 64,
        authority_kind="TRUSTED",
        principal_id="7",
        projection_version=module.PROJECTION,
        raw_observed_at=at.replace(microsecond=123500),
        raw_credential_expires_at=None,
        registry_id=str(uuid4()),
        bound_sha256="b" * 64,
    )
    evidence = dict(
        source_config_id=config_id,
        capability_version="version",
        observed_at=at,
        source_config_revision=2,
        credential_expires_at=None,
    )
    data = dict(
        probe=dict(evidence_id=evidence_id, release_id=release_id),
        head=dict(evidence_id=evidence_id, revision=1),
        proof=proof,
        evidence=evidence,
        raw=dict(bound_sha256="b" * 64, source_config_id=config_id, source_config_revision=2),
        account=dict(
            id=account_id, auth_status="AUTHORIZED", account_status="ACTIVE", unbound_at=None
        ),
        config=config,
        release=release,
        events=[],
    )

    async def access(*args):
        data["events"].append("authorization")
        return current

    async def sources(*args):
        data["events"].append("sources")
        return [LockedRow(data["config"])], data["release"]

    async def clock(*args):
        data["events"].append("clock")
        return 200  # 发布前clock不是GET永久版本；全局其他动作不使本观察自失效。

    async def accounts(*args):
        data["events"].append("accounts")
        return [data["account"]]

    async def one(session, sql, values):
        if "SELECT p.evidence_id" in sql:
            return data["probe"]
        assert "FOR SHARE" in sql
        if "FROM orbit_account_identity_head" in sql:
            return data["head"]
        if "FROM orbit_identity_publication_provenance" in sql:
            return data["proof"]
        if "FROM orbit_account_identity_evidence" in sql:
            return data["evidence"]
        if "FROM orbit_meta_raw_head" in sql:
            return data["raw"]
        raise AssertionError("未声明SQL")

    async def history(*args):
        data["events"].append("history")
        return {
            "account_id": account_id,
            "resources": [],
            "capability_version": "version",
            "observed_at": "2026-11-09T00:00:00.123Z",
        }

    async def kind(*args):
        assert args[-1] == "TRUSTED"

    def validate(e, a, s, value, now):
        data["events"].append("validate-original")
        assert e is evidence and a is data["account"] and s["id"] == config_id

    class Session:
        async def execute(self, sql):
            assert "UTC_TIMESTAMP(6)" in str(sql)
            return SimpleNamespace(scalar_one=lambda: datetime(2026, 11, 10))

    for name, value in dict(
        require_business_access=access,
        lock_sources=sources,
        clock=clock,
        current_accounts=accounts,
        one=one,
        verify_history=history,
        authority_database=kind,
        validate_evidence=validate,
    ).items():
        monkeypatch.setattr(module, name, value)
    return data, Session(), account_id


async def test_read_uses_current_sources_before_clock_and_exact_original_shape(graph):
    data, session, account = graph
    value = await module.IdentityPublicationReadmodel().get(session, 1, account)
    assert set(value) == {"account_id", "resources", "capability_version", "observed_at"}
    assert data["events"] == [
        "authorization",
        "sources",
        "clock",
        "accounts",
        "history",
        "validate-original",
    ]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("revoked", "IDENTITY_PUBLICATION_RELEASE_UNAVAILABLE"),
        ("wrong-config", "ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE"),
        ("principal-change", "ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE"),
        ("rounding", "IDENTITY_PUBLICATION_HISTORY_INVALID"),
        ("projection", "IDENTITY_PUBLICATION_HISTORY_INVALID"),
        ("raw-root", "IDENTITY_PUBLICATION_RAW_UNAVAILABLE"),
        ("new-head", "IDENTITY_PUBLICATION_SOURCE_RETRY"),
        ("legacy", "IDENTITY_PUBLICATION_SOURCE_RETRY"),
        ("unavailable-account", "ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE"),
    ],
)
async def test_invalid_or_changed_current_proof_never_returns_stale_resources(
    graph, mutation, code
):
    data, session, account = graph
    if mutation == "revoked":
        data["release"]["revoked_at"] = datetime.now(UTC)
    elif mutation == "wrong-config":
        data["evidence"]["source_config_id"] = str(uuid4())
    elif mutation == "principal-change":
        data["config"]["settings_json"]["systemUserId"] = "99"
    elif mutation == "rounding":
        data["evidence"]["observed_at"] = data["evidence"]["observed_at"].replace(
            microsecond=124000
        )
    elif mutation == "projection":
        data["proof"]["projection_version"] = "UNKNOWN"
    elif mutation == "raw-root":
        data["raw"]["bound_sha256"] = "0" * 64
    elif mutation == "new-head":
        data["head"] = deepcopy(data["head"]) | {"evidence_id": str(uuid4())}
    elif mutation == "legacy":
        data["probe"] = None
    else:
        data["account"]["auth_status"] = "UNKNOWN"
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationReadmodel().get(session, 1, account)
    assert (failure.value.status, failure.value.code) == (503, code)
    assert "history" not in data["events"]


async def test_unknown_account_checks_current_scope_before_missing_source(graph, monkeypatch):
    data, session, account = graph
    data["probe"] = None

    async def denied(*args):
        raise OrbitError(404, "NOT_FOUND", "账户不在当前范围")

    monkeypatch.setattr(module, "current_accounts", denied)
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationReadmodel().get(session, 1, account)
    assert failure.value.status == 404
    assert data["events"] == ["authorization", "clock"]


async def test_authorized_account_without_head_is_explicitly_unsynced(graph):
    data, session, account = graph
    data["probe"], data["head"] = None, None
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationReadmodel().get(session, 1, account)
    assert (failure.value.status, failure.value.code) == (503, "ACCOUNT_IDENTITIES_UNSYNCED")
    assert data["events"] == ["authorization", "clock", "accounts"]


async def test_malformed_public_uuid_is_original_422_not_internal_503(graph):
    data, session, account = graph
    with pytest.raises(OrbitError) as failure:
        await module.IdentityPublicationReadmodel().get(session, 1, "not-uuid")
    assert (failure.value.status, failure.value.code, failure.value.pointer) == (
        422,
        "FIELD_INVALID",
        "/id",
    )
    assert data["events"] == []
