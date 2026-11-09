"""管理员登记关联；UNKNOWN不代表Profile存在、已登录或可执行。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from orbit_api import account_access
from orbit_api import execution_agent_access as access
from orbit_api.agent_monitor_store import batch_binding_identities
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.profile_binding_access import cas, fingerprint, query_rows, visible
from orbit_api.profile_binding_contract import identifier
from orbit_api.reference_access import verify_csrf

JOIN = (
    " FROM orbit_profile_binding b JOIN orbit_ad_account a ON "
    "a.tenant_id=b.tenant_id AND a.id=b.account_id JOIN orbit_execution_agent g ON "
    "g.tenant_id=b.tenant_id AND g.id=b.agent_id "
)


def public_binding(row):
    return {
        key: row[key]
        for key in (
            "id",
            "revision",
            "account_id",
            "agent_id",
            "profile_external_id",
            "identity_state",
            "verified_at",
        )
    } | {
        "ownership": {"owner_user_id": row["owner_user_id"], "owner_team_id": row["owner_team_id"]}
    }


class ProfileBindingStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def row(self, session, current, resource_id, *, write=False):
        result = await query_rows(
            session,
            "SELECT b.*"
            + JOIN
            + "WHERE b.tenant_id=:tenant AND b.id=:id AND ("
            + visible(current)
            + ") "
            + ("FOR UPDATE OF b" if write else "FOR SHARE OF b,a,g"),
            access.parameters(current) | {"id": identifier(resource_id)},
        )
        if not result:
            raise OrbitError(404, "NOT_FOUND", "关联不存在或当前不可见")
        return result[0]

    async def get(self, session, actor, resource_id):
        current = await access.context(session, actor, "environments.read")
        await access.clock(session, current)
        row = await self.row(session, current, resource_id)
        observations = await batch_binding_identities(session, current.tenant_id, [row])
        return public_binding(row) | observations[row["id"]]

    async def list(self, session, actor, size=50, cursor=None):
        current = await access.context(session, actor, "environments.read")
        version = await access.clock(session, current)
        binding = await fingerprint(session, current, version, size)
        after = ""
        as_of = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        if cursor:
            claims = self.tokens.verify("PROFILE_BINDING_CURSOR_V1", cursor)
            if claims.get("binding") != binding:
                raise OrbitError(409, "CURSOR_STALE", "当前账户范围或关联已变化，请重新查询")
            after, as_of = identifier(claims.get("after")), claims["as_of"]
        found = await query_rows(
            session,
            "SELECT b.*"
            + JOIN
            + "WHERE b.tenant_id=:tenant AND b.id>:after AND ("
            + visible(current)
            + ") "
            "ORDER BY b.id LIMIT :limit FOR SHARE OF b,a,g",
            access.parameters(current) | {"after": after, "limit": size + 1},
        )
        items = found[:size]
        following = (
            self.tokens.issue(
                "PROFILE_BINDING_CURSOR_V1",
                {"binding": binding, "after": items[-1]["id"], "as_of": as_of},
            )
            if len(found) > size
            else None
        )
        observations = await batch_binding_identities(session, current.tenant_id, items)
        return {
            "items": [public_binding(row) | observations[row["id"]] for row in items],
            "next_cursor": following,
            "scope_version": version,
            "data_as_of": as_of,
        }

    async def account(self, session, current, account_id):
        # 写权限由enroll+SUPER_ADMIN控制；账户仅核当前租户数据范围。
        caller = current
        result = await query_rows(
            session,
            "SELECT a.id,a.owner_user_id,a.owner_team_id FROM orbit_ad_account a "
            "WHERE a.tenant_id=:tenant AND a.id=:id AND a.unbound_at IS NULL AND ("
            + account_access.visible_clause(caller, "a")
            + ") FOR SHARE",
            account_access.parameters(caller) | {"id": account_id},
        )
        if not result:
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不可见")
        return result[0]

    async def save(
        self, session, actor, authorization, csrf, key, value, resource_id, expected, request_id
    ):
        current = await access.context(session, actor, "environments.enroll", write=True)
        verify_csrf(self.tokens, current, authorization, csrf)
        await access.clock(session, current, write=True)
        operation = "profile_binding.update" if resource_id else "profile_binding.create"
        input_hash = digest([resource_id, expected, value])
        replay = await access.replay(session, current, operation, key, input_hash)
        if replay is not None:
            return replay
        previous = await self.row(session, current, resource_id) if resource_id else None
        if previous:
            cas(previous, expected)
        accounts = sorted({value["account_id"]} | ({previous["account_id"]} if previous else set()))
        checked = {i: await self.account(session, current, i) for i in accounts}
        account = checked[value["account_id"]]
        if any(
            value["ownership"][field] != account[field]
            for field in ("owner_user_id", "owner_team_id")
        ):
            raise OrbitError(422, "OWNERSHIP_MISMATCH", "归属必须与当前账户严格一致", "/ownership")
        agent = await query_rows(
            session,
            "SELECT id,state FROM orbit_execution_agent "
            "WHERE tenant_id=:tenant AND id=:id FOR SHARE",
            access.parameters(current) | {"id": value["agent_id"]},
        )
        if not agent:
            raise OrbitError(404, "NOT_FOUND", "执行设备不存在或不可见")
        if agent[0]["state"] == "REVOKED":
            raise OrbitError(409, "AGENT_REVOKED", "目标执行设备已撤销，请选择有效设备")
        revision = expected + 1 if previous else 1
        resource_id = resource_id or str(uuid4())
        params = (
            access.parameters(current)
            | value
            | value["ownership"]
            | {"id": resource_id, "revision": revision}
        )
        try:
            if previous:
                await session.execute(
                    text(
                        "UPDATE orbit_profile_binding SET account_id=:account_id,"
                        "agent_id=:agent_id,profile_external_id=:profile_external_id,"
                        "owner_user_id=:owner_user_id,owner_team_id=:owner_team_id,revision=:revision,"
                        "identity_state='UNKNOWN',verified_at=NULL,updated_at=UTC_TIMESTAMP(6) "
                        "WHERE tenant_id=:tenant AND id=:id AND revision=:expected"
                    ),
                    params | {"expected": expected},
                )
            else:
                await session.execute(
                    text(
                        "INSERT INTO orbit_profile_binding "
                        "(tenant_id,id,account_id,agent_id,profile_external_id,owner_user_id,owner_team_id,"
                        "revision,identity_state,verified_at,created_at,updated_at) "
                        "VALUES(:tenant,:id,:account_id,:agent_id,"
                        ":profile_external_id,:owner_user_id,:owner_team_id,1,'UNKNOWN',NULL,"
                        "UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))"
                    ),
                    params,
                )
        except IntegrityError as error:
            if getattr(error.orig, "args", (None,))[0] != 1062:
                raise
            raise OrbitError(409, "PROFILE_BINDING_EXISTS", "该账户与Profile关联已登记") from None
        result = value | {
            "id": resource_id,
            "revision": revision,
            "identity_state": "UNKNOWN",
            "verified_at": None,
        }
        await access.event(
            session,
            current,
            "PROFILE_BINDING",
            resource_id,
            revision,
            operation,
            request_id,
            {"previous": public_binding(previous) if previous else None, "current": result},
        )
        await access.remember(session, current, operation, key, input_hash, result)
        return result

    async def unbind(
        self, session, actor, authorization, csrf, key, resource_id, expected, value, request_id
    ):
        current = await access.context(session, actor, "environments.enroll", write=True)
        verify_csrf(self.tokens, current, authorization, csrf)
        await access.clock(session, current, write=True)
        operation = "profile_binding.unbind"
        input_hash = digest([resource_id, expected, value])
        replay = await access.replay(session, current, operation, key, input_hash)
        if replay is not None:
            return replay
        previous = await self.row(session, current, resource_id, write=True)
        cas(previous, expected)
        await self.account(session, current, previous["account_id"])
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one()
        await session.execute(
            text(
                "UPDATE orbit_profile_binding SET unbound_at=:now,"
                "revision=revision+1,identity_state='UNKNOWN',verified_at=NULL,updated_at=:now "
                "WHERE tenant_id=:tenant AND id=:id AND revision=:expected"
            ),
            access.parameters(current) | {"id": resource_id, "expected": expected, "now": now},
        )
        result = {
            "id": resource_id,
            "revision": expected + 1,
            "unbound_at": now.replace(tzinfo=UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
        }
        await access.event(
            session,
            current,
            "PROFILE_BINDING",
            resource_id,
            expected + 1,
            operation,
            request_id,
            value,
        )
        await access.remember(session, current, operation, key, input_hash, result)
        return result
