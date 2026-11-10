"""生产指标来源必须核独立封存与当前连接，结构不能代替采集成功。"""

from uuid import uuid4

import pytest
from test_metrics_query_store import head, query, scope

from orbit_api.errors import OrbitError
from orbit_api.meta_metrics_provider import meta_source_proof
from orbit_api.metrics_query_store import (
    MetricReadSourceProvider,
    MetricsQueryStore,
    publication_validation_binding,
)


def test_oauth_publication_only_accepts_exact_checkpoint_proof():
    proof = meta_source_proof(
        dict(
            id=str(uuid4()),
            connection_id=str(uuid4()),
            connection_revision=1,
            account_source_revision=1,
            inventory_hash="e" * 64,
            api_version="v24.0",
        )
    )
    item = head(authority_kind="TRUSTED", source_proof_json=proof)
    assert publication_validation_binding(item)
    for changed in (
        {"kind": "OTHER"},
        {"connection_revision": True},
        {"token": "secret"},
        {"inventory_hash": "bad"},
    ):
        with pytest.raises(OrbitError):
            publication_validation_binding(item | {"source_proof_json": proof | changed})


@pytest.mark.asyncio
async def test_other_trusted_provider_cannot_unlock_empty_config_checkpoint():
    class Other(MetricReadSourceProvider):
        async def verify_publications(self, *a):
            raise AssertionError("must reject before provider")

    proof = meta_source_proof(
        dict(
            id=str(uuid4()),
            connection_id=str(uuid4()),
            connection_revision=1,
            account_source_revision=1,
            inventory_hash="e" * 64,
            api_version="v24.0",
        )
    )
    with pytest.raises(OrbitError):
        await MetricsQueryStore(Other())._verify(
            object(), scope(), query(), [head(authority_kind="TRUSTED", source_proof_json=proof)]
        )


@pytest.mark.asyncio
async def test_sealed_history_survives_connection_expiry_but_rejects_revoked_receipt(monkeypatch):
    import hashlib

    import orbit_api.meta_metrics_provider as module
    from orbit_api.directory_tokens import canonical

    proof = meta_source_proof(
        dict(
            id=str(uuid4()),
            connection_id=str(uuid4()),
            connection_revision=2,
            account_source_revision=3,
            inventory_hash="e" * 64,
            api_version="v24.0",
        )
    )
    item = head(authority_kind="TRUSTED", source_proof_json=proof)
    binding = publication_validation_binding(item)
    saved = dict(
        publication_id=item["id"],
        binding_json=list(binding),
        binding_hash=hashlib.sha256(canonical(binding).encode()).hexdigest(),
        revoked_at=None,
        checkpoint_state="PUBLISHED",
        checkpoint_publication=item["id"],
        profile_source="META",
        profile_authority="TRUSTED",
        payload_hash=item["profile_hash"],
        checkpoint_profile_hash=item["profile_hash"],
        adapter_profile_hash=item["profile_hash"],
        adapter_revoked=None,
        inventory_hash=proof["inventory_hash"],
        checkpoint_inventory=proof["inventory_hash"],
        capture_sequence=item["capture_sequence_max"],
        checkpoint_id=proof["checkpoint_id"],
        connection_id=proof["connection_id"],
        connection_revision=2,
        account_source_revision=3,
        api_version="v24.0",
    )

    async def current(*args):
        return None

    async def stored(session, sql, params):
        assert "JOIN orbit_meta_connection " not in sql
        assert "JOIN orbit_meta_account_source " not in sql
        return [saved]

    monkeypatch.setattr(module, "current_scope", current)
    monkeypatch.setattr(module, "rows", stored)
    provider = module.MetaMetricReadSource()
    assert len(await provider.verify_publications(object(), scope(), query(), [item])) == 1
    saved["revoked_at"] = "revoked"
    with pytest.raises(OrbitError):
        await provider.verify_publications(object(), scope(), query(), [item])
