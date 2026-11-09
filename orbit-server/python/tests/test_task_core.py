"""T1合同与读投影纯测，真实SQL/权限由独立工具另验。"""

from dataclasses import asdict, replace
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.launch_dag import DagManifest, DagNode
from orbit_api.task_contract import (
    GraphDigest,
    chunk_manifest,
    digest,
    filters,
    node_id,
    validate_dag,
)
from orbit_api.task_manifest import isolated
from orbit_api.task_store import TaskStore

TASK, ACCOUNT, OWNER, TEAM, TENANT = (str(UUID(int=i)) for i in range(1, 6))


def dag():
    nodes = (
        DagNode(
            "campaign",
            "CAMPAIGN",
            (),
            ACCOUNT,
            "campaign",
            "/campaigns/0",
            "CREATE_PAUSED",
            "a" * 64,
        ),
        DagNode(
            "verify",
            "VERIFY",
            ("campaign",),
            ACCOUNT,
            "campaign",
            "/campaigns/0",
            "VERIFY",
            "b" * 64,
        ),
    )
    graph = digest(
        [
            1,
            1,
            "c" * 64,
            "d" * 64,
            [{k: v for k, v in asdict(row).items() if k != "source_pointer"} for row in nodes],
        ]
    )
    return DagManifest(
        1, 1, "c" * 64, "d" * 64, graph, 1, 0, 0, 2, (("CAMPAIGN", 1), ("VERIFY", 1)), (), nodes
    )


@pytest.mark.parametrize(
    "query",
    [
        {"q": "name"},
        {"page_size": "201"},
        {"page_size": "050"},
        {"status": "SCHEDULED"},
        {"operator_user_id": "bad"},
        {"cursor": ""},
        {"extra": "x"},
        {"date_from": "2026-01-01"},
        {"channel_id": ACCOUNT},
        {"metric_profile_id": ACCOUNT},
        {"entity_type": "AD"},
    ],
)
def test_unimplemented_or_invalid_filters_are_explicit(query):
    with pytest.raises(OrbitError) as failure:
        filters(query)
    if "extra" in query:
        assert failure.value.status == 400 and failure.value.code == "UNKNOWN_FIELD"
    else:
        assert failure.value.status == 422
        assert failure.value.code == "FIELD_VALIDATION_FAILED"
        assert failure.value.pointer == "/" + next(iter(query))


@pytest.mark.parametrize("q", ["x" * 101, "a\nb", "\u200b", "   "])
def test_node_text_boundary_uses_original_task_error_code_and_pointer(q):
    with pytest.raises(OrbitError) as failure:
        filters({"q": q}, nodes=True)
    assert failure.value.status == 422
    assert failure.value.code == "FIELD_VALIDATION_FAILED"
    assert failure.value.pointer == "/q"


def test_node_key_prefix_and_original_enums_page_sizes():
    value, cursor = filters(
        {"q": "camp/", "status": "BLOCKED_AUTH", "page_size": "200"}, nodes=True
    )
    assert value == {
        "q": "camp/",
        "status": "BLOCKED_AUTH",
        "page_size": 200,
        "operator_user_id": None,
    }
    assert cursor is None


def test_complete_topology_and_stable_uuid_chunk_hash():
    value = dag()
    records = validate_dag(value)
    assert len(records) == 2 and records[1]["parent_keys"] == ("campaign",)
    assert chunk_manifest(records) == [(0, 2, digest(records))]
    assert node_id(TASK, "campaign") == node_id(TASK, "campaign")
    assert node_id(TASK, "campaign") != node_id(ACCOUNT, "campaign")


def test_streaming_graph_hash_matches_original_b_canonical_bytes_across_chunks():
    value = dag()
    records = [asdict(row) for row in value.nodes]
    graph = GraphDigest(1, 1, value.plan_input_hash, value.allocation_input_hash)
    graph.append(records[:1])
    graph.append(records[1:])
    assert graph.count == 2
    assert graph.hexdigest() == value.graph_hash
    assert graph.hexdigest() == value.graph_hash  # 完成读取不破坏内部摘要状态。


@pytest.mark.parametrize(
    "schema,plan_hash,allocation_hash",
    [
        (None, None, None),
        (1, None, "a" * 64),
        (True, "a" * 64, "b" * 64),
        (1, "A" * 64, "b" * 64),
        (2, "a" * 64, "b" * 64),
    ],
)
def test_missing_or_untyped_legacy_header_never_guessed(schema, plan_hash, allocation_hash):
    with pytest.raises(OrbitError) as error:
        GraphDigest(schema, 1, plan_hash, allocation_hash)
    assert error.value.code == "TASK_DAG_HEADER_UNVERIFIED"


@pytest.mark.parametrize(
    "change",
    [
        {"nodes": ()},
        {"total_dag_node_count": 3},
        {"graph_hash": "f" * 64},
        {"nodes": tuple(reversed(dag().nodes))},
        {"nodes": (dag().nodes[0], dag().nodes[0])},
        {"nodes": (replace(dag().nodes[0], kind="SYNC"), dag().nodes[1])},
        {"nodes": (replace(dag().nodes[0], parent_keys=("verify",)), dag().nodes[1])},
    ],
)
def test_empty_partial_forged_or_cyclic_manifest_rejected(change):
    with pytest.raises(OrbitError):
        validate_dag(replace(dag(), **change))


@pytest.mark.asyncio
async def test_missing_production_provider_fails_before_touching_sql():
    with pytest.raises(OrbitError) as error:
        await isolated(None, "TRUSTED")
    assert error.value.code == "TASK_AUTHORITY_PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,port,database",
    [
        ("remote", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "production"),
    ],
)
async def test_isolated_producer_cannot_enter_production(host, port, database):
    class Result:
        def scalar_one(self):
            return database

    class Session:
        bind = SimpleNamespace(url=SimpleNamespace(host=host, port=port))

        def in_transaction(self):
            return True

        async def execute(self, *args):
            return Result()

    with pytest.raises(OrbitError) as error:
        await isolated(Session(), "ISOLATED_TEST")
    assert error.value.status == 503


@pytest.mark.asyncio
async def test_manifest_requires_outer_transaction_before_any_sql():
    with pytest.raises(ValueError):
        await isolated(SimpleNamespace(bind=None, in_transaction=lambda: False), "ISOLATED_TEST")


def test_sparse_task_list_is_complete_persistent_count_and_signed_first_node_cursor():
    issued = []

    class Tokens:
        def issue(self, purpose, claims):
            issued.append((purpose, claims))
            return "signed"

    row = {
        "tenant_id": TENANT,
        "id": TASK,
        "revision": 1,
        "owner_user_id": OWNER,
        "owner_team_id": TEAM,
        "state": "QUEUED",
        "latest_event_id": ACCOUNT,
        "needs_manual_reconciliation": 0,
        "created_at": datetime(2026, 11, 8),
        "node_count": 1206,
        "graph_hash": "a" * 64,
        "execution_mode": "META_API",
    }
    value = TaskStore(Tokens()).public(row, "current-auth")
    assert value["nodes"] == [] and value["node_count"] == 1206
    assert value["next_node_cursor"] == "signed"
    assert value["ownership"] == {"owner_user_id": OWNER, "owner_team_id": TEAM}
    assert issued[0][0] == "TASK_NODE_CURSOR_V1" and issued[0][1]["after"] == -1


def test_real_tool_fixture_compiles_nonempty_original_b_dag_and_normalized_source_hash():
    import importlib.util
    from pathlib import Path

    location = Path(__file__).resolve().parents[2] / "tools/task_core_fixture.py"
    spec = importlib.util.spec_from_file_location("task_core_fixture_pure", location)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    value = fixture.plan(OWNER, TEAM)
    graph = fixture.compile_dag(value)
    records = validate_dag(graph)
    assert len(records) == 1206
    assert {row["kind"] for row in records} == {
        "UPLOAD",
        "CAMPAIGN",
        "ADSET",
        "CREATIVE",
        "AD",
        "VERIFY",
    }
    assert graph.execution_authorized is False
