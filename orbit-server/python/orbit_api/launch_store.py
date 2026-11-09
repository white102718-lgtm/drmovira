"""真实服务器投放草稿：原合同、双向引用权限、版本CAS和同事务审计幂等。"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api import launch_access as access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import ensure_config_size, uuid_field
from orbit_api.launch_expansion import expanded_counts
from orbit_api.launch_options import actor_label
from orbit_api.launch_references import validate_sources
from orbit_api.reference_access import scope_version, verify_csrf
from orbit_api.reference_store import utc_text

PAGE_BYTES = 8 * 1024 * 1024
PLAN_COLUMNS = """id,owner_user_id,owner_team_id,channel_id,name,state,revision,
payload_json,payload_hash,payload_bytes,created_at,updated_at"""


def public_plan(row):
    return _decode(row["payload_json"]) | {
        "id": row["id"],
        "revision": row["revision"],
        "state": row["state"],
        "created_at": utc_text(row["created_at"]),
        "updated_at": utc_text(row["updated_at"]),
    }


def bounded_page(metadata, size, byte_column):
    """原Page必须返回完整对象；先用小元数据限额再集合读JSON，避免200×5MiB。"""
    selected, byte_count = [], 0
    for row in metadata[:size]:
        estimate = row[byte_column] + 1024
        if selected and byte_count + estimate > PAGE_BYTES:
            break
        selected.append(row["id"])
        byte_count += estimate
    return selected


class LaunchStore:
    def __init__(self, tokens, *, metric_profile_fixture=False):
        if type(metric_profile_fixture) is not bool:
            raise ValueError("指标隔离开关必须由可信构造器提供")
        self.tokens = tokens
        self.metric_profile_fixture = metric_profile_fixture

    async def capabilities(self, session, actor, authorization, *, validation_provider=None):
        current = await access.context(session, actor, "launch.read")
        actions = []
        for action in ("create", "edit", "execute", "publish"):
            try:
                await access.context(session, actor, "launch." + action)
                actions.append(action)
            except OrbitError as error:
                if error.status != 403:
                    raise
        from orbit_api.launch_validation_store import LaunchValidationStore

        validation_ready = False
        try:
            await LaunchValidationStore(self.tokens, validation_provider).require_provider(session)
            validation_ready = True
        except OrbitError as error:
            if error.status != 503:
                raise
        return {
            **await actor_label(session, current),
            "actions": actions,
            "data_role": current.data_role,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
            "execution_available": False,
            "validation_available": validation_ready and "edit" in actions,
            "blocked_dependencies": [
                *([] if validation_ready else ["IDENTITY_VERIFICATION", "CAPABILITY_POLICY"]),
                "COMMAND_PIPELINE",
            ],
        }

    async def row(self, session, current, identifier, *, write=False, unlocked=False):
        identifier = uuid_field(identifier, ("id",))
        suffix = "" if unlocked else " FOR UPDATE" if write else " FOR SHARE"
        row = (
            (
                await session.execute(
                    text(
                        f"SELECT {PLAN_COLUMNS} FROM orbit_launch_plan "
                        "WHERE tenant_id=:tenant AND id=:id" + suffix
                    ),
                    access.parameters(current) | {"id": identifier},
                )
            )
            .mappings()
            .first()
        )
        if row is None or not access.readable(current, await access.teams(session, current), row):
            raise OrbitError(404, "NOT_FOUND", "计划不存在或当前不可见")
        return row

    async def get(self, session, actor, identifier):
        current = await access.context(session, actor, "launch.read")
        return public_plan(await self.row(session, current, identifier))

    async def list(self, session, actor, filters, cursor=None):
        current = await access.context(session, actor, "launch.read")
        version = (await access.clock(session, current))["plan_revision"]
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
            claims = self.tokens.verify("LAUNCH_CURSOR_V1", cursor)
            if claims.get("scope") != binding:
                raise OrbitError(409, "SCOPE_CHANGED", "筛选或权限范围已变化，请从首页加载")
            if claims.get("revision") != version:
                raise OrbitError(409, "LAUNCH_CHANGED", "计划目录已变化，请从首页加载")
            after, as_of = uuid_field(claims.get("after"), ("cursor",)), claims.get("as_of")
        clauses = [
            "p.tenant_id=:tenant",
            "p.id>:after",
            "(" + access.scope_clause(current, "p") + ")",
        ]
        values = access.parameters(current) | {"after": after, "limit": filters["page_size"] + 1}
        if filters.get("q"):
            clauses.append("INSTR(p.name,:q)>0")
            values["q"] = filters["q"]
        for field, column in (("operator_user_id", "owner_user_id"), ("channel_id", "channel_id")):
            if filters.get(field):
                clauses.append(f"p.{column}=:{field}")
                values[field] = filters[field]
        if filters.get("status"):
            clauses.append("p.state=:state")
            values["state"] = filters["status"]
        for field, operator in (("date_from", ">="), ("date_to", "<")):
            if filters.get(field):
                clauses.append(f"p.created_at{operator}:{field}")
                values[field] = filters[field]
        metadata = (
            (
                await session.execute(
                    text(
                        "SELECT p.id,p.payload_bytes FROM orbit_launch_plan p WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY p.id LIMIT :limit"
                    ),
                    values,
                )
            )
            .mappings()
            .all()
        )
        identifiers = bounded_page(metadata, filters["page_size"], "payload_bytes")
        rows = []
        if identifiers:
            rows = (
                (
                    await session.execute(
                        text(
                            f"SELECT {PLAN_COLUMNS} FROM orbit_launch_plan "
                            "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"tenant": current.tenant_id, "ids": identifiers},
                    )
                )
                .mappings()
                .all()
            )
        token = (
            self.tokens.issue(
                "LAUNCH_CURSOR_V1",
                {"scope": binding, "revision": version, "after": identifiers[-1], "as_of": as_of},
            )
            if len(metadata) > len(identifiers)
            else None
        )
        return {
            "items": [public_plan(row) for row in rows],
            "next_cursor": token,
            "scope_version": scope,
            "data_as_of": as_of,
        }

    async def save(
        self, session, actor, authorization, csrf, key, value, identifier, expected, request_id
    ):
        operation = "plan.update" if identifier else "plan.create"
        payload_hash = access.digest([identifier, expected, value])
        successful = await access.successful_replay(
            session, actor, "launch.read", operation, key, payload_hash
        )
        if successful is not None:
            current, result = successful
            verify_csrf(self.tokens, current, authorization, csrf)
            await self.row(session, current, result["id"])
            return result
        permission = "launch.edit" if identifier else "launch.create"
        current = await access.context(session, actor, permission)
        verify_csrf(self.tokens, current, authorization, csrf)
        # 无锁预读只检查旧资源与状态，来源锁取得后重新锁行CAS；不逆序锁plan→material。
        previous = (
            await self.row(session, current, identifier, unlocked=True) if identifier else None
        )
        if previous and previous["state"] not in {"DRAFT", "VALIDATED"}:
            raise OrbitError(409, "PLAN_STATE_CONFLICT", "已提交或归档计划不能覆盖编辑")
        # 幂等绑定原规范请求（包括原scope ID），解析副本不可改变死锁重试闭包里的原输入。
        value = deepcopy(value)
        expanded_counts(value)
        dependencies = await validate_sources(
            session,
            current,
            value,
            permission=permission,
            isolated_fixture=self.metric_profile_fixture,
        )
        expanded_counts(value)
        if "account_scope_snapshot" in dependencies:
            ensure_config_size(value)
        await access.clock(session, current, write=True)
        operation = "plan.update" if identifier else "plan.create"
        replayed = await access.replay(session, current, operation, key, payload_hash)
        if replayed:
            # 首次只读探测未命中后的并发胜者，仍遵守相同的当前读取权限。
            read_current = await access.context(session, actor, "launch.read")
            await self.row(session, read_current, replayed["id"])
            return replayed
        if identifier:
            previous = await self.row(session, current, identifier, write=True)
            if previous["revision"] != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "计划已被修改，请重新加载")
            if previous["state"] not in {"DRAFT", "VALIDATED"}:
                raise OrbitError(409, "PLAN_STATE_CONFLICT", "计划状态已变化")
            if previous["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "计划版本已达上限")
            # 正文不变但精确指标来源换版，仍须建立新的PlanVersion；无关目录时钟不触发。
            from orbit_api.launch_plan_source import capture_plan_source

            # validate只递增状态CAS头，不制造配置版本；先按真实最新配置源核完整性。
            source = await capture_plan_source(session, current, previous)
            frozen = (
                await session.execute(
                    text(
                        "SELECT dependency_json FROM orbit_launch_plan_version "
                        "WHERE tenant_id=:tenant AND plan_id=:id AND revision=:revision FOR SHARE"
                    ),
                    access.parameters(current)
                    | {"id": identifier, "revision": source.source_revision},
                )
            ).scalar_one()
            old_metric = _decode(frozen).get("metric_profiles", {})
            if _decode(previous["payload_json"]) == value and old_metric == dependencies.get(
                "metric_profiles", {}
            ):
                result = public_plan(previous)
                await access.remember(session, current, operation, key, payload_hash, result)
                return result
        return await self.persist(
            session,
            current,
            value,
            dependencies,
            identifier,
            previous,
            operation,
            key,
            payload_hash,
            request_id,
        )

    async def persist(
        self,
        session,
        current,
        value,
        dependencies,
        identifier,
        previous,
        operation,
        key,
        payload_hash,
        request_id,
    ):
        identifier = identifier or str(uuid4())
        revision = previous["revision"] + 1 if previous else 1
        payload = canonical(value)
        values = access.parameters(current) | {
            "id": identifier,
            "revision": revision,
            "owner": value["ownership"]["owner_user_id"],
            "team": value["ownership"]["owner_team_id"],
            "channel": value.get("channel_id"),
            "name": value["name"],
            "payload": payload,
            "hash": access.digest(value),
            "bytes": len(payload.encode()),
            "account_count": len(value["account_ids"]),
            "asset_count": len(value["asset_ids"]),
            "dependencies": canonical(dependencies),
        }
        if previous:
            await session.execute(
                text("""UPDATE orbit_launch_plan SET owner_user_id=:owner,
            owner_team_id=:team,channel_id=:channel,name=:name,state='DRAFT',revision=:revision,
            payload_json=:payload,payload_hash=:hash,payload_bytes=:bytes,
            account_count=:account_count,asset_count=:asset_count,updated_at=UTC_TIMESTAMP(3)
            WHERE tenant_id=:tenant AND id=:id"""),
                values,
            )
        else:
            await session.execute(
                text("""INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,
            owner_team_id,channel_id,name,state,revision,payload_json,payload_hash,payload_bytes,
            account_count,asset_count,created_at,updated_at) VALUES(:tenant,:id,:owner,:team,
            :channel,:name,'DRAFT',:revision,:payload,:hash,:bytes,:account_count,:asset_count,
            UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
                values,
            )
        await session.execute(
            text("""INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,
        revision,payload_json,payload_hash,dependency_json,created_at,created_by)
        VALUES(:tenant,:id,:revision,:payload,:hash,:dependencies,UTC_TIMESTAMP(3),:actor)"""),
            values,
        )
        await session.execute(
            text("DELETE FROM orbit_launch_plan_reference WHERE tenant_id=:tenant AND plan_id=:id"),
            values,
        )
        refs = [
            {
                "tenant": current.tenant_id,
                "plan": identifier,
                "kind": kind,
                "id": reference_id,
                "revision": row["revision"],
            }
            for kind, rows in (
                ("ACCOUNT", dependencies["accounts"]),
                ("ASSET", dependencies["assets"]),
            )
            for reference_id, row in rows.items()
        ]
        if refs:
            await session.execute(
                text("""INSERT INTO orbit_launch_plan_reference(tenant_id,
            plan_id,kind,reference_id,source_revision)
            VALUES(:tenant,:plan,:kind,:id,:revision)"""),
                refs,
            )
        await access.event(
            session,
            current,
            "PLAN",
            identifier,
            revision,
            operation,
            request_id,
            {
                "old_revision": previous["revision"] if previous else None,
                "new_revision": revision,
                "payload_hash": values["hash"],
            },
        )
        result = public_plan(await self.row(session, current, identifier))
        await access.remember(session, current, operation, key, payload_hash, result)
        return result
