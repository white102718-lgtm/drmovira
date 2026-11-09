"""配置模板真实事务：冻结共享成员、非所有者不可编辑、应用新草稿不携带来源资源。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from orbit_api import launch_access as access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import ensure_config_size, uuid_field
from orbit_api.launch_options import actor_label
from orbit_api.launch_references import validate_sources
from orbit_api.launch_store import LaunchStore, bounded_page
from orbit_api.reference_access import active_owner_teams, scope_version, verify_csrf
from orbit_api.reference_store import utc_text
from orbit_api.template_contract import template_draft

COLUMNS = """id,owner_user_id,owner_team_id,name,description,visibility,state,
revision,config_json,config_hash,config_bytes,dependency_json"""


def visible_clause(current, alias="t"):
    return (
        "("
        + access.scope_clause(current, alias, current_managers=True)
        + ") OR ("
        + f"{alias}.visibility='TEAM' AND {alias}.owner_team_id=:team AND EXISTS("
        + "SELECT 1 FROM orbit_launch_template_recipient r "
        + f"WHERE r.tenant_id={alias}.tenant_id AND r.template_id={alias}.id "
        + "AND r.user_id=:subject FOR SHARE))"
    )


def public_template(row, recipients):
    return {
        "id": row["id"],
        "revision": row["revision"],
        "name": row["name"],
        "description": row["description"],
        "visibility": row["visibility"],
        "state": row["state"],
        "campaigns": _decode(row["config_json"]),
        "recipient_user_ids": recipients,
        "ownership": {"owner_user_id": row["owner_user_id"], "owner_team_id": row["owner_team_id"]},
    }


async def recipient_sets(session, current, identifiers):
    if not identifiers:
        return {}
    rows = (
        (
            await session.execute(
                text(
                    "SELECT template_id,user_id FROM orbit_launch_template_recipient "
                    "WHERE tenant_id=:tenant AND template_id IN :ids "
                    "ORDER BY template_id,user_id FOR SHARE"
                ).bindparams(bindparam("ids", expanding=True)),
                {"tenant": current.tenant_id, "ids": identifiers},
            )
        )
        .mappings()
        .all()
    )
    result = {identifier: [] for identifier in identifiers}
    for row in rows:
        result[row["template_id"]].append(row["user_id"])
    return result


class TemplateStore:
    def __init__(self, tokens, *, metric_profile_fixture=False):
        if type(metric_profile_fixture) is not bool:
            raise ValueError("指标隔离开关必须由可信构造器提供")
        self.tokens = tokens
        self.metric_profile_fixture = metric_profile_fixture

    async def row(self, session, current, identifier, *, write=False, unlocked=False):
        identifier = uuid_field(identifier, ("id",))
        values = access.parameters(current) | {"id": identifier, "team": current.team_id}
        suffix = "" if unlocked else " FOR UPDATE" if write else " FOR SHARE"
        row = (
            (
                await session.execute(
                    text(
                        f"SELECT {COLUMNS} FROM orbit_launch_template t "
                        "WHERE t.tenant_id=:tenant AND t.id=:id AND ("
                        + visible_clause(current)
                        + ")"
                        + suffix
                    ),
                    values,
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "模板不存在或当前不可见")
        return row

    async def get(self, session, actor, identifier):
        current = await access.context(session, actor, "templates.read")
        row = await self.row(session, current, identifier)
        return public_template(
            row, (await recipient_sets(session, current, [row["id"]]))[row["id"]]
        )

    async def capabilities(self, session, actor, authorization):
        current = await access.context(session, actor, "templates.read")
        actions = []
        for action in ("create", "edit", "share", "archive"):
            try:
                await access.context(session, actor, "templates." + action)
                actions.append(action)
            except OrbitError as error:
                if error.status != 403:
                    raise
        return {
            **await actor_label(session, current),
            "actions": actions,
            "data_role": current.data_role,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
        }

    async def list(self, session, actor, filters, cursor=None):
        current = await access.context(session, actor, "templates.read")
        version = (await access.clock(session, current))["template_revision"]
        scope = await scope_version(session, current)
        binding = access.digest(
            [
                actor,
                current.tenant_id,
                current.subject_id,
                current.team_id,
                current.data_role,
                await access.teams(session, current),
                scope,
                filters,
            ]
        )
        after, as_of = "", utc_text(datetime.now(UTC).replace(tzinfo=None))
        if cursor:
            claims = self.tokens.verify("TEMPLATE_CURSOR_V1", cursor)
            if claims.get("scope") != binding:
                raise OrbitError(409, "SCOPE_CHANGED", "模板范围或筛选已变化，请从首页加载")
            if claims.get("revision") != version:
                raise OrbitError(409, "TEMPLATE_CHANGED", "模板已变化，请从首页加载")
            after, as_of = uuid_field(claims.get("after"), ("cursor",)), claims.get("as_of")
        clauses = ["t.tenant_id=:tenant", "t.id>:after", "(" + visible_clause(current) + ")"]
        values = access.parameters(current) | {
            "team": current.team_id,
            "after": after,
            "limit": filters["page_size"] + 1,
        }
        if filters.get("q"):
            clauses.append("INSTR(t.name,:q)>0")
            values["q"] = filters["q"]
        if filters.get("operator_user_id"):
            clauses.append("t.owner_user_id=:operator_user_id")
            values["operator_user_id"] = filters["operator_user_id"]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"t.created_at{operator}:{field}")
                values[field] = filters[field]
        if filters.get("status"):
            clauses.append("t.state=:status")
            values["status"] = filters["status"]
        metadata = (
            (
                await session.execute(
                    text(
                        "SELECT t.id,t.config_bytes FROM orbit_launch_template t WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY t.id LIMIT :limit"
                    ),
                    values,
                )
            )
            .mappings()
            .all()
        )
        identifiers = bounded_page(metadata, filters["page_size"], "config_bytes")
        rows = []
        if identifiers:
            rows = (
                (
                    await session.execute(
                        text(
                            f"SELECT {COLUMNS} FROM orbit_launch_template "
                            "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"tenant": current.tenant_id, "ids": identifiers},
                    )
                )
                .mappings()
                .all()
            )
        recipients = await recipient_sets(session, current, identifiers)
        token = (
            self.tokens.issue(
                "TEMPLATE_CURSOR_V1",
                {"scope": binding, "revision": version, "after": identifiers[-1], "as_of": as_of},
            )
            if len(metadata) > len(identifiers)
            else None
        )
        return {
            "items": [public_template(row, recipients[row["id"]]) for row in rows],
            "next_cursor": token,
            "scope_version": scope,
            "data_as_of": as_of,
        }

    async def resolve_recipients(self, session, current, value, ownership, previous=None):
        identifiers = sorted(value["recipient_user_ids"])
        if value["visibility"] == "TEAM":
            if not identifiers:
                # 原PERMISSIONS指定默认当前团队启用人员冻结集合；501人不得截断分享。
                identifiers = list(
                    (
                        await session.execute(
                            text("""SELECT b.id FROM orbit_business_user b
                JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0'
                JOIN orbit_user_scope s ON s.user_id=b.user_id
                AND s.tenant_id=b.tenant_id AND s.enabled=1
                JOIN orbit_business_team t ON t.tenant_id=b.tenant_id
                AND t.id=b.team_id AND t.enabled=1
                WHERE b.tenant_id=:tenant AND b.team_id=:team AND b.enabled=1 AND b.invited=0
                ORDER BY b.id LIMIT 501 FOR SHARE"""),
                            {"tenant": current.tenant_id, "team": ownership["owner_team_id"]},
                        )
                    ).scalars()
                )
                if len(identifiers) > 500:
                    raise OrbitError(
                        422,
                        "RECIPIENT_LIMIT",
                        "当前团队超过五百人，请明确选择共享成员",
                        "/recipient_user_ids",
                    )
            previous_ids = (
                (await recipient_sets(session, current, [previous["id"]]))[previous["id"]]
                if previous
                else []
            )
            if not previous or previous["visibility"] != "TEAM" or identifiers != previous_ids:
                await access.context(session, current.actor_id, "templates.share")
            owners = await active_owner_teams(session, current, identifiers)
            if set(owners) != set(identifiers) or any(
                team != ownership["owner_team_id"] for team in owners.values()
            ):
                raise OrbitError(
                    422,
                    "RECIPIENT_UNAVAILABLE",
                    "共享成员必须为当前同团队启用且已激活人员",
                    "/recipient_user_ids",
                )
        elif previous and previous["visibility"] == "TEAM":
            await access.context(session, current.actor_id, "templates.share")
        return identifiers

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
        mode="save",
    ):
        operation = "template." + (mode if mode != "save" else "update" if identifier else "create")
        payload_hash = access.digest([identifier, expected, value])
        successful = await access.successful_replay(
            session, actor, "templates.read", operation, key, payload_hash
        )
        if successful is not None:
            current, result = successful
            verify_csrf(self.tokens, current, authorization, csrf)
            await self.row(session, current, result["id"])
            return result
        permission = "templates." + (mode if mode != "save" else "edit" if identifier else "create")
        current = await access.context(session, actor, permission)
        verify_csrf(self.tokens, current, authorization, csrf)
        previous = (
            await self.row(session, current, identifier, unlocked=True) if identifier else None
        )
        source_revision = previous["revision"] if previous else None
        if previous and previous["owner_user_id"] != current.subject_id:
            raise OrbitError(
                403, "TEMPLATE_OWNER_REQUIRED", "共享或管理范围不会授予编辑他人模板权限"
            )
        ownership = {
            "owner_user_id": previous["owner_user_id"] if previous else current.subject_id,
            "owner_team_id": previous["owner_team_id"] if previous else current.team_id,
        }
        owner_actor = await access.owner(session, current, ownership)
        if mode == "save":
            from orbit_api.metric_profile_references import (
                collect_metric_profile_ids,
                resolve_metric_profile_dependencies,
            )

            desired = dict(value)
            dependencies = await resolve_metric_profile_dependencies(
                session,
                current,
                owner_actor,
                ownership,
                collect_metric_profile_ids(desired["campaigns"]),
                permission=permission,
                isolated_fixture=self.metric_profile_fixture,
            )
        else:
            # 共享/归档不重写模板内容的来源；未知历史保持NULL，不能伪造已核验的空快照。
            dependencies = (
                _decode(previous["dependency_json"])
                if previous.get("dependency_json") is not None
                else None
            )
            desired = public_template(
                previous, (await recipient_sets(session, current, [identifier]))[identifier]
            )
            desired = {
                key: desired[key]
                for key in ("name", "description", "visibility", "campaigns", "recipient_user_ids")
            }
            if mode == "share":
                desired.update(visibility="TEAM", recipient_user_ids=value["recipient_user_ids"])
        if mode != "archive":
            desired["recipient_user_ids"] = await self.resolve_recipients(
                session, current, desired, ownership, previous
            )
        ensure_config_size(desired)
        await access.clock(session, current, write=True)
        operation = "template." + (mode if mode != "save" else "update" if identifier else "create")
        payload_hash = access.digest([identifier, expected, value])
        replayed = await access.replay(session, current, operation, key, payload_hash)
        if replayed:
            read_current = await access.context(session, actor, "templates.read")
            await self.row(session, read_current, replayed["id"])
            return replayed
        if identifier:
            previous = await self.row(session, current, identifier, write=True)
            if previous["owner_user_id"] != current.subject_id:
                raise OrbitError(403, "TEMPLATE_OWNER_REQUIRED", "仅模板所有者可维护")
            if previous["revision"] != expected or source_revision != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "模板已被修改，请重新加载")
            if previous["state"] != "ACTIVE" and mode != "archive":
                raise OrbitError(409, "TEMPLATE_ARCHIVED", "归档模板不能修改或共享")
            if previous["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "模板版本已达上限")
        identifier = identifier or str(uuid4())
        revision = previous["revision"] + 1 if previous else 1
        state = "ARCHIVED" if mode == "archive" else "ACTIVE"
        if previous:
            old = public_template(
                previous, (await recipient_sets(session, current, [identifier]))[identifier]
            )
            comparable = {field: old[field] for field in desired}
            previous_dependencies = (
                _decode(previous["dependency_json"])
                if previous.get("dependency_json") is not None
                else {}
            )
            metric_same = previous_dependencies.get("metric_profiles", {}) == (
                dependencies or {}
            ).get("metric_profiles", {})
            if comparable == desired and previous["state"] == state and metric_same:
                await access.remember(session, current, operation, key, payload_hash, old)
                return old
        values = access.parameters(current) | {
            "id": identifier,
            "owner": ownership["owner_user_id"],
            "team": ownership["owner_team_id"],
            "name": desired["name"],
            "description": desired["description"],
            "visibility": desired["visibility"],
            "state": state,
            "revision": revision,
            "config": canonical(desired["campaigns"]),
            "hash": access.digest(desired),
            "bytes": len(canonical(desired).encode()),
            "dependencies": canonical(dependencies) if dependencies is not None else None,
        }
        try:
            if previous:
                await session.execute(
                    text("""UPDATE orbit_launch_template SET name=:name,
                description=:description,visibility=:visibility,state=:state,revision=:revision,
                config_json=:config,config_hash=:hash,config_bytes=:bytes,dependency_json=:dependencies,updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant AND id=:id"""),
                    values,
                )
            else:
                await session.execute(
                    text("""INSERT INTO orbit_launch_template(tenant_id,id,
                owner_user_id,owner_team_id,name,description,visibility,state,revision,config_json,
                config_hash,config_bytes,dependency_json,created_at,updated_at)
                VALUES(:tenant,:id,:owner,:team,
                :name,:description,:visibility,:state,:revision,:config,:hash,:bytes,:dependencies,
                UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
                    values,
                )
        except IntegrityError as error:
            if error.orig.args and error.orig.args[0] == 1062:
                raise OrbitError(
                    409, "TEMPLATE_NAME_CONFLICT", "同一拥有者已有此规范化名称模板"
                ) from None
            raise
        await session.execute(
            text(
                "DELETE FROM orbit_launch_template_recipient "
                "WHERE tenant_id=:tenant AND template_id=:id"
            ),
            values,
        )
        if desired["recipient_user_ids"]:
            await session.execute(
                text("""INSERT INTO orbit_launch_template_recipient
            (tenant_id,template_id,user_id) VALUES(:tenant,:id,:user)"""),
                [values | {"user": recipient} for recipient in desired["recipient_user_ids"]],
            )
        await session.execute(
            text("""INSERT INTO orbit_launch_template_version(tenant_id,
        template_id,revision,value_json,dependency_json,created_at,created_by)
        VALUES(:tenant,:id,:revision,:value,:dependencies,UTC_TIMESTAMP(3),:actor)"""),
            values | {"value": canonical(desired | {"ownership": ownership, "state": state})},
        )
        await access.event(
            session,
            current,
            "TEMPLATE",
            identifier,
            revision,
            operation,
            request_id,
            {
                "old_revision": previous["revision"] if previous else None,
                "new_revision": revision,
                "reason": value.get("reason"),
                "config_hash": values["hash"],
            },
        )
        result = public_template(
            await self.row(session, current, identifier), desired["recipient_user_ids"]
        )
        await access.remember(session, current, operation, key, payload_hash, result)
        return result

    async def apply(
        self, session, actor, authorization, csrf, key, identifier, expected, value, request_id
    ):
        operation = "template.apply"
        payload_hash = access.digest([identifier, expected, value])
        successful = await access.successful_replay(
            session, actor, "templates.read", operation, key, payload_hash
        )
        plans = LaunchStore(self.tokens, metric_profile_fixture=self.metric_profile_fixture)
        if successful is not None:
            current, result = successful
            verify_csrf(self.tokens, current, authorization, csrf)
            await self.row(session, current, identifier)
            plan_current = await access.context(session, actor, "launch.read")
            await plans.row(session, plan_current, result["id"])
            return result
        current = await access.context(session, actor, "templates.read")
        await access.context(session, actor, "launch.create")
        verify_csrf(self.tokens, current, authorization, csrf)
        previous = await self.row(session, current, identifier, unlocked=True)
        source_revision = previous["revision"]
        draft = template_draft({"campaigns": _decode(previous["config_json"])}, value["ownership"])
        dependencies = await validate_sources(
            session,
            current,
            draft,
            permission="launch.create",
            isolated_fixture=self.metric_profile_fixture,
        )
        await access.clock(session, current, write=True)
        operation = "template.apply"
        payload_hash = access.digest([identifier, expected, value])
        replayed = await access.replay(session, current, operation, key, payload_hash)
        if replayed:
            template_current = await access.context(session, actor, "templates.read")
            await self.row(session, template_current, identifier)
            plan_current = await access.context(session, actor, "launch.read")
            await plans.row(session, plan_current, replayed["id"])
            return replayed
        previous = await self.row(session, current, identifier, write=True)
        if previous["revision"] != expected or source_revision != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "模板已被修改，请重新加载")
        if previous["state"] != "ACTIVE":
            raise OrbitError(409, "TEMPLATE_ARCHIVED", "归档模板不能应用")
        dependencies["template"] = {"id": identifier, "revision": expected}
        return await plans.persist(
            session,
            current,
            draft,
            dependencies,
            None,
            None,
            operation,
            key,
            payload_hash,
            request_id,
        )
