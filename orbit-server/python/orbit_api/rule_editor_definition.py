"""编辑原定义的有限元数据读取；不授予私有快照或当前完整账户范围。"""

import re

from sqlalchemy import text

from orbit_api.errors import OrbitError
from orbit_api.rule_access import authorize_rule, require_rule_visible, revalidate_access
from orbit_api.rule_contract import MAX_SAFE, identifier
from orbit_api.rule_store import RuleStore


def unavailable():
    raise OrbitError(503, "RULE_DEFINITION_UNAVAILABLE", "规则定义或冻结范围元数据不完整")


def _uuid(value):
    try:
        return identifier(value, "/stored_definition")
    except (OrbitError, TypeError, ValueError):
        unavailable()


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        unavailable()


def definition_response(head, version, manifest):
    """仅核完整定义/封存header；不扫描成员，不把历史owner当当前owner。"""
    try:
        if version is None or manifest is None:
            unavailable()
        for key in (
            "tenant_id",
            "revision",
            "name",
            "owner_user_id",
            "owner_team_id",
            "target_level",
            "state",
            "manifest_id",
            "metric_profile_id",
        ):
            if head[key] != version[key]:
                unavailable()
        if head["id"] != version["rule_id"]:
            unavailable()
        for key in ("payload_hash", "metric_profile_hash", "profile_proof_hash"):
            _hash(version[key])
        if not isinstance(version["metric_profile_version"], str) or not (
            1 <= len(version["metric_profile_version"]) <= 64
        ):
            unavailable()
        _uuid(version["event_id"])
        rule = RuleStore.public(dict(head) | dict(version) | {"id": head["id"]})
        if (
            manifest["tenant_id"] != head["tenant_id"]
            or manifest["rule_id"] != rule["id"]
            or manifest["id"] != head["manifest_id"]
            or manifest["source_snapshot_id"] != rule["scope_snapshot_id"]
            or type(manifest["sealed"]) is not int
            or manifest["sealed"] != 1
            or type(manifest["member_count"]) is not int
            or not 1 <= manifest["member_count"] <= 50000
            or manifest["source_kind"] not in {"ACCOUNT", "RULE"}
        ):
            unavailable()
        for key in ("id", "source_snapshot_id", "owner_user_id", "owner_team_id"):
            _uuid(manifest[key])
        for key in (
            "source_snapshot_hash",
            "member_ids_hash",
            "creator_auth_fingerprint",
            "owner_auth_fingerprint",
        ):
            _hash(manifest[key])
        source = manifest["source_snapshot_id"]
        if manifest["account_source_snapshot_id"] != (
            source if manifest["source_kind"] == "ACCOUNT" else None
        ) or manifest["rule_source_snapshot_id"] != (
            source if manifest["source_kind"] == "RULE" else None
        ):
            unavailable()
        return {
            "rule": rule,
            "stored_scope": {
                "id": source,
                "count": manifest["member_count"],
                **rule["ownership"],
            },
        }
    except (KeyError, TypeError, ValueError, OrbitError):
        unavailable()


class RuleEditorDefinitionStore:
    async def get(self, session, actor, rule_id):
        rule_id = identifier(rule_id, "/id")
        access = await authorize_rule(session, actor, "rules.edit")
        tenant = access.current.tenant_id
        clock = (
            await session.execute(
                text("SELECT revision FROM orbit_rule_clock WHERE tenant_id=:tenant FOR SHARE"),
                {"tenant": tenant},
            )
        ).scalar_one_or_none()
        if type(clock) is not int or not 1 <= clock <= MAX_SAFE:
            unavailable()
        params = {"tenant": tenant, "id": rule_id}
        head = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_rule_head WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        require_rule_visible(access, head)
        version = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_rule_version WHERE tenant_id=:tenant AND rule_id=:id "
                        "AND revision=:revision FOR SHARE"
                    ),
                    params | {"revision": head["revision"]},
                )
            )
            .mappings()
            .first()
        )
        manifest = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_rule_scope_manifest WHERE tenant_id=:tenant "
                        "AND rule_id=:id AND id=:manifest FOR SHARE"
                    ),
                    params | {"manifest": head["manifest_id"]},
                )
            )
            .mappings()
            .first()
        )
        result = definition_response(head, version, manifest)
        await revalidate_access(session, access)
        return result
