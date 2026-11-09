"""持久未来分配激活器；未注册到公共读取/采集，不宣称到期投影已自动追平。"""

from dataclasses import fields
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import text

from orbit_api.account_access import event, visible_clause
from orbit_api.account_actions_contract import Assignment
from orbit_api.account_actions_store import assignment_vendor, ownership
from orbit_api.account_alias_snapshots import append_account_alias_snapshot
from orbit_api.account_identities_store import identifier, utc
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams


class AccountActionsWorker:
    async def advance_due(self, session, tenant_id, *, now=None, limit=50, include_blocked=False):
        """同事务有界激活；恢复BLOCKED必须显式选择，不偷偷当作外部广告任务自动重发。

        新future区间已在受理事务建立，激活仅追平当前owner投影；不回写旧日事实。
        任意SQL/审计错误向外抛出，由调用方回滚，不能把未提交操作计成功。
        """
        if not session.in_transaction():
            raise ValueError("到期投影推进必须使用显式外层事务")
        tenant_id = identifier(tenant_id, "/tenant_id")
        if type(limit) is not int or not 1 <= limit <= 100 or type(include_blocked) is not bool:
            raise OrbitError(422, "FIELD_INVALID", "到期分配批量控制参数无效")
        now = now or datetime.now(UTC)
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("到期推进参考时间必须带可信时区")
        now = now.astimezone(UTC)
        version = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant "
                    "FOR UPDATE SKIP LOCKED"
                ),
                {"tenant": tenant_id},
            )
        ).scalar_one_or_none()
        if version is None:
            return {"activated": 0, "blocked": 0, "busy": True}
        if version >= MAX_REVISION - limit - 1:
            raise OrbitError(409, "REVISION_EXHAUSTED", "到期分配审计版本已达上限")
        states = "('SCHEDULED','BLOCKED')" if include_blocked else "('SCHEDULED')"
        due = list(
            (
                await session.execute(
                    text(
                        "SELECT id,account_id FROM orbit_account_command WHERE tenant_id=:tenant "
                        "AND kind='ASSIGNMENT' AND active_kind='ASSIGNMENT' AND state IN "
                        + states
                        + " AND effective_from<=:now ORDER BY effective_from,id LIMIT :limit"
                    ),
                    {"tenant": tenant_id, "now": now.replace(tzinfo=None), "limit": limit},
                )
            ).mappings()
        )
        activated, blocked = 0, 0
        for item in due:
            params = {"tenant": tenant_id, "id": item["account_id"], "command": item["id"]}
            account = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_ad_account WHERE tenant_id=:tenant "
                            "AND id=:id FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            command = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_account_command WHERE tenant_id=:tenant "
                            "AND id=:command FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .one()
            )
            if command["active_kind"] is None or command["state"] == "SUCCEEDED":
                continue
            if command["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "分配命令版本已达上限")
            audit = SimpleNamespace(
                actor_id=command["actor_id"],
                tenant_id=tenant_id,
                subject_id=command["actor_subject_id"],
            )
            try:
                current = await require_business_access(
                    session,
                    command["actor_id"],
                    "accounts",
                    "accounts.assign",
                    acting_subject=False,
                )
                if (
                    current.tenant_id != tenant_id
                    or current.subject_id != command["actor_subject_id"]
                ):
                    raise OrbitError(403, "ASSIGNMENT_ACTOR_CHANGED", "分配原业务身份已变化")
                visible = (
                    await session.execute(
                        text(
                            "SELECT 1 FROM orbit_ad_account a WHERE a.tenant_id=:tenant "
                            "AND a.id=:id "
                            "AND (" + visible_clause(current, "a") + ") FOR SHARE OF a"
                        ),
                        params | {"actor": current.actor_id, "subject": current.subject_id},
                    )
                ).scalar_one_or_none()
                if account is None or visible is None or account["unbound_at"] is not None:
                    raise OrbitError(
                        403, "ASSIGNMENT_SCOPE_CHANGED", "分配原账户已不可见或本地解绑"
                    )
                source, payload = _decode(command["source_json"]), _decode(command["payload_json"])
                if ownership(account) != ownership(source):
                    raise OrbitError(
                        409, "ACCOUNT_OWNERSHIP_CHANGED", "当前账户归属已偏离原分配来源"
                    )
                if account["revision"] >= MAX_REVISION:
                    raise OrbitError(409, "REVISION_EXHAUSTED", "账户版本已达上限")
                if account["timezone_id"] != source.get("timezone_id") or account[
                    "currency"
                ] != source.get("currency"):
                    raise OrbitError(
                        409, "ASSIGNMENT_ACCOUNT_METADATA_CHANGED", "账户时区或币种已偏离冻结分配"
                    )
                target = Assignment(
                    **{field.name: payload[field.name] for field in fields(Assignment)}
                )
                vendor, alias = await assignment_vendor(
                    session,
                    current,
                    await managed_teams(session, current),
                    target,
                    acting_subject=False,
                )
                future = (
                    (
                        await session.execute(
                            text(
                                "SELECT * FROM orbit_account_assignment WHERE tenant_id=:tenant "
                                "AND id=:assignment FOR UPDATE"
                            ),
                            params | {"assignment": command["assignment_id"]},
                        )
                    )
                    .mappings()
                    .first()
                )
                desired = {
                    "owner_user_id": target.operator_user_id,
                    "owner_team_id": target.owner_team_id,
                    "vendor_id": target.vendor_id,
                }
                if (
                    future is None
                    or ownership(future) != desired
                    or future["ends_at"] is not None
                    or future["revision"] != 1
                    or utc(future["starts_at"]) != utc(command["effective_from"])
                ):
                    raise OrbitError(409, "ASSIGNMENT_HISTORY_CHANGED", "未来区间与冻结分配不一致")
            except OrbitError as error:
                await session.execute(
                    text(
                        "UPDATE orbit_account_command SET state='BLOCKED',last_error_code=:error,"
                        "revision=revision+1,updated_at=UTC_TIMESTAMP(3) "
                        "WHERE tenant_id=:tenant AND id=:command"
                    ),
                    params | {"error": error.code},
                )
                await event(
                    session,
                    audit,
                    "COMMAND",
                    command["id"],
                    command["revision"] + 1,
                    "ACCOUNT_ASSIGNMENT_BLOCKED",
                    command["request_id"],
                    {"code": error.code},
                )
                blocked += 1
                continue
            await session.execute(
                text(
                    "UPDATE orbit_ad_account SET owner_user_id=:owner_user_id,"
                    "owner_team_id=:owner_team_id,"
                    "vendor_id=:vendor_id,revision=revision+1 WHERE tenant_id=:tenant AND id=:id"
                ),
                params | desired,
            )
            await session.execute(
                text(
                    "UPDATE orbit_account_assignment SET revision=2 "
                    "WHERE tenant_id=:tenant AND id=:assignment"
                ),
                params | {"assignment": command["assignment_id"]},
            )
            if vendor is not None:
                await append_account_alias_snapshot(
                    session,
                    current,
                    vendor,
                    resource_type="ASSIGNMENT",
                    resource_id=command["assignment_id"],
                    resource_revision=2,
                    request_id=command["request_id"],
                    permission="accounts.assign",
                    acting_subject=False,
                )
            await session.execute(
                text(
                    "UPDATE orbit_account_command SET state='SUCCEEDED',active_kind=NULL,"
                    "activation_alias_json=:alias,last_error_code=NULL,revision=revision+1,"
                    "updated_at=UTC_TIMESTAMP(3),completed_at=UTC_TIMESTAMP(3) "
                    "WHERE tenant_id=:tenant AND id=:command"
                ),
                params | {"alias": canonical(alias)},
            )
            await event(
                session,
                current,
                "COMMAND",
                command["id"],
                command["revision"] + 1,
                "ACCOUNT_ASSIGNMENT_ACTIVATED",
                command["request_id"],
                {
                    "account_id": account["id"],
                    "assignment_id": command["assignment_id"],
                    "reason": payload["reason"],
                    "effective_from": payload["effective_from"],
                },
            )
            activated += 1
        return {"activated": activated, "blocked": blocked, "busy": False}
