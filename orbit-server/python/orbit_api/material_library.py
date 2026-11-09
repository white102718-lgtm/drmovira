"""素材列表、元数据、标签分类及原子归档；统计未接入时明确拒绝指标筛选。"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orbit_api.configuration_store import MAX_REVISION, _uuid
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.material_security import require_clean_scan, safe_asset_rows
from orbit_api.material_store import ASSET_COLUMNS, MaterialStore, one, rows


def revision_guard(row, expected):
    if row["revision"] != expected:
        raise OrbitError(409, "REVISION_CONFLICT", "对象版本已变化，请刷新")
    if expected >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "对象版本已达上限")


class MaterialLibrary(MaterialStore):
    async def list(self, session, actor, filters, cursor=None):
        context = await self.context(session, actor)
        clock = await one(
            session,
            "SELECT revision FROM orbit_material_clock WHERE tenant_id=:tenant",
            {"tenant": context.tenant_id},
        )
        if clock is None:
            raise OrbitError(503, "MATERIAL_NOT_INITIALIZED", "素材目录尚未初始化")
        scope_version = await self.scope_version(session, context)
        managed = await rows(
            session,
            """SELECT team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id=:actor AND enabled=1 ORDER BY team_id
            FOR SHARE""",
            {"tenant": context.tenant_id, "actor": actor},
        )
        scope = hashlib.sha256(
            canonical(
                [
                    context.tenant_id,
                    actor,
                    context.subject_id,
                    context.data_role,
                    [r["team_id"] for r in managed],
                    clock["revision"],
                    scope_version,
                    filters,
                ]
            ).encode()
        ).hexdigest()
        after, name = "", ""
        watermark = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if cursor:
            claims = self.tokens.verify("MATERIAL_CURSOR_V1", cursor)
            if claims.get("scope") != scope:
                raise OrbitError(409, "CURSOR_STALE", "素材、筛选或权限发生变化，请从首页加载")
            after, name, watermark = (
                _uuid(claims.get("after")),
                claims.get("name"),
                claims.get("as_of"),
            )
            if not isinstance(name, str) or not isinstance(watermark, str):
                raise OrbitError(400, "TOKEN_INVALID", "素材游标无效")
        params = {
            "tenant": context.tenant_id,
            "subject": context.subject_id,
            "actor": actor,
            "limit": filters["page_size"] + 1,
            "after": after,
            "name": name,
        }
        clauses = ["a.tenant_id=:tenant"]
        if context.data_role != "SUPER_ADMIN":
            scope_sql = "a.owner_user_id=:subject"
            if context.data_role == "TEAM_ADMIN":
                scope_sql += """ OR EXISTS(SELECT 1 FROM orbit_business_team_manager m
                  WHERE m.tenant_id=a.tenant_id AND m.team_id=a.owner_team_id
                    AND m.manager_user_id=:actor AND m.enabled=1)"""
            clauses.append("(" + scope_sql + ")")
        if filters.get("q"):
            clauses.append("INSTR(a.name,:q)>0")
            params["q"] = filters["q"]
        for key, column in (
            ("status", "state"),
            ("category_id", "category_id"),
            ("kind", "kind"),
            ("operator_user_id", "owner_user_id"),
        ):
            if filters.get(key):
                clauses.append(f"a.{column}=:{key}")
                params[key] = filters[key]
        if not filters.get("status"):
            clauses.append("a.state<>'ARCHIVED'")
        if filters.get("tag_ids"):
            for index, tag_id in enumerate(filters["tag_ids"]):
                params[f"tag{index}"] = tag_id
            tag_sql = ",".join(f":tag{i}" for i in range(len(filters["tag_ids"])))
            if filters.get("tag_match", "ALL") == "ANY":
                clauses.append(f"""EXISTS(SELECT 1 FROM orbit_material_asset_tag t
                    WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.id
                      AND t.tag_id IN({tag_sql}))""")
            else:
                for index in range(len(filters["tag_ids"])):
                    clauses.append(f"""EXISTS(SELECT 1 FROM orbit_material_asset_tag t
                      WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.id
                        AND t.tag_id=:tag{index})""")
        descending = filters.get("direction", "ASC") == "DESC"
        operator, direction = ("<", "DESC") if descending else (">", "ASC")
        if filters.get("sort", "name") == "name":
            if after:
                clauses.append(
                    f"(a.name {operator} :name OR (a.name=:name AND a.id {operator} :after))"
                )
            order = f"a.name {direction},a.id {direction}"
        else:
            # 指标未接入前不可把未知指标伪装成0排序；保留可解释错误。
            raise OrbitError(
                503, "MATERIAL_METRICS_UNAVAILABLE", "素材指标尚未接入事实汇总，请按名称排序"
            )
        columns = ",".join("a." + p.strip() for p in ASSET_COLUMNS.replace("\n", "").split(","))
        result = await rows(
            session,
            f"SELECT {columns} FROM orbit_material_asset a WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY {order} LIMIT :limit",
            params,
        )
        page = result[: filters["page_size"]]
        page = await safe_asset_rows(session, context.tenant_id, page)
        tags = await self.tags(session, context.tenant_id, [r["id"] for r in page])
        next_cursor = None
        if len(result) > len(page):
            last = page[-1]
            next_cursor = self.tokens.issue(
                "MATERIAL_CURSOR_V1",
                {"scope": scope, "after": last["id"], "name": last["name"], "as_of": watermark},
            )
        return {
            "items": [self.public_asset(r, tags[r["id"]]) for r in page],
            "next_cursor": next_cursor,
            "data_as_of": watermark,
            "scope_version": scope_version,
        }

    async def edit(
        self, session, actor, authorization, csrf, key, asset_id, expected, value, request_id
    ):
        context, digest, replay = await self.begin_write(
            session,
            actor,
            authorization,
            csrf,
            key,
            "assets.edit",
            [asset_id, expected, value.model_dump()],
        )
        if replay is not None:
            return replay
        row = await self.asset(session, context, asset_id, lock=True)
        revision_guard(row, expected)
        if row["state"] != "READY":
            raise OrbitError(409, "ASSET_NOT_READY", "只有READY素材可以修改业务元数据")
        await require_clean_scan(session, context.tenant_id, row)
        old_tags = (await self.tags(session, context.tenant_id, [asset_id]))[asset_id]
        await self.validate_metadata(session, context, value, old_tags)
        await session.execute(
            text("""UPDATE orbit_material_asset SET name=:name,category_id=:category,
          revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id"""),
            {
                "tenant": context.tenant_id,
                "id": asset_id,
                "name": value.name,
                "category": value.category_id,
            },
        )
        await self.replace_tags(session, context.tenant_id, asset_id, value.tag_ids)
        response = self.public_asset(
            {**row, **value.model_dump(), "revision": expected + 1, "_scan_verified": True},
            value.tag_ids,
        )
        before = {
            "name": row["name"],
            "category_id": row["category_id"],
            "tag_ids": sorted(old_tags),
        }
        difference = {
            field: {"before": before[field], "after": after}
            for field, after in value.model_dump().items()
            if before[field] != after
        }
        await self.changed(
            session, context, "ASSET_EDITED", asset_id, expected + 1, request_id, difference
        )
        return await self.finish(session, context, key, digest, response)

    async def bulk_delete(self, session, actor, authorization, csrf, key, value, request_id):
        context, digest, replay = await self.begin_write(
            session, actor, authorization, csrf, key, "assets.delete", value.model_dump()
        )
        if replay is not None:
            return replay
        # 输入已经按UUID排序；先锁全部对象和引用，再开始任何修改，失败整批回滚。
        assets = []
        for item in value.assets:
            row = await self.asset(session, context, item.id, lock=True)
            revision_guard(row, item.revision)
            if row["state"] == "ARCHIVED":
                raise OrbitError(409, "ASSET_ARCHIVED", "素材已归档")
            active = await one(
                session,
                """SELECT id FROM orbit_material_reference
               WHERE tenant_id=:tenant AND asset_id=:id AND active=1
                 AND kind IN('ALLOCATION','EXECUTION') LIMIT 1 FOR UPDATE""",
                {"tenant": context.tenant_id, "id": item.id},
            )
            if active:
                raise OrbitError(409, "ASSET_REFERENCED", "素材存在活跃分配或执行引用，整批未删除")
            assets.append(row)
        for row in assets:
            await session.execute(
                text("""UPDATE orbit_material_asset SET state='ARCHIVED',
              revision=revision+1,archived_at=UTC_TIMESTAMP(3),updated_at=UTC_TIMESTAMP(3)
              WHERE tenant_id=:tenant AND id=:id"""),
                {"tenant": context.tenant_id, "id": row["id"]},
            )
            await self.changed(
                session,
                context,
                "ASSET_ARCHIVED",
                row["id"],
                row["revision"] + 1,
                request_id,
                {"reason": value.reason, "state": {"before": row["state"], "after": "ARCHIVED"}},
            )
            await session.execute(
                text("""UPDATE orbit_material_job SET state='FAILED',claim_id=NULL
                WHERE tenant_id=:tenant AND asset_id=:id AND state IN('PENDING','RUNNING')"""),
                {"tenant": context.tenant_id, "id": row["id"]},
            )
        return await self.finish(
            session,
            context,
            key,
            digest,
            {"id": str(uuid4()), "revision": 1, "state": "ARCHIVED", "request_id": request_id},
        )

    async def references(self, session, actor, asset_id, after="", limit=50):
        context = await self.context(session, actor)
        asset = await self.asset(session, context, asset_id)
        scope_version = await self.scope_version(session, context)
        scope = hashlib.sha256(
            canonical(
                [
                    "REFERENCES",
                    context.tenant_id,
                    actor,
                    context.subject_id,
                    context.data_role,
                    asset_id,
                    asset["revision"],
                    scope_version,
                ]
            ).encode()
        ).hexdigest()
        cursor = ""
        if after:
            claims = self.tokens.verify("MATERIAL_CURSOR_V1", after)
            if claims.get("scope") != scope:
                raise OrbitError(409, "CURSOR_STALE", "素材或引用权限已变化，请重新加载")
            cursor = _uuid(claims.get("after"))
        values = await rows(
            session,
            """SELECT id,kind,resource_id,active FROM orbit_material_reference
            WHERE tenant_id=:tenant AND asset_id=:id AND id>:after ORDER BY id LIMIT :limit""",
            {"tenant": context.tenant_id, "id": asset_id, "after": cursor, "limit": limit + 1},
        )
        return {
            "items": [
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "resource_id": r["resource_id"],
                    "active": bool(r["active"]),
                }
                for r in values[:limit]
            ],
            "next_cursor": self.tokens.issue(
                "MATERIAL_CURSOR_V1", {"scope": scope, "after": values[limit - 1]["id"]}
            )
            if len(values) > limit
            else None,
        }

    async def taxonomy_list(self, session, actor, kind, after="", filters=None):
        filters = filters or {"q": "", "status": "", "page_size": 50}
        limit = filters["page_size"]
        context = await self.context(session, actor, "tags.read")
        clock = await one(
            session,
            """SELECT revision FROM orbit_material_clock
            WHERE tenant_id=:tenant FOR SHARE""",
            {"tenant": context.tenant_id},
        )
        if clock is None:
            raise OrbitError(503, "MATERIAL_NOT_INITIALIZED", "素材目录尚未初始化")
        scope_version = await self.scope_version(session, context)
        managed = await rows(
            session,
            """SELECT team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id=:actor AND enabled=1 ORDER BY team_id""",
            {"tenant": context.tenant_id, "actor": actor},
        )
        scope = hashlib.sha256(
            canonical(
                [
                    context.tenant_id,
                    actor,
                    context.subject_id,
                    context.data_role,
                    [row["team_id"] for row in managed],
                    kind,
                    clock["revision"],
                    scope_version,
                    filters,
                ]
            ).encode()
        ).hexdigest()
        watermark = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        cursor = ""
        if after:
            claims = self.tokens.verify("MATERIAL_TAXONOMY_CURSOR_V1", after)
            if claims.get("scope") != scope:
                raise OrbitError(409, "CURSOR_STALE", "分类标签或权限已变化，请重新加载")
            cursor = _uuid(claims.get("after"))
            watermark = claims.get("as_of")
            if not isinstance(watermark, str):
                raise OrbitError(400, "TOKEN_INVALID", "分类标签游标无效")
        clauses = ["tenant_id=:tenant", "kind=:kind", "id>:after"]
        params = {"tenant": context.tenant_id, "kind": kind, "after": cursor, "limit": limit + 1}
        if filters["q"]:
            clauses.append("INSTR(name,:q)>0")
            params["q"] = filters["q"]
        if filters["status"]:
            clauses.append("state=:status")
            params["status"] = filters["status"]
        values = await rows(
            session,
            "SELECT id,name,group_name,state,revision FROM orbit_material_taxonomy WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id LIMIT :limit",
            params,
        )
        values = [dict(row) for row in values]
        counts = await self.taxonomy_counts(session, actor, kind, [r["id"] for r in values[:limit]])
        for row in values[:limit]:
            row["visible_asset_count"] = counts[row["id"]]
        return {
            "items": [self.taxonomy_public(r, kind) for r in values[:limit]],
            "next_cursor": self.tokens.issue(
                "MATERIAL_TAXONOMY_CURSOR_V1",
                {"scope": scope, "after": values[limit - 1]["id"], "as_of": watermark},
            )
            if len(values) > limit
            else None,
            "data_as_of": watermark,
            "scope_version": scope_version,
        }

    async def taxonomy_get(self, session, actor, kind, resource_id):
        context = await self.context(session, actor, "tags.read")
        row = await one(
            session,
            """SELECT id,name,group_name,state,revision
            FROM orbit_material_taxonomy WHERE tenant_id=:tenant AND id=:id AND kind=:kind
            FOR SHARE""",
            {"tenant": context.tenant_id, "id": _uuid(resource_id), "kind": kind},
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "分类或标签不存在")
        row = dict(row)
        counts = await self.taxonomy_counts(session, actor, kind, [row["id"]])
        row["visible_asset_count"] = counts[row["id"]]
        return self.taxonomy_public(row, kind)

    async def taxonomy_counts(self, session, actor, kind, identifiers):
        """一页一次聚合，仅计算当前可读且未归档素材；无素材读权限返回未知而非0。"""
        if not identifiers:
            return {}
        try:
            context = await self.context(session, actor, "assets.read")
        except OrbitError as error:
            if error.status == 403:
                return dict.fromkeys(identifiers)
            raise
        params = {"tenant": context.tenant_id, "subject": context.subject_id, "actor": actor}
        keys = []
        for index, identifier in enumerate(identifiers):
            key = "taxonomy_" + str(index)
            keys.append(":" + key)
            params[key] = identifier
        scope = ""
        if context.data_role != "SUPER_ADMIN":
            scope = " AND (a.owner_user_id=:subject"
            if context.data_role == "TEAM_ADMIN":
                scope += """ OR EXISTS(SELECT 1 FROM orbit_business_team_manager m
                    WHERE m.tenant_id=a.tenant_id AND m.team_id=a.owner_team_id
                    AND m.manager_user_id=:actor AND m.enabled=1)"""
            scope += ")"
        if kind == "TAG":
            source = """orbit_material_asset_tag t JOIN orbit_material_asset a
                ON a.tenant_id=t.tenant_id AND a.id=t.asset_id"""
            identifier_column = "t.tag_id"
        else:
            source = "orbit_material_asset a"
            identifier_column = "a.category_id"
        counts = await rows(
            session,
            f"SELECT {identifier_column} AS id,COUNT(*) AS total FROM {source} "
            f"WHERE a.tenant_id=:tenant AND a.state<>'ARCHIVED' "
            f"AND {identifier_column} IN ({','.join(keys)})"
            + scope
            + f" GROUP BY {identifier_column}",
            params,
        )
        result = dict.fromkeys(identifiers, 0)
        result.update({row["id"]: int(row["total"]) for row in counts})
        return result

    @staticmethod
    def taxonomy_public(row, kind):
        value = {k: row[k] for k in ("id", "name", "state", "revision")}
        if kind == "TAG":
            value["group"] = row["group_name"]
        if "visible_asset_count" in row:
            value["visible_asset_count"] = row["visible_asset_count"]
        return value

    async def taxonomy_save(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        kind,
        value,
        request_id,
        resource_id=None,
        expected=0,
        archive=False,
    ):
        action = "tags.archive" if archive else "tags.edit" if resource_id else "tags.create"
        context, digest, replay = await self.begin_write(
            session,
            actor,
            authorization,
            csrf,
            key,
            action,
            [kind, resource_id, expected, value.model_dump()],
        )
        if replay is not None:
            return replay
        resource_id = _uuid(resource_id) if resource_id else str(uuid4())
        params = {"tenant": context.tenant_id, "id": resource_id, "kind": kind}
        previous = await one(
            session,
            """SELECT id,name,group_name,state,revision,is_system
           FROM orbit_material_taxonomy WHERE tenant_id=:tenant AND id=:id AND kind=:kind
           FOR UPDATE""",
            params,
        )
        if expected:
            if previous is None:
                raise OrbitError(404, "NOT_FOUND", "标签或分类不存在")
            revision_guard(previous, expected)
        if archive:
            if previous["is_system"]:
                raise OrbitError(409, "SYSTEM_CATEGORY_FIXED", "系统未分类不可停用")
            if kind == "CATEGORY":
                referenced = await one(
                    session,
                    """SELECT id FROM orbit_material_asset
                 WHERE tenant_id=:tenant AND category_id=:id
                   AND state<>'ARCHIVED' LIMIT 1 FOR SHARE""",
                    params,
                )
                if referenced:
                    raise OrbitError(409, "CATEGORY_REFERENCED", "分类仍有关联素材，请先迁移分类")
            await session.execute(
                text("""UPDATE orbit_material_taxonomy SET state='DISABLED',
                revision=revision+1 WHERE tenant_id=:tenant AND id=:id"""),
                params,
            )
            response = self.taxonomy_public(
                {**previous, "state": "DISABLED", "revision": expected + 1}, kind
            )
        else:
            params |= {"name": value.name, "group": getattr(value, "group", "")}
            try:
                if previous:
                    if previous["is_system"] and value.name != previous["name"]:
                        raise OrbitError(409, "SYSTEM_CATEGORY_FIXED", "系统未分类不可改名")
                    await session.execute(
                        text("""UPDATE orbit_material_taxonomy SET name=:name,
                       group_name=:group,revision=revision+1 WHERE tenant_id=:tenant AND id=:id"""),
                        params,
                    )
                else:
                    await session.execute(
                        text("""INSERT INTO orbit_material_taxonomy
                       (tenant_id,id,kind,name,group_name)
                       VALUES(:tenant,:id,:kind,:name,:group)"""),
                        params,
                    )
            except IntegrityError:
                raise OrbitError(409, "NAME_CONFLICT", "同组分类或标签名称已存在") from None
            response = self.taxonomy_public(
                {
                    "id": resource_id,
                    "name": value.name,
                    "group_name": getattr(value, "group", ""),
                    "revision": expected + 1,
                    "state": previous["state"] if previous else "ENABLED",
                },
                kind,
            )
        before = self.taxonomy_public(previous, kind) if previous else {}
        difference = {
            field: {"before": before.get(field), "after": after}
            for field, after in response.items()
            if field not in {"id", "revision"} and before.get(field) != after
        }
        if archive:
            difference["reason"] = value.reason
        await self.changed(
            session, context, action, resource_id, response["revision"], request_id, difference
        )
        return await self.finish(session, context, key, digest, response)
