"""渠道完整写流程：实时归属/目录复核、CAS、幂等、原子审计及不删除的停用。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.errors import OrbitError
from orbit_api.reference_access import (
    clock,
    event,
    managed_teams,
    readable,
    remember,
    replay,
    scope_clause,
    scope_version,
    validate_ownership,
    verify_csrf,
)
from orbit_api.reference_contract import uuid_value
from orbit_api.reference_store import utc_text
from orbit_api.team_store import state_hash


def active_channel_value(value):
    """Retired dictionary fields are never exposed or carried into new writes."""
    return {key: item for key, item in value.items() if key not in {"product_id", "agent_id", "product_locked"}}


def public_channel(row):
    return {
        **active_channel_value(_decode(row["value_json"])),
        "id": row["id"],
        "revision": row["revision"],
        "created_at": utc_text(row["created_at"]),
        "updated_at": utc_text(row["updated_at"]),
    }


class ChannelStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def context(self, session, actor, action="read"):
        return await require_business_access(session, actor, "channels", "channels." + action)

    async def capabilities(self, session, actor, authorization):
        context = await self.context(session, actor)
        actions = []
        for action in ("create", "edit", "assign", "archive"):
            try:
                await self.context(session, actor, action)
                actions.append(action)
            except OrbitError as error:
                if error.status != 403:
                    raise
        return {
            "actions": actions,
            "data_role": context.data_role,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, context.tenant_id)},
            ),
        }

    async def row(self, session, context, channel_id, *, write=False):
        channel_id = uuid_value(channel_id, "/id")
        row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT id,value_json,revision,product_locked,created_at,updated_at FROM
                        orbit_channel WHERE tenant_id=:tenant AND id=:id
                        """
                        + ("FOR UPDATE" if write else "FOR SHARE")
                    ),
                    {"tenant": context.tenant_id, "id": channel_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None or not readable(
            context, await managed_teams(session, context), _decode(row["value_json"])["ownership"]
        ):
            raise OrbitError(404, "NOT_FOUND", "渠道不存在或不可见")
        return row

    async def get(self, session, actor, channel_id):
        context = await self.context(session, actor)
        return public_channel(await self.row(session, context, channel_id))

    async def edit_context(self, session, actor, channel_id):
        context = await self.context(session, actor)
        await self.row(session, context, channel_id)
        return {"references": {}}

    async def list(self, session, actor, filters, cursor=None):
        context = await self.context(session, actor)
        version = await clock(session, context)
        scope = await scope_version(session, context)
        managed = await managed_teams(session, context)
        binding = state_hash(
            [actor, context.tenant_id, context.data_role, context.team_id, managed, scope, filters]
        )
        after, watermark = "", utc_text(datetime.now(UTC).replace(tzinfo=None))
        if cursor:
            claims = self.tokens.verify("CHANNEL_CURSOR_V1", cursor)
            if claims.get("scope") != binding:
                raise OrbitError(409, "SCOPE_CHANGED", "权限或筛选已变化，请从首页重新加载")
            if claims.get("revision") != version["channel_revision"]:
                raise OrbitError(409, "CHANNEL_CHANGED", "渠道目录已变化，请从首页重新加载")
            after = uuid_value(claims.get("after"), "/cursor")
            watermark = claims.get("as_of")
        clauses = [
            "c.tenant_id=:tenant",
            "c.id>:after",
            "(" + scope_clause(context, "c", "orbit_channel_owner", "channel_id") + ")",
        ]
        params = {
            "tenant": context.tenant_id,
            "subject": context.subject_id,
            "actor": actor,
            "after": after,
            "limit": filters["page_size"] + 1,
        }
        if filters.get("q"):
            clauses.append("(INSTR(c.name,:q)>0 OR INSTR(c.code,:q)>0)")
            params["q"] = filters["q"]
        for field in ("status",):
            if filters.get(field):
                clauses.append(f"c.{field}=:{field}")
                params[field] = filters[field]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"c.created_at{operator}:{field}")
                params[field] = filters[field]
        rows = list(
            (
                await session.execute(
                    text(
                        """
                SELECT c.id,c.value_json,c.revision,c.created_at,c.updated_at
                FROM orbit_channel c WHERE
                """
                        + " AND ".join(clauses)
                        + " ORDER BY c.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        page = rows[: filters["page_size"]]
        token = (
            self.tokens.issue(
                "CHANNEL_CURSOR_V1",
                {
                    "scope": binding,
                    "revision": version["channel_revision"],
                    "after": page[-1]["id"],
                    "as_of": watermark,
                },
            )
            if len(rows) > len(page)
            else None
        )
        return {
            "items": [public_channel(row) for row in page],
            "next_cursor": token,
            "scope_version": scope,
            "data_as_of": watermark,
        }

    async def save(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        value,
        channel_id,
        expected,
        request_id,
        mode="save",
    ):
        context = await self.context(
            session,
            actor,
            {"owners": "assign", "archive": "archive"}.get(
                mode, "edit" if channel_id else "create"
            ),
        )
        verify_csrf(self.tokens, context, authorization, csrf)
        version = await clock(session, context, write=True)
        digest = state_hash(["CHANNEL", mode, channel_id, expected, value])
        previous_result = await replay(session, context, key, digest)
        if previous_result is not None:
            # 创建重放也不能在撤销拥有者范围后泄露原对象。
            await self.row(session, context, channel_id or previous_result["id"])
            return active_channel_value(previous_result)
        before_row = (
            await self.row(session, context, channel_id, write=True) if channel_id else None
        )
        before = public_channel(before_row) if before_row else None
        if before_row and expected != before_row["revision"]:
            raise OrbitError(409, "REVISION_CONFLICT", "渠道已被修改，请刷新详情后重试")
        if (
            version["channel_revision"] >= MAX_REVISION
            or before_row
            and before_row["revision"] >= MAX_REVISION
        ):
            raise OrbitError(409, "REVISION_EXHAUSTED", "渠道版本已达上限")
        prior = _decode(before_row["value_json"]) if before_row else None
        if mode == "archive":
            if prior["status"] == "DISABLED":
                raise OrbitError(409, "INVALID_TRANSITION", "渠道已经停用")
            after = {**prior, "status": "DISABLED"}
        elif mode == "owners":
            after = {**prior, "ownership": value["ownership"]}
        else:
            after = value
            if prior and prior["ownership"] != after["ownership"]:
                # 编辑权限不能旁路专门的分配动作。
                await self.context(session, actor, "assign")
        if mode != "archive":
            await validate_ownership(
                session, context, after["ownership"], previous=prior["ownership"] if prior else None
            )
        after = active_channel_value(after)
        channel_id = channel_id or str(uuid4())
        params = {
            "tenant": context.tenant_id,
            "id": channel_id,
            "code": after["code"],
            "name": after["name"],
            "team": after["ownership"]["owner_team_id"],
            "product": None,
            "agent": None,
            "status": after["status"],
        }
        from orbit_api.directory_tokens import canonical

        params["value"] = canonical(after)
        try:
            if before_row:
                await session.execute(
                    text("""
                UPDATE orbit_channel SET
                code=:code,name=:name,owner_team_id=:team,product_id=:product,agent_id=:agent,
                status=:status,value_json=:value,revision=revision+1,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant AND id=:id
                """),
                    params,
                )
            else:
                await session.execute(
                    text("""
                INSERT INTO orbit_channel
                (tenant_id,id,code,name,owner_team_id,product_id,agent_id,status,value_json,revision,created_at,updated_at)
                VALUES(:tenant,:id,:code,:name,:team,:product,:agent,:status,:value,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))
                """),
                    params,
                )
        except IntegrityError:
            raise OrbitError(
                409, "CHANNEL_CODE_CONFLICT", "同租户渠道ID已存在，请修改渠道ID"
            ) from None
        await session.execute(
            text("DELETE FROM orbit_channel_owner WHERE tenant_id=:tenant AND channel_id=:id"),
            params,
        )
        await session.execute(
            text(
                """
                INSERT INTO orbit_channel_owner(tenant_id,channel_id,user_id)
                VALUES(:tenant,:id,:user)
                """
            ),
            [
                {"tenant": context.tenant_id, "id": channel_id, "user": owner}
                for owner in after["ownership"]["data_owner_user_ids"]
            ],
        )
        # 事务中的目标行可由修改前管理员读取；分配给他人后响应不重新泄露新范围其他对象。
        result_row = (
            (
                await session.execute(
                    text(
                        """
                SELECT id,value_json,revision,created_at,updated_at FROM
                orbit_channel WHERE tenant_id=:tenant AND id=:id
                """
                    ),
                    params,
                )
            )
            .mappings()
            .one()
        )
        result = public_channel(result_row)
        await session.execute(
            text(
                """
                UPDATE orbit_reference_clock SET channel_revision=channel_revision+1 WHERE
                tenant_id=:tenant
                """
            ),
            params,
        )
        await event(
            session,
            context,
            "CHANNEL",
            channel_id,
            result["revision"],
            before,
            result,
            value.get("reason", "新增渠道" if before is None else "编辑渠道"),
            request_id,
            {"action": mode, "catalog_revision": version["revision"]},
        )
        await remember(session, context, key, digest, result)
        return result

    async def display_labels(self, session, actor, identifiers):
        context = await self.context(session, actor)
        predicate = scope_clause(context, "c", "orbit_channel_owner", "channel_id")
        params = {
            "tenant": context.tenant_id,
            "actor": actor,
            "subject": context.subject_id,
            "ids": identifiers,
        }
        rows = list(
            (
                await session.execute(
                    text(
                        """
            SELECT c.id,t.name AS team_name
            FROM orbit_channel c
            JOIN orbit_business_team t ON t.tenant_id=c.tenant_id AND t.id=c.owner_team_id
            WHERE c.tenant_id=:tenant AND c.id IN :ids AND (
            """
                        + predicate
                        + ") ORDER BY c.id"
                    ).bindparams(bindparam("ids", expanding=True)),
                    params,
                )
            ).mappings()
        )
        labels = {row["id"]: {**dict(row), "owners": []} for row in rows}
        if labels:
            # 整页只用两次有界SQL，不为每渠道/拥有者单独查名称。
            owner_rows = (
                await session.execute(
                    text("""
                SELECT o.channel_id,b.id,b.display_name,u.nick_name,u.user_name
                FROM orbit_channel_owner o
                JOIN orbit_business_user b ON b.tenant_id=o.tenant_id AND b.id=o.user_id
                JOIN sys_user u ON u.user_id=b.user_id
                WHERE o.tenant_id=:tenant AND o.channel_id IN :ids ORDER BY o.channel_id,b.id
            """).bindparams(bindparam("ids", expanding=True)),
                    {"tenant": context.tenant_id, "ids": sorted(labels)},
                )
            ).mappings()
            for row in owner_rows:
                labels[row["channel_id"]]["owners"].append(
                    {
                        "id": row["id"],
                        "name": row["display_name"] or row["nick_name"] or row["user_name"],
                    }
                )
        return {"items": list(labels.values())}

    async def ownership_options(self, session, actor, after="", page_size=50):
        context = await self.context(session, actor)
        after = uuid_value(after, "/after") if after else ""
        conditions = ["b.tenant_id=:tenant", "b.enabled=1", "b.invited=0", "b.id>:after"]
        params = {
            "tenant": context.tenant_id,
            "actor": actor,
            "subject": context.subject_id,
            "after": after,
            "limit": page_size + 1,
        }
        if context.data_role == "USER":
            conditions.append("b.id=:subject")
        elif context.data_role == "TEAM_ADMIN":
            conditions.append(
                """
                (b.id=:subject OR EXISTS(SELECT 1 FROM orbit_business_team_manager m
                WHERE m.tenant_id=b.tenant_id AND m.team_id=b.team_id
                AND m.manager_user_id=:actor AND m.enabled=1))
                """
            )
        rows = list(
            (
                await session.execute(
                    text(
                        """
                SELECT b.id,b.display_name,b.team_id,t.name AS team_name FROM
                orbit_business_user b JOIN orbit_business_team t ON
                t.tenant_id=b.tenant_id AND t.id=b.team_id AND t.enabled=1 JOIN
                sys_user u ON u.user_id=b.user_id AND u.status='0' AND
                u.del_flag='0' JOIN orbit_user_scope s ON s.user_id=u.user_id
                AND s.tenant_id=b.tenant_id AND s.enabled=1 WHERE
                """
                        + " AND ".join(conditions)
                        + " ORDER BY b.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        return {
            "items": [dict(row) for row in rows[:page_size]],
            "next_after": rows[page_size - 1]["id"] if len(rows) > page_size else None,
        }
