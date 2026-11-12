"""引用目录：有界批量预检、逐行错误、短事务原子提交和稳定UUID候选分页。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import require_active_kind
from orbit_api.reference_access import (
    active_owner_teams,
    assert_write_ownership,
    clock,
    event,
    managed_teams,
    readable,
    reference_context,
    remember,
    replay,
    scope_clause,
    scope_version,
    verify_csrf,
)
from orbit_api.reference_contract import KINDS, normalize_row, uuid_value
from orbit_api.team_store import state_hash


def utc_text(value):
    return value.isoformat(timespec="milliseconds") + "Z"


async def records(session, tenant, identifiers):
    result = {}
    identifiers = sorted(set(identifiers))
    for offset in range(0, len(identifiers), 500):
        rows = (
            await session.execute(
                text("""
                     SELECT id,kind,value_json,revision,catalog_revision,updated_at FROM
                     orbit_reference_record WHERE tenant_id=:tenant AND id IN :ids FOR SHARE
                     """).bindparams(bindparam("ids", expanding=True)),
                {"tenant": tenant, "ids": identifiers[offset : offset + 500]},
            )
        ).mappings()
        result.update({row["id"]: dict(row) for row in rows})
    return result


def public_record(row):
    return {
        "value": _decode(row["value_json"]),
        "revision": row["revision"],
        "catalog_revision": row["catalog_revision"],
        "updated_at": utc_text(row["updated_at"]),
    }


class ReferenceStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def capabilities(self, session, actor, authorization):
        context = await reference_context(session, actor, "VENDOR", maintenance=True)
        version = await clock(session, context)
        return {
            "catalog_revision": version["revision"],
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, context.tenant_id)},
            ),
        }

    async def list(self, session, actor, kind, filters, cursor=None):
        require_active_kind(kind)
        if kind not in KINDS:
            raise OrbitError(422, "FIELD_INVALID", "引用资料类别无效")
        context = await reference_context(session, actor, kind)
        managed = await managed_teams(session, context)
        version = await clock(session, context)
        scope = await scope_version(session, context)
        owner = filters.get("owner_user_id")
        if owner:
            owner = uuid_value(owner, "/owner_user_id")
            if context.data_role == "USER" and owner != context.subject_id:
                raise OrbitError(403, "OWNERSHIP_DENIED", "普通用户不能指定其他拥有者")
            target = (
                (
                    await session.execute(
                        text("""
                SELECT b.team_id FROM orbit_business_user b JOIN sys_user u ON
                u.user_id=b.user_id AND u.status='0' AND u.del_flag='0' JOIN
                orbit_business_team t ON t.tenant_id=b.tenant_id AND
                t.id=b.team_id AND t.enabled=1
                JOIN orbit_user_scope s ON s.user_id=b.user_id
                AND s.tenant_id=b.tenant_id AND s.enabled=1 WHERE b.tenant_id=:tenant AND
                b.id=:owner AND b.enabled=1 AND b.invited=0 FOR SHARE
                """),
                        {"tenant": context.tenant_id, "owner": owner},
                    )
                )
                .mappings()
                .first()
            )
            if (
                target is None
                or context.data_role == "TEAM_ADMIN"
                and owner != context.subject_id
                and target["team_id"] not in managed
            ):
                raise OrbitError(404, "NOT_FOUND", "拥有者不存在或不可见")
        scope_hash = state_hash(
            [
                actor,
                context.tenant_id,
                context.data_role,
                context.team_id,
                managed,
                scope,
                kind,
                filters,
            ]
        )
        after = ""
        if cursor:
            claims = self.tokens.verify("REFERENCE_CURSOR_V1", cursor)
            if claims.get("scope") != scope_hash:
                raise OrbitError(409, "SCOPE_CHANGED", "筛选或权限范围已变化，请从首页重新加载")
            if claims.get("revision") != version["revision"]:
                raise OrbitError(409, "CATALOG_CHANGED", "引用目录已变化，请从首页重新加载")
            after = uuid_value(claims.get("after"), "/cursor")
        clauses = [
            "r.tenant_id=:tenant",
            "r.kind=:kind",
            "r.id>:after",
            "(" + scope_clause(context, "r", "orbit_reference_owner", "reference_id") + ")",
        ]
        params = {
            "tenant": context.tenant_id,
            "actor": actor,
            "subject": context.subject_id,
            "kind": kind,
            "after": after,
            "limit": filters.get("page_size", 50) + 1,
        }
        if owner:
            clauses.append(
                """
                EXISTS(SELECT 1 FROM orbit_reference_owner ro WHERE ro.tenant_id=r.tenant_id AND
                ro.reference_id=r.id AND ro.user_id=:owner)
                """
            )
            params["owner"] = owner
            clauses.append("r.owner_team_id=:target_team")
            params["target_team"] = target["team_id"]
        rows = list(
            (
                await session.execute(
                    text(
                        """
                SELECT
                r.id,r.kind,r.value_json,r.revision,r.catalog_revision,r.updated_at
                FROM orbit_reference_record r WHERE
                """
                        + " AND ".join(clauses)
                        + " ORDER BY r.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        page = rows[: filters.get("page_size", 50)]
        next_cursor = (
            self.tokens.issue(
                "REFERENCE_CURSOR_V1",
                {"scope": scope_hash, "revision": version["revision"], "after": page[-1]["id"]},
            )
            if len(rows) > len(page)
            else None
        )
        return {
            "items": [public_record(row) for row in page],
            "next_cursor": next_cursor,
            "catalog_revision": version["revision"],
            "scope_version": scope,
        }

    async def validate(self, session, context, value):
        require_active_kind(value.kind)
        normalized, issues, seen_ids, seen_sources = [], [], set(), set()
        for index, raw in enumerate(value.items):
            try:
                row = normalize_row(raw, value.kind)
                if row["id"] in seen_ids or row["source_key"] in seen_sources:
                    raise OrbitError(422, "DUPLICATE_VALUE", "同批UUID或来源键重复")
                seen_ids.add(row["id"])
                seen_sources.add(row["source_key"])
                normalized.append((index, row))
            except OrbitError as error:
                issues.append({"row": index, "code": error.code, "message": error.message})
        old = await records(
            session,
            context.tenant_id,
            [row["id"] for _, row in normalized],
        )
        sources = {}
        if seen_sources:
            rows = (
                await session.execute(
                    text("""
                SELECT id,source_key FROM orbit_reference_record WHERE
                tenant_id=:tenant AND kind=:kind AND source_key IN :sources FOR
                SHARE
                """).bindparams(bindparam("sources", expanding=True)),
                    {
                        "tenant": context.tenant_id,
                        "kind": value.kind,
                        "sources": sorted(seen_sources),
                    },
                )
            ).mappings()
            sources = {row["source_key"]: row["id"] for row in rows}
        owners = sorted({owner for _, row in normalized for owner in row["data_owner_user_ids"]})
        people = {}
        for offset in range(0, len(owners), 500):
            rows = (
                await session.execute(
                    text("""
                SELECT b.id,b.team_id FROM orbit_business_user b JOIN
                orbit_business_team t ON t.tenant_id=b.tenant_id AND
                t.id=b.team_id AND t.enabled=1 JOIN sys_user u ON
                u.user_id=b.user_id AND u.status='0' AND u.del_flag='0' JOIN
                orbit_user_scope s ON s.user_id=u.user_id AND
                s.tenant_id=b.tenant_id AND s.enabled=1 WHERE
                b.tenant_id=:tenant AND b.enabled=1 AND b.invited=0 AND b.id IN
                :ids FOR SHARE
                """).bindparams(bindparam("ids", expanding=True)),
                    {"tenant": context.tenant_id, "ids": owners[offset : offset + 500]},
                )
            ).mappings()
            people.update({row["id"]: row["team_id"] for row in rows})
        managed = await managed_teams(session, context)
        valid, differences = [], []
        for index, row in normalized:
            try:
                if not readable(context, managed, row):
                    raise OrbitError(403, "OWNERSHIP_DENIED", "目标归属不在当前数据范围")
                before = old.get(row["id"])
                if before and not readable(context, managed, _decode(before["value_json"])):
                    raise OrbitError(404, "NOT_FOUND", "资料不存在或不可见")
                before_value = _decode(before["value_json"]) if before else None
                assert_write_ownership(
                    context,
                    managed,
                    {key: row[key] for key in ("owner_team_id", "data_owner_user_ids")},
                    previous={
                        key: before_value[key] for key in ("owner_team_id", "data_owner_user_ids")
                    }
                    if before_value
                    else None,
                )
                if any(
                    people.get(owner) != row["owner_team_id"]
                    for owner in row["data_owner_user_ids"]
                ):
                    raise OrbitError(
                        422, "OWNER_UNAVAILABLE", "拥有者必须同租户、同团队、启用且已激活"
                    )
                before = old.get(row["id"])
                if before and (
                    before["kind"] != row["kind"]
                    or not readable(context, managed, _decode(before["value_json"]))
                ):
                    raise OrbitError(422, "REFERENCE_CONFLICT", "UUID与现有类别或数据范围冲突")
                if (
                    before
                    and _decode(before["value_json"])["source_key"] != row["source_key"]
                    or row["source_key"] in sources
                    and sources[row["source_key"]] != row["id"]
                ):
                    raise OrbitError(422, "SOURCE_CONFLICT", "来源键与稳定UUID绑定冲突")
                if before and before["revision"] >= MAX_REVISION:
                    raise OrbitError(422, "REVISION_EXHAUSTED", "资料版本已达上限")
                valid.append(row)
                differences.append(
                    {
                        "row": index,
                        "id": row["id"],
                        "action": "UPDATE" if before else "CREATE",
                        "before": _decode(before["value_json"]) if before else None,
                        "after": row,
                    }
                )
            except OrbitError as error:
                if error.status in {403, 404}:
                    raise
                issues.append({"row": index, "code": error.code, "message": error.message})
        return valid, sorted(issues, key=lambda item: item["row"]), differences

    async def preview(self, session, actor, authorization, csrf, key, value, request_id):
        require_active_kind(value.kind)
        context = await reference_context(session, actor, value.kind, maintenance=True)
        verify_csrf(self.tokens, context, authorization, csrf)
        version = await clock(session, context, write=True)
        digest = state_hash(["REFERENCE_PREVIEW", value.model_dump()])
        previous = await replay(session, context, key, digest)
        if previous is not None:
            await self.get(session, actor, previous["id"])
            return previous
        if version["revision"] != value.base_catalog_revision:
            raise OrbitError(409, "CATALOG_CHANGED", "引用目录已变化，请刷新目录版本后重新预检")
        valid, issues, differences = await self.validate(session, context, value)
        now = datetime.now(UTC).replace(tzinfo=None)
        result = {
            "id": str(uuid4()),
            "revision": 1,
            "state": "REJECTED" if issues else "VALIDATED",
            "base_catalog_revision": version["revision"],
            "expires_at": utc_text(now + timedelta(minutes=15)),
            "issues": issues,
            "created_count": sum(item["action"] == "CREATE" for item in differences),
            "updated_count": sum(item["action"] == "UPDATE" for item in differences),
        }
        await session.execute(
            text("""
                INSERT INTO orbit_reference_import
                (tenant_id,id,actor_id,team_ids_json,input_json,result_json,state,revision,base_revision,expires_at,created_at)
                VALUES(:tenant,:id,:actor,:teams,:input,:result,:state,1,:base,:expires,:now)
                """),
            {
                "tenant": context.tenant_id,
                "id": result["id"],
                "actor": actor,
                "teams": canonical(sorted({row["owner_team_id"] for row in valid})),
                "input": canonical(value.model_dump()),
                "result": canonical(result),
                "state": result["state"],
                "base": version["revision"],
                "expires": now + timedelta(minutes=15),
                "now": now,
            },
        )
        await remember(session, context, key, digest, result)
        return result

    async def assert_preview_scope(self, session, context, row, *, committing=False):
        """预览不是越权缓存：读取、差异、提交和重放均按完整冻结输入复验。"""
        if row["state"] == "REJECTED" and row["actor_id"] != context.actor_id:
            raise OrbitError(404, "NOT_FOUND", "导入预览不存在或不可见")
        payload = _decode(row["input_json"])
        values = []
        for raw in payload["items"]:
            try:
                values.append(normalize_row(raw, payload["kind"]))
            except OrbitError:
                continue  # 初次预检错误行只允许原操作者读取逐行问题。
        managed = await managed_teams(session, context)
        current = await records(session, context.tenant_id, [value["id"] for value in values])
        for value in values:
            existing = current.get(value["id"])
            before = _decode(existing["value_json"]) if existing else None
            if (
                not readable(context, managed, value)
                or before
                and not readable(context, managed, before)
            ):
                raise OrbitError(404, "NOT_FOUND", "导入预览不存在或不可见")
            try:
                assert_write_ownership(
                    context,
                    managed,
                    {key: value[key] for key in ("owner_team_id", "data_owner_user_ids")},
                    previous={key: before[key] for key in ("owner_team_id", "data_owner_user_ids")}
                    if before
                    else None,
                )
            except OrbitError:
                raise OrbitError(404, "NOT_FOUND", "导入预览不存在或不可见") from None
        if row["state"] != "REJECTED":
            people = await active_owner_teams(
                session,
                context,
                [owner for value in values for owner in value["data_owner_user_ids"]],
            )
            if any(
                people.get(owner) != value["owner_team_id"]
                for value in values
                for owner in value["data_owner_user_ids"]
            ):
                raise OrbitError(
                    422 if committing else 404,
                    "REFERENCE_UNAVAILABLE" if committing else "NOT_FOUND",
                    "预览涉及的拥有者归属已失效" if committing else "导入预览不存在或不可见",
                )

    async def get(self, session, actor, import_id, *, differences=False):
        context = await reference_context(session, actor, "VENDOR", maintenance=True)
        row = (
            (
                await session.execute(
                    text(
                        """
                SELECT input_json,result_json,state,expires_at,actor_id FROM
                orbit_reference_import WHERE tenant_id=:tenant AND id=:id FOR
                SHARE
                """
                    ),
                    {"tenant": context.tenant_id, "id": uuid_value(import_id, "/id")},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "导入预览不存在或不可见")
        require_active_kind(_decode(row["input_json"])["kind"])
        await self.assert_preview_scope(session, context, row)
        result = _decode(row["result_json"])
        if row["state"] != "COMMITTED" and row["expires_at"] <= datetime.now(UTC).replace(
            tzinfo=None
        ):
            result["state"] = "EXPIRED"
        if differences:
            # 明确标注当前差异，提交仍以冻结输入和原目录版本重新复验。
            from orbit_api.reference_contract import ReferenceImport

            _, issues, changes = await self.validate(
                session, context, ReferenceImport.model_validate(_decode(row["input_json"]))
            )
            return {"items": changes, "issues": issues, "state": result["state"]}
        return result

    async def commit(
        self, session, actor, authorization, csrf, key, import_id, expected, request_id
    ):
        from orbit_api.reference_contract import ReferenceImport

        context = await reference_context(session, actor, "VENDOR", maintenance=True)
        verify_csrf(self.tokens, context, authorization, csrf)
        version = await clock(session, context, write=True)
        import_id = uuid_value(import_id, "/id")
        digest = state_hash(["REFERENCE_COMMIT", import_id, expected])
        previous = await replay(session, context, key, digest)
        if previous is not None:
            await self.get(session, actor, import_id)
            return previous
        row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT input_json,result_json,state,revision,base_revision,expires_at,
                        actor_id FROM
                        orbit_reference_import WHERE tenant_id=:tenant AND id=:id FOR UPDATE
                        """
                    ),
                    {"tenant": context.tenant_id, "id": import_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "导入预览不存在或不可见")
        require_active_kind(_decode(row["input_json"])["kind"])
        await self.assert_preview_scope(session, context, row, committing=True)
        if row["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "预览版本已变化")
        if row["state"] != "VALIDATED":
            raise OrbitError(409, "INVALID_TRANSITION", "只有已验证且未提交的预览可以提交")
        if row["expires_at"] <= datetime.now(UTC).replace(tzinfo=None):
            raise OrbitError(410, "PREVIEW_EXPIRED", "预检已过期，请重新导入预检")
        if row["base_revision"] != version["revision"]:
            raise OrbitError(409, "CATALOG_CHANGED", "目录已发生变更，请重新预检")
        if version["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "目录版本已达上限")
        value = ReferenceImport.model_validate(_decode(row["input_json"]))
        valid, issues, differences = await self.validate(session, context, value)
        if issues:
            raise OrbitError(422, "REFERENCE_UNAVAILABLE", "提交前引用或拥有者已失效，请重新预检")
        revision = version["revision"] + 1
        parameters = [
            {
                "tenant": context.tenant_id,
                "id": item["id"],
                "kind": item["kind"],
                "source": item["source_key"],
                "name": item["name"],
                "availability": item["availability"],
                "team": item["owner_team_id"],
                "value": canonical(item),
                "revision": revision,
            }
            for item in valid
        ]
        # 同批资料最多500条；使用executemany及集合删除，避免逐行查询/删除的N+1往返。
        await session.execute(
            text("""
            INSERT INTO orbit_reference_record
            (tenant_id,id,kind,source_key,name,availability,owner_team_id,
             value_json,revision,catalog_revision,updated_at)
            VALUES(:tenant,:id,:kind,:source,:name,:availability,:team,
             :value,1,:revision,UTC_TIMESTAMP(3))
            ON DUPLICATE KEY UPDATE name=:name,availability=:availability,
             owner_team_id=:team,value_json=:value,revision=revision+1,
             catalog_revision=:revision,updated_at=UTC_TIMESTAMP(3)
        """),
            parameters,
        )
        identifiers = [item["id"] for item in valid]
        await session.execute(
            text("""DELETE FROM orbit_reference_owner
            WHERE tenant_id=:tenant AND reference_id IN :ids""").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"tenant": context.tenant_id, "ids": identifiers},
        )
        owner_rows = [
            {"tenant": context.tenant_id, "id": item["id"], "user": owner}
            for item in valid
            for owner in item["data_owner_user_ids"]
        ]
        for offset in range(0, len(owner_rows), 500):
            await session.execute(
                text("""INSERT INTO orbit_reference_owner
                (tenant_id,reference_id,user_id) VALUES(:tenant,:id,:user)"""),
                owner_rows[offset : offset + 500],
            )
        before = _decode(row["result_json"])
        result = {**before, "state": "COMMITTED", "revision": expected + 1}
        await session.execute(
            text(
                """
                UPDATE orbit_reference_import SET
                state='COMMITTED',revision=revision+1,result_json=:result WHERE
                tenant_id=:tenant AND id=:id
                """
            ),
            {"tenant": context.tenant_id, "id": import_id, "result": canonical(result)},
        )
        await session.execute(
            text("UPDATE orbit_reference_clock SET revision=:revision WHERE tenant_id=:tenant"),
            {"tenant": context.tenant_id, "revision": revision},
        )
        await event(
            session,
            context,
            "REFERENCE_IMPORT",
            import_id,
            result["revision"],
            before,
            result,
            value.reason,
            request_id,
            {
                "source": value.source,
                "catalog_revision": revision,
                "changes": [
                    {
                        "id": item["id"],
                        "source_key": item["after"]["source_key"],
                        "before_hash": state_hash(item["before"]),
                        "after_hash": state_hash(item["after"]),
                    }
                    for item in differences
                ],
            },
        )
        await remember(session, context, key, digest, result)
        return result
