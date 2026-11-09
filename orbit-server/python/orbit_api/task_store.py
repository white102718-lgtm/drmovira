"""真实已发布Task读取；列表稀疏投影，详情首200，节点有界键集和集合父读取。"""

from datetime import datetime

from sqlalchemy import bindparam, text

from orbit_api import task_access as access
from orbit_api.account_command_contract import database_time
from orbit_api.configuration_store import _decode
from orbit_api.errors import OrbitError
from orbit_api.launch_access import parameters, scope_clause
from orbit_api.task_contract import digest, identifier, node_id


def public_node(row, parents, execution_mode):
    return {
        key: row[key]
        for key in (
            "id",
            "node_key",
            "kind",
            "state",
            "external_id",
            "attempt",
            "error_code",
            "error_message",
            "configuration_state",
            "delivery_state",
        )
    } | {
        "parent_ids": parents,
        "retryable": bool(row["retryable"]),
        "updated_at": database_time(row["updated_at"]),
        "execution_mode": execution_mode,
    }


class TaskStore:
    def __init__(self, tokens):
        self.tokens = tokens

    def node_cursor(self, row, fingerprint, query, after):
        return self.tokens.issue(
            "TASK_NODE_CURSOR_V1",
            {
                "binding": digest(
                    [
                        row["tenant_id"],
                        row["id"],
                        row["revision"],
                        row["graph_hash"],
                        fingerprint,
                        query,
                    ]
                ),
                "after": after,
            },
        )

    def public(self, row, fingerprint, nodes=(), after=-1):
        query = {"q": "", "page_size": 50, "status": None, "operator_user_id": None}
        return {
            "id": row["id"],
            "revision": row["revision"],
            "ownership": {
                "owner_user_id": row["owner_user_id"],
                "owner_team_id": row["owner_team_id"],
            },
            "state": row["state"],
            "nodes": list(nodes),
            "latest_event_id": row["latest_event_id"],
            "needs_manual_reconciliation": bool(row["needs_manual_reconciliation"]),
            "created_at": database_time(row["created_at"]),
            "node_count": row["node_count"],
            "next_node_cursor": self.node_cursor(row, fingerprint, query, after)
            if after + 1 < row["node_count"]
            else None,
            "execution_mode": row["execution_mode"],
        }

    async def nodes(self, session, current, row, query, after=-1):
        clauses = ["tenant_id=:tenant", "task_id=:task", "ordinal>:after"]
        params = parameters(current) | {
            "task": row["id"],
            "after": after,
            "limit": query["page_size"] + 1,
        }
        if query["operator_user_id"] and query["operator_user_id"] != row["owner_user_id"]:
            return [], None
        if query["status"]:
            clauses.append("state=:state")
            params["state"] = query["status"]
        if query["q"]:
            clauses.append("node_key LIKE :q ESCAPE '!'")
            params["q"] = query["q"].replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_task_node WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY ordinal,id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        selected = rows[: query["page_size"]]
        parents = {node["id"]: [] for node in selected}
        if parents:
            edges = (
                await session.execute(
                    text(
                        "SELECT child_id,parent_id FROM orbit_task_edge "
                        "WHERE tenant_id=:tenant AND task_id=:task "
                        "AND child_id IN :ids ORDER BY child_id,parent_id"
                    ).bindparams(bindparam("ids", expanding=True)),
                    params | {"ids": list(parents)},
                )
            ).mappings()
            for edge in edges:
                parents[edge["child_id"]].append(edge["parent_id"])
            for node in selected:
                ordered = [
                    node_id(row["id"], key) for key in _decode(node["initial_json"])["parent_keys"]
                ]
                if set(ordered) != set(parents[node["id"]]):
                    raise OrbitError(
                        503, "TASK_MANIFEST_STATE_UNAVAILABLE", "任务父依赖无法完整核验"
                    )
                parents[node["id"]] = ordered
        return [
            public_node(node, parents[node["id"]], row["execution_mode"]) for node in selected
        ], (selected[-1]["ordinal"] if len(rows) > query["page_size"] else None)

    async def detail(self, session, actor, task_id):
        current, _version, fingerprint = await access.authorize(session, actor)
        await access.clock(session, current)
        row = await access.task(session, current, identifier(task_id))
        nodes, _next = await self.nodes(
            session,
            current,
            row,
            {
                "q": "",
                "page_size": 200,
                "status": None,
                "operator_user_id": None,
            },
        )
        return self.public(row, fingerprint, nodes, len(nodes) - 1)

    async def page_nodes(self, session, actor, task_id, query, cursor=None):
        current, version, fingerprint = await access.authorize(session, actor)
        await access.clock(session, current)
        row = await access.task(session, current, identifier(task_id))
        after = -1
        if cursor:
            claims = self.tokens.verify("TASK_NODE_CURSOR_V1", cursor)
            binding = digest(
                [
                    row["tenant_id"],
                    row["id"],
                    row["revision"],
                    row["graph_hash"],
                    fingerprint,
                    query,
                ]
            )
            after = claims.get("after")
            if (
                claims.get("binding") != binding
                or type(after) is not int
                or not -1 <= after < row["node_count"]
            ):
                access.changed()
        nodes, next_after = await self.nodes(session, current, row, query, after)
        return {
            "items": nodes,
            "next_cursor": self.node_cursor(row, fingerprint, query, next_after)
            if next_after is not None
            else None,
            "data_as_of": database_time(row["updated_at"]),
            "scope_version": version,
        }

    async def list(self, session, actor, query, cursor=None):
        current, version, fingerprint = await access.authorize(session, actor)
        watermark = await access.clock(session, current)
        binding = digest([fingerprint, watermark["revision"], query])
        clauses = [
            "t.tenant_id=:tenant",
            "t.manifest_phase='COMPLETE'",
            "(" + scope_clause(current, "t") + ")",
        ]
        params = parameters(current) | {"limit": query["page_size"] + 1}
        data_as_of = database_time(watermark["reference_at"])
        if query["operator_user_id"]:
            clauses.append("t.owner_user_id=:owner")
            params["owner"] = query["operator_user_id"]
        if query["status"]:
            clauses.append("t.state=:state")
            params["state"] = query["status"]
        if cursor:
            claims = self.tokens.verify("TASK_LIST_CURSOR_V1", cursor)
            if claims.get("binding") != binding:
                access.changed()
            after = identifier(claims.get("after"), "/cursor")
            try:
                created = datetime.fromisoformat(claims["created_at"].replace("Z", "+00:00"))
                frozen = datetime.fromisoformat(claims["data_as_of"].replace("Z", "+00:00"))
                if created.tzinfo is None or frozen.tzinfo is None:
                    raise ValueError
                if (
                    database_time(created) != claims["created_at"]
                    or database_time(frozen) != claims["data_as_of"]
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError, AttributeError):
                access.changed()
            data_as_of = claims["data_as_of"]
            clauses.append("(t.created_at>:created OR (t.created_at=:created AND t.id>:after))")
            params |= {"created": created.replace(tzinfo=None), "after": after}
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT t.* FROM orbit_task t WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY t.created_at,t.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        selected = rows[: query["page_size"]]
        return {
            "items": [self.public(row, fingerprint) for row in selected],
            "next_cursor": self.tokens.issue(
                "TASK_LIST_CURSOR_V1",
                {
                    "binding": binding,
                    "after": selected[-1]["id"],
                    "created_at": database_time(selected[-1]["created_at"]),
                    "data_as_of": data_as_of,
                },
            )
            if len(rows) > query["page_size"]
            else None,
            "data_as_of": data_as_of,
            "scope_version": version,
        }
