"""设备登记控制面：当前权限、CAS和同事务审计，不执行任何localhost网络请求。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api import execution_agent_access as access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.errors import OrbitError
from orbit_api.execution_agent_contract import public_agent
from orbit_api.reference_access import managed_teams, scope_version
from orbit_api.reference_contract import uuid_value

# 查询谓词和公开回读采用同一45/90秒衰减；恢复首条仍由持久SUSPECT阻止假在线。
LIVE_STATE_SQL = (
    "CASE WHEN g.state='REVOKED' THEN 'REVOKED' "
    "WHEN g.last_heartbeat IS NULL OR g.last_heartbeat<=UTC_TIMESTAMP(6)-INTERVAL 90 SECOND "
    "THEN 'OFFLINE' WHEN g.last_heartbeat<=UTC_TIMESTAMP(6)-INTERVAL 45 SECOND "
    "THEN 'SUSPECT' ELSE g.state END"
)
COLUMNS = "g.id,g.name,g.endpoint,g.probe_interval,g.revision,g.state,g.last_heartbeat"


class ExecutionAgentStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def capabilities(self, session, actor, authorization, operation="READ"):
        actions = {"READ": "read", "ENROLL": "enroll", "REVOKE": "revoke", "PROBE": "probe"}
        if operation not in actions:
            raise OrbitError(422, "FIELD_INVALID", "设备操作类型无效", "/operation")
        current = await access.context(
            session, actor, "environments." + actions[operation], write=operation != "READ"
        )
        return {
            "actor_id": current.actor_id,
            "tenant_id": current.tenant_id,
            "data_role": current.data_role,
            "csrf_token": None
            if operation == "READ"
            else self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
        }

    async def row(self, session, current, identifier, *, write=False):
        identifier = uuid_value(identifier, "/id")
        row = (
            (
                await session.execute(
                    text(
                        f"SELECT {COLUMNS} FROM orbit_execution_agent g "
                        "WHERE g.tenant_id=:tenant AND g.id=:id "
                        "AND ("
                        + access.visibility_clause(current)
                        + ") "
                        + ("FOR UPDATE" if write else "FOR SHARE")
                    ),
                    access.parameters(current) | {"id": identifier},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "设备不存在或当前不可见")
        return row

    async def get(self, session, actor, identifier):
        current = await access.context(session, actor, "environments.read")
        await access.clock(session, current)
        return public_agent(await self.row(session, current, identifier))

    async def list(self, session, actor, filters, cursor=None):
        current = await access.context(session, actor, "environments.read")
        for key in ("channel_id", "metric_profile_id", "entity_type"):
            if key in filters:
                raise OrbitError(
                    503,
                    "ENVIRONMENT_FILTER_DEPENDENCY_UNAVAILABLE",
                    "环境关联筛选来源尚未接通",
                    "/" + key,
                )
        # 目录授权先于账户/设备clock，游标绑定权限、两级数据水位和完整筛选。
        directory_revision = await scope_version(session, current)
        teams = await managed_teams(session, current)
        revision = await access.clock(session, current)
        account_revision = (
            await session.execute(
                text("SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant FOR SHARE"),
                access.parameters(current),
            )
        ).scalar_one()
        binding = access.digest(
            [
                current.actor_id,
                current.tenant_id,
                current.data_role,
                current.subject_id,
                teams,
                directory_revision,
                account_revision,
                revision,
                filters,
            ]
        )
        after = ""
        as_of = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        if cursor:
            claims = self.tokens.verify("EXECUTION_AGENT_CURSOR_V1", cursor)
            if claims.get("binding") != binding:
                raise OrbitError(409, "SCOPE_CHANGED", "设备目录或账户范围已变化，请重新查询")
            after = uuid_value(claims.get("after"), "/cursor")
            as_of = claims["data_as_of"]
        where = [
            "g.tenant_id=:tenant",
            "g.id>:after",
            "(" + access.visibility_clause(current) + ")",
        ]
        values = access.parameters(current) | {"after": after, "limit": filters["page_size"] + 1}
        if filters.get("q"):
            where.append("(LOCATE(:q,g.name)>0 OR LOCATE(:q,g.id)>0)")
            values["q"] = filters["q"]
        if filters.get("status"):
            where.append("(" + LIVE_STATE_SQL + ")=:status")
            values["status"] = filters["status"]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if field in filters:
                where.append("g.created_at" + operator + ":" + field)
                values[field] = filters[field]
        if "operator_user_id" in filters:
            where.append(
                "EXISTS(SELECT 1 FROM orbit_profile_binding ob JOIN orbit_ad_account oa "
                "ON oa.tenant_id=ob.tenant_id AND oa.id=ob.account_id "
                "WHERE ob.tenant_id=g.tenant_id "
                "AND ob.agent_id=g.id AND ob.unbound_at IS NULL AND oa.unbound_at IS NULL "
                "AND oa.owner_user_id=ob.owner_user_id AND oa.owner_team_id=ob.owner_team_id "
                "AND oa.owner_user_id=:operator AND ("
                + access.account_access.visible_clause(current, "oa").replace(
                    "AND tm.enabled=1)", "AND tm.enabled=1 FOR SHARE)"
                )
                + ") FOR SHARE)"
            )
            values["operator"] = filters["operator_user_id"]
        rows = (
            (
                await session.execute(
                    text(
                        f"SELECT {COLUMNS} FROM orbit_execution_agent g WHERE "
                        + " AND ".join(where)
                        + " ORDER BY g.id LIMIT :limit FOR SHARE"
                    ),
                    values,
                )
            )
            .mappings()
            .all()
        )
        size = filters["page_size"]
        token = None
        if len(rows) > size:
            token = self.tokens.issue(
                "EXECUTION_AGENT_CURSOR_V1",
                {"binding": binding, "after": rows[size - 1]["id"], "data_as_of": as_of},
            )
        return {
            "items": [public_agent(row) for row in rows[:size]],
            "next_cursor": token,
            "data_as_of": as_of,
            "scope_version": revision,
        }

    async def save(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        value,
        identifier,
        expected,
        request_id,
        *,
        mode="save",
    ):
        action = "revoke" if mode == "revoke" else "enroll"
        current = await access.context(session, actor, "environments." + action, write=True)
        access.verify_csrf(self.tokens, current, authorization, csrf)
        await access.clock(session, current, write=True)
        operation = (
            "agent.revoke" if mode == "revoke" else "agent.update" if identifier else "agent.create"
        )
        intent = access.digest([identifier, expected, value])
        saved = await access.replay(session, current, operation, key, intent)
        if saved is not None:
            await self.row(session, current, saved["id"])
            return saved
        previous = await self.row(session, current, identifier, write=True) if identifier else None
        if previous:
            if previous["revision"] != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "设备已被修改，请重新加载")
            if previous["state"] == "REVOKED":
                raise OrbitError(409, "AGENT_REVOKED", "设备已撤销，不能继续修改")
            if previous["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "设备版本已达上限")
            if mode == "save" and all(
                previous[k] == value[k] for k in ("name", "endpoint", "probe_interval")
            ):
                result = public_agent(previous)
                await access.remember(session, current, operation, key, intent, result)
                return result
        elif mode == "revoke":
            raise OrbitError(404, "NOT_FOUND", "设备不存在")
        identifier = identifier or str(uuid4())
        revision = previous["revision"] + 1 if previous else 1
        params = access.parameters(current) | {"id": identifier, "revision": revision}
        if previous:
            if mode == "revoke":
                await session.execute(
                    text(
                        "UPDATE orbit_execution_agent SET state='REVOKED',revision=:revisi"
                        "on,updated_at=UTC_TIMESTAMP(6) WHERE tenant_id=:tenant AND id=:id"
                    ),
                    params,
                )
            else:
                await session.execute(
                    text(
                        "UPDATE orbit_execution_agent SET name=:name,endpoint=:endpoint,pr"
                        "obe_interval=:probe_interval,revision=:revision,updated_at=UTC_TI"
                        "MESTAMP(6) WHERE tenant_id=:tenant AND id=:id"
                    ),
                    params | value,
                )
        else:
            await session.execute(
                text(
                    "INSERT INTO orbit_execution_agent(tenant_id,id,name,endpoint,prob"
                    "e_interval,revision,state,last_heartbeat,created_at,updated_at) V"
                    "ALUES(:tenant,:id,:name,:endpoint,:probe_interval,1,'OFFLINE',NUL"
                    "L,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))"
                ),
                params | value,
            )
        result = public_agent(await self.row(session, current, identifier))
        await access.event(
            session,
            current,
            "EXECUTION_AGENT",
            identifier,
            revision,
            operation,
            request_id,
            {
                "before_hash": access.digest(public_agent(previous)) if previous else None,
                "after_hash": access.digest(result),
                "reason": value.get("reason"),
            },
        )
        await access.remember(session, current, operation, key, intent, result)
        return result

    async def unavailable(
        self, session, actor, identifier, mode, authorization=None, csrf=None, expected=None
    ):
        current = await access.context(
            session,
            actor,
            "environments.probe" if mode == "probe" else "environments.read",
            write=mode == "probe",
        )
        if mode == "probe":
            access.verify_csrf(self.tokens, current, authorization, csrf)
        await access.clock(session, current)
        row = await self.row(session, current, identifier)
        if mode == "probe" and row["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "设备已被修改")
        raise OrbitError(
            503, "ENVIRONMENT_AGENT_CONNECTION_UNAVAILABLE", "设备mTLS通道及可信Profile来源尚未接通"
        )
