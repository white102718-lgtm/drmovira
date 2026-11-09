"""规则定义完整事务Store；无来源的模拟/启用不开放成功，无AI或平台写入。"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import verify_csrf
from orbit_api.reference_contract import pointer
from orbit_api.rule_access import (
    authorize_rule,
    owner_scope,
    require_rule_visible,
    revalidate_access,
    transaction,
)
from orbit_api.rule_contract import (
    MAX_SAFE,
    Rule,
    RuleWrite,
    _text,
    _utc,
    identifier,
    invalid,
    parse_rule_response,
    parse_rule_write,
)
from orbit_api.rule_profile_references import lock_rule_profile
from orbit_api.rule_scope_references import (
    RuleMember,
    capture_rule_scope,
    resolve_scope_source,
    revalidate_rule_members,
    verify_reused_scope_source,
)

PERMISSIONS = {
    "CREATE": "rules.create",
    "UPDATE": "rules.edit",
    "PAUSE": "rules.pause",
    "ARCHIVE": "rules.archive",
    "ENABLE": "rules.enable",
}
PAGE_SIZES = {20, 50, 100, 200}


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def unavailable():
    raise OrbitError(503, "RULE_STATE_UNAVAILABLE", "规则持久状态或完整引用尚未就绪")


def iso(value):
    if not isinstance(value, datetime):
        unavailable()
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def decoded(value):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        unavailable()


@dataclass(frozen=True)
class RuleQuery:
    q: str | None = None
    status: str | None = None
    operator_user_id: str | None = None
    metric_profile_id: str | None = None
    entity_type: str | None = None
    page_size: int = 50
    cursor: str | None = None


def parse_rule_query(values):
    if not isinstance(values, dict):
        raise OrbitError(400, "INVALID_STRUCTURE", "查询必须是参数对象")
    allowed = set(RuleQuery.__dataclass_fields__) | {"date_from", "date_to", "channel_id"}
    if set(values) - allowed:
        raise OrbitError(
            400, "UNKNOWN_FIELD", "查询包含未知字段", pointer((sorted(set(values) - allowed)[0],))
        )
    for field in ("date_from", "date_to", "channel_id"):
        if values.get(field) is not None and values.get(field) != "":
            invalid("/" + field, "该过滤语义尚未接入，不能静默忽略")
    result = {key: value for key, value in values.items() if key in RuleQuery.__dataclass_fields__}
    page = result.get("page_size", 50)
    if isinstance(page, str) and len(page) <= 32 and re.fullmatch(r"[0-9]+", page):
        page = int(page)
    if type(page) is not int or page not in PAGE_SIZES:
        invalid("/page_size")
    result["page_size"] = page
    for key in ("q", "status", "operator_user_id", "metric_profile_id", "entity_type", "cursor"):
        value = result.get(key)
        if value is not None and not isinstance(value, str):
            raise OrbitError(400, "INVALID_STRUCTURE", "查询字段必须是字符串", "/" + key)
    if result.get("q") is not None:
        # 原GET合同限定100个字符；与规则名称80字符的写入限制分别校验。
        result["q"] = _text(result["q"], "/q", 100, trim=True)
    for key in ("operator_user_id", "metric_profile_id"):
        if result.get(key) is not None:
            result[key] = identifier(result[key], "/" + key)
    if result.get("status") is not None and result["status"] not in {
        "DRAFT",
        "ENABLED",
        "PAUSED",
        "ARCHIVED",
    }:
        invalid("/status")
    if result.get("entity_type") is not None and result["entity_type"] not in {
        "CAMPAIGN",
        "ADSET",
        "AD",
    }:
        invalid("/entity_type")
    if result.get("cursor") is not None and not 1 <= len(result["cursor"]) <= 2048:
        invalid("/cursor")
    return RuleQuery(**result)


class RuleStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def capabilities(self, session, actor, authorization, action):
        permissions = PERMISSIONS | {"SIMULATE": "rules.read"}
        if not isinstance(action, str) or action not in permissions:
            invalid("/action", "请选择原规则动作")
        access = await authorize_rule(session, actor, permissions[action])
        return {
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {
                    "binding": self.tokens.session_binding(
                        authorization, actor, access.current.tenant_id
                    ),
                },
            )
        }

    async def _clock(self, session, access, *, write=False):
        row = (
            (
                await session.execute(
                    text(
                        "SELECT revision,UTC_TIMESTAMP(3) AS now FROM orbit_rule_clock "
                        "WHERE tenant_id=:tenant " + ("FOR UPDATE" if write else "FOR SHARE")
                    ),
                    {"tenant": access.current.tenant_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(503, "RULE_INITIALIZATION_REQUIRED", "规则业务迁移尚未完成")
        if type(row["revision"]) is not int or not 1 <= row["revision"] <= MAX_SAFE:
            unavailable()
        if write and row["revision"] == MAX_SAFE:
            raise OrbitError(409, "REVISION_EXHAUSTED", "规则目录版本已达上限")
        return row

    async def _row(self, session, access, rule_id, *, lock="SHARE"):
        rule_id = identifier(rule_id, "/id")
        row = (
            (
                await session.execute(
                    text(
                        "SELECT h.*,v.payload_json,v.payload_hash,v.metric_profile_version,"
                        "v.metric_profile_hash,v.profile_proof_hash FROM orbit_rule_head h "
                        "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id AND v.rule_id=h.id "
                        "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.id=:id "
                        + (
                            "FOR UPDATE OF h,v"
                            if lock == "UPDATE"
                            else "FOR SHARE OF h,v"
                            if lock
                            else ""
                        )
                    ),
                    {"tenant": access.current.tenant_id, "id": rule_id},
                )
            )
            .mappings()
            .first()
        )
        require_rule_visible(access, row)
        return dict(row)

    @staticmethod
    def public(row):
        try:
            body = decoded(row["payload_json"])
            value = parse_rule_write(canonical(body).encode()).model_dump()
            if (
                digest(value) != row["payload_hash"]
                or value["name"] != row["name"]
                or value["ownership"]["owner_user_id"] != row["owner_user_id"]
                or value["ownership"]["owner_team_id"] != row["owner_team_id"]
                or value["target_level"] != row["target_level"]
                or value["metric_profile_id"] != row["metric_profile_id"]
            ):
                unavailable()
            value.update(
                id=row["id"],
                revision=row["revision"],
                state=row["state"],
                next_run_at=iso(row["next_run_at"]) if row["next_run_at"] is not None else None,
            )
            return parse_rule_response(Rule, value).model_dump()
        except (KeyError, TypeError, ValueError, UnicodeError, OrbitError):
            unavailable()

    async def get(self, session, actor, rule_id):
        access = await authorize_rule(session, actor, "rules.read")
        await self._clock(session, access)
        return self.public(await self._row(session, access, rule_id))

    async def list(self, session, actor, query):
        if not isinstance(query, RuleQuery):
            raise ValueError("规则列表必须先严格解析原查询")
        query = parse_rule_query(
            {
                key: getattr(query, key)
                for key in RuleQuery.__dataclass_fields__
                if getattr(query, key) is not None
            }
        )
        access = await authorize_rule(session, actor, "rules.read")
        filters = {k: getattr(query, k) for k in RuleQuery.__dataclass_fields__ if k != "cursor"}
        binding = digest([access.current.tenant_id, actor, access.auth_fingerprint, filters])
        claims = self.tokens.verify("RULE_CURSOR_V1", query.cursor) if query.cursor else None
        if claims is not None and claims.get("binding") != binding:
            raise OrbitError(409, "SCOPE_CHANGED", "规则分页授权或过滤已变化")
        watermark = await self._clock(session, access)
        params = {
            "tenant": access.current.tenant_id,
            "subject": access.current.subject_id,
            "limit": query.page_size + 1,
        }
        clauses = ["h.tenant_id=:tenant"]
        if access.current.data_role != "SUPER_ADMIN":
            visible = "h.owner_user_id=:subject"
            if access.current.data_role == "TEAM_ADMIN" and access.managed_team_ids:
                visible += " OR h.owner_team_id IN :teams"
                params["teams"] = list(access.managed_team_ids)
            clauses.append("(" + visible + ")")
        for field, column in (
            ("status", "state"),
            ("operator_user_id", "owner_user_id"),
            ("metric_profile_id", "metric_profile_id"),
            ("entity_type", "target_level"),
        ):
            if getattr(query, field) is not None:
                clauses.append("h." + column + "=:" + field)
                params[field] = getattr(query, field)
        if query.q is not None:
            clauses.append("h.name LIKE :search ESCAPE '!'")
            params["search"] = (
                "%" + query.q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            )
        as_of = iso(watermark["now"])
        if claims is not None:
            if type(claims.get("revision")) is not int or not 1 <= claims["revision"] <= MAX_SAFE:
                raise OrbitError(400, "TOKEN_INVALID", "规则分页游标无效")
            if claims.get("revision") != watermark["revision"]:
                raise OrbitError(409, "RULE_CURSOR_STALE", "规则目录已变化，请从首页重新查询")
            try:
                if not isinstance(claims.get("after_time"), str) or not isinstance(
                    claims.get("as_of"), str
                ):
                    raise ValueError
                _utc(claims["after_time"], "/cursor")
                _utc(claims["as_of"], "/cursor")
                params["after_time"] = datetime.fromisoformat(
                    claims["after_time"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                params["after_id"] = identifier(claims["after_id"], "/cursor")
                as_of = claims["as_of"]
                datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError, OrbitError):
                raise OrbitError(400, "TOKEN_INVALID", "规则分页游标无效") from None
            clauses.append(
                "(h.created_at<:after_time OR (h.created_at=:after_time AND h.id<:after_id))"
            )
        sql = text(
            "SELECT h.*,v.payload_json,v.payload_hash,v.metric_profile_version,"
            "v.metric_profile_hash,v.profile_proof_hash FROM orbit_rule_head h "
            "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id "
            "AND v.rule_id=h.id AND v.revision=h.revision "
            "WHERE "
            + " AND ".join(clauses)
            + " ORDER BY h.created_at DESC,h.id DESC LIMIT :limit FOR SHARE OF h,v"
        )
        if "teams" in params:
            sql = sql.bindparams(bindparam("teams", expanding=True))
        rows = list((await session.execute(sql, params)).mappings())
        items = [self.public(row) for row in rows[: query.page_size]]
        cursor = None
        if len(rows) > query.page_size:
            last = rows[query.page_size - 1]
            cursor = self.tokens.issue(
                "RULE_CURSOR_V1",
                {
                    "binding": binding,
                    "revision": watermark["revision"],
                    "after_time": iso(last["created_at"]),
                    "after_id": last["id"],
                    "as_of": as_of,
                },
            )
        return {
            "items": items,
            "next_cursor": cursor,
            "data_as_of": as_of,
            "scope_version": access.auth_version,
        }

    def _csrf(self, access, authorization, csrf):
        try:
            verify_csrf(self.tokens, access.current, authorization, csrf)
        except OrbitError:
            raise OrbitError(403, "CSRF_INVALID", "规则会话校验已失效") from None

    @staticmethod
    def _key(key):
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not 16 <= len(key) <= 128
            or any(ord(c) < 32 or ord(c) == 127 for c in key)
        ):
            raise OrbitError(400, "IDEMPOTENCY_KEY_INVALID", "需要16至128位ASCII幂等键")
        return hashlib.sha256(key.encode()).hexdigest()

    async def _receipt(self, session, access, operation, key_hash, intent_hash, *, locked=False):
        row = (
            (
                await session.execute(
                    text(
                        "SELECT intent_hash,rule_id,response_json FROM orbit_rule_idempotency "
                        "WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND operation=:op AND key_hash=:key " + ("FOR UPDATE" if locked else "")
                    ),
                    {
                        "tenant": access.current.tenant_id,
                        "actor": access.current.actor_id,
                        "op": operation,
                        "key": key_hash,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        # 当前原operation动作始终授权，旧成功也不以read替换它；先当前对象范围再解释意图。
        await revalidate_access(session, access)
        if not locked:
            await self._clock(session, access)
        await self._row(session, access, row["rule_id"])
        if row["intent_hash"] != intent_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一键不能改变原操作完整意图")
        try:
            result = parse_rule_response(Rule, decoded(row["response_json"])).model_dump()
            if result["id"] != row["rule_id"]:
                unavailable()
            return result
        except (KeyError, TypeError, ValueError, OrbitError):
            unavailable()

    async def _remember(self, session, access, operation, key_hash, intent_hash, result):
        await session.execute(
            text(
                "INSERT INTO orbit_rule_idempotency "
                "(tenant_id,actor_id,operation,key_hash,intent_hash,rule_id,response_json) "
                "VALUES(:tenant,:actor,:op,:key,:hash,:id,:body) "
                "ON DUPLICATE KEY UPDATE key_hash=key_hash"
            ),
            {
                "tenant": access.current.tenant_id,
                "actor": access.current.actor_id,
                "op": operation,
                "key": key_hash,
                "hash": intent_hash,
                "id": result["id"],
                "body": canonical(result),
            },
        )
        stored = await self._receipt(session, access, operation, key_hash, intent_hash, locked=True)
        if stored != result:
            unavailable()

    @staticmethod
    def _expected(expected):
        if expected is None:
            raise OrbitError(400, "REVISION_REQUIRED", "需要带引号的If-Match版本")
        if type(expected) is not int or not 1 <= expected <= MAX_SAFE:
            invalid("/If-Match")

    async def _manifest_members(self, session, access, rule_id, manifest_id):
        params = {"tenant": access.current.tenant_id, "rule": rule_id, "id": manifest_id}
        header = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_rule_scope_manifest WHERE tenant_id=:tenant "
                        "AND rule_id=:rule AND id=:id AND sealed=1 FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if header is None or not 1 <= header["member_count"] <= 50000:
            unavailable()
        result, after = [], ""
        while True:
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT account_id,frozen_owner_user_id,frozen_owner_team_id,"
                            "frozen_currency,"
                            "frozen_revision FROM orbit_rule_scope_member WHERE tenant_id=:tenant "
                            "AND manifest_id=:id AND account_id>:after "
                            "ORDER BY account_id LIMIT 1000 FOR SHARE"
                        ),
                        params | {"after": after},
                    )
                ).mappings()
            )
            if not rows:
                break
            for row in rows:
                if row["account_id"] <= after or len(result) >= 50000:
                    unavailable()
                after = row["account_id"]
                result.append(
                    RuleMember(
                        after,
                        row["frozen_owner_user_id"],
                        row["frozen_owner_team_id"],
                        row["frozen_currency"],
                        row["frozen_revision"],
                    )
                )
        if (
            len(result) != header["member_count"]
            or digest([m.account_id for m in result]) != header["member_ids_hash"]
        ):
            unavailable()
        return dict(header), tuple(result)

    async def save(
        self, session, actor, authorization, csrf, key, value, rule_id, expected, request_id
    ):
        """create/完整PUT；调用方须持外层事务，提交成功后才外显201/200。"""
        transaction(session)
        operation = "UPDATE" if rule_id else "CREATE"
        if rule_id:
            rule_id = identifier(rule_id, "/id")
            self._expected(expected)
        elif expected is not None:
            invalid("/If-Match")
        body = parse_rule_write(
            canonical(value.model_dump() if hasattr(value, "model_dump") else value).encode()
        ).model_dump()
        access = await authorize_rule(session, actor, PERMISSIONS[operation])
        self._csrf(access, authorization, csrf)
        key_hash = self._key(key)
        intent = digest([operation, rule_id, expected, body])
        success = await self._receipt(session, access, operation, key_hash, intent)
        if success is not None:
            return success
        # CREATE只生成一次真实目标ID，使scope首次绑定与最终manifest准确一致。
        target_rule_id = rule_id or str(uuid4())
        request_id = identifier(request_id, "/request_id")
        previous, scope, reused, profile, error = None, None, None, None, None
        try:
            previous = await self._row(session, access, rule_id, lock="") if rule_id else None
            if previous is not None and previous["state"] not in {"DRAFT", "PAUSED"}:
                raise OrbitError(409, "RULE_STATE_CONFLICT", "启用规则须先暂停，归档规则不可编辑")
            owner = await owner_scope(
                session,
                access,
                body["ownership"],
                for_write=True,
                previous={
                    "owner_user_id": previous["owner_user_id"],
                    "owner_team_id": previous["owner_team_id"],
                }
                if previous
                else None,
            )
            profile = await lock_rule_profile(session, access, owner, body["metric_profile_id"])
            old_body = self.public(previous) if previous else None
            if old_body and old_body["scope_snapshot_id"] == body["scope_snapshot_id"]:
                # 先accountclock/当前成员，再ruleclock/head；不借原creator私有接口。
                from orbit_api.account_access import clock as account_clock

                await account_clock(session, access.current)
                # 固定source锁在manifest/member之前；碰撞不能借同scope复用分支绕过。
                await resolve_scope_source(session, access, body["scope_snapshot_id"])
                reused, members = await self._manifest_members(
                    session, access, rule_id, previous["manifest_id"]
                )
                await verify_reused_scope_source(
                    session, access, body["scope_snapshot_id"], reused, rule_id
                )
                await revalidate_rule_members(session, access, owner, members)
            else:
                scope = await capture_rule_scope(
                    session,
                    access,
                    body["scope_snapshot_id"],
                    owner,
                    target_rule_id=target_rule_id,
                    expected=expected,
                )
        except OrbitError as caught:
            # 未锁预读不是最终授权：先让并发成功键/当前对象范围及CAS裁决，再暴露业务来源错误。
            error = caught
        await self._clock(session, access, write=True)
        replay = await self._receipt(session, access, operation, key_hash, intent, locked=True)
        if replay is not None:
            return replay
        locked = await self._row(session, access, rule_id, lock="UPDATE") if rule_id else None
        if locked is not None:
            if locked["revision"] != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "规则已变化，请重新加载")
            if locked["state"] not in {"DRAFT", "PAUSED"}:
                raise OrbitError(409, "RULE_STATE_CONFLICT", "启用或归档规则不可覆盖编辑")
            if previous is not None and (
                previous["revision"],
                previous["manifest_id"],
                previous["payload_hash"],
            ) != (locked["revision"], locked["manifest_id"], locked["payload_hash"]):
                raise OrbitError(409, "RULE_SOURCE_CHANGED", "规则预读源已变化，请重新提交")
        if error is not None:
            raise error
        await revalidate_access(session, access)
        duplicate = (
            (
                await session.execute(
                    text(
                        "SELECT id FROM orbit_rule_head WHERE tenant_id=:tenant "
                        "AND active_name=:name "
                        "AND id<>:id LIMIT 1 FOR UPDATE"
                    ),
                    {"tenant": access.current.tenant_id, "name": body["name"], "id": rule_id or ""},
                )
            )
            .mappings()
            .first()
        )
        if duplicate is not None:
            raise OrbitError(409, "RULE_NAME_CONFLICT", "租户内未归档规则名称已使用", "/name")
        if (
            locked
            and digest(body) == locked["payload_hash"]
            and (
                profile.version,
                profile.profile_hash,
                digest(decoded(profile.source_proof_json.decode())),
            )
            == (
                locked["metric_profile_version"],
                locked["metric_profile_hash"],
                locked["profile_proof_hash"],
            )
        ):
            result = self.public(locked)
            await self._remember(session, access, operation, key_hash, intent, result)
            return result
        return await self._persist(
            session,
            access,
            operation,
            key_hash,
            intent,
            body,
            locked,
            profile,
            reused,
            scope,
            request_id,
            reason=None,
            creation_rule_id=target_rule_id,
        )

    async def _persist_manifest(self, session, access, rule_id, scope):
        if scope.source_kind not in {"ACCOUNT", "RULE"} or (
            scope.source_kind == "RULE" and scope._target_rule_id != rule_id
        ):
            raise ValueError("RULE_SCOPE_TARGET_BINDING_REQUIRED")
        manifest_id = str(uuid4())
        values = {
            "tenant": access.current.tenant_id,
            "manifest": manifest_id,
            "rule": rule_id,
            "source": scope.snapshot_id,
            "source_kind": scope.source_kind,
            "source_hash": scope.snapshot_hash,
            "hash": scope.member_hash,
            "count": len(scope.members),
            "actor": access.current.actor_id,
            "creator_auth": access.auth_fingerprint,
            "owner": scope._owner.current.subject_id,
            "team": scope._owner.current.team_id,
            "owner_auth": scope._owner.auth_fingerprint,
        }
        await session.execute(
            text(
                "INSERT INTO orbit_rule_scope_manifest(tenant_id,id,rule_id,"
                "source_snapshot_id,source_kind,"
                "source_snapshot_hash,member_ids_hash,member_count,created_by,creator_auth_fingerprint,"
                "owner_user_id,owner_team_id,owner_auth_fingerprint) VALUES "
                "(:tenant,:manifest,:rule,:source,:source_kind,:source_hash,:hash,:count,:actor,:creator_auth,:owner,:team,:owner_auth)"
            ),
            values,
        )
        for offset in range(0, len(scope.members), 1000):
            await session.execute(
                text(
                    "INSERT INTO orbit_rule_scope_member(tenant_id,manifest_id,account_id,"
                    "frozen_owner_user_id,frozen_owner_team_id,frozen_currency,frozen_revision) "
                    "VALUES(:tenant,:manifest,:account,:owner,:team,:currency,:revision)"
                ),
                [
                    {
                        "tenant": values["tenant"],
                        "manifest": manifest_id,
                        "account": member.account_id,
                        "owner": member.owner_user_id,
                        "team": member.owner_team_id,
                        "currency": member.currency,
                        "revision": member.revision,
                    }
                    for member in scope.members[offset : offset + 1000]
                ],
            )
        await session.execute(
            text(
                "UPDATE orbit_rule_scope_manifest SET sealed=1 "
                "WHERE tenant_id=:tenant AND id=:manifest"
            ),
            values,
        )
        return manifest_id

    async def _persist(
        self,
        session,
        access,
        operation,
        key_hash,
        intent,
        body,
        previous,
        profile,
        reused,
        scope,
        request_id,
        *,
        reason,
        creation_rule_id=None,
    ):
        rule_id = previous["id"] if previous else creation_rule_id or str(uuid4())
        revision = previous["revision"] + 1 if previous else 1
        if revision > MAX_SAFE:
            raise OrbitError(409, "REVISION_EXHAUSTED", "规则版本已达上限")
        state = (
            "PAUSED"
            if operation == "PAUSE"
            else "ARCHIVED"
            if operation == "ARCHIVE"
            else previous["state"]
            if previous
            else "DRAFT"
        )
        manifest_id = (
            previous["manifest_id"]
            if operation in {"PAUSE", "ARCHIVE"}
            else reused["id"]
            if reused
            else await self._persist_manifest(session, access, rule_id, scope)
        )
        values = {
            "tenant": access.current.tenant_id,
            "id": rule_id,
            "revision": revision,
            "actor": access.current.actor_id,
            "event": str(uuid4()),
            "request": request_id,
            "op": operation,
            "reason": reason,
            "name": body["name"],
            "state": state,
            "owner": body["ownership"]["owner_user_id"],
            "team": body["ownership"]["owner_team_id"],
            "target": body["target_level"],
            "manifest": manifest_id,
            "profile": body["metric_profile_id"],
            "profile_version": profile.version if profile else previous["metric_profile_version"],
            "profile_hash": profile.profile_hash if profile else previous["metric_profile_hash"],
            "proof_hash": digest(decoded(profile.source_proof_json.decode()))
            if profile
            else previous["profile_proof_hash"],
            "payload": canonical(body),
            "hash": digest(body),
            "details": canonical(
                {
                    "before_revision": previous["revision"] if previous else None,
                    "before_hash": previous["payload_hash"] if previous else None,
                    "before_state": previous["state"] if previous else None,
                    "after_hash": digest(body),
                    "after_state": state,
                }
            ),
        }
        await session.execute(
            text(
                "INSERT INTO orbit_rule_event(tenant_id,id,rule_id,revision,actor_id,request_id,"
                "action,reason,details_json) "
                "VALUES(:tenant,:event,:id,:revision,:actor,:request,:op,:reason,:details)"
            ),
            values,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_rule_version(tenant_id,rule_id,revision,payload_json,"
                "payload_hash,name,"
                "owner_user_id,owner_team_id,target_level,state,manifest_id,metric_profile_id,"
                "metric_profile_version,metric_profile_hash,profile_proof_hash,event_id) VALUES "
                "(:tenant,:id,:revision,:payload,:hash,:name,:owner,:team,:target,:state,:manifest,:profile,"
                ":profile_version,:profile_hash,:proof_hash,:event)"
            ),
            values,
        )
        if previous is None:
            await session.execute(
                text(
                    "INSERT INTO orbit_rule_head(tenant_id,id,revision,name,owner_user_id,"
                    "owner_team_id,"
                    "target_level,metric_profile_id,manifest_id,state,created_by) "
                    "VALUES(:tenant,:id,:revision,:name,:owner,:team,:target,:profile,:manifest,:state,:actor)"
                ),
                values,
            )
        else:
            updated = await session.execute(
                text(
                    "UPDATE orbit_rule_head SET revision=:revision,name=:name,owner_user_id=:owner,"
                    "owner_team_id=:team,target_level=:target,metric_profile_id=:profile,manifest_id=:manifest,"
                    "state=:state,next_run_at=NULL,updated_at=UTC_TIMESTAMP(3) "
                    "WHERE tenant_id=:tenant AND id=:id AND revision=:old_revision"
                ),
                values | {"old_revision": previous["revision"]},
            )
            if updated.rowcount != 1:
                raise OrbitError(409, "REVISION_CONFLICT", "规则CAS未命中")
        await session.execute(
            text("INSERT INTO orbit_rule_outbox(tenant_id,event_id) VALUES(:tenant,:event)"), values
        )
        await session.execute(
            text("UPDATE orbit_rule_clock SET revision=revision+1 WHERE tenant_id=:tenant"), values
        )
        result = self.public(await self._row(session, access, rule_id))
        await self._remember(session, access, operation, key_hash, intent, result)
        return result

    async def stop(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        rule_id,
        expected,
        reason,
        request_id,
        *,
        archive=False,
    ):
        transaction(session)
        if type(archive) is not bool:
            raise ValueError("归档分支必须由服务端显式指定")
        operation = "ARCHIVE" if archive else "PAUSE"
        rule_id = identifier(rule_id, "/id")
        self._expected(expected)
        reason = _text(reason, "/reason", 1000, trim=True)
        access = await authorize_rule(session, actor, PERMISSIONS[operation])
        self._csrf(access, authorization, csrf)
        key_hash, intent = (
            self._key(key),
            digest([operation, rule_id, expected, {"reason": reason}]),
        )
        replay = await self._receipt(session, access, operation, key_hash, intent)
        if replay is not None:
            return replay
        await self._clock(session, access, write=True)
        replay = await self._receipt(session, access, operation, key_hash, intent, locked=True)
        if replay is not None:
            return replay
        previous = await self._row(session, access, rule_id, lock="UPDATE")
        if previous["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "规则已变化")
        if previous["state"] not in ({"DRAFT", "PAUSED"} if archive else {"ENABLED"}):
            raise OrbitError(409, "RULE_STATE_CONFLICT", "当前规则状态不允许该操作")
        public = self.public(previous)
        body = {field: public[field] for field in RuleWrite.model_fields}
        return await self._persist(
            session,
            access,
            operation,
            key_hash,
            intent,
            body,
            previous,
            None,
            None,
            None,
            identifier(request_id, "/request_id"),
            reason=reason,
        )

    async def enable(
        self, session, actor, authorization, csrf, key, rule_id, expected, simulation_id, request_id
    ):
        transaction(session)
        access = await authorize_rule(session, actor, "rules.enable")
        self._csrf(access, authorization, csrf)
        self._expected(expected)
        rule_id, simulation_id = (
            identifier(rule_id, "/id"),
            identifier(simulation_id, "/simulation_id"),
        )
        key_hash = self._key(key)
        intent = digest(["ENABLE", rule_id, expected, {"simulation_id": simulation_id}])
        replay = await self._receipt(session, access, "ENABLE", key_hash, intent)
        if replay is not None:
            return replay
        await self._clock(session, access)
        row = await self._row(session, access, rule_id)
        if row["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "规则已变化")
        if row["state"] not in {"DRAFT", "PAUSED"}:
            raise OrbitError(409, "RULE_STATE_CONFLICT", "只有草稿或暂停规则可启用")
        raise OrbitError(
            503,
            "RULE_SIMULATION_SOURCE_UNAVAILABLE",
            "真实同版本十五分钟模拟来源尚未接入，不能启用",
        )

    async def simulate(
        self, session, actor, authorization, csrf, key, rule_id, expected, request_id
    ):
        transaction(session)
        access = await authorize_rule(session, actor, "rules.read")
        self._csrf(access, authorization, csrf)
        self._key(key)
        self._expected(expected)
        await self._clock(session, access)
        row = await self._row(session, access, identifier(rule_id, "/id"))
        if row["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "规则已变化")
        raise OrbitError(503, "RULE_SIMULATION_SOURCE_UNAVAILABLE", "完整真实事实模拟来源尚未接入")

    async def runs(self, session, actor, rule_id):
        access = await authorize_rule(session, actor, "rules.read")
        await self._clock(session, access)
        await self._row(session, access, identifier(rule_id, "/id"))
        raise OrbitError(
            503, "RULE_RUN_STORE_UNAVAILABLE", "真实调度记录尚未接入，不能以空数组冒充"
        )
