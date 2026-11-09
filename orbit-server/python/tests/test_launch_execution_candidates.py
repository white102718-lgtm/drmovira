"""候选目录纯协议与真实规范编码测试；无MySQL/平台/生产issuer。"""

import copy
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
from test_launch_execution_lease_contract import NOW

import orbit_api.launch_execution_candidates as module
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.task_contract import GraphDigest, node_id


def uid(value):
    return str(UUID(int=value))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def fragments(payload, size=1):
    for offset in range(0, len(payload), size):
        yield payload[offset : offset + size]


@pytest.mark.asyncio
async def test_json_unicode_escapes_numbers_and_utf8_split_every_byte():
    document = {
        "x": '中文😀\\"\n',
        "n": 1234567,
        "nodes": [{"node_key": "甲😀"}, {"value": -12.25e3}],
    }
    rows = [
        row
        async for row in module._JsonStream(
            fragments(json.dumps(document, ensure_ascii=False).encode())
        ).records()
    ]
    assert rows == [
        ("x", document["x"]),
        ("n", 1234567),
        ("node", document["nodes"][0]),
        ("node", document["nodes"][1]),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        b'{"nodes":[],"nodes":[]}',
        b'{"nodes":[{"x":1,"x":2}]}',
        b'{"nodes":[]}{}',
        b'{"nodes":[',
        b'{"nodes":[]',
        b'{"nodes":[1,]}',
        b'{"nodes":[],}',
        b'{"nodes":[],"x":NaN}',
        b'{"nodes":[],"x":Infinity}',
        b'{"x":1}',
        b'{"nodes":true}',
        b'{"nodes":[1e]}',
        b'{"nodes":[],"x":"bad\x00text"}',
        b'{"nodes":[],"x":"\xff"}',
        b'{"nodes":[],"x":"\\ud800"}',
    ],
)
async def test_json_bad_input_fails_closed(payload):
    with pytest.raises((OrbitError, UnicodeError)):
        _ = [row async for row in module._JsonStream(fragments(payload)).records()]


@pytest.mark.asyncio
async def test_json_memory_budget_is_internal_503_not_business_field_limit(monkeypatch):
    monkeypatch.setattr(module, "VALUE_MEMORY_BUDGET", 128)
    with pytest.raises(OrbitError) as caught:
        _ = [
            row
            async for row in module._JsonStream(
                fragments(json.dumps({"nodes": [], "x": "x" * 256}).encode(), 32)
            ).records()
        ]
    assert caught.value.status == 503 and caught.value.code == "EXECUTION_DIRECTORY_MEMORY_BUDGET"


def fixture():
    tenant, task_id, prep_id = uid(1), uid(2), uid(3)
    owner, team = uid(4), uid(5)
    source = {
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
        "name": "中文计划",
        "execution_mode": "META_API",
    }
    originals = []
    for key, parents in [("root", []), ("child", ["root"])]:
        originals.append(
            dict(
                node_key=key,
                kind="CAMPAIGN",
                parent_keys=parents,
                account_id=uid(9),
                target_key=key,
                source_pointer="/campaigns/0",
                purpose="CREATE",
                configuration_hash="a" * 64,
                asset_id=None,
                asset_revision=None,
            )
        )
    documents = [
        original
        | {
            "resolved_configuration": {"name": original["node_key"]},
            "resolved_configuration_hash": sha({"name": original["node_key"]}),
        }
        for original in originals
    ]
    graph = GraphDigest(1, 1, "b" * 64, "c" * 64)
    graph.append(originals)
    heads = [(0, 2, sha(originals))]
    task = dict(
        tenant_id=tenant,
        id=task_id,
        revision=2,
        owner_user_id=owner,
        owner_team_id=team,
        source_plan_id=uid(6),
        source_revision=1,
        source_hash=sha(source),
        execution_mode="META_API",
        state="RUNNING",
        manifest_phase="COMPLETE",
        graph_hash=graph.hexdigest(),
        manifest_hash=sha(heads),
        expected_node_count=2,
        expected_chunk_count=1,
        node_count=2,
        edge_count=1,
        dag_schema_version=1,
        plan_input_hash="b" * 64,
        allocation_input_hash="c" * 64,
    )
    observation = [{"kind": "EXPLICIT_TEST_NOT_AUTHORITY", "revision": 1}]
    document = dict(
        schema_version=1,
        tenant_id=tenant,
        plan_id=task["source_plan_id"],
        plan_revision=1,
        source_payload_hash=task["source_hash"],
        validation_hash="d" * 64,
        source_payload=source,
        observation_refs=observation,
        dag=dict(
            node_count=2,
            graph_hash=task["graph_hash"],
            plan_input_hash=task["plan_input_hash"],
            allocation_input_hash=task["allocation_input_hash"],
        ),
        nodes=documents,
    )
    encoded = canonical(document).encode()
    byte_chunks = [
        dict(
            ordinal=index,
            payload=payload,
            byte_length=len(payload),
            chunk_hash=hashlib.sha256(payload).hexdigest(),
        )
        for index, payload in enumerate(
            [encoded[offset : offset + 31] for offset in range(0, len(encoded), 31)]
        )
    ]
    prep = dict(
        tenant_id=tenant,
        id=prep_id,
        task_id=task_id,
        plan_id=task["source_plan_id"],
        source_revision=1,
        payload_hash=task["source_hash"],
        state="ACCEPTED",
        actor_id=1,
        subject_id=uid(7),
        owner_user_id=owner,
        owner_team_id=team,
        manifest_schema_version=1,
        manifest_hash=hashlib.sha256(encoded).hexdigest(),
        task_chunk_hash=task["manifest_hash"],
        graph_hash=task["graph_hash"],
        plan_input_hash=task["plan_input_hash"],
        allocation_input_hash=task["allocation_input_hash"],
        sealed_at=NOW,
        sealed_revision=1,
        accepted_at=NOW,
        validation_id=uid(8),
        validation_hash="d" * 64,
        intent_hash="e" * 64,
        validated_head_revision=2,
        accepted_head_revision=3,
        accepted_request_id=uid(10),
    )
    for suffix, count in [
        ("bytes", len(encoded)),
        ("byte_chunks", len(byte_chunks)),
        ("node_count", 2),
        ("node_chunks", 1),
        ("command_count", 2),
        ("edge_count", 1),
    ]:
        prep["expected_" + suffix] = prep["persisted_" + suffix] = count
    accepted = dict(
        tenant_id=tenant,
        plan_id=prep["plan_id"],
        source_revision=1,
        task_id=task_id,
        preparation_id=prep_id,
        validation_id=prep["validation_id"],
        validated_head_revision=2,
        submitted_head_revision=3,
        validation_hash=prep["validation_hash"],
        manifest_hash=prep["manifest_hash"],
        intent_hash=prep["intent_hash"],
        accepted_request_id=prep["accepted_request_id"],
        accepted_by=1,
    )
    nodes, commands = [], []
    for ordinal, original in enumerate(originals):
        node = dict(
            tenant_id=tenant,
            task_id=task_id,
            id=node_id(task_id, original["node_key"]),
            ordinal=ordinal,
            node_key=original["node_key"],
            kind=original["kind"],
            state="SUCCEEDED" if ordinal == 0 else "QUEUED",
            attempt=0,
            initial_json=copy.deepcopy(original),
        )
        command = dict(
            tenant_id=tenant,
            task_id=task_id,
            node_id=node["id"],
            preparation_id=prep_id,
            ordinal=ordinal,
            node_key=node["node_key"],
            kind=node["kind"],
            state=node["state"],
            attempt=0,
            purpose=original["purpose"],
            account_id=original["account_id"],
            target_key=original["target_key"],
            resolved_configuration_json=documents[ordinal]["resolved_configuration"],
            resolved_configuration_hash=documents[ordinal]["resolved_configuration_hash"],
            observation_binding_hash=sha(observation),
        )
        nodes.append(node)
        commands.append(command)
    grant = module.CandidateGrant(
        tenant,
        task_id,
        1,
        prep["subject_id"],
        owner,
        team,
        1,
        1,
        task["source_hash"],
        prep["manifest_hash"],
        prep["intent_hash"],
        NOW + timedelta(hours=1),
    )
    return dict(
        task=task,
        prep=prep,
        accepted=accepted,
        nodes=nodes,
        commands=commands,
        byte_chunks=byte_chunks,
        heads=heads,
        grant=grant,
        source=source,
        runtimes=[],
        attempts=[],
        edge_rows=[
            dict(
                child_id=nodes[1]["id"], parent_id=nodes[0]["id"], parent_ordinal=0, child_ordinal=1
            )
        ],
    )


class Result:
    def __init__(self, values):
        self.values = values

    def mappings(self):
        return self

    def __iter__(self):
        if not self.values:
            return iter(())
        keys = tuple(self.values[0])
        return iter(
            IteratorResult(
                SimpleResultMetaData(keys),
                iter(tuple(row[key] for key in keys) for row in self.values),
            ).mappings()
        )


class Session:
    def __init__(self, data):
        self.data, self.transaction, self.queries = data, None, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        assert self.transaction is None

    def in_transaction(self):
        return self.transaction is not None

    def get_transaction(self):
        return self.transaction

    def begin(self):
        return Transaction(self)

    async def execute(self, sql, params):
        sql = " ".join(str(sql).split())
        self.queries.append((sql, params))
        assert sql.startswith("SELECT ")
        d = self.data
        if "UTC_TIMESTAMP" in sql:
            rows = [{"now": NOW.replace(tzinfo=None)}]
        elif "FROM orbit_task_clock" in sql:
            rows = [{"revision": 1}]
        elif "FROM orbit_task WHERE" in sql:
            rows = [d["task"]]
        elif "FROM orbit_launch_execution_preparation" in sql:
            rows = [d["prep"]]
        elif "FROM orbit_launch_execution_acceptance" in sql:
            rows = [d["accepted"]]
        elif "FROM orbit_launch_plan_version" in sql:
            rows = [{"payload_hash": d["task"]["source_hash"], "payload_json": d["source"]}]
        elif "FROM orbit_launch_execution_byte_chunk" in sql:
            rows = [row for row in d["byte_chunks"] if row["ordinal"] >= params["after"]][:16]
        elif sql.startswith("SELECT CAST(COALESCE(SUM"):
            values = [
                len(canonical(node["initial_json"]).encode())
                + len(canonical(command["resolved_configuration_json"]).encode())
                for node, command in zip(d["nodes"], d["commands"], strict=True)
                if params["after"] <= node["ordinal"] < params["end"]
            ]
            rows = [{"storage_bytes": sum(values)}]
        elif sql.startswith("SELECT n.*"):
            rows = []
            for node, command in zip(d["nodes"], d["commands"], strict=True):
                if node["ordinal"] >= params["after"]:
                    rows.append(
                        node
                        | {
                            key: command[key]
                            for key in (
                                "preparation_id",
                                "node_id",
                                "purpose",
                                "account_id",
                                "target_key",
                                "resolved_configuration_json",
                                "resolved_configuration_hash",
                                "observation_binding_hash",
                            )
                        }
                        | {
                            "command_kind": command["kind"],
                            "command_node_key": command["node_key"],
                            "command_ordinal": command["ordinal"],
                        }
                    )
            rows = rows[: params["limit"]]
        elif sql.startswith("SELECT e.child_id,e.parent_id"):
            rows = [row for row in d["edge_rows"] if row["child_id"] in params["ids"]]
        elif sql.startswith("SELECT DISTINCT"):
            rows = [
                {"observation_binding_hash": value}
                for value in sorted({row["observation_binding_hash"] for row in d["commands"]})
            ]
        elif "FROM orbit_task_chunk" in sql and not sql.startswith("SELECT COUNT"):
            rows = [
                dict(ordinal=o, expected_count=n, expected_hash=h, persisted=1)
                for o, n, h in d["heads"]
            ]
        elif sql.startswith("SELECT COUNT"):
            table = sql.split(" FROM ")[1].split()[0]
            rows = [
                {
                    "n": len(
                        d[
                            {
                                "orbit_task_node": "nodes",
                                "orbit_launch_execution_command": "commands",
                                "orbit_task_edge": "edge_rows",
                                "orbit_task_chunk": "heads",
                            }[table]
                        ]
                    )
                }
            ]
        elif "FROM orbit_task_node WHERE" in sql:
            assert sql.startswith("SELECT id,ordinal,kind,state,attempt FROM")
            rows = [row for row in d["nodes"] if row["ordinal"] > params["after"]][
                : params["limit"]
            ]
            rows = [
                {key: row[key] for key in ("id", "ordinal", "kind", "state", "attempt")}
                for row in rows
            ]
        elif sql.startswith("SELECT a.*"):
            rows = d["attempts"]
        elif "FROM orbit_execution_command_runtime WHERE" in sql:
            rows = d["runtimes"]
        elif sql.startswith("SELECT e.child_id,p.state"):
            states = {row["id"]: row["state"] for row in d["nodes"]}
            rows = [
                dict(child_id=row["child_id"], state=states[row["parent_id"]])
                for row in d["edge_rows"]
                if row["child_id"] in params["ids"]
            ]
        elif "FROM orbit_launch_execution_command WHERE" in sql:
            rows = [row for row in d["commands"] if row["node_id"] in params["ids"]]
            assert sql.startswith(
                "SELECT node_id,state,attempt,resolved_configuration_hash,"
                "account_id,target_key FROM"
            )
            rows = [
                {
                    key: row[key]
                    for key in (
                        "node_id",
                        "state",
                        "attempt",
                        "resolved_configuration_hash",
                        "account_id",
                        "target_key",
                    )
                }
                for row in rows
            ]
        else:
            raise AssertionError(sql)
        return Result(copy.deepcopy(rows))


class Transaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.transaction = self

    async def __aexit__(self, *args):
        self.session.transaction = None


class Authority(module.ExecutionCandidateAuthority):
    def __init__(self, grant):
        self.grant = grant
        self.calls = 0

    async def capture(self, task_id):
        return self.grant

    async def revalidate(self, session, grant):
        self.calls += 1
        return self.grant


@pytest.mark.asyncio
async def test_default_unavailable_before_database_factory():
    factory = Mock()
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(sessions_factory=factory).page(uid(2))
    assert caught.value.status == 503
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_complete_stream_original_hash_graph_parent_ready_and_readonly():
    data = fixture()
    session = Session(data)
    authority = Authority(data["grant"])
    reader = module.ExecutionCandidateDirectory(authority, lambda: session, clock=lambda: NOW)
    page = await reader.page(data["task"]["id"], limit=20)
    assert len(page.items) == 1 and page.items[0].node_id == data["nodes"][1]["id"]
    assert page.raw_rows == 2 and page.next_ordinal is None and page.execution_authorized is False
    assert session.transaction is None and authority.calls == 2
    assert "orbit_task_clock" in session.queries[0][0] and "FOR SHARE" in session.queries[0][0]
    assert "FROM orbit_task WHERE" in session.queries[1][0]
    assert "orbit_launch_execution_preparation" in session.queries[2][0]
    assert all(sql.startswith("SELECT ") for sql, _ in session.queries)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "bad_bytes",
        "missing_tail",
        "bad_graph",
        "missing_edge",
        "back_edge",
        "bad_configuration",
        "bad_command_kind",
        "bad_chunk_root",
        "bad_intent",
        "source_owner",
        "extra_node",
        "unknown_parent",
        "command_state",
    ],
)
async def test_corruption_never_returns_partial_candidate(change):
    data = fixture()
    if change == "bad_bytes":
        data["byte_chunks"][-1]["payload"] += b"x"
    elif change == "missing_tail":
        data["byte_chunks"].pop()
    elif change == "bad_graph":
        data["task"]["graph_hash"] = data["prep"]["graph_hash"] = "f" * 64
    elif change == "missing_edge":
        data["edge_rows"] = []
    elif change == "back_edge":
        data["edge_rows"][0]["parent_ordinal"] = 2
    elif change == "bad_configuration":
        data["commands"][1]["resolved_configuration_json"] = {"name": "forged"}
    elif change == "bad_command_kind":
        data["commands"][1]["kind"] = "ENABLE"
    elif change == "bad_chunk_root":
        data["heads"][0] = (0, 2, "f" * 64)
    elif change == "bad_intent":
        data["accepted"]["intent_hash"] = "f" * 64
    elif change == "source_owner":
        data["source"]["ownership"]["owner_user_id"] = uid(20)
    elif change == "extra_node":
        data["nodes"].append(copy.deepcopy(data["nodes"][-1]))
    elif change == "unknown_parent":
        data["edge_rows"][0]["parent_ordinal"] = None
    else:
        data["commands"][1]["state"] = "CANCELLED"
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
        ).page(data["task"]["id"])
    assert caught.value.status == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "CANCELLED",
        "UNKNOWN",
        "SUCCEEDED",
        "FAILED",
        "RETRY_WAIT",
        "EXPIRED",
        "BLOCKED_AUTH",
        "NEEDS_HUMAN",
    ],
)
async def test_terminal_unknown_or_retry_nodes_never_revived(state):
    data = fixture()
    data["nodes"][1]["state"] = data["commands"][1]["state"] = state
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
    ).page(data["task"]["id"])
    assert page.items == ()


@pytest.mark.asyncio
async def test_failed_parent_filters_queued_child_without_fabricating_failure():
    data = fixture()
    data["nodes"][0]["state"] = data["commands"][0]["state"] = "FAILED"
    original = copy.deepcopy(data)
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
    ).page(data["task"]["id"], after_ordinal=0)
    assert page.items == () and page.raw_rows == 1 and data == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 1},
        {"limit": True},
        {"after_ordinal": True},
        {"after_ordinal": -1},
        {"after_ordinal": "0"},
        {"after_ordinal": 100000},
    ],
)
async def test_bad_cursor_or_size_before_factory(kwargs):
    data = fixture()
    factory = Mock()
    with pytest.raises(ValueError):
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), factory, clock=lambda: NOW
        ).page(uid(2), **kwargs)
    factory.assert_not_called()


@pytest.mark.parametrize("permission", ["tasks.read", "tasks.reconcile", "launch.edit", "TRUSTED"])
def test_grant_permission_cannot_be_substituted(permission):
    with pytest.raises(ValueError):
        replace(fixture()["grant"], permission=permission)


def initial_runtime(data):
    return dict(
        node_id=data["nodes"][1]["id"],
        revision=1,
        active_attempt=None,
        fencing_token=0,
        claim_id=None,
        worker_id=None,
        lease_expires_at=None,
        unknown_since=None,
        last_reconciled_at=None,
        next_reconcile_at=None,
        needs_manual_reconciliation=0,
    )


@pytest.mark.asyncio
async def test_initial_runtime_is_readonly_revision_hint_not_new_claim():
    data = fixture()
    data["runtimes"] = [initial_runtime(data)]
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
    ).page(uid(2))
    assert len(page.items) == 1 and page.items[0].runtime_revision == 1
    assert data["runtimes"][0]["active_attempt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("fencing_token", 1),
        ("claim_id", uid(50)),
        ("worker_id", uid(51)),
        ("lease_expires_at", NOW),
        ("unknown_since", NOW),
        ("needs_manual_reconciliation", 1),
        ("revision", True),
    ],
)
async def test_unclaimed_runtime_cannot_hide_old_or_partial_binding(field, value):
    data = fixture()
    runtime = initial_runtime(data)
    runtime[field] = value
    data["runtimes"] = [runtime]
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
        ).page(uid(2))
    assert caught.value.status == 503


def active(data):
    runtime = initial_runtime(data)
    runtime.update(
        active_attempt=1,
        fencing_token=1,
        claim_id=uid(50),
        worker_id=uid(51),
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    data["runtimes"] = [runtime]
    data["nodes"][1].update(attempt=1, state="RUNNING")
    data["commands"][1].update(attempt=1, state="RUNNING")
    grant, prep, command = data["grant"], data["prep"], data["commands"][1]
    attempt = dict(
        tenant_id=grant.tenant_id,
        task_id=grant.task_id,
        node_id=runtime["node_id"],
        preparation_id=prep["id"],
        attempt_no=1,
        fencing_token=1,
        claim_id=runtime["claim_id"],
        worker_id=runtime["worker_id"],
        execution_mode=data["task"]["execution_mode"],
        command_hash=command["resolved_configuration_hash"],
        manifest_hash=prep["manifest_hash"],
        source_hash=grant.source_hash,
        authority_hash="a" * 64,
        authorization_hash="b" * 64,
        actor_id=grant.actor_id,
        subject_id=grant.subject_id,
        owner_user_id=grant.owner_user_id,
        owner_team_id=grant.owner_team_id,
        auth_version=grant.auth_revision,
    )
    data["attempts"] = [attempt]
    return runtime, attempt


@pytest.mark.asyncio
async def test_current_active_binding_verified_but_never_reclaimed():
    data = fixture()
    active(data)
    original = copy.deepcopy(data)
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
    ).page(uid(2))
    assert page.items == () and data == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("fencing_token", 2),
        ("attempt_no", 2),
        ("claim_id", uid(99)),
        ("worker_id", uid(99)),
        ("preparation_id", uid(99)),
        ("owner_user_id", uid(99)),
        ("owner_team_id", uid(99)),
        ("subject_id", uid(99)),
        ("actor_id", 2),
        ("source_hash", "f" * 64),
        ("manifest_hash", "f" * 64),
        ("command_hash", "f" * 64),
        ("execution_mode", "ADSPOWER_UI"),
    ],
)
async def test_active_generation_binding_mismatch_is_not_silently_filtered(field, value):
    data = fixture()
    _, attempt = active(data)
    attempt[field] = value
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
        ).page(uid(2))
    assert caught.value.status == 503


@pytest.mark.asyncio
async def test_current_authority_drift_after_stream_discards_whole_page():
    data = fixture()

    class Changing(Authority):
        async def revalidate(self, session, grant):
            self.calls += 1
            return grant if self.calls == 1 else replace(grant, auth_revision=2)

    session = Session(data)
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Changing(data["grant"]), lambda: session, clock=lambda: NOW
        ).page(uid(2))
    assert caught.value.code == "EXECUTION_DIRECTORY_AUTHORITY_CHANGED"
    assert session.transaction is None


@pytest.mark.asyncio
async def test_final_sql_time_expiry_fails_even_if_application_clock_behind():
    data = fixture()

    class LateSql(Session):
        async def execute(self, sql, params):
            if "UTC_TIMESTAMP" in str(sql):
                return Result([{"now": data["grant"].expires_at.replace(tzinfo=None)}])
            return await super().execute(sql, params)

    with pytest.raises(OrbitError):
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: LateSql(data), clock=lambda: NOW
        ).page(uid(2))


@pytest.mark.asyncio
async def test_small_memory_batches_preserve_real_chunk_and_graph_root(monkeypatch):
    monkeypatch.setattr(module, "BATCH_MEMORY_BUDGET", 700)
    data = fixture()
    session = Session(data)
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: session, clock=lambda: NOW
    ).page(uid(2))
    assert len(page.items) == 1
    reads = [(sql, params) for sql, params in session.queries if sql.startswith("SELECT n.*")]
    assert len(reads) == 2 and all(params["limit"] == 1 for _, params in reads)


@pytest.mark.asyncio
async def test_storage_budget_checked_before_loading_json_payloads():
    data = fixture()

    class Oversized(Session):
        async def execute(self, sql, params):
            if str(sql).startswith("SELECT CAST(COALESCE(SUM"):
                return Result([{"storage_bytes": module.BATCH_MEMORY_BUDGET * 2 + 1}])
            return await super().execute(sql, params)

    session = Oversized(data)
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: session, clock=lambda: NOW
        ).page(uid(2))
    assert caught.value.code == "EXECUTION_DIRECTORY_MEMORY_BUDGET"
    assert not any(sql.startswith("SELECT n.*") for sql, _ in session.queries)


@pytest.mark.asyncio
async def test_integrity_proof_cannot_cross_session_transaction_identity():
    data = fixture()

    class ChangedTransaction(Session):
        observed = False

        def get_transaction(self):
            if self.observed:
                return object()
            self.observed = True
            return self.transaction

    session = ChangedTransaction(data)
    with pytest.raises(OrbitError):
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: session, clock=lambda: NOW
        ).page(uid(2))
    assert session.transaction is None


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [20, 50, 100, 200])
async def test_four_original_page_sizes_keep_raw_keyset_and_current_bindings(limit):
    data = fixture()
    session = Session(data)
    page = await module.ExecutionCandidateDirectory(
        Authority(data["grant"]), lambda: session, clock=lambda: NOW
    ).page(uid(2), after_ordinal=0, limit=limit)
    assert page.raw_rows == 1 and page.items[0].ordinal == 1
    query = [(sql, params) for sql, params in session.queries if "ordinal>:after" in sql]
    assert len(query) == 1 and query[0][1]["after"] == 0 and query[0][1]["limit"] == limit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["building", "unaccepted", "mode", "unknown_dag", "partial_count"]
)
async def test_incomplete_or_wrong_origin_is_not_candidate(change):
    data = fixture()
    if change == "building":
        data["task"]["manifest_phase"] = "BUILDING"
    elif change == "unaccepted":
        data["prep"]["state"] = "SEALED"
    elif change == "mode":
        data["task"]["execution_mode"] = "ADSPOWER_UI"
    elif change == "unknown_dag":
        data["task"]["dag_schema_version"] = None
    else:
        data["prep"]["persisted_command_count"] -= 1
    with pytest.raises(OrbitError) as caught:
        await module.ExecutionCandidateDirectory(
            Authority(data["grant"]), lambda: Session(data), clock=lambda: NOW
        ).page(uid(2))
    assert caught.value.status == 503
