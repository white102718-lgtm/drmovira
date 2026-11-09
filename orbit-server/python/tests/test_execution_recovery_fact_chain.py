"""事实链完整性纯测；不连接数据库、不代表来源权威。"""

import hashlib
from dataclasses import asdict, replace
from datetime import timedelta

import pytest
from test_launch_execution_lease_contract import NOW, binding, fact

from orbit_api.directory_tokens import canonical
from orbit_api.launch_execution_lease_store import fact_chain_seed, fact_chain_step


def test_chain_seed_binds_domain_and_entire_attempt():
    original = binding()
    expected = hashlib.sha256(
        canonical({"domain": "ORBIT_EXECUTION_FACT_CHAIN_V1", "binding": asdict(original)}).encode()
    ).digest()
    assert fact_chain_seed(original) == expected
    assert fact_chain_seed(replace(original, auth_version=original.auth_version + 1)) != expected


def test_complete_fact_canonical_hash_matches_independent_document():
    record = fact()
    seed = fact_chain_seed(record.binding)
    document = asdict(record)
    document.update(
        occurred_at=record.occurred_at.isoformat(timespec="microseconds"),
        recorded_at=NOW.isoformat(timespec="microseconds"),
        sequence=1,
    )
    assert (
        fact_chain_step(seed, 1, record, NOW)
        == hashlib.sha256(seed + canonical(document).encode()).digest()
    )


@pytest.mark.parametrize("part", ["sequence", "event", "hash", "recorded", "occurred", "previous"])
def test_chain_changes_with_every_fact_identity_time_and_order(part):
    record = fact()
    previous = fact_chain_seed(record.binding)
    expected = fact_chain_step(previous, 1, record, NOW)
    sequence, recorded = 1, NOW
    if part == "sequence":
        sequence = 2
    elif part == "event":
        record = replace(record, event_id="00000000-0000-0000-0000-000000000099")
    elif part == "hash":
        record = replace(record, evidence_sha256="a" * 64)
    elif part == "recorded":
        recorded += timedelta(microseconds=1)
    elif part == "occurred":
        record = replace(record, occurred_at=record.occurred_at - timedelta(microseconds=1))
    else:
        previous = bytes(32)
    assert fact_chain_step(previous, sequence, record, recorded) != expected


def test_289_rows_streamed_chain_keeps_late_fact_and_order():
    record = fact()
    root = fact_chain_seed(record.binding)
    for sequence in range(1, 289):
        root = fact_chain_step(root, sequence, record, NOW)
    assert fact_chain_step(root, 289, record, NOW) != root
    changed = replace(record, evidence_sha256="c" * 64)
    assert fact_chain_step(root, 289, record, NOW) != fact_chain_step(root, 289, changed, NOW)
