"""真实户商代称、实时范围及原子CAS；不修改名称，不回写历史业务快照。"""

from sqlalchemy import bindparam, text

from orbit_api.authorization import BusinessContext
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.errors import OrbitError
from orbit_api.reference_access import (
    assert_write_ownership,
    clock,
    event,
    managed_teams,
    readable,
    reference_context,
    remember,
    replay,
    verify_csrf,
)
from orbit_api.reference_contract import uuid_value
from orbit_api.reference_store import records, utc_text
from orbit_api.team_store import state_hash


async def alias_rows(session, tenant, identifiers, *, write=False):
    if not identifiers:
        return {}
    rows = (
        await session.execute(
            text(
                "SELECT vendor_id,alias,revision,updated_at FROM orbit_vendor_alias "
                "WHERE tenant_id=:tenant AND vendor_id IN :ids "
                + ("FOR UPDATE" if write else "FOR SHARE")
            ).bindparams(bindparam("ids", expanding=True)),
            {"tenant": tenant, "ids": list(identifiers)},
        )
    ).mappings()
    return {row["vendor_id"]: row for row in rows}


def public_alias(identifier, row=None):
    return {
        "vendor_id": identifier,
        "alias": row["alias"] if row else None,
        "revision": row["revision"] if row else 1,
        "updated_at": utc_text(row["updated_at"]) if row else None,
    }


async def visible_vendors(session, context, identifiers):
    found = await records(session, context.tenant_id, identifiers)
    managed = await managed_teams(session, context)
    return {
        identifier: _decode(row["value_json"])
        for identifier, row in found.items()
        if row["kind"] == "VENDOR" and readable(context, managed, _decode(row["value_json"]))
    }


async def resolve_vendor_alias_snapshots(session, context, identifiers):
    """供账户当前展示/历史冻结使用；每次重新授权，仅返回可见户商的最小来源。"""
    if not isinstance(context, BusinessContext):
        raise OrbitError(403, "PERMISSION_DENIED", "必须使用当前可信业务上下文")
    identifiers = list(dict.fromkeys(identifiers))
    if len(identifiers) > 200:
        raise OrbitError(422, "FIELD_INVALID", "一次最多读取200个户商代称")
    identifiers = [uuid_value(value, "/vendor_ids") for value in identifiers]
    current = await reference_context(session, context.actor_id, "VENDOR")
    if current.tenant_id != context.tenant_id or current.subject_id != context.subject_id:
        raise OrbitError(403, "PERMISSION_DENIED", "业务上下文已失效")
    visible = await visible_vendors(session, current, identifiers)
    rows = await alias_rows(session, current.tenant_id, visible)
    return {
        identifier: {
            "alias": rows[identifier]["alias"] if identifier in rows else None,
            "alias_revision": rows[identifier]["revision"] if identifier in rows else 1,
            "source": "VENDOR_ALIAS" if identifier in rows else "UNSET",
            "vendor_availability": value["availability"],
        }
        for identifier, value in visible.items()
    }


async def resolve_vendor_aliases(session, context, identifiers):
    return {
        identifier: value["alias"]
        for identifier, value in (
            await resolve_vendor_alias_snapshots(session, context, identifiers)
        ).items()
    }


class VendorAliasStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def capabilities(self, session, actor, authorization):
        context = await reference_context(session, actor, "VENDOR")
        try:
            await reference_context(session, actor, "VENDOR", maintenance=True)
            can_manage = True
        except OrbitError as error:
            if error.status != 403:
                raise
            can_manage = False
        return {
            "can_manage": can_manage,
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {"binding": self.tokens.session_binding(authorization, actor, context.tenant_id)},
            ),
        }

    async def read(self, session, actor, identifiers, *, single=False):
        context = await reference_context(session, actor, "VENDOR")
        identifiers = [uuid_value(value, "/vendor_id") for value in identifiers]
        version = await clock(session, context)
        visible = await visible_vendors(session, context, identifiers)
        if single and identifiers[0] not in visible:
            raise OrbitError(404, "NOT_FOUND", "户商不存在或不可见")
        rows = await alias_rows(session, context.tenant_id, visible)
        items = [
            public_alias(identifier, rows.get(identifier))
            for identifier in identifiers
            if identifier in visible
        ]
        if single:
            return items[0] | {"catalog_revision": version["revision"]}
        return {"items": items, "catalog_revision": version["revision"]}

    async def save(
        self, session, actor, authorization, csrf, key, identifier, expected, value, request_id
    ):
        context = await reference_context(session, actor, "VENDOR", maintenance=True)
        verify_csrf(self.tokens, context, authorization, csrf)
        identifier = uuid_value(identifier, "/vendor_id")
        version = await clock(session, context, write=True)
        visible = await visible_vendors(session, context, [identifier])
        if identifier not in visible:
            raise OrbitError(404, "NOT_FOUND", "户商不存在或不可见")
        vendor = visible[identifier]
        assert_write_ownership(
            context,
            await managed_teams(session, context),
            {key: vendor[key] for key in ("owner_team_id", "data_owner_user_ids")},
        )
        digest = state_hash(["VENDOR_ALIAS", identifier, expected, value])
        prior_response = await replay(session, context, key, digest)
        if prior_response is not None:
            return prior_response
        rows = await alias_rows(session, context.tenant_id, [identifier], write=True)
        before = public_alias(identifier, rows.get(identifier))
        if expected != before["revision"]:
            raise OrbitError(409, "REVISION_CONFLICT", "户商代称已修改，请重新读取")
        if before["alias"] == value["alias"]:
            # 未设置→仍未知及同值维护均不伪造修改时间、编辑事件或水位。
            result = before | {"catalog_revision": version["revision"]}
            await remember(session, context, key, digest, result)
            return result
        if before["revision"] >= MAX_REVISION or version["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "代称或目录版本已达上限")
        await session.execute(
            text("""INSERT INTO orbit_vendor_alias
            (tenant_id,vendor_id,alias,revision,updated_at,updated_by)
            VALUES(:tenant,:vendor,:alias,:revision,UTC_TIMESTAMP(3),:actor)
            ON DUPLICATE KEY UPDATE alias=:alias,revision=:revision,
            updated_at=UTC_TIMESTAMP(3),updated_by=:actor"""),
            {
                "tenant": context.tenant_id,
                "vendor": identifier,
                "alias": value["alias"],
                "revision": before["revision"] + 1,
                "actor": actor,
            },
        )
        await session.execute(
            text("UPDATE orbit_reference_clock SET revision=revision+1 WHERE tenant_id=:tenant"),
            {"tenant": context.tenant_id},
        )
        result = public_alias(
            identifier, (await alias_rows(session, context.tenant_id, [identifier]))[identifier]
        )
        result["catalog_revision"] = version["revision"] + 1
        await event(
            session,
            context,
            "VENDOR_ALIAS",
            identifier,
            result["revision"],
            before,
            result,
            value["reason"],
            request_id,
            {"catalog_revision": result["catalog_revision"]},
        )
        await remember(session, context, key, digest, result)
        return result
