"""规则账户候选和creator私有冻结；只沿原rules动作，外层事务原子发布。"""

import hashlib
import json
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError

from orbit_api.account_access import clock
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_store import utc
from orbit_api.account_selection import selection_sql
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import verify_csrf
from orbit_api.rule_access import (
    authorize_rule,
    owner_scope,
    readable,
    require_rule_visible,
    revalidate_access,
    revalidate_owner,
    transaction,
)
from orbit_api.rule_contract import MAX_SAFE, identifier
from orbit_api.rule_editor_scope_contract import PURPOSE, ScopeContext, ScopeQuery, ScopeWrite
from orbit_api.rule_store import RuleStore
from orbit_api.scope_selection_engine import BATCH_SIZE, FrozenMemberRoot


def changed():
    raise OrbitError(409, "RULE_EDITOR_SCOPE_CHANGED", "规则账户范围或当前授权已变化，请重新选择")


def missing():
    raise OrbitError(404, "NOT_FOUND", "规则账户范围不存在或不属于当前创建者")


def corrupt():
    raise OrbitError(503, "RULE_EDITOR_SCOPE_UNAVAILABLE", "规则账户范围完整性尚未就绪")


async def rows(session, statement, values, *, ids=None):
    query = text(statement)
    if ids is not None:
        query = query.bindparams(bindparam("ids", expanding=True))
        values = values | {"ids": list(ids)}
    return list((await session.execute(query, values)).mappings())


def visibility(current, managed, prefix):
    # prefix是本模块两个固定调用点，不接受请求SQL、别名或回调。
    if prefix not in {"caller", "owner"}:
        raise ValueError("FIXED_SCOPE_PREFIX_REQUIRED")
    values = {prefix + "_subject": current.subject_id}
    if current.data_role == "SUPER_ADMIN":
        return "1=1", values
    clause = "a.owner_user_id=:" + prefix + "_subject"
    if current.data_role == "TEAM_ADMIN" and managed:
        names = []
        for index, team in enumerate(managed):
            name = prefix + "_team_" + str(index)
            names.append(":" + name)
            values[name] = team
        clause += " OR a.owner_team_id IN (" + ",".join(names) + ")"
    return "(" + clause + ")", values


class RuleEditorScopeStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def _rule(self, session, access, rule_id, *, lock=False):
        found = await rows(
            session,
            "SELECT h.*,v.payload_json,v.payload_hash,v.metric_profile_version,"
            "v.metric_profile_hash,v.profile_proof_hash FROM orbit_rule_head h "
            "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id AND v.rule_id=h.id "
            "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.id=:id "
            + ("FOR SHARE OF h,v" if lock else ""),
            {"tenant": access.current.tenant_id, "id": rule_id},
        )
        value = dict(found[0]) if len(found) == 1 else None
        require_rule_visible(access, value)
        RuleStore.public(value)
        return value

    async def _begin(self, session, actor, context, *, editing=True):
        transaction(session)
        if not isinstance(context, ScopeContext):
            raise ValueError("TYPED_SCOPE_CONTEXT_REQUIRED")
        access = await authorize_rule(
            session, actor, "rules.create" if context.action == "CREATE" else "rules.edit"
        )
        previous = await self._rule(session, access, context.rule_id) if context.rule_id else None
        if editing and previous is not None and previous["state"] not in {"DRAFT", "PAUSED"}:
            raise OrbitError(409, "RULE_STATE_CONFLICT", "当前规则状态不能重新选择账户")
        owner = await owner_scope(
            session, access, context.ownership, for_write=True, previous=previous
        )
        return access, owner, previous

    async def _finish(self, session, access, owner, previous, *, expected=None):
        if previous is not None:
            clocks = await rows(
                session,
                "SELECT revision FROM orbit_rule_clock WHERE tenant_id=:tenant FOR SHARE",
                {"tenant": access.current.tenant_id},
            )
            if len(clocks) != 1:
                corrupt()
            current = await self._rule(session, access, previous["id"], lock=True)
            if (
                any(
                    current[key] != previous[key]
                    for key in (
                        "revision",
                        "payload_hash",
                        "owner_user_id",
                        "owner_team_id",
                        "state",
                    )
                )
                or expected is not None
                and current["revision"] != expected
            ):
                changed()
            # previous仅来自同事务当前规则，scope历史previous不授永久旧owner指派权。
            await owner_scope(
                session,
                access,
                {"owner_user_id": owner.current.subject_id, "owner_team_id": owner.current.team_id},
                for_write=True,
                previous=current,
            )
        await revalidate_access(session, access)
        await revalidate_owner(session, access, owner)

    async def _watermark(self, session, access):
        revision = await clock(session, access.current)
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        return revision, iso(utc(now))

    def _cursor(self, query, binding, *, domain):
        if query.cursor is None:
            return "", None
        claims = self.tokens.verify(PURPOSE, query.cursor)
        if claims.get("domain") != domain or claims.get("binding") != binding:
            changed()
        after = identifier(claims.get("after"), "/cursor")
        from orbit_api.rule_contract import _utc

        _utc(claims.get("as_of"), "/cursor")
        return after, claims["as_of"]

    def _binding(self, authorization, access, owner, previous, query, version, extra):
        value = asdict(query)
        value.pop("cursor")
        return hashlib.sha256(
            canonical(
                [
                    self.tokens.session_binding(
                        authorization, access.current.actor_id, access.current.tenant_id
                    ),
                    access.auth_fingerprint,
                    owner.auth_fingerprint,
                    previous["revision"] if previous else None,
                    version,
                    value,
                    extra,
                ]
            ).encode()
        ).hexdigest()

    def _page(self, query, binding, rows_, as_of, access, *, domain):
        page = rows_[: query.page_size]
        return {
            "items": [
                {
                    "account_id": row["account_id"],
                    "external_id": row["external_id"],
                    "name": row["name"],
                }
                for row in page
            ],
            "next_cursor": self.tokens.issue(
                PURPOSE,
                {
                    "domain": domain,
                    "binding": binding,
                    "as_of": as_of,
                    "after": page[-1]["account_id"],
                },
            )
            if len(rows_) > query.page_size
            else None,
            "data_as_of": as_of,
            "scope_version": access.auth_version,
        }

    async def accounts(self, session, actor, authorization, query):
        if not isinstance(query, ScopeQuery) or query.context is None:
            raise ValueError("TYPED_ACCOUNT_QUERY_REQUIRED")
        access, owner, previous = await self._begin(session, actor, query.context)
        version, now = await self._watermark(session, access)
        binding = self._binding(authorization, access, owner, previous, query, version, None)
        after, as_of = self._cursor(query, binding, domain="RULE_EDITOR_ACCOUNTS_V1")
        if as_of is not None and as_of > now:
            changed()
        clauses, values = self._clauses(access, owner, query.query)
        found = await rows(
            session,
            "SELECT a.id AS account_id,a.external_id,a.name FROM orbit_ad_account a WHERE "
            + " AND ".join(clauses + ["a.id>:after"])
            + " ORDER BY a.id LIMIT :limit FOR SHARE OF a",
            values | {"after": after, "limit": query.page_size + 1},
        )
        await self._finish(session, access, owner, previous)
        return self._page(
            query, binding, found, as_of or now, access, domain="RULE_EDITOR_ACCOUNTS_V1"
        )

    def _clauses(self, access, owner, query):
        caller_sql, caller = visibility(access.current, access.managed_team_ids, "caller")
        owner_sql, owned = visibility(owner.current, owner.managed_team_ids, "owner")
        filters_, selected = selection_sql(query)
        return ["a.tenant_id=:tenant", caller_sql, owner_sql] + filters_, {
            "tenant": access.current.tenant_id,
        } | caller | owned | selected

    @staticmethod
    def public(row):
        return {
            "id": row["id"],
            "count": row["member_count"],
            "hash": row["members_hash"],
            "scope_version": row["scope_version"],
            "created_at": iso(utc(row["created_at"])),
        }

    async def create(self, session, actor, authorization, csrf, key, value, expected, request_id):
        if not isinstance(value, ScopeWrite):
            raise ValueError("TYPED_SCOPE_WRITE_REQUIRED")
        access, owner, previous = await self._begin(session, actor, value.context, editing=False)
        try:
            verify_csrf(self.tokens, access.current, authorization, csrf)
        except OrbitError:
            raise OrbitError(403, "CSRF_INVALID", "规则账户会话校验已失效") from None
        request_id = identifier(request_id, "/request_id")
        tenant = access.current.tenant_id
        version, _now = await self._watermark(session, access)
        params = {"tenant": tenant, "actor": actor, "key": key}
        stored = await rows(
            session,
            "SELECT * FROM orbit_rule_editor_scope_snapshot WHERE "
            "tenant_id=:tenant AND actor_id=:actor "
            "AND request_key=:key",
            params,
        )
        if stored:
            # 当前锁读不能沿用外层RR旧快照中的ready/count/hash。
            return await self._replay(session, access, owner, previous, value, params, expected)
        if previous is not None and previous["state"] not in {"DRAFT", "PAUSED"}:
            raise OrbitError(409, "RULE_STATE_CONFLICT", "当前规则状态不能重新选择账户")
        if previous is None:
            if expected is not None:
                raise OrbitError(400, "INVALID_STRUCTURE", "新建不能携带If-Match")
        elif (
            type(expected) is not int
            or not 1 <= expected <= MAX_SAFE
            or previous["revision"] != expected
        ):
            changed()
        identifier_new = str(uuid4())
        intent = json.loads(value.canonical) | {"rule_revision": expected}
        params |= {
            "id": identifier_new,
            "action": value.context.action,
            "rule": value.context.rule_id,
            "rule_revision": expected,
            "owner": value.context.owner_user_id,
            "team": value.context.owner_team_id,
            "scope": access.auth_version,
            "auth": access.auth_fingerprint,
            "owner_auth": owner.auth_fingerprint,
            "clock": version,
            "hash": hashlib.sha256(canonical(intent).encode()).hexdigest(),
            "body": canonical(intent),
        }
        # 不锁不存在的unique gap，也不借ON DUPLICATE触发对sealed范围的UPDATE。
        try:
            await session.execute(
                text(
                    "INSERT INTO orbit_rule_editor_scope_snapshot(tenant_id,id,"
                    "actor_id,action,rule_id,rule_revision,"
                    "owner_user_id,owner_team_id,scope_version,"
                    "auth_fingerprint,owner_auth_fingerprint,"
                    "account_clock_revision,request_key,request_hash,request_json) VALUES "
                    "(:tenant,:id,:actor,:action,:rule,:rule_revision,:owner,"
                    ":team,:scope,:auth,:owner_auth,:clock,:key,:hash,:body)"
                ),
                params,
            )
        except DBAPIError as error:
            if not error.orig.args or error.orig.args[0] != 1062:
                raise
            return await self._replay(session, access, owner, previous, value, params, expected)
        root = FrozenMemberRoot()
        selected = value.selection
        clauses, values = self._clauses(access, owner, selected.query or {"q": ""})
        ids = selected.account_ids if selected.mode == "IDS" else None
        # IDS按最多1000个排序ID分别读取；FILTER每轮真实keyset，均无50k参数IN。
        batches = range(0, len(ids), BATCH_SIZE) if ids is not None else None
        indexes = iter(batches) if batches is not None else None
        while True:
            batch_ids = (
                ids[next_index : next_index + BATCH_SIZE]
                if indexes is not None and (next_index := next(indexes, None)) is not None
                else None
            )
            if indexes is not None and batch_ids is None:
                break
            found = await rows(
                session,
                "SELECT a.id AS account_id,a.external_id,a.name,a.name_prefix,"
                "a.revision AS account_revision,"
                "a.owner_user_id,a.owner_team_id,a.currency FROM orbit_ad_account a WHERE "
                + " AND ".join(clauses + (["a.id IN :ids"] if ids is not None else ["a.id>:after"]))
                + " ORDER BY a.id LIMIT :limit FOR SHARE OF a",
                values | {"after": root.after, "limit": BATCH_SIZE},
                ids=batch_ids,
            )
            if batch_ids is not None and len(found) != len(batch_ids):
                missing()
            if not found:
                break
            payloads = []
            for row in found:
                root.add(row)
                payloads.append(dict(row) | {"tenant": tenant, "snapshot": identifier_new})
            await session.execute(
                text(
                    "INSERT INTO orbit_rule_editor_scope_member(tenant_id,"
                    "snapshot_id,account_id,external_id,name,"
                    "name_prefix,account_revision,owner_user_id,owner_team_id,currency) VALUES "
                    "(:tenant,:snapshot,:account_id,:external_id,:name,"
                    ":name_prefix,:account_revision,:owner_user_id,:owner_team_id,:currency)"
                ),
                payloads,
            )
        if root.count == 0:
            raise OrbitError(422, "SCOPE_ACCOUNT_LIMIT", "规则必须选择1至50000个账户")
        if ids is not None and root.count != len(ids):
            missing()
        await self._finish(session, access, owner, previous, expected=expected)
        params |= {
            "count": root.count,
            "root": root.hexdigest(),
            "event": str(uuid4()),
            "request": request_id,
        }
        await session.execute(
            text(
                "UPDATE orbit_rule_editor_scope_snapshot SET ready=1,member_count=:count,"
                "members_hash=:root WHERE tenant_id=:tenant AND id=:id"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_rule_editor_scope_event(tenant_id,id,"
                "snapshot_id,actor_id,request_id,member_count,members_hash) "
                "VALUES(:tenant,:event,:id,:actor,:request,:count,:root)"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_rule_editor_scope_outbox(tenant_id,event_id,"
                "snapshot_id) VALUES(:tenant,:event,:id)"
            ),
            params,
        )
        result = await rows(
            session,
            "SELECT * FROM orbit_rule_editor_scope_snapshot WHERE "
            "tenant_id=:tenant AND id=:id FOR SHARE",
            params,
        )
        if len(result) != 1:
            corrupt()
        return self.public(result[0])

    async def _replay(self, session, access, owner, previous, value, params, expected):
        found = await rows(
            session,
            "SELECT * FROM orbit_rule_editor_scope_snapshot "
            "WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR SHARE",
            params,
        )
        if len(found) != 1:
            corrupt()
        row = dict(found[0])
        try:
            intent = (
                json.loads(row["request_json"])
                if isinstance(row["request_json"], str)
                else row["request_json"]
            )
            saved_revision = intent["rule_revision"]
            body = {k: v for k, v in intent.items() if k != "rule_revision"}
            if hashlib.sha256(canonical(intent).encode()).hexdigest() != row["request_hash"]:
                corrupt()
            if canonical(body) != value.canonical:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同规则账户选择")
            if saved_revision != row["rule_revision"]:
                corrupt()
            # If-Match也是原请求意图；当前head可已变化，但不能换CAS沿用原key。
            requested = json.loads(value.canonical) | {"rule_revision": expected}
            if canonical(intent) != canonical(requested):
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同规则版本的账户选择")
            if (
                row["action"] != value.context.action
                or row["rule_id"] != value.context.rule_id
                or row["owner_user_id"] != value.context.owner_user_id
                or row["owner_team_id"] != value.context.owner_team_id
            ):
                corrupt()
        except (KeyError, TypeError, ValueError):
            corrupt()
        await self._verify_snapshot(session, access, owner, row)
        await self._finish(session, access, owner, previous)
        return self.public(row)

    async def _verify_snapshot(self, session, access, owner, snapshot):
        if (
            snapshot["actor_id"] != access.current.actor_id
            or snapshot["tenant_id"] != access.current.tenant_id
        ):
            missing()
        if (
            snapshot["ready"] != 1
            or snapshot["scope_version"] != access.auth_version
            or snapshot["auth_fingerprint"] != access.auth_fingerprint
            or snapshot["owner_auth_fingerprint"] != owner.auth_fingerprint
        ):
            changed()
        root = FrozenMemberRoot()
        while True:
            found = await rows(
                session,
                "SELECT m.*,a.id AS current_id,a.owner_user_id AS "
                "current_owner,a.owner_team_id AS current_team "
                "FROM orbit_rule_editor_scope_member m LEFT JOIN orbit_ad_account a "
                "ON a.tenant_id=m.tenant_id AND a.id=m.account_id "
                "WHERE m.tenant_id=:tenant AND m.snapshot_id=:id AND m.account_id>:after "
                "ORDER BY m.account_id LIMIT 1000 FOR SHARE OF m,a",
                {"tenant": access.current.tenant_id, "id": snapshot["id"], "after": root.after},
            )
            if not found:
                break
            for row in found:
                live = {"owner_user_id": row["current_owner"], "owner_team_id": row["current_team"]}
                if (
                    row["current_id"] != row["account_id"]
                    or not readable(access.current, access.managed_team_ids, live)
                    or not readable(owner.current, owner.managed_team_ids, live)
                ):
                    changed()
                try:
                    root.add(row)
                except OrbitError as error:
                    # 持久成员不是本次用户字段；坏UUID不得伪装为请求参数422。
                    if error.status == 422 and error.code in {
                        "FIELD_INVALID",
                        "FIELD_VALIDATION_FAILED",
                    }:
                        corrupt()
                    raise
        if (
            root.count != snapshot["member_count"]
            or not 1 <= root.count <= 50000
            or root.hexdigest() != snapshot["members_hash"]
        ):
            corrupt()

    async def members(self, session, actor, authorization, snapshot_id, query):
        transaction(session)
        snapshot_id = identifier(snapshot_id, "/snapshot_id")
        if not isinstance(query, ScopeQuery) or query.context is not None:
            raise ValueError("TYPED_MEMBER_QUERY_REQUIRED")
        # 预读仅取得原动作/owner上下文；不能据此返回成员，之后当前锁完整重验。
        found = await rows(
            session,
            "SELECT * FROM orbit_rule_editor_scope_snapshot WHERE id=:id AND actor_id=:actor",
            {"id": snapshot_id, "actor": actor},
        )
        if len(found) != 1:
            missing()
        probe = dict(found[0])
        scope_context = ScopeContext(
            probe["action"], probe["rule_id"], probe["owner_user_id"], probe["owner_team_id"]
        )
        access, owner, previous = await self._begin(session, actor, scope_context, editing=False)
        version, now = await self._watermark(session, access)
        found = await rows(
            session,
            "SELECT * FROM orbit_rule_editor_scope_snapshot WHERE "
            "tenant_id=:tenant AND id=:id AND actor_id=:actor FOR SHARE",
            {"tenant": access.current.tenant_id, "id": snapshot_id, "actor": actor},
        )
        if len(found) != 1:
            missing()
        snapshot = dict(found[0])
        if snapshot != probe:
            changed()
        await self._verify_snapshot(session, access, owner, snapshot)
        binding = self._binding(
            authorization,
            access,
            owner,
            previous,
            query,
            version,
            [snapshot_id, snapshot["members_hash"], snapshot["member_count"]],
        )
        after, as_of = self._cursor(query, binding, domain="RULE_EDITOR_SCOPE_MEMBERS_V1")
        if as_of is not None and as_of > now:
            changed()
        clauses = ["tenant_id=:tenant", "snapshot_id=:id", "account_id>:after"]
        values = {
            "tenant": access.current.tenant_id,
            "id": snapshot_id,
            "after": after,
            "limit": query.page_size + 1,
        }
        q = query.query["q"]
        if q:
            external = q[4:] if q.startswith("act_") else q
            if external.isascii() and external.isdigit():
                clauses.append("external_id=:external")
                values["external"] = external
            else:
                clauses.append("name_prefix LIKE :search ESCAPE '!'")
                values["search"] = q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        found = await rows(
            session,
            "SELECT account_id,external_id,name FROM orbit_rule_editor_scope_member WHERE "
            + " AND ".join(clauses)
            + " ORDER BY account_id LIMIT :limit FOR SHARE",
            values,
        )
        await self._finish(session, access, owner, previous)
        return self._page(
            query,
            binding,
            found,
            as_of or iso(utc(snapshot["created_at"])),
            access,
            domain="RULE_EDITOR_SCOPE_MEMBERS_V1",
        )
