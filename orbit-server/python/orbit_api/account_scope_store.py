"""原跨页范围：有界分块冻结，实时授权重验，不以账户改名重写选择历史。"""

import hashlib
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock, context, parameters, visible_clause
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_store import identifier, utc
from orbit_api.account_scope_contract import MAX_MEMBERS
from orbit_api.account_selection import selection_sql
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import verify_csrf
from orbit_api.scope_visibility_verdict import verified_snapshot


def changed():
    raise OrbitError(409, "SCOPE_CHANGED", "账户范围授权已变化，请重新冻结选择")


class AccountScopeStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def capabilities(self, session, actor, authorization):
        current, _version, _digest = await self.authorize(session, actor)
        return {
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
            "max_members": MAX_MEMBERS,
            "max_plan_accounts": 500,
        }

    async def authorize(self, session, actor):
        current, managed = await context(session, actor, "accounts.read")
        version = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": actor},
            )
        ).scalar_one()
        if type(version) is not int or not 1 <= version <= MAX_REVISION:
            raise OrbitError(409, "SCOPE_VERSION_INVALID", "真实授权版本不符合原合同范围")
        digest = hashlib.sha256(
            canonical(
                [
                    actor,
                    current.tenant_id,
                    current.subject_id,
                    current.data_role,
                    current.team_id,
                    sorted(managed),
                    version,
                ]
            ).encode()
        ).hexdigest()
        await clock(session, current)
        return current, version, digest

    async def snapshot(self, session, current, version, digest, snapshot_id):
        # 原授权每次仍由调用者实时核验；成功证明仅省去同依赖下的全体成员重复扫描。
        return await verified_snapshot(session, current, version, digest, snapshot_id)

    @staticmethod
    def public(row):
        return {
            "id": row["id"],
            "count": row["member_count"],
            "scope_version": row["scope_version"],
            "hash": row["members_hash"],
            "created_at": iso(utc(row["created_at"])),
        }

    async def create(self, session, actor, authorization, csrf, key, selection, request_id):
        if not session.in_transaction():
            raise ValueError("冻结范围必须有显式外层事务")
        current, version, digest = await self.authorize(session, actor)
        try:
            verify_csrf(self.tokens, current, authorization, csrf)
        except OrbitError:
            # 原写入合同CSRF失败为403；签名Token结构错误不能以普通游标400冒充。
            raise OrbitError(403, "CSRF_INVALID", "账户范围会话校验已失效") from None
        request_id = identifier(request_id, "/request_id")
        identifier_new = str(uuid4())
        payload_hash = hashlib.sha256(selection.canonical.encode()).hexdigest()
        params = parameters(current) | {
            "id": identifier_new,
            "scope": version,
            "auth": digest,
            "key": key,
            "hash": payload_hash,
            "body": selection.canonical,
        }
        await session.execute(
            text(
                "INSERT INTO orbit_account_scope_snapshot "
                "(tenant_id,id,actor_id,scope_version,auth_fingerprint,request_key,request_hash,"
                "request_json,created_at) VALUES "
                "(:tenant,:id,:actor,:scope,:auth,:key,:hash,:body,UTC_TIMESTAMP(3)) "
                "ON DUPLICATE KEY UPDATE request_key=request_key"
            ),
            params,
        )
        stored = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_scope_snapshot WHERE tenant_id=:tenant "
                        "AND actor_id=:actor AND request_key=:key FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .one()
        )
        if stored["request_hash"] != payload_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同的账户选择")
        if stored["ready"]:
            replay = await self.snapshot(session, current, version, digest, stored["id"])
            return self.public(replay)
        if stored["id"] != identifier_new:
            raise OrbitError(409, "SNAPSHOT_INCOMPLETE", "范围尚未完成，请使用原幂等键重试")
        clauses = ["a.tenant_id=:tenant", "(" + visible_clause(current, "a") + ")", "a.id>:after"]
        if selection.mode == "FILTER":
            extra, values = selection_sql(selection.query)
            clauses.extend(extra)
            params.update(values)
        else:
            clauses.append("a.id IN :ids")
        after, count, ids_offset, members_hash = "", 0, 0, hashlib.sha256(b"[")
        while True:
            if selection.mode == "IDS":
                if ids_offset >= len(selection.account_ids):
                    break
                params["ids"] = list(selection.account_ids[ids_offset : ids_offset + 1000])
                ids_offset += 1000
            statement = text(
                "SELECT a.id,a.external_id,a.name,a.name_prefix,a.revision,a.owner_user_id,"
                "a.owner_team_id,a.currency FROM orbit_ad_account a WHERE "
                + " AND ".join(clauses)
                + " ORDER BY a.id LIMIT :limit FOR SHARE OF a"
            )
            if selection.mode == "IDS":
                statement = statement.bindparams(bindparam("ids", expanding=True))
            rows = list(
                (
                    await session.execute(
                        statement,
                        params | {"after": after, "limit": min(1000, MAX_MEMBERS + 1 - count)},
                    )
                ).mappings()
            )
            if not rows:
                break
            if count + len(rows) > MAX_MEMBERS:
                raise OrbitError(422, "SCOPE_ACCOUNT_LIMIT", "账户范围超过50000项，不允许截断")
            batch = []
            for row in rows:
                frozen = [
                    row["id"],
                    row["external_id"],
                    row["name"],
                    row["revision"],
                    row["owner_user_id"],
                    row["owner_team_id"],
                    row["currency"],
                ]
                if count:
                    members_hash.update(b",")
                members_hash.update(canonical(frozen).encode())
                count += 1
                batch.append(params | dict(row) | {"snapshot": identifier_new})
            await session.execute(
                text(
                    "INSERT INTO orbit_account_scope_member "
                    "(tenant_id,snapshot_id,account_id,external_id,name,name_prefix,account_revision,"
                    "owner_user_id,owner_team_id,currency) VALUES "
                    "(:tenant,:snapshot,:id,:external_id,:name,:name_prefix,:revision,"
                    ":owner_user_id,:owner_team_id,:currency)"
                ),
                batch,
            )
            after = rows[-1]["id"]
        if selection.mode == "IDS" and count != len(selection.account_ids):
            raise OrbitError(404, "NOT_FOUND", "选择包含不存在或不可见的账户")
        members_hash.update(b"]")
        params.update({"count": count, "members_hash": members_hash.hexdigest()})
        await session.execute(
            text(
                "UPDATE orbit_account_scope_snapshot SET ready=1,member_count=:count,"
                "members_hash=:members_hash WHERE tenant_id=:tenant AND id=:id"
            ),
            params,
        )
        event_id = str(uuid4())
        await session.execute(
            text(
                "INSERT INTO orbit_account_scope_event "
                "(id,tenant_id,snapshot_id,actor_id,request_id,member_count,"
                "members_hash,created_at) "
                "VALUES(:event,:tenant,:id,:actor,:request,:count,:members_hash,UTC_TIMESTAMP(3))"
            ),
            params | {"event": event_id, "request": request_id},
        )
        await session.execute(
            text(
                "INSERT INTO orbit_account_scope_outbox(event_id,tenant_id,snapshot_id,created_at) "
                "VALUES(:event,:tenant,:id,UTC_TIMESTAMP(3))"
            ),
            params | {"event": event_id},
        )
        return self.public(
            dict(stored) | {"member_count": count, "members_hash": members_hash.hexdigest()}
        )

    async def members(self, session, actor, snapshot_id, query, page_size=50, cursor=None):
        current, version, digest = await self.authorize(session, actor)
        snapshot = await self.snapshot(session, current, version, digest, snapshot_id)
        snapshot_id = snapshot["id"]
        binding = hashlib.sha256(
            canonical([snapshot_id, digest, query, page_size]).encode()
        ).hexdigest()
        after = ""
        if cursor:
            claims = self.tokens.verify("ACCOUNT_SCOPE_CURSOR_V1", cursor)
            if claims.get("binding") != binding:
                changed()
            after = identifier(claims.get("after"), "/cursor")
        params = parameters(current) | {
            "id": snapshot_id,
            "after": after,
            "limit": page_size + 1,
        }
        clauses = ["tenant_id=:tenant", "snapshot_id=:id", "account_id>:after"]
        if query:
            numeric = query[4:] if query.startswith("act_") else query
            if numeric.isascii() and numeric.isdigit():
                clauses.append("external_id=:external")
                params["external"] = numeric
            else:
                clauses.append("name_prefix LIKE :search ESCAPE '!'")
                params["search"] = (
                    query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
                )
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT account_id,external_id,name FROM orbit_account_scope_member WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY account_id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        items = [dict(row) for row in rows[:page_size]]
        return {
            "items": items,
            "next_cursor": self.tokens.issue(
                "ACCOUNT_SCOPE_CURSOR_V1", {"binding": binding, "after": items[-1]["account_id"]}
            )
            if len(rows) > page_size
            else None,
            "data_as_of": iso(utc(snapshot["created_at"])),
            "scope_version": version,
        }

    async def resolve_for_plan(
        self, session, current, snapshot_id, *, owner_user_id, owner_team_id
    ):
        """原launch事务调用，返回冻结实际ID；不代替launch授权或即时资源预检。"""
        live, version, digest = await self.authorize(session, current.actor_id)
        if live != current:
            changed()
        snapshot = await self.snapshot(session, current, version, digest, snapshot_id)
        snapshot_id = snapshot["id"]
        if not 1 <= snapshot["member_count"] <= 500:
            raise OrbitError(422, "PLAN_ACCOUNT_LIMIT", "计划仅允许1至500个账户，不允许截断范围")
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT a.id,a.owner_user_id,a.owner_team_id,a.currency,"
                        "m.owner_user_id frozen_owner,m.owner_team_id frozen_team,"
                        "m.currency frozen_currency FROM orbit_account_scope_member m "
                        "JOIN orbit_ad_account a ON a.tenant_id=m.tenant_id AND a.id=m.account_id "
                        "WHERE m.tenant_id=:tenant AND m.snapshot_id=:id "
                        "ORDER BY a.id LIMIT 501 FOR SHARE OF a"
                    ),
                    parameters(current) | {"id": snapshot_id},
                )
            ).mappings()
        )
        if len(rows) != snapshot["member_count"]:
            changed()
        currencies = set()
        for row in rows:
            if (
                row["owner_user_id"] != row["frozen_owner"]
                or row["owner_team_id"] != row["frozen_team"]
                or row["currency"] != row["frozen_currency"]
                or row["owner_user_id"] != owner_user_id
                or row["owner_team_id"] != owner_team_id
            ):
                raise OrbitError(409, "ACCOUNT_OWNERSHIP_CHANGED", "账户投手、团队或币种已变化")
            currencies.add(row["currency"])
        if len(currencies) != 1:
            raise OrbitError(422, "PLAN_ACCOUNT_CURRENCY_MISMATCH", "计划账户必须属于同一币种")
        return [row["id"] for row in rows]
