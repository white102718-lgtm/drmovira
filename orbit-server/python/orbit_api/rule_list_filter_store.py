"""当前可见Rule head引用ID键集；RC读取，规则clock冻结候选，末段当前授权。"""

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError
from orbit_api.rule_access import authorize_rule, revalidate_access, transaction
from orbit_api.rule_contract import MAX_SAFE, _utc, identifier
from orbit_api.rule_list_filter_contract import (
    DOMAIN,
    PURPOSE,
    RuleListFilterQuery,
    parse_list_filter_query,
    response_page,
    unavailable,
)
from orbit_api.rule_store import RuleStore, digest, iso


def visible_clause(access):
    current = access.current
    values = {"tenant": current.tenant_id, "subject": current.subject_id}
    if current.data_role == "SUPER_ADMIN":
        return "h.tenant_id=:tenant", values
    scope = "h.owner_user_id=:subject"
    if current.data_role == "TEAM_ADMIN" and access.managed_team_ids:
        scope += " OR h.owner_team_id IN :teams"
        values["teams"] = list(access.managed_team_ids)
    return "h.tenant_id=:tenant AND (" + scope + ")", values


def cursor_claims(tokens, token, binding, revision):
    if token is None:
        return "", None
    claims = tokens.verify(PURPOSE, token)
    if (
        type(claims) is not dict
        or set(claims) != {"binding", "revision", "after_id", "as_of", "exp", "kid"}
        or type(claims.get("revision")) is not int
        or not 1 <= claims["revision"] <= MAX_SAFE
    ):
        raise OrbitError(400, "TOKEN_INVALID", "规则候选分页游标无效")
    if claims["binding"] != binding or claims["revision"] != revision:
        raise OrbitError(409, "RULE_FILTER_CURSOR_STALE", "规则或当前授权已变化，请重新查询")
    try:
        after = identifier(claims["after_id"], "/cursor")
        _utc(claims["as_of"], "/cursor")
        if after != claims["after_id"]:
            raise ValueError
    except (OrbitError, ValueError, TypeError):
        raise OrbitError(400, "TOKEN_INVALID", "规则候选分页游标无效") from None
    return after, claims["as_of"]


class RuleListFilterStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def options(self, session, actor, authorization, query):
        transaction(session)
        if type(query) is not RuleListFilterQuery:
            raise ValueError("PARSED_RULE_LIST_FILTER_QUERY_REQUIRED")
        query = parse_list_filter_query(
            {"kind": query.kind, "page_size": query.page_size}
            | ({"cursor": query.cursor} if query.cursor is not None else {})
        )
        # Store不允许任意RR调用方误把旧read view与当前clock混用。
        isolation = (await session.connection()).get_isolation_level
        if await isolation() != "READ COMMITTED":
            raise ValueError("RULE_LIST_FILTER_READ_COMMITTED_REQUIRED")
        access = await authorize_rule(session, actor, "rules.read")
        clock = await RuleStore(None)._clock(session, access)
        binding = digest(
            [
                DOMAIN,
                access.current.tenant_id,
                actor,
                access.auth_fingerprint,
                self.tokens.session_binding(authorization, actor, access.current.tenant_id),
                query.kind,
                query.page_size,
            ]
        )
        after, as_of = cursor_claims(self.tokens, query.cursor, binding, clock["revision"])
        now = iso(clock["now"])
        if as_of is not None and as_of > now:
            raise OrbitError(400, "TOKEN_INVALID", "规则候选分页游标无效")
        column = "owner_user_id" if query.kind == "OPERATOR" else "metric_profile_id"
        clause, values = visible_clause(access)
        sql = text(
            "SELECT DISTINCT h."
            + column
            + " AS id FROM orbit_rule_head h WHERE "
            + clause
            + " AND h."
            + column
            + ">:after ORDER BY h."
            + column
            + " LIMIT :limit"
        )
        if "teams" in values:
            sql = sql.bindparams(bindparam("teams", expanding=True))
        found = list(
            (
                await session.execute(sql, values | {"after": after, "limit": query.page_size + 1})
            ).mappings()
        )
        ids = []
        for row in found:
            try:
                current = identifier(row["id"], "/items/id")
                if current != row["id"] or current <= (ids[-1] if ids else after):
                    unavailable()
            except (KeyError, TypeError, OrbitError):
                unavailable()
            ids.append(current)
        if len(ids) > query.page_size + 1:
            unavailable()
        shown = ids[: query.page_size]
        labels = {}
        if query.kind == "OPERATOR" and shown:
            names = text(
                "SELECT id,display_name FROM orbit_business_user "
                "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id"
            ).bindparams(bindparam("ids", expanding=True))
            for row in (
                await session.execute(names, {"tenant": access.current.tenant_id, "ids": shown})
            ).mappings():
                if row["id"] not in shown or row["id"] in labels:
                    unavailable()
                labels[row["id"]] = row["display_name"]
        cursor = None
        as_of = as_of or now
        if len(ids) > query.page_size:
            cursor = self.tokens.issue(
                PURPOSE,
                {
                    "binding": binding,
                    "revision": clock["revision"],
                    "after_id": shown[-1],
                    "as_of": as_of,
                },
            )
        value = response_page(
            {
                "items": [{"id": item, "label": labels.get(item)} for item in shown],
                "next_cursor": cursor,
                "data_as_of": as_of,
                "scope_version": access.auth_version,
            }
        )
        await revalidate_access(session, access)
        return value
