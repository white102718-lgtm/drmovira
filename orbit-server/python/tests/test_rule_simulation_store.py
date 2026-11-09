"""063协议第一阶段纯测；无真实来源、SQL落库、READY或成功HTTP验收。"""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_rule_contract import sample_rule
from test_rule_editor_definition import uid

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_simulation_contract import (
    OriginalSimulationReceipt,
    SimulationIntent,
    SimulationQuality,
    SimulationSnapshot,
    confirmation_unexpired,
    digest,
    simulation_response,
    validate_summary,
)
from orbit_api.rule_simulation_evaluator import ALGORITHM_VERSION, EvaluationSummary
from orbit_api.rule_simulation_protocol import RuleSimulationAccess, RuleSimulationSource
from orbit_api.rule_simulation_store import RuleSimulationStore

NOW = datetime(2026, 11, 9, 0, 0, 0, 123499, tzinfo=UTC)


def intent():
    return SimulationIntent(91, uid(3), 2, "a" * 64, uid(5))


def snapshot(**changes):
    value = SimulationSnapshot(
        uid(1),
        91,
        uid(3),
        2,
        canonical(sample_rule()),
        uid(6),
        "b" * 64,
        "c" * 64,
        "d" * 64,
        2,
        "e" * 64,
        "f" * 64,
        1,
        "1" * 64,
        "verified-v1",
        "2" * 64,
        "3" * 64,
        uid(7),
        4,
        9,
        "4" * 64,
        NOW,
        SimulationQuality(0, 1, 0, 0, 1, NOW - timedelta(minutes=31)),
    )
    return replace(value, **changes)


def summary(**changes):
    value = snapshot()
    return replace(
        EvaluationSummary(
            ALGORITHM_VERSION,
            digest(value.rule().model_dump()),
            1,
            0,
            1,
            0,
            1,
            value.entity_ids_root,
            "5" * 64,
        ),
        **changes,
    )


def test_snapshot_quality_and_rule_are_deeply_detached_no_eligible():
    value = snapshot()
    output = value.payload()
    original = value.input_hash
    output["rule"]["groups"].clear()
    output["quality"]["stale_unit_count"] = 0
    value.rule().groups.clear()
    assert value.input_hash == original and value.leaf_count == 1 and value.unit_count == 6
    assert not hasattr(value.quality, "eligible") and not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.quality.sparse_entity_count = 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_count", 0),
        ("account_count", 50001),
        ("entity_count", 2147483648),
        ("entity_count", True),
        ("profile_hash", "A" * 64),
        ("source_generation", 0),
        ("rule_json", "{}"),
        ("rule_json", "  " + canonical(sample_rule())),
        ("evaluated_at", NOW.replace(tzinfo=None)),
        ("tenant_id", "not-a-uuid"),
    ],
)
def test_snapshot_structural_shape_does_not_silently_normalize_or_fake_counts(field, value):
    with pytest.raises((ValueError, OrbitError)):
        snapshot(**{field: value})


def test_quality_count_and_future_observation_rejected_but_sparse_unknown_allowed():
    with pytest.raises(ValueError):
        snapshot(quality=SimulationQuality(7, 0, 0, 0, 0, None))
    with pytest.raises(ValueError):
        snapshot(quality=SimulationQuality(0, 0, 0, 0, 0, NOW + timedelta(microseconds=1)))
    validate_summary(snapshot(), summary())
    assert snapshot().quality.stale_unit_count == 1 and summary().unknown_count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"scanned_count": 2},
        {"hit_count": 1},
        {"condition_count": 0},
        {"entity_ids_root": "6" * 64},
        {"rule_hash": "7" * 64},
        {"algorithm": "unknown"},
        {"results_root": "bad"},
        {"hit_count": True},
    ],
)
def test_no_partial_or_misbound_summary_pretends_complete(changes):
    with pytest.raises(ValueError):
        validate_summary(snapshot(), summary(**changes))


@pytest.mark.parametrize("microsecond", [123499, 123500, 999999])
def test_original_thirteen_projection_only_and_fifteen_minute_exact_boundary(microsecond):
    value, evaluated = snapshot(), summary()
    seal = NOW.replace(microsecond=microsecond) + timedelta(seconds=1)
    result = simulation_response(
        value,
        evaluated,
        simulation_id=uid(20),
        snapshot_id=uid(21),
        sealed_at=seal,
        conditions=[
            {
                "entity_id": uid(90),
                "condition_index": 0,
                "value": None,
                "result": "UNKNOWN",
                "reason_code": "METRIC_MISSING",
            }
        ],
        next_cursor=None,
    )
    assert len(result) == 13 and result["unknown_count"] == 1
    assert result["revision"] == 2 and result["scanned_count"] == 1
    # 本函数仅原DTO结构投影；并非Store来源/SQL已完成/发出成功响应。
    expires = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
    assert expires == seal + timedelta(minutes=15)
    assert confirmation_unexpired(expires, expires - timedelta(microseconds=1))
    assert not confirmation_unexpired(expires, expires)
    assert not confirmation_unexpired(expires, expires + timedelta(microseconds=1))


@pytest.mark.parametrize(
    "identifier", [uid(20), uid(6), uid(7), sample_rule()["scope_snapshot_id"]]
)
def test_snapshot_id_cannot_alias_simulation_scope_manifest_or_publication(identifier):
    with pytest.raises(ValueError):
        simulation_response(
            snapshot(),
            summary(),
            simulation_id=uid(20),
            snapshot_id=identifier,
            sealed_at=NOW,
            conditions=[],
            next_cursor=None,
        )


def test_first_response_cannot_hide_required_leaf_as_empty_success_or_fake_more_cursor():
    for conditions, cursor in (
        ([], None),
        ([], "opaque"),
        (
            [
                {
                    "entity_id": uid(90),
                    "condition_index": 0,
                    "value": None,
                    "result": "UNKNOWN",
                    "reason_code": "METRIC_MISSING",
                }
            ],
            "unnecessary",
        ),
    ):
        with pytest.raises(ValueError):
            simulation_response(
                snapshot(),
                summary(),
                simulation_id=uid(20),
                snapshot_id=uid(21),
                sealed_at=NOW,
                conditions=conditions,
                next_cursor=cursor,
            )


def test_original_success_receipt_preserves_exact_bytes_and_detaches_parsed_document():
    document = simulation_response(
        snapshot(),
        summary(),
        simulation_id=uid(20),
        snapshot_id=uid(21),
        sealed_at=NOW,
        conditions=[
            {
                "entity_id": uid(90),
                "condition_index": 0,
                "value": None,
                "result": "UNKNOWN",
                "reason_code": "METRIC_MISSING",
            }
        ],
        next_cursor=None,
    )
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode()
    receipt = bound_receipt(raw, document)
    assert receipt.response_bytes is raw and receipt.document() == document
    receipt.document()["expires_at"] = "2099-01-01T00:00:00Z"
    assert receipt.document() == document
    assert receipt.response_bytes != canonical(document).encode()
    assert len(receipt.response_hash) == 64
    with pytest.raises(ValueError):
        bound_receipt(bytearray(raw), document)


@pytest.mark.asyncio
async def test_protocol_cancel_and_provider_commit_never_returns_prepared_input():
    import asyncio

    for failure in ("cancel", "commit"):
        access, source, session = PureAccess(), PureSource(), Session()
        store = RuleSimulationStore(access=access, source=source)

        async def capture(
            _session, _auth, _intent, *, selected_failure=failure, selected_source=source
        ):
            if selected_failure == "cancel":
                raise asyncio.CancelledError
            _session.tx = object()
            return selected_source.value

        source.capture = capture
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ValueError):
            await store.prepare_inputs(session, intent())


class Session:
    def __init__(self):
        self.tx = object()
        self.sync_session = SimpleNamespace(get_transaction=lambda: self.tx)
        self.execute = Mock(side_effect=AssertionError("PURE_NO_SQL"))

    def in_transaction(self):
        return self.tx is not None


class PureAccess(RuleSimulationAccess):
    """只有纯协议替身，不是生产或ISOLATED SQL authority。"""

    def __init__(self):
        super().__init__()
        self.calls = 0
        self.revision = 2
        self.fingerprint = "c" * 64

    async def authorize(self, session, request, *, snapshot=None):
        self.calls += 1
        return self._issue(
            session,
            tenant_id=uid(1),
            actor_id=request.actor_id,
            rule_id=request.rule_id,
            current_revision=self.revision,
            auth_fingerprint=self.fingerprint,
        )


class PureSource(RuleSimulationSource):
    """只纯协议，验证计数与事务；不冒充真实SQL指标源。"""

    def __init__(self):
        self.value = snapshot()
        self.capture_count = 0
        self.checked = 0
        self.ack = None

    async def capture(self, session, auth, request):
        self.capture_count += 1
        return self.value

    async def revalidate(self, session, auth, value):
        self.checked += 1
        assert value is self.value
        return self.ack


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["both", "source", "access"])
async def test_default_or_partial_dependencies_fail_before_any_sql_or_facade(mode):
    access, source, session = PureAccess(), PureSource(), Session()
    store = RuleSimulationStore(
        access=None if mode in {"both", "access"} else access,
        source=None if mode in {"both", "source"} else source,
    )
    with pytest.raises(OrbitError) as caught:
        await store.prepare_inputs(session, intent())
    assert caught.value.code == "RULE_SIMULATION_SOURCE_UNAVAILABLE"
    session.execute.assert_not_called()
    assert access.calls == source.capture_count == source.checked == 0


@pytest.mark.asyncio
async def test_explicit_protocol_requires_same_store_session_and_exact_transaction():
    access, source, session = PureAccess(), PureSource(), Session()
    store = RuleSimulationStore(access=access, source=source)
    prepared = await store.prepare_inputs(session, intent())
    assert prepared.snapshot is source.value and access.calls == 2 and source.checked == 1
    with pytest.raises(ValueError):
        await RuleSimulationStore(access=access, source=source).revalidate_inputs(session, prepared)
    with pytest.raises(ValueError):
        await store.revalidate_inputs(Session(), prepared)
    session.tx = object()
    with pytest.raises(ValueError):
        await store.revalidate_inputs(session, prepared)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_current_head_or_auth_or_captured_binding_drift_fail_closed():
    for change in ("revision", "auth", "tenant", "ack"):
        access, source, session = PureAccess(), PureSource(), Session()
        store = RuleSimulationStore(access=access, source=source)
        if change == "revision":
            access.revision += 1
        elif change == "tenant":
            source.value = replace(source.value, tenant_id=uid(99))
        elif change == "ack":
            source.ack = True
        else:
            source.value = replace(source.value, auth_fingerprint="9" * 64)
        with pytest.raises(OrbitError):
            await store.prepare_inputs(session, intent())


def test_candidate_eight_tables_utf8_fk_and_twentyfour_immutable_guards_not_executed():
    sql = (
        Path(__file__).parents[2] / "docs/orbit/sql-drafts/063_rule_simulation_candidate.sql"
    ).read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE ") == 8
    assert sql.count("COLLATE=utf8mb4_0900_as_cs COMMENT=") == 8
    assert sql.count("CREATE TRIGGER ") == 24
    assert "response_bytes MEDIUMBLOB" in sql and "SHA2(response_bytes,256)=response_hash" in sql
    assert "scanned_count IS NOT NULL" in sql and "unknown_count IS NOT NULL" in sql
    assert "REFERENCES orbit_metric_capture_cell" in sql
    assert "REFERENCES orbit_rule_scope_member" in sql
    assert "DROP TRIGGER" not in sql and "FOREIGN_KEY_CHECKS" not in sql


def bound_receipt(raw, document, *, expected=None):
    expected = document if expected is None else expected
    header = {
        key: value for key, value in expected.items() if key not in {"conditions", "next_cursor"}
    }
    return OriginalSimulationReceipt.bind(
        raw,
        response_json=canonical(document),
        header=header,
        first_conditions=expected["conditions"],
        next_cursor=expected["next_cursor"],
    )


def receipt_document():
    return simulation_response(
        snapshot(),
        summary(),
        simulation_id=uid(20),
        snapshot_id=uid(21),
        sealed_at=NOW,
        conditions=[
            {
                "entity_id": uid(90),
                "condition_index": 0,
                "value": None,
                "result": "UNKNOWN",
                "reason_code": "METRIC_MISSING",
            }
        ],
        next_cursor=None,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", uid(22)),
        ("revision", 3),
        ("hash", "a" * 64),
        ("next_cursor", "another-session-cursor"),
    ],
)
def test_receipt_other_valid_document_with_its_correct_byte_hash_is_not_bound(field, value):
    original = receipt_document()
    other = {**original, field: value}
    raw = canonical(other).encode()
    import hashlib

    assert hashlib.sha256(raw).hexdigest() == digest(other)
    with pytest.raises(ValueError, match="SIMULATION_RECEIPT_BINDING_MISMATCH"):
        bound_receipt(raw, original)
    # Even a matching raw/stored pair must match the trusted header and first leaves.
    with pytest.raises(ValueError, match="SIMULATION_RECEIPT_BINDING_MISMATCH"):
        bound_receipt(raw, other, expected=original)


def test_receipt_leaf_order_and_leaf_value_are_bound_not_set_contains():
    original = receipt_document()
    original["conditions"].append({**original["conditions"][0], "condition_index": 1})
    reversed_page = {**original, "conditions": list(reversed(original["conditions"]))}
    with pytest.raises(ValueError, match="SIMULATION_RECEIPT_BINDING_MISMATCH"):
        bound_receipt(canonical(reversed_page).encode(), original)
    changed = json.loads(canonical(original))
    changed["conditions"][0]["reason_code"] = "SOURCE_MISSING"
    with pytest.raises(ValueError, match="SIMULATION_RECEIPT_BINDING_MISMATCH"):
        bound_receipt(canonical(changed).encode(), changed, expected=original)


def test_candidate_binds_raw_json_with_order_sensitive_json_equality():
    sql = (
        Path(__file__).parents[2] / "docs/orbit/sql-drafts/063_rule_simulation_candidate.sql"
    ).read_text(encoding="utf-8")
    assert "CAST(CONVERT(response_bytes USING utf8mb4) AS JSON)=response_json" in sql
    assert "CAST(CONVERT(NEW.response_bytes USING utf8mb4) AS JSON)<=>NEW.response_json" in sql
    assert "RULE_SIM_RESPONSE_BYTES_MISMATCH" in sql
