"""T1真实分块manifest；仅独占隔离库协议夹具，生产无可信provider则503。"""

import re
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api import launch_access, task_access
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_dag import _configuration_hash
from orbit_api.reference_access import managed_teams
from orbit_api.task_contract import (
    CHUNK_SIZE,
    GraphDigest,
    chunk_manifest,
    digest,
    identifier,
    node_id,
    validate_dag,
)


def conflict():
    raise OrbitError(409, "TASK_MANIFEST_CONFLICT", "任务来源版本或完整manifest不一致")


async def isolated(session, producer):
    if producer != "ISOLATED_TEST":
        raise OrbitError(
            503, "TASK_AUTHORITY_PROVIDER_UNAVAILABLE", "真实任务预检/来源授权尚未接通"
        )
    if not session.in_transaction():
        raise ValueError("任务manifest必须显式事务")
    url = session.bind.url
    database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
    if (
        url.host != "127.0.0.1"
        or url.port != 13306
        or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
    ):
        raise OrbitError(503, "TASK_ISOLATED_PRODUCER_FORBIDDEN", "测试构建器仅允许主线本轮隔离库")


async def source(session, current, plan_id, revision):
    row = (
        (
            await session.execute(
                text(
                    "SELECT p.revision current_revision,p.owner_user_id,p.owner_team_id,"
                    "v.payload_json,v.payload_hash FROM orbit_launch_plan p JOIN "
                    "orbit_launch_plan_version v "
                    "ON v.tenant_id=p.tenant_id AND v.plan_id=p.id AND v.revision=:version "
                    "WHERE p.tenant_id=:tenant AND p.id=:plan FOR SHARE OF p,v"
                ),
                {"tenant": current.tenant_id, "plan": plan_id, "version": revision},
            )
        )
        .mappings()
        .first()
    )
    if row is None or not launch_access.readable(
        current, await managed_teams(session, current), row
    ):
        raise OrbitError(404, "NOT_FOUND", "真实计划来源不存在或不可见")
    payload = _decode(row["payload_json"])
    if (
        row["current_revision"] != revision
        or payload["ownership"] != {key: row[key] for key in ("owner_user_id", "owner_team_id")}
        or launch_access.digest(payload) != row["payload_hash"]
    ):
        conflict()
    return row, payload


class TaskManifestStore:
    async def begin(
        self, session, actor, plan_id, revision, dag, request_id, *, producer="TRUSTED"
    ):
        await isolated(session, producer)
        records = validate_dag(dag)
        current = await require_business_access(session, actor, "launch", "launch.execute")
        await launch_access.clock(session, current)
        await task_access.clock(session, current, write=True)
        plan_id, request_id = identifier(plan_id, "/plan_id"), identifier(request_id, "/request_id")
        origin, payload = await source(session, current, plan_id, revision)
        if (
            dag.plan_revision != revision
            or _configuration_hash(payload) != dag.plan_input_hash
            or any(row["account_id"] not in payload["account_ids"] for row in records)
            or any(
                row["asset_id"] is not None and row["asset_id"] not in payload["asset_ids"]
                for row in records
            )
        ):
            conflict()
        chunks = chunk_manifest(records)
        manifest_hash = digest(chunks)
        old = (
            (
                await session.execute(
                    text(
                        "SELECT id,source_hash,graph_hash,manifest_hash,dag_schema_version,"
                        "plan_input_hash,allocation_input_hash FROM orbit_task "
                        "WHERE tenant_id=:tenant AND source_plan_id=:plan AND "
                        "source_revision=:version FOR UPDATE"
                    ),
                    {"tenant": current.tenant_id, "plan": plan_id, "version": revision},
                )
            )
            .mappings()
            .first()
        )
        if old:
            if (
                old["source_hash"] != origin["payload_hash"]
                or old["graph_hash"] != dag.graph_hash
                or old["manifest_hash"] != manifest_hash
                or old["dag_schema_version"] != dag.schema_version
                or old["plan_input_hash"] != dag.plan_input_hash
                or old["allocation_input_hash"] != dag.allocation_input_hash
            ):
                conflict()
            return old["id"]
        task_id = str(uuid4())
        await session.execute(
            text(
                "INSERT INTO orbit_task(tenant_id,id,owner_user_id,owner_team_id,source_plan_id,"
                "source_revision,source_hash,execution_mode,producer_kind,graph_hash,manifest_hash,"
                "expected_node_count,expected_chunk_count,accepted_request_id,created_by,"
                "created_at,updated_at,dag_schema_version,plan_input_hash,allocation_input_hash) "
                "VALUES(:tenant,:id,:owner,:team,:plan,:version,:source,:mode,:producer,:graph,:manifest,"
                ":nodes,:chunks,:request,:actor,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),:schema,:input,:allocation)"
            ),
            {
                "tenant": current.tenant_id,
                "id": task_id,
                "owner": origin["owner_user_id"],
                "team": origin["owner_team_id"],
                "plan": plan_id,
                "version": revision,
                "source": origin["payload_hash"],
                "mode": payload["execution_mode"],
                "producer": producer,
                "graph": dag.graph_hash,
                "manifest": manifest_hash,
                "nodes": len(records),
                "chunks": len(chunks),
                "request": request_id,
                "actor": actor,
                "schema": dag.schema_version,
                "input": dag.plan_input_hash,
                "allocation": dag.allocation_input_hash,
            },
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_task_chunk(tenant_id,task_id,ordinal,expected_count,expected_hash) "
                "VALUES(:tenant,:task,:ordinal,:count,:hash)"
            ),
            [
                {
                    "tenant": current.tenant_id,
                    "task": task_id,
                    "ordinal": ordinal,
                    "count": count,
                    "hash": fingerprint,
                }
                for ordinal, count, fingerprint in chunks
            ],
        )
        return task_id

    async def locked(self, session, actor, task_id):
        await isolated(session, "ISOLATED_TEST")
        current = await require_business_access(session, actor, "launch", "launch.execute")
        await launch_access.clock(session, current)
        await task_access.clock(session, current, write=True)
        row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE"
                    ),
                    {"tenant": current.tenant_id, "task": identifier(task_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["created_by"] != actor:
            raise OrbitError(404, "NOT_FOUND", "构建任务不存在或不属于当前构建者")
        origin, _payload = await source(
            session, current, row["source_plan_id"], row["source_revision"]
        )
        GraphDigest(
            row["dag_schema_version"],
            row["source_revision"],
            row["plan_input_hash"],
            row["allocation_input_hash"],
        )
        if (
            row["producer_kind"] != "ISOLATED_TEST"
            or row["source_hash"] != origin["payload_hash"]
            or any(row[key] != origin[key] for key in ("owner_user_id", "owner_team_id"))
            or row["plan_input_hash"] != _configuration_hash(_payload)
        ):
            conflict()
        return current, row

    async def append(self, session, actor, task_id, ordinal, records):
        current, task = await self.locked(session, actor, task_id)
        if type(ordinal) is not int or not 0 <= ordinal < task["expected_chunk_count"]:
            conflict()
        params = {"tenant": current.tenant_id, "task": task_id, "ordinal": ordinal}
        chunk = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_task_chunk WHERE tenant_id=:tenant AND task_id=:task "
                        "AND ordinal=:ordinal FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if (
            chunk is None
            or len(records) != chunk["expected_count"]
            or digest(records) != chunk["expected_hash"]
        ):
            conflict()
        if chunk["persisted"]:
            return
        if task["manifest_phase"] != "BUILDING" or task["node_count"] != ordinal * CHUNK_SIZE:
            conflict()
        values = [
            params
            | {
                "id": node_id(task_id, row["node_key"]),
                "position": ordinal * CHUNK_SIZE + index,
                "key": row["node_key"],
                "kind": row["kind"],
                "value": canonical(row),
            }
            for index, row in enumerate(records)
        ]
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_task_node(tenant_id,task_id,id,ordinal,node_key,kind,"
                "initial_json,updated_at) "
                "VALUES(:tenant,:task,:id,:position,:key,:kind,:value,UTC_TIMESTAMP(3))"
            ),
            values,
        )
        edges = [
            params
            | {"child": node_id(task_id, row["node_key"]), "parent": node_id(task_id, parent)}
            for row in records
            for parent in row["parent_keys"]
        ]
        if edges:
            await session.execute(
                text(
                    "INSERT INTO orbit_task_edge(tenant_id,task_id,child_id,parent_id) "
                    "VALUES(:tenant,:task,:child,:parent)"
                ),
                edges,
            )
        await session.execute(
            text(
                "UPDATE orbit_task_chunk SET persisted=1 WHERE tenant_id=:tenant AND task_id=:task "
                "AND ordinal=:ordinal"
            ),
            params,
        )
        await session.execute(
            text(
                "UPDATE orbit_task SET node_count=node_count+:nodes,edge_count=edge_count+:edges "
                "WHERE tenant_id=:tenant AND id=:task"
            ),
            params | {"nodes": len(records), "edges": len(edges)},
        )

    async def finalize(self, session, actor, task_id):
        current, task = await self.locked(session, actor, task_id)
        if task["manifest_phase"] == "COMPLETE":
            return
        params = {"tenant": current.tenant_id, "task": task_id}
        chunks = list(
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_task_chunk WHERE tenant_id=:tenant AND "
                        "task_id=:task ORDER BY ordinal"
                    ),
                    params,
                )
            ).mappings()
        )
        if (
            len(chunks) != task["expected_chunk_count"]
            or any(
                row["ordinal"] != index or not row["persisted"] for index, row in enumerate(chunks)
            )
            or digest(
                [(row["ordinal"], row["expected_count"], row["expected_hash"]) for row in chunks]
            )
            != task["manifest_hash"]
            or task["node_count"] != task["expected_node_count"]
        ):
            conflict()
        actual_nodes, actual_edges = 0, 0
        graph = GraphDigest(
            task["dag_schema_version"],
            task["source_revision"],
            task["plan_input_hash"],
            task["allocation_input_hash"],
        )
        for chunk in chunks:
            start = chunk["ordinal"] * CHUNK_SIZE
            nodes = list(
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_task_node "
                            "WHERE tenant_id=:tenant AND task_id=:task AND ordinal>=:start AND "
                            "ordinal<:end "
                            "ORDER BY ordinal"
                        ),
                        params | {"start": start, "end": start + CHUNK_SIZE},
                    )
                ).mappings()
            )
            records = [_decode(row["initial_json"]) for row in nodes]
            graph.append(records)
            if (
                len(nodes) != chunk["expected_count"]
                or digest(records) != chunk["expected_hash"]
                or any(
                    row["ordinal"] != start + i
                    or row["id"] != node_id(task_id, record["node_key"])
                    or row["node_key"] != record["node_key"]
                    or row["kind"] != record["kind"]
                    or row["state"] != "QUEUED"
                    or row["external_id"] is not None
                    or row["attempt"] != 0
                    or row["error_code"] is not None
                    or row["error_message"] is not None
                    or row["retryable"]
                    or row["configuration_state"] != "UNVERIFIED"
                    or row["delivery_state"] != "UNKNOWN"
                    for i, (row, record) in enumerate(zip(nodes, records, strict=True))
                )
            ):
                conflict()
            expected = {
                (node_id(task_id, row["node_key"]), node_id(task_id, parent))
                for row in records
                for parent in row["parent_keys"]
            }
            edges = (
                await session.execute(
                    text(
                        "SELECT child_id,parent_id FROM orbit_task_edge WHERE tenant_id=:tenant "
                        "AND task_id=:task AND child_id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    params | {"ids": [row["id"] for row in nodes]},
                )
            ).all()
            if set(edges) != expected:
                conflict()
            actual_nodes += len(nodes)
            actual_edges += len(edges)
        if (
            actual_nodes != task["node_count"]
            or actual_edges != task["edge_count"]
            or graph.count != task["expected_node_count"]
            or graph.hexdigest() != task["graph_hash"]
        ):
            conflict()
        for table, expected in (
            ("orbit_task_node", actual_nodes),
            ("orbit_task_edge", actual_edges),
        ):
            persisted_count = (
                await session.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id=:tenant AND task_id=:task"),
                    params,
                )
            ).scalar_one()
            if persisted_count != expected:
                conflict()
        event_id, audit_id = str(uuid4()), str(uuid4())
        await session.execute(
            text(
                "INSERT INTO orbit_task_event(tenant_id,task_id,event_id,sequence,task_revision,"
                "node_id,state,occurred_at,request_id) "
                "VALUES(:tenant,:task,:event,1,1,NULL,'QUEUED',"
                "UTC_TIMESTAMP(3),:request)"
            ),
            params | {"event": event_id, "request": task["accepted_request_id"]},
        )
        await session.execute(
            text(
                "UPDATE orbit_task SET "
                "manifest_phase='COMPLETE',latest_event_id=:event,latest_sequence=1,"
                "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:task"
            ),
            params | {"event": event_id},
        )
        await session.execute(
            text("UPDATE orbit_task_clock SET revision=revision+1 WHERE tenant_id=:tenant"), params
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_task_audit(id,tenant_id,task_id,actor_id,request_id,action,created_at) "
                "VALUES(:audit,:tenant,:task,:actor,:request,'MANIFEST_COMPLETE',UTC_TIMESTAMP(3))"
            ),
            params | {"audit": audit_id, "actor": actor, "request": task["accepted_request_id"]},
        )
        await session.execute(
            text(
                "INSERT INTO orbit_task_outbox(audit_id,tenant_id,task_id,created_at) "
                "VALUES(:audit,:tenant,:task,UTC_TIMESTAMP(3))"
            ),
            params | {"audit": audit_id},
        )
