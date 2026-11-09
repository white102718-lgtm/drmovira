"""分配专属候选；仅accounts.assign，不借read/import/system.users扩大权限。"""

import hashlib

from sqlalchemy import text

from orbit_api.account_access import parameters
from orbit_api.account_actions_store import AccountActionsStore
from orbit_api.account_details_store import PERSON_NAME_SQL
from orbit_api.account_identities_store import identifier
from orbit_api.configuration import short_text
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import clock as reference_clock
from orbit_api.reference_access import scope_clause, scope_version, validate_ownership
from orbit_api.vendor_alias_snapshot import freeze_vendor_alias_snapshots

PURPOSE = "ACCOUNT_ASSIGNMENT_OPTIONS_CURSOR_V1"


def parse_options(values):
    """QueryParams重复项由统一边界拒绝；这里固定允许的候选类型及联动字段。"""
    kind = values.get("kind")
    if kind not in {"OWNER", "VENDOR"}:
        raise OrbitError(422, "FIELD_INVALID", "请选择投手或户商候选类型", "/kind")
    size = values.get("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "候选每页仅允许20、50、100、200", "/page_size")
    owner = values.get("owner_user_id")
    if (kind == "OWNER" and owner is not None) or (kind == "VENDOR" and owner is None):
        raise OrbitError(
            422, "FIELD_INVALID", "户商候选须明确目标投手，投手候选不接拥有者", "/owner_user_id"
        )
    if owner is not None:
        owner = identifier(owner, "/owner_user_id")
    query = short_text(values.get("q", ""), 100, "/q", required=False)
    cursor = values.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "候选游标长度无效", "/cursor")
    return {
        "kind": kind,
        "page_size": int(size),
        "owner_user_id": owner,
        "q": query,
        "cursor": cursor,
    }


class AccountAssignmentOptions:
    def __init__(self, tokens):
        self.tokens = tokens

    async def list(self, session, actor, account_id, query):
        current, managed, account = await AccountActionsStore(self.tokens).lock_account(
            session, actor, account_id, "ASSIGNMENT", write=False
        )
        if account["unbound_at"] is not None:
            raise OrbitError(409, "ACCOUNT_ALREADY_UNBOUND", "本地解绑账户不能选择新归属")
        directory_version = await scope_version(session, current)
        auth_version = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": actor},
            )
        ).scalar_one()
        catalog = await reference_clock(session, current)
        fingerprint = hashlib.sha256(
            canonical(
                [
                    actor,
                    current.tenant_id,
                    current.subject_id,
                    current.data_role,
                    current.team_id,
                    sorted(managed),
                    directory_version,
                    auth_version,
                    catalog["revision"],
                    account["id"],
                    account["revision"],
                    {key: value for key, value in query.items() if key != "cursor"},
                ]
            ).encode()
        ).hexdigest()
        after = ""
        if query["cursor"]:
            claims = self.tokens.verify(PURPOSE, query["cursor"])
            if claims.get("binding") != fingerprint:
                raise OrbitError(409, "SCOPE_CHANGED", "分配候选来源或权限已变化，请重新读取")
            after = identifier(claims.get("after"), "/cursor")
        params = parameters(current) | {
            "after": after,
            "limit": query["page_size"] + 1,
            "query": query["q"].replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%",
        }
        if query["kind"] == "OWNER":
            rows = await self.owners(session, current, params)
        else:
            rows = await self.vendors(session, current, query["owner_user_id"], params)
        page = rows[: query["page_size"]]
        return {
            "items": page,
            "next_cursor": self.tokens.issue(
                PURPOSE, {"binding": fingerprint, "after": page[-1]["id"]}
            )
            if len(rows) > len(page)
            else None,
        }

    @staticmethod
    def owner_clause(current):
        if current.data_role == "SUPER_ADMIN":
            return "1=1"
        if current.data_role == "TEAM_ADMIN":
            return (
                "b.id=:subject OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
                "WHERE tm.tenant_id=b.tenant_id AND tm.team_id=b.team_id "
                "AND tm.manager_user_id=:actor AND tm.enabled=1)"
            )
        return "b.id=:subject"

    @classmethod
    async def owners(cls, session, current, params):
        rows = (
            await session.execute(
                text(
                    "SELECT b.id," + PERSON_NAME_SQL + " name,b.team_id,t.name team_name "
                    "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
                    "JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id "
                    "JOIN orbit_business_team t ON t.id=b.team_id AND t.tenant_id=b.tenant_id "
                    "WHERE b.tenant_id=:tenant AND b.id>:after AND b.enabled=1 AND b.invited=0 "
                    "AND s.enabled=1 AND u.status='0' AND u.del_flag='0' AND t.enabled=1 "
                    "AND (" + cls.owner_clause(current) + ") "
                    "AND " + PERSON_NAME_SQL + " LIKE :query ESCAPE '!' "
                    "ORDER BY b.id LIMIT :limit FOR SHARE OF b,u,s,t"
                ),
                params,
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def vendors(self, session, current, owner, params):
        target = (
            (
                await session.execute(
                    text(
                        "SELECT b.team_id FROM orbit_business_user b "
                        "JOIN sys_user u ON u.user_id=b.user_id "
                        "JOIN orbit_user_scope s ON s.user_id=b.user_id "
                        "AND s.tenant_id=b.tenant_id "
                        "JOIN orbit_business_team t ON t.id=b.team_id AND t.tenant_id=b.tenant_id "
                        "WHERE b.tenant_id=:tenant AND b.id=:owner AND b.enabled=1 AND b.invited=0 "
                        "AND s.enabled=1 AND u.status='0' AND u.del_flag='0' AND t.enabled=1 "
                        "AND (" + self.owner_clause(current) + ") FOR SHARE OF b,u,s,t"
                    ),
                    params | {"owner": owner},
                )
            )
            .mappings()
            .first()
        )
        if target is None:
            raise OrbitError(404, "NOT_FOUND", "目标投手不存在或不可管理")
        await validate_ownership(
            session, current, {"owner_team_id": target["team_id"], "data_owner_user_ids": [owner]}
        )
        records = list(
            (
                await session.execute(
                    text(
                        "SELECT r.id,r.kind,r.value_json,r.revision,"
                        "r.catalog_revision,r.updated_at "
                        "FROM orbit_reference_record r "
                        "WHERE r.tenant_id=:tenant AND r.kind='VENDOR' "
                        "AND r.availability='AVAILABLE' AND r.owner_team_id=:team AND r.id>:after "
                        "AND r.name LIKE :query ESCAPE '!' "
                        "AND ("
                        + scope_clause(current, "r", "orbit_reference_owner", "reference_id")
                        + ") "
                        "AND EXISTS(SELECT 1 FROM orbit_reference_owner o "
                        "WHERE o.tenant_id=r.tenant_id "
                        "AND o.reference_id=r.id AND o.user_id=:owner) "
                        "ORDER BY r.id LIMIT :limit FOR SHARE OF r"
                    ),
                    params | {"team": target["team_id"], "owner": owner},
                )
            ).mappings()
        )
        # +1仅用于has_more，不进入别名helper的200上限；不按旧目录name推断alias。
        page = records[: params["limit"] - 1]
        aliases = (
            await freeze_vendor_alias_snapshots(
                session,
                current,
                {row["id"]: dict(row) for row in page},
                permission="accounts.assign",
            )
            if page
            else {}
        )
        values = []
        for row in records:
            value = _decode(row["value_json"])
            if (
                value["availability"] != "AVAILABLE"
                or value["owner_team_id"] != target["team_id"]
                or owner not in value["data_owner_user_ids"]
            ):
                raise OrbitError(409, "CATALOG_CHANGED", "户商候选资料与索引归属不一致")
            values.append(
                {
                    "id": row["id"],
                    "name": value["name"],
                    "alias": aliases.get(row["id"], {}).get("alias"),
                }
            )
        return values
