"""049恢复的内存SQL边界；不替代真实MySQL/权限/来源验收。"""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_metrics_query_store import (
    NOW,
    OWNER,
    PROFILE,
    TENANT,
    FakeResult,
    RegisteredPureSource,
    Session,
    head,
    query,
    scope,
)

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_store import MetricsQueryStore, metric_query_hash


class PersistedSession(Session):
    def __init__(self, sources, header):
        super().__init__(sources)
        self.header = header

    async def execute(self, statement, values=None):
        sql = str(statement)
        if "FROM orbit_metric_query_snapshot q" in sql:
            self.calls.append((sql, dict(values)))
            return FakeResult([self.header] if self.header is not None else [])
        if "p.id=:publication_id" in sql:
            self.calls.append((sql, dict(values)))
            value = self.heads.get(values["publication_id"])
            return FakeResult(
                [value] if value and value["generation"] == values["generation"] else []
            )
        return await super().execute(statement, values)


def persisted(source, **changes):
    return {
        "id": str(uuid4()),
        "tenant_id": TENANT,
        "actor_id": 1,
        "subject_id": OWNER,
        "auth_version": 1,
        "auth_fingerprint": "d" * 64,
        "account_scope_snapshot_id": None,
        "account_scope_hash": None,
        "account_scope_count": None,
        "query_json": canonical(query()),
        "query_hash": metric_query_hash(query()),
        "source_publication_id": source["id"],
        "source_generation": source["generation"],
        "profile_id": PROFILE,
        "profile_version": source["profile_version"],
        "profile_hash": source["profile_hash"],
        "state": "BUILDING",
        "cleanup_requested": 0,
        "expected_manifest_version": "orbit-metric-expectation-canonical-lines-v2",
        "expected_membership_count": 0,
        "expected_unit_hash": "a" * 64,
        "expected_membership_hash": "b" * 64,
        **changes,
    }


def fixture(monkeypatch, **changes):
    old = head(generation=10)
    newer = head(generation=20)
    row = persisted(old, **changes)
    session = PersistedSession([old, newer], row)
    source = RegisteredPureSource([old, newer])
    auth = AsyncMock(return_value=scope())
    monkeypatch.setattr("orbit_api.metrics_query_store.authorize_metric_scope", auth)
    monkeypatch.setattr("orbit_api.metrics_query_store.fixture_boundary", AsyncMock())
    return MetricsQueryStore(source, clock=lambda: NOW), session, source, auth, row


def test_resume_uses_persisted_old_anchor_not_new_latest_and_readonly_metadata(monkeypatch):
    async def run():
        store, session, _, auth, row = fixture(monkeypatch)
        context = await store.resume_persisted_query(session, 1, row["id"])
        result = await store.describe_context(session, context)
        assert result["source_generation"] == 10 and session.anchor["generation"] == 20
        assert result["source_publication_id"] == row["source_publication_id"]
        assert result["query_hash"] == row["query_hash"]
        with pytest.raises(TypeError):
            result["source_generation"] = 20
        with pytest.raises(TypeError):
            result["query"]["q"] = "forged"
        assert auth.await_count >= 3
        session.transaction = object()
        with pytest.raises(OrbitError) as error:
            await store.describe_context(session, context)
        assert error.value.status == 409

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_id": 2},
        {"subject_id": str(uuid4())},
        {"tenant_id": str(uuid4())},
        {"auth_version": 2},
        {"auth_version": True},
        {"auth_fingerprint": "f" * 64},
        {"account_scope_hash": "f" * 64},
        {"account_scope_count": 0},
        {"account_scope_snapshot_id": str(uuid4())},
        {"query_hash": "f" * 64},
        {"query_json": canonical(query(q="changed"))},
        {"state": "EXPIRED"},
        {"state": "OTHER"},
        {"query_json": canonical(query(cursor="opaque"))},
    ],
)
def test_resume_rejects_persisted_binding_mismatch(monkeypatch, changes):
    async def run():
        store, session, _, _, row = fixture(monkeypatch, **changes)
        with pytest.raises(OrbitError) as error:
            await store.resume_persisted_query(session, 1, row["id"])
        assert error.value.status == 409
        assert not store._contexts

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [
        {"profile_version": "other"},
        {"profile_hash": "f" * 64},
        {"source_publication_id": str(uuid4())},
        {"source_generation": 999},
        {"query_json": "{broken"},
    ],
)
def test_resume_rejects_bad_profile_source_or_query(monkeypatch, changes):
    async def run():
        store, session, _, _, row = fixture(monkeypatch, **changes)
        with pytest.raises(OrbitError):
            await store.resume_persisted_query(session, 1, row["id"])
        assert not store._contexts

    asyncio.run(run())


def test_cleanup_or_missing_query_404_and_no_source_verification(monkeypatch):
    async def run():
        for cleanup in (False, True):
            store, session, source, _, row = fixture(monkeypatch, cleanup_requested=1)
            if not cleanup:
                session.header = None
            with pytest.raises(OrbitError) as error:
                await store.resume_persisted_query(session, 1, row["id"])
            assert error.value.status == 404 and source.calls == []

    asyncio.run(run())


def test_current_scope_change_cannot_reuse_persisted_auth(monkeypatch):
    async def run():
        store, session, _, auth, row = fixture(monkeypatch)
        auth.return_value = replace(scope(), auth_version=2)
        with pytest.raises(OrbitError) as error:
            await store.resume_persisted_query(session, 1, row["id"])
        assert error.value.status == 409

    asyncio.run(run())


def test_default_resume_and_describe_provider_none_are_zero_sql(monkeypatch):
    async def run():
        store = MetricsQueryStore()
        session = type("UnusedSession", (), {"execute": AsyncMock()})()
        for call in (
            store.resume_persisted_query(session, 1, str(uuid4())),
            store.describe_context(session, object()),
        ):
            with pytest.raises(OrbitError) as error:
                await call
            assert error.value.status == 503
        session.execute.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("null_mask", range(1, 16))
def test_missing_or_mixed_null_expected_manifest_never_resumes_legacy_row(monkeypatch, null_mask):
    fields = (
        "expected_manifest_version",
        "expected_unit_hash",
        "expected_membership_hash",
        "expected_membership_count",
    )
    changes = {field: None for index, field in enumerate(fields) if null_mask & (1 << index)}

    async def run():
        store, session, _, _, row = fixture(monkeypatch, **changes)
        with pytest.raises(OrbitError) as error:
            await store.resume_persisted_query(session, 1, row["id"])
        assert error.value.status == 503 and not store._contexts

    asyncio.run(run())


def test_v1_expected_manifest_cannot_be_reinterpreted_as_v2_name_evidence(monkeypatch):
    async def run():
        store, session, _, _, row = fixture(
            monkeypatch, expected_manifest_version="orbit-metric-expectation-canonical-lines-v1"
        )
        with pytest.raises(OrbitError) as error:
            await store.resume_persisted_query(session, 1, row["id"])
        assert error.value.status == 503

    asyncio.run(run())
