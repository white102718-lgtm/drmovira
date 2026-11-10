"""账户本地动作事务：未来分配、真实只读排队、本地解绑，均不触发平台写入。"""

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import clock, context, event, parameters, visible_clause
from orbit_api.account_actions_contract import next_business_midnight, validate_effective
from orbit_api.account_alias_snapshots import append_account_alias_snapshot
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_store import identifier, utc
from orbit_api.account_platform import AccountReadFailure, MetaReadConfiguration
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_account_sources import account_source, connection_row, source_marker
from orbit_api.reference_access import readable, validate_ownership, verify_csrf
from orbit_api.reference_store import records
from orbit_api.vendor_alias_snapshot import freeze_vendor_alias_snapshots

PERMISSIONS = {
    "ASSIGNMENT": "accounts.assign",
    "SYNC": "accounts.sync",
    "UNBIND": "accounts.unbind",
}


def ownership(row):
    return {key: row[key] for key in ("owner_user_id", "owner_team_id", "vendor_id")}


def projection_instant(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("到期保护必须使用带时区的可信时刻")
    return now.astimezone(UTC).replace(tzinfo=None)


async def require_projection_current(session, tenant, account_id, now):
    """对象动作/同步门禁；共享读取另有租户门禁，接线后的真实复验由主线执行。"""
    pending = (
        await session.execute(
            text(
                "SELECT 1 FROM orbit_account_command WHERE tenant_id=:tenant "
                "AND account_id=:id AND kind='ASSIGNMENT' AND active_kind='ASSIGNMENT' "
                "AND effective_from<=:now LIMIT 1 FOR SHARE"
            ),
            {"tenant": tenant, "id": account_id, "now": projection_instant(now)},
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise OrbitError(
            503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "账户到期归属尚未追平，请恢复分配任务后重试"
        )


async def require_tenant_projections_current(session, tenant, now):
    """列表/范围筛选前的保守门禁；不因旧owner过滤而漏掉本应转入的新账户。

    不在每个GET升级账户时钟写锁，避免20并发读被串行；独立Worker追平后再恢复读取。
    已由主线接公共账户clock，旧导入Worker另接；真实到期保护正在排队验收。
    """
    pending = (
        await session.execute(
            text(
                "SELECT 1 FROM orbit_account_command WHERE tenant_id=:tenant "
                "AND active_kind='ASSIGNMENT' AND effective_from<=:now LIMIT 1 FOR SHARE"
            ),
            {"tenant": tenant, "now": projection_instant(now)},
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise OrbitError(
            503,
            "ACCOUNT_ASSIGNMENT_PROJECTION_LAG",
            "存在到期未追平账户，范围查询暂不可用，请先恢复分配任务",
        )


async def assignment_vendor(session, current, managed, target, *, acting_subject=True):
    await validate_ownership(
        session,
        current,
        {"owner_team_id": target.owner_team_id, "data_owner_user_ids": [target.operator_user_id]},
    )
    if target.vendor_id is None:
        return None, {"alias": None, "alias_revision": None, "source": "NO_VENDOR"}
    vendor = (await records(session, current.tenant_id, [target.vendor_id])).get(target.vendor_id)
    if vendor is None or vendor["kind"] != "VENDOR":
        raise OrbitError(404, "NOT_FOUND", "目标户商不存在或不可见")
    value = _decode(vendor["value_json"])
    if not readable(current, managed, value):
        raise OrbitError(404, "NOT_FOUND", "目标户商不存在或不可见")
    if (
        value["availability"] != "AVAILABLE"
        or value["owner_team_id"] != target.owner_team_id
        or target.operator_user_id not in value["data_owner_user_ids"]
    ):
        raise OrbitError(422, "REFERENCE_OWNER_MISMATCH", "目标户商必须启用且对目标团队投手可读")
    frozen = await freeze_vendor_alias_snapshots(
        session,
        current,
        {target.vendor_id: vendor},
        permission="accounts.assign",
        acting_subject=acting_subject,
    )
    return vendor, frozen[target.vendor_id] | {"name": value["name"]}


class AccountActionsStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def lock_account(self, session, actor, account_id, kind, *, write=True):
        account_id = identifier(account_id, "/id")
        current, managed = await context(session, actor, PERMISSIONS[kind])
        clock_revision = await clock(session, current, write=write)
        if clock_revision >= MAX_REVISION - 3:
            raise OrbitError(409, "REVISION_EXHAUSTED", "账户动作审计版本已达安全上限")
        row = (
            (
                await session.execute(
                    text(
                        "SELECT a.* FROM orbit_ad_account a WHERE a.tenant_id=:tenant "
                        "AND a.id=:id AND ("
                        + visible_clause(current, "a")
                        + ") "
                        + ("FOR UPDATE OF a" if write else "FOR SHARE OF a")
                    ),
                    parameters(current) | {"id": account_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前动作范围")
        await require_projection_current(session, current.tenant_id, account_id, datetime.now(UTC))
        return current, managed, row

    async def capabilities(self, session, actor, authorization, account_id, kind):
        current, _managed, account = await self.lock_account(
            session, actor, account_id, kind, write=False
        )
        return {
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            ),
            "revision": account["revision"],
            "next_effective_from": iso(
                next_business_midnight(account["timezone_id"], datetime.now(UTC))
            )
            if kind == "ASSIGNMENT"
            else None,
        }

    async def begin(
        self, session, actor, account_id, kind, expected, key, authorization, csrf, payload
    ):
        if not session.in_transaction():
            raise ValueError("账户动作必须在显式外层事务中")
        current, managed, account = await self.lock_account(session, actor, account_id, kind)
        try:
            verify_csrf(self.tokens, current, authorization, csrf)
        except OrbitError:
            raise OrbitError(403, "CSRF_INVALID", "账户动作会话校验已失效") from None
        digest = hashlib.sha256(
            canonical([kind, account["id"], expected, payload]).encode()
        ).hexdigest()
        old = (
            (
                await session.execute(
                    text(
                        "SELECT request_hash,response_json FROM orbit_account_command "
                        "WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND request_key=:key FOR UPDATE"
                    ),
                    parameters(current) | {"key": key},
                )
            )
            .mappings()
            .first()
        )
        if old:
            if old["request_hash"] != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他账户动作内容")
            return current, managed, account, digest, _decode(old["response_json"])
        if account["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "账户版本已更新，请刷新后重试")
        if account["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "账户版本已达上限")
        if account["unbound_at"] is not None:
            raise OrbitError(409, "ACCOUNT_ALREADY_UNBOUND", "账户已本地解绑，不能执行该新动作")
        pending = (
            await session.execute(
                text(
                    "SELECT 1 FROM orbit_account_command WHERE tenant_id=:tenant "
                    "AND account_id=:id "
                    + (
                        "AND active_kind IN ('ASSIGNMENT',:kind) "
                        if kind == "UNBIND"
                        else "AND active_kind=:kind "
                    )
                    + "LIMIT 1 FOR UPDATE"
                ),
                parameters(current) | {"id": account["id"], "kind": kind},
            )
        ).scalar_one_or_none()
        if pending is not None:
            raise OrbitError(
                409, "ACCOUNT_ACTION_PENDING", "账户存在待生效或同类待执行动作，请先处理原任务"
            )
        return current, managed, account, digest, None

    async def command(
        self,
        session,
        current,
        account,
        kind,
        state,
        key,
        digest,
        payload,
        request_id,
        *,
        assignment_id=None,
        effective=None,
        source=None,
        alias=None,
    ):
        request_id = identifier(request_id, "/request_id")
        command_id, revision = str(uuid4()), account["revision"] + 1
        ack = {"id": account["id"], "revision": revision, "state": state, "request_id": request_id}
        await session.execute(
            text(
                "INSERT INTO orbit_account_command "
                "(tenant_id,id,account_id,kind,state,actor_id,actor_subject_id,request_key,request_hash,"
                "request_id,accepted_account_revision,source_json,payload_json,response_json,"
                "assignment_id,effective_from,active_kind,source_config_id,source_config_revision,"
                "last_error_code,created_at,updated_at,completed_at) VALUES "
                "(:tenant,:command,:id,:kind,:state,:actor,:subject,:key,:hash,:request,:revision,"
                ":old,:body,:ack,:assignment,:effective,:active,:config,:config_revision,:error,"
                "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),"
                + ("UTC_TIMESTAMP(3)" if state == "SUCCEEDED" else "NULL")
                + ")"
            ),
            parameters(current)
            | {
                "command": command_id,
                "id": account["id"],
                "kind": kind,
                "state": state,
                "key": key,
                "hash": digest,
                "request": request_id,
                "revision": revision,
                "old": canonical(
                    ownership(account)
                    | {
                        "target_alias_at_accept": alias,
                        "timezone_id": account["timezone_id"],
                        "currency": account["currency"],
                    }
                    | (
                        {"meta_connection_source": source["meta_source"]}
                        if source and "meta_source" in source
                        else {}
                    )
                ),
                "body": canonical(payload),
                "ack": canonical(ack),
                "assignment": assignment_id,
                "effective": effective.replace(tzinfo=None) if effective else None,
                "active": None if state == "SUCCEEDED" else kind,
                "config": source["id"] if source else None,
                "config_revision": source["revision"] if source else None,
                "error": "ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED" if kind == "SYNC" else None,
            },
        )
        await session.execute(
            text(
                "UPDATE orbit_ad_account SET revision=:revision WHERE tenant_id=:tenant AND id=:id"
            ),
            parameters(current) | {"id": account["id"], "revision": revision},
        )
        await event(
            session,
            current,
            "ACCOUNT",
            account["id"],
            revision,
            "ACCOUNT_" + kind + "_" + state,
            request_id,
            {"command_id": command_id, "reason": payload["reason"]},
        )
        return ack

    async def assign(
        self, session, actor, account_id, expected, key, authorization, csrf, value, request_id
    ):
        payload = asdict(value)
        current, managed, account, digest, old = await self.begin(
            session, actor, account_id, "ASSIGNMENT", expected, key, authorization, csrf, payload
        )
        if old:
            return old
        now = datetime.now(UTC)
        effective = validate_effective(value.effective_from, account["timezone_id"], now)
        vendor, alias = await assignment_vendor(session, current, managed, value)
        target = {
            "owner_user_id": value.operator_user_id,
            "owner_team_id": value.owner_team_id,
            "vendor_id": value.vendor_id,
        }
        if target == ownership(account):
            raise OrbitError(409, "ASSIGNMENT_NO_CHANGE", "投手、团队和户商均未变化")
        intervals = list(
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_assignment WHERE tenant_id=:tenant "
                        "AND account_id=:id AND (ends_at IS NULL OR ends_at>:now) "
                        "ORDER BY starts_at LIMIT 3 FOR UPDATE"
                    ),
                    parameters(current) | {"id": account["id"], "now": now.replace(tzinfo=None)},
                )
            ).mappings()
        )
        if (
            len(intervals) != 1
            or intervals[0]["ends_at"] is not None
            or utc(intervals[0]["starts_at"]) > now
            or ownership(intervals[0]) != ownership(account)
        ):
            raise OrbitError(409, "ASSIGNMENT_HISTORY_CONFLICT", "当前归属区间不唯一或已有未来转移")
        if intervals[0]["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "归属区间版本已达上限")
        assignment_id = str(uuid4())
        params = (
            parameters(current)
            | {
                "id": intervals[0]["id"],
                "account": account["id"],
                "new": assignment_id,
                "effective": effective.replace(tzinfo=None),
                "reason": value.reason,
            }
            | target
        )
        await session.execute(
            text(
                "UPDATE orbit_account_assignment SET ends_at=:effective,revision=revision+1 "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_account_assignment "
                "(tenant_id,id,account_id,owner_user_id,owner_team_id,vendor_id,starts_at,reason) "
                "VALUES(:tenant,:new,:account,:owner_user_id,:owner_team_id,:vendor_id,:effective,:reason)"
            ),
            params,
        )
        if vendor is not None:
            await append_account_alias_snapshot(
                session,
                current,
                vendor,
                resource_type="ASSIGNMENT",
                resource_id=assignment_id,
                resource_revision=1,
                request_id=request_id,
                permission="accounts.assign",
            )
        return await self.command(
            session,
            current,
            account,
            "ASSIGNMENT",
            "SCHEDULED",
            key,
            digest,
            payload,
            request_id,
            assignment_id=assignment_id,
            effective=effective,
            alias=alias,
        )

    async def sync(
        self, session, actor, account_id, expected, key, authorization, csrf, reason, request_id
    ):
        payload = {"reason": reason}
        current, _managed, account, digest, old = await self.begin(
            session, actor, account_id, "SYNC", expected, key, authorization, csrf, payload
        )
        if old:
            return old
        selected = await account_source(session, current.tenant_id, account["id"])
        if selected is not None:
            try:
                await connection_row(
                    session,
                    current.tenant_id,
                    selected["connection_id"],
                    selected["connection_revision"],
                )
            except AccountReadFailure:
                raise OrbitError(
                    409, "ACCOUNT_SYNC_SOURCE_CHANGED", "账户明确关联的Meta连接已失效"
                ) from None
            from orbit_api.meta_sync_runtime import enqueue_metrics

            await enqueue_metrics(session, current, account, request_id, require_policy=False)
            return await self.command(
                session,
                current,
                account,
                "SYNC",
                "WAITING_EXECUTOR",
                key,
                digest,
                payload,
                request_id,
                source={
                    "id": selected["connection_id"],
                    "revision": selected["connection_revision"],
                    "meta_source": source_marker(selected),
                },
            )
        sources = list(
            (
                await session.execute(
                    text(
                        "SELECT id,revision,settings_json,secrets_json "
                        "FROM orbit_system_configuration "
                        "WHERE tenant_id=:tenant AND section='META_BM' AND enabled=1 "
                        "AND verification_status='READ_VERIFIED' ORDER BY id LIMIT 2 FOR SHARE"
                    ),
                    parameters(current),
                )
            ).mappings()
        )
        secrets = _decode(sources[0]["secrets_json"]) if len(sources) == 1 else None
        if len(sources) != 1 or not isinstance(secrets, dict) or not secrets.get("accessToken"):
            raise OrbitError(
                503, "ACCOUNT_SYNC_SOURCE_UNAVAILABLE", "只读同步需要唯一已验证来源，不能猜测Token"
            )
        settings = _decode(sources[0]["settings_json"])
        try:
            # 入队只验证冻结来源结构；Token仍是密文，真实执行前必须解密并再次实时核验。
            MetaReadConfiguration(
                settings.get("businessId"), settings.get("graphVersion"), "STRUCTURE_CHECK_ONLY"
            ).validate()
        except (AccountReadFailure, AttributeError):
            raise OrbitError(
                503, "ACCOUNT_SYNC_SOURCE_UNAVAILABLE", "只读同步来源配置结构未验证"
            ) from None
        return await self.command(
            session,
            current,
            account,
            "SYNC",
            "WAITING_EXECUTOR",
            key,
            digest,
            payload,
            request_id,
            source=sources[0],
        )

    async def unbind(
        self, session, actor, account_id, expected, key, authorization, csrf, reason, request_id
    ):
        payload = {"reason": reason}
        current, _managed, account, digest, old = await self.begin(
            session, actor, account_id, "UNBIND", expected, key, authorization, csrf, payload
        )
        if old:
            return old
        now = datetime.now(UTC).replace(tzinfo=None)
        params = parameters(current) | {"id": account["id"], "now": now}
        for table, clause in (
            ("orbit_account_command", "kind='SYNC' AND active_kind='SYNC'"),
            ("orbit_account_assignment", "starts_at<:now AND ends_at IS NULL"),
        ):
            exhausted = (
                await session.execute(
                    text(
                        "SELECT 1 FROM " + table + " WHERE tenant_id=:tenant AND account_id=:id "
                        "AND (" + clause + ") AND revision>=:maximum LIMIT 1 FOR UPDATE"
                    ),
                    params | {"maximum": MAX_REVISION},
                )
            ).scalar_one_or_none()
            if exhausted is not None:
                raise OrbitError(409, "REVISION_EXHAUSTED", "解绑关联记录版本已达上限")
        # 未执行只读任务也不能在本地解绑后恢复账户；状态明确终止，不擅自读取平台。
        await session.execute(
            text(
                "UPDATE orbit_account_command SET state='FAILED',active_kind=NULL,"
                "last_error_code='ACCOUNT_LOCALLY_UNBOUND',revision=revision+1,"
                "updated_at=:now,completed_at=:now WHERE tenant_id=:tenant AND account_id=:id "
                "AND kind='SYNC' AND active_kind='SYNC'"
            ),
            params,
        )
        await session.execute(
            text("UPDATE orbit_ad_account SET unbound_at=:now WHERE tenant_id=:tenant AND id=:id"),
            params,
        )
        # 只结束本地当前区间，不删除历史、事实、平台广告或全局BM凭据。
        await session.execute(
            text(
                "UPDATE orbit_account_assignment SET ends_at=:now,revision=revision+1 "
                "WHERE tenant_id=:tenant AND account_id=:id AND starts_at<:now AND ends_at IS NULL"
            ),
            params,
        )
        return await self.command(
            session,
            current,
            account,
            "UNBIND",
            "SUCCEEDED",
            key,
            digest,
            payload,
            request_id,
        )
