"""规则原create/edit独立候选，只读当前来源；不授予模拟/启用/平台能力。"""

import hashlib
from dataclasses import asdict
from datetime import UTC

from sqlalchemy import bindparam, text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metric_profile_query import validated_public_profile
from orbit_api.metric_profile_store import fixture_boundary
from orbit_api.reference_access import assert_write_ownership
from orbit_api.rule_access import (
    authorize_rule,
    owner_scope,
    require_rule_visible,
    revalidate_access,
    revalidate_owner,
    transaction,
)
from orbit_api.rule_contract import MAX_SAFE, identifier
from orbit_api.rule_editor_contract import PURPOSE, EditorQuery
from orbit_api.rule_store import RuleStore, iso


def unavailable():
    raise OrbitError(503, "RULE_EDITOR_UNAVAILABLE", "规则候选来源或完整性尚未就绪")


def changed():
    raise OrbitError(409, "RULE_EDITOR_CHANGED", "规则、人员范围或候选来源已变化，请重新加载")


async def rows(session, sql, values, *, ids=None):
    statement = text(sql)
    if ids is not None:
        statement = statement.bindparams(bindparam("ids", expanding=True))
        values = values | {"ids": list(ids)}
    return list((await session.execute(statement, values)).mappings())


async def one(session, sql, values):
    found = await rows(session, sql, values)
    if len(found) != 1:
        unavailable()
    return found[0]


def positive(value):
    if type(value) is not int or not 1 <= value <= MAX_SAFE:
        unavailable()
    return value


LABEL_SQL = (
    "SELECT b.id,b.team_id,t.name AS team_name,"
    "COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name) AS name,"
    "b.enabled,b.invited,u.status,u.del_flag,t.enabled AS team_enabled,s.enabled AS scope_enabled "
    "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
    "JOIN orbit_business_team t ON t.tenant_id=b.tenant_id AND t.id=b.team_id "
    "JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id "
)


def owner_item(row):
    if row is None:
        return None
    result = {key: row[key] for key in ("id", "team_id", "name", "team_name")}
    identifier(result["id"], "/owner_user_id")
    identifier(result["team_id"], "/owner_team_id")
    if any(not isinstance(result[key], str) or not result[key] for key in ("name", "team_name")):
        unavailable()
    return result


def owner_active(row):
    return row is not None and (
        row["enabled"],
        row["invited"],
        row["status"],
        row["del_flag"],
        row["team_enabled"],
        row["scope_enabled"],
    ) == (1, 0, "0", "0", 1, 1)


class RuleEditorStore:
    def __init__(self, tokens, *, isolated_fixture=False):
        if type(isolated_fixture) is not bool:
            raise ValueError("RULE_EDITOR_FIXTURE_MUST_BE_TRUSTED_BOOLEAN")
        self.tokens, self.isolated_fixture = tokens, isolated_fixture

    async def _begin(self, session, actor, query):
        transaction(session)
        if not isinstance(query, EditorQuery):
            raise ValueError("TYPED_EDITOR_QUERY_REQUIRED")
        access = await authorize_rule(
            session, actor, "rules.create" if query.action == "CREATE" else "rules.edit"
        )
        if self.isolated_fixture:
            await fixture_boundary(session)  # 空页/无profile同样不得绕过隔离护栏。
        previous = (
            await self._rule(session, access, query.rule_id, lock=False) if query.rule_id else None
        )
        directory = await one(
            session,
            "SELECT revision,UTC_TIMESTAMP(3) AS now FROM orbit_directory_clock "
            "WHERE tenant_id=:tenant FOR SHARE",
            {"tenant": access.current.tenant_id},
        )
        positive(directory["revision"])
        return access, previous, directory

    async def _rule(self, session, access, rule_id, *, lock):
        found = await rows(
            session,
            "SELECT h.*,v.payload_json,v.payload_hash,v.metric_profile_version,"
            "v.metric_profile_hash,v.profile_proof_hash FROM orbit_rule_head h "
            "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id AND v.rule_id=h.id "
            "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.id=:id "
            + ("FOR SHARE OF h,v" if lock else ""),
            {"tenant": access.current.tenant_id, "id": rule_id},
        )
        row = dict(found[0]) if len(found) == 1 else None
        require_rule_visible(access, row)
        RuleStore.public(row)  # 原公开纯序列化/原11字段hash与投影比对，不借.get的rules.read。
        return row

    async def _finish(self, session, access, previous):
        if previous is not None:
            clock = await one(
                session,
                "SELECT revision FROM orbit_rule_clock WHERE tenant_id=:tenant FOR SHARE",
                {"tenant": access.current.tenant_id},
            )
            positive(clock["revision"])
            current = await self._rule(session, access, previous["id"], lock=True)
            if any(
                current[key] != previous[key]
                for key in (
                    "revision",
                    "payload_hash",
                    "owner_user_id",
                    "owner_team_id",
                    "state",
                    "metric_profile_id",
                    "metric_profile_version",
                    "metric_profile_hash",
                )
            ):
                changed()
            previous = current
        await revalidate_access(session, access)
        return previous

    async def _label(self, session, access, owner_id):
        found = await rows(
            session,
            LABEL_SQL + "WHERE b.tenant_id=:tenant AND b.id=:id FOR SHARE",
            {"tenant": access.current.tenant_id, "id": owner_id},
        )
        return found[0] if len(found) == 1 else None

    async def _profiles(self, session, access, *, after="", limit=201, exact=None):
        values = {"tenant": access.current.tenant_id, "after": after, "limit": limit}
        clause = " AND h.id=:id" if exact else ""
        if exact:
            values["id"] = exact
        probe_sql = (
            "SELECT h.id,h.current_version,v.source,v.authority_kind,v.source_config_id,"
            "v.source_config_revision FROM orbit_metric_profile_head h "
            "JOIN orbit_metric_profile_version v "
            "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
            "WHERE h.tenant_id=:tenant AND h.state='ENABLED' AND h.id>:after"
            + clause
            + " ORDER BY h.id LIMIT :limit"
        )
        probe = await rows(session, probe_sql, values)
        if len(probe) > limit or len({row["id"] for row in probe}) != len(probe):
            unavailable()
        sources = set()
        for row in probe:
            if row["source"] == "FIXTURE" and row["authority_kind"] == "ISOLATED_TEST":
                if not self.isolated_fixture:
                    unavailable()
            elif (
                row["source"] == "META"
                and row["authority_kind"] == "TRUSTED"
                and row["source_config_id"]
            ):
                sources.add(row["source_config_id"])
            else:
                unavailable()
        configurations = {}
        for source in sorted(sources):
            config = await one(
                session,
                "SELECT id,revision,enabled,section FROM orbit_system_configuration "
                "WHERE tenant_id=:tenant AND id=:id FOR SHARE",
                {"tenant": access.current.tenant_id, "id": source},
            )
            if config["enabled"] != 1 or config["section"] != "META_BM":
                changed()
            if any(
                row["source_config_revision"] != config["revision"]
                for row in probe
                if row["source_config_id"] == source
            ):
                changed()
            configurations[source] = dict(config)
        clock = await one(
            session,
            "SELECT revision,UTC_TIMESTAMP(3) AS now FROM orbit_metric_profile_clock "
            "WHERE tenant_id=:tenant FOR SHARE",
            {"tenant": access.current.tenant_id},
        )
        positive(clock["revision"])
        result = []
        if probe:
            found = await rows(
                session,
                "SELECT h.id,h.current_version,h.revision AS head_revision,"
                "h.state,v.source,v.authority_kind,"
                "v.payload_json,v.payload_hash,v.source_config_id,"
                "v.source_config_revision,v.source_sha256,"
                "v.evidence_ref,v.observed_at,v.source_proof_json "
                "FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v "
                "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
                "WHERE h.tenant_id=:tenant AND h.id IN :ids ORDER BY h.id FOR SHARE OF h,v",
                {"tenant": access.current.tenant_id},
                ids=[row["id"] for row in probe],
            )
            if [row["id"] for row in found] != [row["id"] for row in probe]:
                changed()
            for before, row in zip(probe, found, strict=True):
                if row["state"] != "ENABLED" or any(
                    row[key] != before[key]
                    for key in (
                        "current_version",
                        "source",
                        "authority_kind",
                        "source_config_id",
                        "source_config_revision",
                    )
                ):
                    changed()
                positive(row["head_revision"])
                # 使用前置当前锁读的配置值，不在clock之后依赖RR旧视图的LEFT JOIN配置。
                config = configurations.get(row["source_config_id"])
                row = dict(row) | {
                    "config_id": config["id"] if config else None,
                    "config_section": config["section"] if config else None,
                    "config_enabled": config["enabled"] if config else None,
                    "config_revision": config["revision"] if config else None,
                }
                profile = validated_public_profile(
                    row,
                    isolated_fixture=self.isolated_fixture,
                    now=clock["now"].replace(tzinfo=UTC),
                )
                if profile["verified"] is not True:
                    unavailable()
                result.append(profile)
        return result, clock

    def _cursor(self, query):
        if query.cursor is None:
            return None, ""
        claims = self.tokens.verify(PURPOSE, query.cursor)
        if type(claims.get("v")) is not int or claims["v"] != 1:
            changed()
        return claims, identifier(claims.get("after"), "/cursor")

    def _page(
        self,
        access,
        previous,
        query,
        directory,
        watermark,
        profiles,
        claims,
        authorization,
        owner=None,
    ):
        selection = asdict(query)
        selection.pop("cursor")
        binding = hashlib.sha256(
            canonical(
                [
                    "RULE_EDITOR_OPTIONS_V1",
                    self.tokens.session_binding(
                        authorization, access.current.actor_id, access.current.tenant_id
                    ),
                    access.auth_fingerprint,
                    list(access.managed_team_ids),
                    selection,
                    previous["revision"] if previous else None,
                    directory["revision"],
                    owner.auth_fingerprint if owner else None,
                    list(owner.managed_team_ids) if owner else None,
                ]
            ).encode()
        ).hexdigest()
        as_of = iso(watermark["now"])
        if claims:
            if (
                claims.get("binding") != binding
                or type(claims.get("watermark")) is not int
                or claims["watermark"] != watermark["revision"]
            ):
                changed()
            as_of = claims.get("as_of")
            if not isinstance(as_of, str) or as_of > iso(watermark["now"]):
                changed()
            from orbit_api.rule_contract import _utc

            _utc(as_of, "/cursor")
        page = profiles[: query.page_size]
        next_cursor = (
            self.tokens.issue(
                PURPOSE,
                {
                    "v": 1,
                    "binding": binding,
                    "watermark": watermark["revision"],
                    "as_of": as_of,
                    "after": page[-1]["id"],
                },
            )
            if len(profiles) > query.page_size
            else None
        )
        return {
            "items": page,
            "next_cursor": next_cursor,
            "data_as_of": as_of,
            "scope_version": access.auth_version,
        }

    async def options(self, session, actor, authorization, query):
        access, previous, directory = await self._begin(session, actor, query)
        claims, after = self._cursor(query)
        owner = None
        if query.kind == "OWNER":
            predicate = "1=1" if access.current.data_role == "SUPER_ADMIN" else "b.id=:subject"
            values = {
                "tenant": access.current.tenant_id,
                "subject": access.current.subject_id,
                "after": after,
                "limit": query.page_size + 1,
            }
            if access.current.data_role == "TEAM_ADMIN" and access.managed_team_ids:
                predicate += " OR b.team_id IN :managed"
                values["managed"] = list(access.managed_team_ids)
            sql = LABEL_SQL + (
                "WHERE b.tenant_id=:tenant AND b.id>:after AND b.enabled=1 AND b.invited=0 "
                "AND u.status='0' AND u.del_flag='0' AND t.enabled=1 AND s.enabled=1 AND ("
                + predicate
                + ") AND (:empty=1 OR COALESCE(NULLIF(b.display_name,''),"
                "NULLIF(u.nick_name,''),u.user_name) "
                "LIKE :search ESCAPE '!') ORDER BY b.id LIMIT :limit FOR SHARE"
            )
            values |= {
                "empty": int(not query.q),
                "search": query.q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%",
            }
            statement = text(sql)
            if "managed" in values:
                statement = statement.bindparams(bindparam("managed", expanding=True))
            found = list((await session.execute(statement, values)).mappings())
            result, watermark = [owner_item(row) for row in found], directory
        elif query.kind == "PROFILE":
            # 候选是新选择入口：先沿新指派边界拒绝无权目标，不能先读口径后用错误差异泄露。
            # UPDATE保留旧owner走edit-context；最终保存/候选复验的previous仅取当前锁定Rule。
            assert_write_ownership(
                access.current,
                access.managed_team_ids,
                {
                    "owner_team_id": query.owner_team_id,
                    "data_owner_user_ids": [query.owner_user_id],
                },
            )
            owner = await owner_scope(
                session,
                access,
                {"owner_user_id": query.owner_user_id, "owner_team_id": query.owner_team_id},
            )
            result, watermark = await self._profiles(
                session, access, after=after, limit=query.page_size + 1, exact=query.q or None
            )
        else:
            raise ValueError("OPTIONS_KIND_REQUIRED")
        previous = await self._finish(session, access, previous)
        if owner:
            await revalidate_owner(session, access, owner)
            await owner_scope(
                session,
                access,
                {"owner_user_id": query.owner_user_id, "owner_team_id": query.owner_team_id},
                for_write=True,
                previous=previous,
            )
        return self._page(
            access, previous, query, directory, watermark, result, claims, authorization, owner
        )

    async def context(self, session, actor, authorization, query):
        access, previous, directory = await self._begin(session, actor, query)
        ownership = (
            {"owner_user_id": previous["owner_user_id"], "owner_team_id": previous["owner_team_id"]}
            if previous
            else {
                "owner_user_id": access.current.subject_id,
                "owner_team_id": access.current.team_id,
            }
        )
        label = await self._label(session, access, ownership["owner_user_id"])
        active = owner_active(label) and label["team_id"] == ownership["owner_team_id"]
        owner, profile = None, None
        if active:
            owner = await owner_scope(session, access, ownership)
            if previous:
                profiles, _ = await self._profiles(
                    session, access, exact=previous["metric_profile_id"], limit=1
                )
                profile = profiles[0] if profiles else None
        previous = await self._finish(session, access, previous)
        can_keep = False
        if owner:
            await revalidate_owner(session, access, owner)
            try:
                assert_write_ownership(
                    access.current,
                    access.managed_team_ids,
                    {
                        "owner_team_id": ownership["owner_team_id"],
                        "data_owner_user_ids": [ownership["owner_user_id"]],
                    },
                    previous={
                        "owner_team_id": previous["owner_team_id"],
                        "data_owner_user_ids": [previous["owner_user_id"]],
                    }
                    if previous
                    else None,
                )
                can_keep = True
            except OrbitError as error:
                if error.code != "OWNERSHIP_DENIED":
                    raise
        return {
            "action": query.action,
            "rule_id": query.rule_id,
            "rule_revision": previous["revision"] if previous else None,
            "editable": previous is None or previous["state"] in {"DRAFT", "PAUSED"},
            "csrf_token": self.tokens.issue(
                "DIRECTORY_CSRF_V1",
                {
                    "binding": self.tokens.session_binding(
                        authorization, actor, access.current.tenant_id
                    )
                },
            ),
            "default_ownership": ownership,
            "selected_owner": {"item": owner_item(label), "can_keep": can_keep},
            "selected_profile": None
            if previous is None
            else {
                "id": previous["metric_profile_id"],
                "bound_version": previous["metric_profile_version"],
                "current": profile,
                "status": "UNAVAILABLE"
                if profile is None
                else "CURRENT"
                if profile["version"] == previous["metric_profile_version"]
                else "CHANGED",
            },
        }
