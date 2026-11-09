"""受控动作能力发行、撤销和当前权限读模型，调用者承担外层完整事务。"""

from datetime import UTC
from uuid import uuid4

from sqlalchemy import text

from orbit_api import execution_agent_access as access
from orbit_api.agent_capability_contract import (
    VERSIONS,
    AcceptanceEvidence,
    effective_state,
    public_capability,
    validate_target,
)
from orbit_api.agent_monitor_store import now_utc
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.profile_binding_access import fingerprint, query_rows, visible
from orbit_api.profile_binding_contract import identifier
from orbit_api.profile_binding_store import ProfileBindingStore

JOIN = (
    " FROM orbit_agent_action_capability c JOIN orbit_profile_binding b ON b.tenant_id=c.tenant_id "
    "AND b.id=c.profile_binding_id "
    "JOIN orbit_execution_agent g ON g.tenant_id=b.tenant_id AND g.id=b.agent_id "
    "JOIN orbit_ad_account a ON a.tenant_id=b.tenant_id AND a.id=b.account_id "
)
COLUMNS = (
    "c.*,b.revision current_binding_revision,g.revision current_agent_revision,g.state agent_state,"
    "b.unbound_at,a.unbound_at account_unbound_at,"
    "(a.owner_user_id=b.owner_user_id AND a.owner_team_id=b.owner_team_id) ownership_matches"
)


def unverified():
    raise OrbitError(422, "CAPABILITY_UNVERIFIED", "该动作、层级和环境版本尚无有效验收回执")


async def require_verified(
    session, *, tenant_id, agent_id, profile_binding_id, operation_kind, entity_type, versions
):
    """领取及每次发送前重核；不能用身份VALID、旧版本或另一账户的回执解锁。"""
    validate_target(operation_kind, entity_type, versions)
    values = {
        "tenant": identifier(tenant_id),
        "agent": identifier(agent_id),
        "binding": identifier(profile_binding_id),
        "operation": operation_kind,
        "entity": entity_type,
        **versions,
    }
    rows = await query_rows(
        session,
        "SELECT "
        + COLUMNS
        + JOIN
        + "WHERE c.tenant_id=:tenant AND c.agent_id=:agent AND b.agent_id=:agent "
        "AND c.profile_binding_id=:binding "
        "AND c.operation_kind=:operation AND c.entity_type=:entity AND "
        + " AND ".join("c." + key + "=:" + key for key in VERSIONS)
        + " ORDER BY c.issued_revision DESC,c.id LIMIT 1 FOR SHARE OF c,b,g,a",
        values,
    )
    if not rows or effective_state(rows[0], await now_utc(session)) != "VERIFIED":
        unverified()
    return rows[0]


class AgentCapabilityStore:
    def __init__(self, tokens=None):
        self.tokens = tokens

    async def list(self, session, actor, size=50, cursor=None):
        current = await access.context(session, actor, "environments.read")
        version = await access.clock(session, current)
        scope = await fingerprint(session, current, version, size)
        after = ""
        now = await now_utc(session)
        as_of = now.isoformat().replace("+00:00", "Z")
        if cursor:
            claims = self.tokens.verify("AGENT_CAPABILITY_CURSOR_V1", cursor)
            if claims.get("binding") != scope:
                raise OrbitError(409, "CURSOR_STALE", "能力或当前账户范围已变化，请重新查询")
            after = identifier(claims.get("after"))
            as_of = claims["as_of"]
        rows = await query_rows(
            session,
            "SELECT "
            + COLUMNS
            + JOIN
            + "WHERE c.tenant_id=:tenant AND c.id>:after AND ("
            + visible(current)
            + ") "
            "ORDER BY c.id LIMIT :limit FOR SHARE OF c,b,g,a",
            access.parameters(current) | {"after": after, "limit": size + 1},
        )
        items = rows[:size]
        following = (
            self.tokens.issue(
                "AGENT_CAPABILITY_CURSOR_V1",
                {"binding": scope, "after": items[-1]["id"], "as_of": as_of},
            )
            if len(rows) > size
            else None
        )
        return {
            "items": [public_capability(row, now) for row in items],
            "next_cursor": following,
            "data_as_of": as_of,
            "scope_version": version,
        }

    async def publish(
        self,
        session,
        actor,
        *,
        profile_binding_id,
        operation_kind,
        entity_type,
        versions,
        evidence,
        request_id,
    ):
        """仅供受控验收程序调用；不挂用户/Agent HTTP，不接受verified布尔。"""
        if not isinstance(evidence, AcceptanceEvidence):
            raise ValueError("ACCEPTANCE_EVIDENCE_REQUIRED")
        validate_target(operation_kind, entity_type, versions)
        now = await now_utc(session)
        if evidence.verified_at > now or evidence.expires_at <= now:
            raise ValueError("EVIDENCE_TIME_INVALID")
        current = await access.context(session, actor, "environments.enroll", write=True)
        revision = await access.clock(session, current, write=True)
        binding = await ProfileBindingStore(self.tokens).row(session, current, profile_binding_id)
        agent = (
            await query_rows(
                session,
                "SELECT revision,state FROM orbit_execution_agent WHERE tenant_id=:tenant "
                "AND id=:id FOR SHARE",
                access.parameters(current) | {"id": binding["agent_id"]},
            )
        )[0]
        if agent["state"] == "REVOKED":
            unverified()
        identifier_value = str(uuid4())
        values = access.parameters(current) | {
            "id": identifier_value,
            "agent": binding["agent_id"],
            "binding": binding["id"],
            "agent_revision": agent["revision"],
            "issued_revision": revision + 1,
            "binding_revision": binding["revision"],
            "operation": operation_kind,
            "entity": entity_type,
            **versions,
            "ref": "acceptance:" + identifier_value,
            "sha": evidence.source_sha256,
            "cases": canonical(dict(evidence.cases)),
            "verified": evidence.verified_at.astimezone(UTC).replace(tzinfo=None),
            "expires": evidence.expires_at.astimezone(UTC).replace(tzinfo=None),
        }
        await session.execute(
            text(
                "INSERT INTO orbit_agent_action_capability "
                "(tenant_id,id,agent_id,profile_binding_id,agent_revision,binding_revision,issued_revision,operation_kind,entity_type,"
                + ",".join(VERSIONS)
                + ",state,evidence_ref,evidence_sha256,evidence_cases,verified_at,expires_at) "
                "VALUES(:tenant,:id,:agent,:binding,:agent_revision,:binding_revision,:issued_revision,:operation,:entity,"
                + ",".join(":" + key for key in VERSIONS)
                + ",'VERIFIED',:ref,:sha,:cases,:verified,:expires)"
            ),
            values,
        )
        await self.changed(
            session, current, revision, identifier_value, "capability.issued", request_id
        )
        return identifier_value

    async def revoke(self, session, actor, capability_id, request_id):
        current = await access.context(session, actor, "environments.revoke", write=True)
        revision = await access.clock(session, current, write=True)
        rows = await query_rows(
            session,
            "SELECT id,state FROM orbit_agent_action_capability WHERE tenant_id=:tenant "
            "AND id=:id FOR UPDATE",
            access.parameters(current) | {"id": identifier(capability_id)},
        )
        if not rows:
            raise OrbitError(404, "NOT_FOUND", "能力回执不存在")
        if rows[0]["state"] == "REVOKED":
            return
        await session.execute(
            text(
                "UPDATE orbit_agent_action_capability SET state='REVOKED',"
                "revoked_at=UTC_TIMESTAMP(6) "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            access.parameters(current) | {"id": capability_id},
        )
        await self.changed(
            session, current, revision, capability_id, "capability.revoked", request_id
        )

    async def changed(self, session, current, revision, identifier_value, action, request_id):
        await session.execute(
            text(
                "UPDATE orbit_execution_agent_clock SET revision=revision+1 WHERE tenant_id=:tenant"
            ),
            access.parameters(current),
        )
        await access.event(
            session,
            current,
            "AGENT_CAPABILITY",
            identifier_value,
            revision + 1,
            action,
            request_id,
            {},
        )
