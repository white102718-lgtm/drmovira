"""导入受理：真实户商与拥有者交集、原始输入对象、逐token结果及幂等审计同事务。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import clock, context, event, parameters, visible_clause
from orbit_api.account_alias_snapshots import append_account_alias_snapshot
from orbit_api.account_contract import batch_summary, tokenize
from orbit_api.account_metadata import unknown_observation
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import readable, scope_version, validate_ownership, verify_csrf
from orbit_api.reference_store import records


class AccountImportStore:
    def __init__(self, tokens, objects):
        self.tokens, self.objects = tokens, objects

    async def capabilities(self, session, actor, authorization):
        current, _ = await context(session, actor, "accounts.import")
        return {
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
            "default_owner_user_id": current.subject_id,
            "default_owner_team_id": current.team_id,
        }

    async def owner_options(self, session, actor, query="", cursor=None):
        current, _ = await context(session, actor, "accounts.import")
        version = await scope_version(session, current)
        after = ""
        if cursor:
            claims = self.tokens.verify("ACCOUNT_IMPORT_CURSOR_V1", cursor)
            if (
                claims.get("kind") != "OWNER"
                or claims.get("actor") != actor
                or claims.get("scope") != version
                or claims.get("query") != query
            ):
                raise OrbitError(409, "SCOPE_CHANGED", "投手候选范围已变化，请重新读取")
            from orbit_api.identity_contract import _uuid

            after = _uuid(claims.get("after"), "/cursor")
        clauses = [
            "b.tenant_id=:tenant",
            "b.id>:after",
            "b.enabled=1",
            "b.invited=0",
            "s.enabled=1",
            "u.status='0'",
            "u.del_flag='0'",
            "t.enabled=1",
        ]
        if current.data_role == "USER":
            clauses.append("b.id=:subject")
        elif current.data_role == "TEAM_ADMIN":
            clauses.append(
                "(b.id=:subject OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
                "WHERE tm.tenant_id=b.tenant_id AND tm.team_id=b.team_id "
                "AND tm.manager_user_id=:actor AND tm.enabled=1))"
            )
        params = parameters(current) | {"after": after}
        if query:
            clauses.append("b.display_name LIKE :query ESCAPE '!'")
            params["query"] = query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        rows = list(
            (
                await session.execute(
                    text(
                        """SELECT b.id,b.display_name AS name,b.team_id,t.name AS team_name
            FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id
            JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id
            JOIN orbit_business_team t ON t.id=b.team_id AND t.tenant_id=b.tenant_id
            WHERE """
                        + " AND ".join(clauses)
                        + " ORDER BY b.id LIMIT 51"
                    ),
                    params,
                )
            ).mappings()
        )
        next_cursor = (
            self.tokens.issue(
                "ACCOUNT_IMPORT_CURSOR_V1",
                {
                    "kind": "OWNER",
                    "actor": actor,
                    "scope": version,
                    "query": query,
                    "after": rows[49]["id"],
                },
            )
            if len(rows) > 50
            else None
        )
        return {"items": [dict(row) for row in rows[:50]], "next_cursor": next_cursor}

    async def create(self, session, actor, authorization, csrf, key, value, request_id):
        current, managed = await context(session, actor, "accounts.import")
        verify_csrf(self.tokens, current, authorization, csrf)
        await clock(session, current, write=True)
        payload_hash = hashlib.sha256(
            canonical(
                [
                    "ACCOUNT_IMPORT",
                    value.vendor_id,
                    value.owner_user_id,
                    value.owner_team_id,
                    value.account_ids_text,
                ]
            ).encode()
        ).hexdigest()
        params = parameters(current) | {"key": key}
        old = (
            (
                await session.execute(
                    text(
                        "SELECT payload_hash,response_json FROM orbit_account_idempotency "
                        "WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND request_key=:key FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if old:
            if old["payload_hash"] != payload_hash:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的导入内容")
            # 重放也重新读取批次权限，不能通过旧回执恢复已失去的数据访问。
            await self.get(session, actor, _decode(old["response_json"])["id"])
            return _decode(old["response_json"])
        ownership = {
            "owner_team_id": value.owner_team_id,
            "data_owner_user_ids": [value.owner_user_id],
        }
        await validate_ownership(session, current, ownership)
        vendor = None
        if value.vendor_id is not None:
            vendor = (await records(session, current.tenant_id, [value.vendor_id])).get(
                value.vendor_id
            )
            if (
                vendor is None
                or vendor["kind"] != "VENDOR"
                or not readable(current, managed, _decode(vendor["value_json"]))
            ):
                raise OrbitError(404, "NOT_FOUND", "户商不存在或不可见")
            reference = _decode(vendor["value_json"])
            if reference["availability"] != "AVAILABLE":
                raise OrbitError(422, "VENDOR_DISABLED", "户商已停用，不能创建导入", "/vendor_id")
            if (
                reference["owner_team_id"] != value.owner_team_id
                or value.owner_user_id not in reference["data_owner_user_ids"]
            ):
                raise OrbitError(
                    422,
                    "REFERENCE_OWNER_MISMATCH",
                    "户商必须同时对目标拥有者可读且属于目标团队",
                    "/vendor_id",
                )
        identifier, input_ref = str(uuid4()), str(uuid4())
        rows = tokenize(value.account_ids_text)
        summary = batch_summary([row["state"] for row in rows], started=False)
        # 原始对象先写入且不可覆盖；若数据库回滚仅留下未引用对象，绝不留下假成功业务记录。
        input_hash = self.objects.put(current.tenant_id, input_ref, value.account_ids_text)
        version = await scope_version(session, current)
        await session.execute(
            text("""INSERT INTO orbit_account_import
            (tenant_id,id,vendor_id,vendor_revision,owner_user_id,owner_team_id,actor_id,actor_subject_id,
             scope_version,input_hash,input_ref,state,total,success_count,failed_count,duplicate_count,created_at,updated_at)
            VALUES(:tenant,:id,:vendor,:vendor_revision,:owner,:team,:actor,:subject,:scope,:hash,:input_ref,
                :state,:total,:success_count,:failed_count,:duplicate_count,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
            params
            | {
                "id": identifier,
                "vendor": value.vendor_id,
                "vendor_revision": vendor["revision"] if vendor else None,
                "owner": value.owner_user_id,
                "team": value.owner_team_id,
                "scope": version,
                "hash": input_hash,
                "input_ref": input_ref,
            }
            | summary,
        )
        public_rows = []
        for row in rows:
            public = {
                "id": str(uuid4()),
                **row,
                "account_id": None,
                "name": None,
                "spend": unknown_observation("XXX"),
                "retryable": False,
                "error_code": "IMPORT_ID_INVALID" if row["state"] == "INVALID" else None,
                "observed_at": None,
            }
            public_rows.append(public)
        # 最多500项用单次executemany，不按每行重新查询户商、用户或角色。
        await session.execute(
            text("""INSERT INTO orbit_account_import_row
            (tenant_id,id,batch_id,token_index,line_no,column_no,raw_display,normalized_id,duplicate_of,state,next_attempt_at,value_json)
            VALUES(:tenant,:id,:batch,:token_index,:line_no,:column,:raw_display,:normalized_id,:duplicate_of,:state,UTC_TIMESTAMP(3),:result)"""),
            [
                parameters(current) | public | {"batch": identifier, "result": canonical(public)}
                for public in public_rows
            ],
        )
        if vendor is not None:
            await append_account_alias_snapshot(
                session,
                current,
                vendor,
                resource_type="IMPORT",
                resource_id=identifier,
                resource_revision=1,
                request_id=request_id,
                permission="accounts.import",
            )
        await event(
            session,
            current,
            "IMPORT",
            identifier,
            1,
            "IMPORT_ACCEPTED",
            request_id,
            {"input_hash": input_hash, "total": len(rows)},
        )
        result = await self.get(session, actor, identifier)
        await session.execute(
            text("""INSERT INTO orbit_account_idempotency
            (tenant_id,actor_id,request_key,payload_hash,response_json,created_at)
            VALUES(:tenant,:actor,:key,:hash,:result,UTC_TIMESTAMP(3))"""),
            params | {"hash": payload_hash, "result": canonical(result)},
        )
        return result

    async def get(self, session, actor, identifier, cursor=None):
        current, _ = await context(session, actor, "accounts.import")
        params = parameters(current) | {"id": identifier}
        batch = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_import b "
                        "WHERE b.tenant_id=:tenant AND b.id=:id AND ("
                        + visible_clause(current, "b")
                        + ") FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if batch is None:
            raise OrbitError(404, "NOT_FOUND", "导入批次不存在或不可见")
        scope = await scope_version(session, current)
        after = -1
        if cursor:
            claims = self.tokens.verify("ACCOUNT_IMPORT_CURSOR_V1", cursor)
            if (
                claims.get("actor") != actor
                or claims.get("tenant") != current.tenant_id
                or claims.get("batch") != identifier
                or claims.get("scope") != scope
            ):
                raise OrbitError(409, "SCOPE_CHANGED", "批次或权限范围已变化，请重新读取")
            after = claims.get("after")
            if type(after) is not int or not 0 <= after < 500:
                raise OrbitError(400, "TOKEN_INVALID", "导入行游标无效")
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT token_index,value_json FROM orbit_account_import_row "
                        "WHERE tenant_id=:tenant AND batch_id=:id AND token_index>:after "
                        "ORDER BY token_index LIMIT 201"
                    ),
                    params | {"after": after},
                )
            ).mappings()
        )
        following = (
            self.tokens.issue(
                "ACCOUNT_IMPORT_CURSOR_V1",
                {
                    "actor": actor,
                    "tenant": current.tenant_id,
                    "batch": identifier,
                    "scope": scope,
                    "after": rows[199]["token_index"],
                },
            )
            if len(rows) > 200
            else None
        )
        return {
            **{
                key: batch[key]
                for key in (
                    "id",
                    "revision",
                    "vendor_id",
                    "state",
                    "total",
                    "success_count",
                    "failed_count",
                    "duplicate_count",
                )
            },
            "rows": [_decode(row["value_json"]) for row in rows[:200]],
            "next_cursor": following,
        }
