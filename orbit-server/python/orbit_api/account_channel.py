"""账户当前渠道：真实账户权限、CAS/幂等及同事务审计；不改历史快照。"""

import hashlib

from sqlalchemy import text

from orbit_api.account_access import clock, context, event, parameters, visible_clause
from orbit_api.account_actions_contract import body, invalid, reason
from orbit_api.account_identities_store import identifier
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import clock as reference_clock
from orbit_api.reference_access import readable, verify_csrf


def parse_write(raw):
    value = body(raw)
    if set(value) != {"channel_id", "reason"}:
        invalid("/")
    return {
        "channel_id": identifier(value["channel_id"], "/channel_id")
        if value["channel_id"] is not None
        else None,
        "reason": reason(value["reason"]),
    }


class AccountChannelStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def account(self, session, actor, account_id, *, write=False):
        if not session.in_transaction():
            raise ValueError("ACCOUNT_CHANNEL_TRANSACTION_REQUIRED")
        account_id = identifier(account_id, "/account_id")
        current, managed = await context(
            session, actor, "accounts.assign" if write else "accounts.read"
        )
        await clock(session, current, write=write)
        # 锁序账户clock→引用clock→账户/渠道；规则筛选沿用此顺序后锁ruleclock。
        await reference_clock(session, current)
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
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不可见")
        return current, managed, row

    async def read(self, session, actor, account_id, authorization):
        current, _, account = await self.account(session, actor, account_id)
        channel = (
            await session.execute(
                text(
                    "SELECT channel_id FROM orbit_account_current_channel WHERE "
                    "tenant_id=:tenant AND account_id=:id FOR SHARE"
                ),
                parameters(current) | {"id": account["id"]},
            )
        ).scalar_one_or_none()
        csrf = None
        try:
            await require_business_access(session, actor, "accounts", "accounts.assign")
            csrf = self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, current.tenant_id)},
            )
        except OrbitError as error:
            if error.status != 403:
                raise
        return {
            "account_id": account["id"],
            "channel_id": channel,
            "revision": account["revision"],
            "csrf_token": csrf,
        }

    async def write(
        self, session, actor, account_id, expected, key, authorization, csrf, value, request_id
    ):
        current, managed, account = await self.account(session, actor, account_id, write=True)
        verify_csrf(self.tokens, current, authorization, csrf)
        channel_id = value["channel_id"]
        if channel_id is not None:
            channel = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_channel WHERE tenant_id=:tenant AND "
                            "id=:id FOR SHARE"
                        ),
                        parameters(current) | {"id": channel_id},
                    )
                )
                .mappings()
                .first()
            )
            if channel is None or not readable(
                current, managed, _decode(channel["value_json"])["ownership"]
            ):
                raise OrbitError(404, "NOT_FOUND", "渠道不存在或不可见")
        digest = hashlib.sha256(canonical([account["id"], expected, value]).encode()).hexdigest()
        params = parameters(current) | {"id": account["id"], "key": key}
        old = (
            (
                await session.execute(
                    text(
                        "SELECT payload_hash,response_json FROM "
                        "orbit_account_channel_idempotency WHERE tenant_id=:tenant "
                        "AND actor_id=:actor AND request_key=:key FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if old:
            if old["payload_hash"] != digest:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "该幂等键已用于不同渠道修改")
            return _decode(old["response_json"])
        if channel_id is not None and channel["status"] != "ENABLED":
            raise OrbitError(422, "CHANNEL_DISABLED", "停用渠道不能新关联到账户", "/channel_id")
        if account["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "账户版本已更新，请重新读取")
        if expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "账户版本已达上限")
        if account["unbound_at"] is not None:
            raise OrbitError(409, "ACCOUNT_ALREADY_UNBOUND", "账户已解绑，不能修改渠道")
        before = (
            await session.execute(
                text(
                    "SELECT channel_id FROM orbit_account_current_channel WHERE "
                    "tenant_id=:tenant AND account_id=:id FOR UPDATE"
                ),
                params,
            )
        ).scalar_one_or_none()
        result = {
            "account_id": account["id"],
            "channel_id": channel_id,
            "revision": expected + 1,
            "csrf_token": None,
        }
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_account_current_channel(tenant_id,account_id,channel_id,updated_at) "
                "VALUES(:tenant,:id,:channel,UTC_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE "
                "channel_id=:channel,updated_at=UTC_TIMESTAMP(3)"
            ),
            params | {"channel": channel_id},
        )
        await session.execute(
            text(
                "UPDATE orbit_ad_account SET revision=:revision WHERE tenant_id=:tenant AND id=:id"
            ),
            params | {"revision": expected + 1},
        )
        await event(
            session,
            current,
            "ACCOUNT",
            account["id"],
            expected + 1,
            "CURRENT_CHANNEL_CHANGED",
            request_id,
            {"before_channel_id": before, "channel_id": channel_id, "reason": value["reason"]},
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_account_channel_idempotency(tenant_id,actor_id,request_key,"
                "payload_hash,response_json) VALUES(:tenant,:actor,:key,:hash,:response)"
            ),
            params | {"hash": digest, "response": canonical(result)},
        )
        return result
