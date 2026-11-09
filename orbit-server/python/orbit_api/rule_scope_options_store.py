"""规则筛选候选的双方账户交集；只读目录，不授予指派权限。"""

import hashlib
import unicodedata
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncConnection

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_contract import MAX_SAFE, _utc, identifier
from orbit_api.rule_editor_scope_store import RuleEditorScopeStore, rows, visibility
from orbit_api.rule_editor_store import LABEL_SQL, owner_active
from orbit_api.rule_scope_options_contract import PURPOSE, ScopeOptionsQuery


def unavailable():
    raise OrbitError(503, "RULE_SCOPE_OPTIONS_UNAVAILABLE", "筛选候选当前不可用，请稍后重试")


def changed():
    raise OrbitError(409, "RULE_SCOPE_OPTIONS_CHANGED", "筛选候选或当前权限已变化，请重新查询")


def require_read_committed(session):
    # 明确检查真实独占连接，不依靠可伪造的session.info标志或外层锁推断子查询读取。
    connection = session.bind
    if (
        not isinstance(connection, AsyncConnection)
        or connection.sync_connection.get_execution_options().get("isolation_level")
        != "READ COMMITTED"
        or not session.in_transaction()
    ):
        raise ValueError("RULE_SCOPE_OPTIONS_OWNED_READ_COMMITTED_REQUIRED")


def prefix(value):
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def ref_visibility(scope, name):
    """仅数据拥有者/明确管理团队；同团队普通成员不扩大为整个团队。"""
    if name not in {"caller", "owner"}:
        raise ValueError("FIXED_SCOPE_PREFIX_REQUIRED")
    current = scope.current
    if current.data_role == "SUPER_ADMIN":
        return "1=1", {}
    clause = (
        "EXISTS (SELECT 1 FROM orbit_reference_owner ro WHERE ro.tenant_id=r.tenant_id "
        "AND ro.reference_id=r.id AND ro.user_id=:" + name + "_ref_subject)"
    )
    params = {name + "_ref_subject": current.subject_id}
    if current.data_role == "TEAM_ADMIN" and scope.managed_team_ids:
        keys = []
        for i, team in enumerate(scope.managed_team_ids):
            key = name + "_ref_team_" + str(i)
            keys.append(":" + key)
            params[key] = team
        clause = "(" + clause + " OR r.owner_team_id IN (" + ",".join(keys) + "))"
    return clause, params


def public_operator(row):
    try:
        result = {key: row[key] for key in ("id", "name", "team_id", "team_name")}
        for key in ("id", "team_id"):
            if identifier(result[key], "/" + key) != result[key]:
                unavailable()
        for key in ("name", "team_name"):
            if type(result[key]) is not str or not result[key] or len(result[key]) > 255:
                unavailable()
        # 非布尔数据库状态不转换成假正常；已停用历史人员仍显示active=false。
        for key in ("enabled", "invited", "team_enabled", "scope_enabled"):
            if type(row[key]) is not int or row[key] not in {0, 1}:
                unavailable()
        if row["status"] not in {"0", "1"} or row["del_flag"] not in {"0", "2"}:
            unavailable()
        return result | {"active": owner_active(row)}
    except (KeyError, TypeError, OrbitError):
        unavailable()


def public_vendor(row):
    try:
        result = {key: row[key] for key in ("id", "name", "alias", "availability")}
        if identifier(result["id"], "/id") != result["id"]:
            unavailable()
        if type(result["name"]) is not str or not 1 <= len(result["name"]) <= 255:
            unavailable()
        alias = result["alias"]
        if alias is not None and (
            type(alias) is not str
            or not 1 <= len(alias) <= 30
            or unicodedata.normalize("NFC", alias) != alias
        ):
            unavailable()
        if result["availability"] not in {"AVAILABLE", "UNAVAILABLE"}:
            unavailable()
        return result
    except (KeyError, TypeError, OrbitError):
        unavailable()


class RuleScopeOptionsStore:
    def __init__(self, tokens):
        self.tokens = tokens
        self.scopes = RuleEditorScopeStore(tokens)

    async def clocks(self, session, access):
        tenant = {"tenant": access.current.tenant_id}
        reference = await rows(
            session,
            "SELECT revision FROM orbit_reference_clock WHERE tenant_id=:tenant FOR SHARE",
            tenant,
        )
        directory = await rows(
            session,
            "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE",
            tenant,
        )
        if len(reference) != 1 or len(directory) != 1:
            unavailable()
        versions = [reference[0]["revision"], directory[0]["revision"]]
        if any(type(v) is not int or not 0 <= v <= MAX_SAFE for v in versions):
            unavailable()
        account, now = await self.scopes._watermark(session, access)
        return versions + [account], now

    def binding(self, authorization, access, owner, previous, query, versions):
        intent = asdict(query)
        intent.pop("cursor")
        head = (
            [
                previous[k]
                for k in (
                    "id",
                    "revision",
                    "payload_hash",
                    "owner_user_id",
                    "owner_team_id",
                    "state",
                )
            ]
            if previous is not None
            else None
        )
        return hashlib.sha256(
            canonical(
                [
                    self.tokens.session_binding(
                        authorization, access.current.actor_id, access.current.tenant_id
                    ),
                    access.auth_fingerprint,
                    owner.auth_fingerprint,
                    head,
                    intent,
                    versions,
                ]
            ).encode()
        ).hexdigest()

    async def options(self, session, actor, authorization, query):
        if not isinstance(query, ScopeOptionsQuery):
            raise ValueError("TYPED_SCOPE_OPTIONS_QUERY_REQUIRED")
        require_read_committed(session)
        access, owner, previous = await self.scopes._begin(session, actor, query.context)
        versions, now = await self.clocks(session, access)
        binding = self.binding(authorization, access, owner, previous, query, versions)
        after, as_of = "", now
        if query.cursor is not None:
            claims = self.tokens.verify(PURPOSE, query.cursor)
            if claims.get("binding") != binding or claims.get("kind") != query.kind:
                changed()
            try:
                after = identifier(claims.get("after"), "/cursor")
                _utc(claims.get("as_of"), "/cursor")
                as_of = claims["as_of"]
            except (OrbitError, KeyError, TypeError):
                raise OrbitError(400, "TOKEN_INVALID", "候选游标无效，请重新查询") from None
            if as_of > now:
                changed()
        caller_clause, caller_params = visibility(access.current, access.managed_team_ids, "caller")
        owner_clause, owner_params = visibility(owner.current, owner.managed_team_ids, "owner")
        params = (
            {"tenant": access.current.tenant_id, "after": after, "limit": query.page_size + 1}
            | caller_params
            | owner_params
        )
        account_scope = "a.tenant_id=:tenant AND " + caller_clause + " AND " + owner_clause
        if query.kind == "OPERATOR":
            sql = (
                LABEL_SQL + " WHERE b.tenant_id=:tenant AND b.id>:after "
                "AND EXISTS (SELECT 1 FROM orbit_ad_account a WHERE "
                + account_scope
                + " AND a.owner_user_id=b.id)"
            )
            if query.exact_id:
                sql += " AND b.id=:exact_id"
                params["exact_id"] = query.exact_id
            elif query.q:
                sql += (
                    " AND COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name) "
                    "LIKE :q ESCAPE '!'"
                )
                params["q"] = prefix(query.q)
            sql += " ORDER BY b.id LIMIT :limit FOR SHARE OF b,u,t,s"
            found = await rows(session, sql, params)
            convert = public_operator
        else:
            caller_ref, cp = ref_visibility(access, "caller")
            owner_ref, op = ref_visibility(owner, "owner")
            params |= cp | op
            sql = (
                "SELECT r.id,r.name,r.availability,va.alias FROM orbit_reference_record r "
                "LEFT JOIN orbit_vendor_alias va ON va.tenant_id=r.tenant_id AND va.vendor_id=r.id "
                "WHERE r.tenant_id=:tenant AND r.kind='VENDOR' AND r.id>:after AND ("
                + caller_ref
                + ") AND ("
                + owner_ref
                + ") AND EXISTS (SELECT 1 FROM orbit_ad_account a WHERE "
                + account_scope
                + " AND a.vendor_id=r.id)"
            )
            if query.exact_id:
                sql += " AND r.id=:exact_id"
                params["exact_id"] = query.exact_id
            elif query.q:
                sql += " AND (r.name LIKE :q ESCAPE '!' OR va.alias LIKE :q ESCAPE '!')"
                params["q"] = prefix(query.q)
            # 引用clock保护缺失alias行；不对LEFT JOIN可空端使用FOR SHARE。
            sql += " ORDER BY r.id LIMIT :limit FOR SHARE OF r"
            found = await rows(session, sql, params)
            convert = public_vendor
        if len(found) > query.page_size + 1:
            unavailable()
        items = [convert(row) for row in found]
        if any(items[i]["id"] >= items[i + 1]["id"] for i in range(len(items) - 1)):
            unavailable()
        await self.scopes._finish(session, access, owner, previous)
        page = items[: query.page_size]
        return {
            "items": page,
            "next_cursor": self.tokens.issue(
                PURPOSE,
                {"binding": binding, "kind": query.kind, "after": page[-1]["id"], "as_of": as_of},
            )
            if len(items) > query.page_size
            else None,
            "data_as_of": as_of,
            "scope_version": access.auth_version,
        }
