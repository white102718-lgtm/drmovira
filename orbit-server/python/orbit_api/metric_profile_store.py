"""指标profile不可变发布/精确映射读取；不注册HTTP，不执行平台写入或自动授予权威。"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api.authorization import BusinessContext, require_business_access, require_system_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import uuid_field
from orbit_api.metric_profile_contract import (
    MAX_REVISION,
    MetricPublication,
    check_proof,
    parse_source_proof,
    proof_values,
    publication,
    unavailable,
)


class MetricProfileAuthority(ABC):
    kind = "TRUSTED"

    @abstractmethod
    async def capture(self, profile_id, version, adapter_version):
        """没有session，事务外只读采集，必须返回完整原profile和明确目标参数映射/来源证明。"""

    @abstractmethod
    async def revalidate(self, session, current, prepared):
        """仅来源DB锁，禁止网络I/O；核当前真实META来源和显式mapping，返回同一proof。"""


async def one(session, statement, values):
    return (await session.execute(text(statement), values)).mappings().first()


def transaction(session):
    if not session.in_transaction():
        raise ValueError("指标注册表必须由调用者持有外层事务")


def checked_prepared(prepared):
    if not isinstance(prepared, MetricPublication):
        unavailable()
    try:
        checked = publication(
            prepared.profile(),
            prepared.adapter_version,
            json.loads(prepared.attribution_json),
            prepared.proof,
        )
    except (ValueError, TypeError, UnicodeError, OrbitError):
        unavailable()
    if checked != prepared:
        unavailable()
    return checked


def proof_document(proof):
    return canonical(
        {
            "source_sha256": proof.source_sha256,
            "observed_at": proof.observed_at.isoformat(),
            "evidence_ref": proof.evidence_ref,
            "source_config_id": proof.source_config_id,
            "source_config_revision": proof.source_config_revision,
            **(
                {
                    "source_connection_id": proof.source_connection_id,
                    "source_connection_revision": proof.source_connection_revision,
                }
                if proof.source_connection_id is not None
                else {}
            ),
        }
    )


async def fixture_boundary(session):
    bind = getattr(session, "bind", None)
    url = getattr(bind, "url", None)
    if url is None:
        # 独占连接会话绑定AsyncConnection，URL仍来自其原Engine；不另开连接。
        url = getattr(getattr(bind, "engine", None), "url", None)
    if url is None or url.host != "127.0.0.1" or url.port != 13306:
        unavailable()
    database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
    if not isinstance(database, str) or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        unavailable()


class MetricProfileStore:
    def __init__(self, authority=None):
        self.authority = authority

    def require_authority(self):
        if not isinstance(self.authority, MetricProfileAuthority) or self.authority.kind not in {
            "TRUSTED",
            "ISOLATED_TEST",
        }:
            unavailable()
        return self.authority

    async def prepare(self, profile_id, version, adapter_version):
        """调用方不能持SQL事务等待本方法；实际来源采集不在publish写事务中。"""
        authority = self.require_authority()
        identifier = uuid_field(profile_id, ("profile_id",))
        if any(
            not isinstance(value, str) or not 1 <= len(value) <= 64
            for value in (version, adapter_version)
        ):
            raise OrbitError(422, "FIELD_INVALID", "需要明确配置及适配版本")
        prepared = checked_prepared(await authority.capture(identifier, version, adapter_version))
        if (prepared.profile()["id"], prepared.profile()["version"], prepared.adapter_version) != (
            identifier,
            version,
            adapter_version,
        ):
            unavailable()
        return prepared

    async def _writer(self, session, current):
        transaction(session)
        if not isinstance(current, BusinessContext):
            raise ValueError("内部发行要求当前服务端授权上下文")
        fresh = await require_system_access(
            session, current.actor_id, 31086, "system.release.manage"
        )
        if fresh != current:
            raise OrbitError(403, "PERMISSION_DENIED", "发行授权范围已变化")

    async def _clock(self, session, tenant, *, write=True):
        row = await one(
            session,
            "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=:tenant "
            + ("FOR UPDATE" if write else "FOR SHARE"),
            {"tenant": tenant},
        )
        if row is None:
            raise OrbitError(503, "METRIC_PROFILE_INITIALIZATION_REQUIRED", "指标注册表尚未初始化")
        if type(row["revision"]) is not int or not 1 <= row["revision"] <= MAX_REVISION:
            unavailable()
        if write and row["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "指标目录版本已达上限")
        return row["revision"]

    async def _event(self, session, current, identifier, revision, action, request_id, details):
        values = {
            "tenant": current.tenant_id,
            "event": str(uuid4()),
            "actor": current.actor_id,
            "id": identifier,
            "revision": revision,
            "action": action,
            "request": uuid_field(request_id, ("request_id",)),
            "details": canonical(details),
        }
        await session.execute(
            text(
                "INSERT INTO orbit_metric_profile_audit(tenant_id,id,actor_id,profile_id,"
                "revision,action,request_id,details_json) VALUES(:tenant,"
                ":event,:actor,:id,:revision,:action,:request,:details)"
            ),
            values,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_metric_profile_outbox(tenant_id,event_id,"
                "state) VALUES(:tenant,:event,'PENDING')"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=:tenant"
            ),
            values,
        )

    async def publish(self, session, current, prepared, expected, request_id):
        authority = self.require_authority()
        prepared = checked_prepared(prepared)
        profile = prepared.profile()
        if authority.kind == "ISOLATED_TEST":
            await fixture_boundary(session)
            if profile["source"] != "FIXTURE":
                unavailable()
        elif profile["source"] != "META":
            unavailable()
        await self._writer(session, current)
        if type(expected) is not int or not 0 <= expected <= MAX_REVISION:
            raise OrbitError(422, "FIELD_INVALID", "发行头版本无效")
        fresh_proof = await authority.revalidate(session, current, prepared)
        if fresh_proof != prepared.proof:
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标配置来源已变化")
        check_proof(fresh_proof, profile["source"])
        if profile["source"] == "META":
            await validate_current_source(session, current.tenant_id, fresh_proof)
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        if not isinstance(now, datetime):
            unavailable()
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        if prepared.proof.observed_at > now:
            raise OrbitError(
                409, "METRIC_PROFILE_SOURCE_CHANGED", "指标观察时间不能晚于数据库当前时间"
            )
        watermark = await self._clock(session, current.tenant_id)
        params = {
            "tenant": current.tenant_id,
            "id": profile["id"],
            "version": profile["version"],
            "adapter": prepared.adapter_version,
            "profile": prepared.profile_json.decode(),
            "profile_hash": prepared.profile_hash,
            "mapping": prepared.attribution_json.decode(),
            "mapping_hash": prepared.attribution_hash,
            "proof": proof_document(prepared.proof),
            "kind": authority.kind,
            "source": profile["source"],
            "actor": current.actor_id,
            "registry": watermark + 1,
        } | proof_values(prepared.proof)
        head = await one(
            session,
            "SELECT current_version,revision,state FROM orbit_metric_profile_head "
            "WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            params,
        )
        version = await one(
            session,
            "SELECT payload_hash,source_proof_json FROM orbit_metric_profile_version "
            "WHERE tenant_id=:tenant AND profile_id=:id AND version=:version FOR SHARE",
            params,
        )
        binding = await one(
            session,
            "SELECT profile_hash,mapping_hash,source_proof_json,revoked_at "
            "FROM orbit_metric_profile_adapter "
            "WHERE tenant_id=:tenant AND profile_id=:id AND "
            "profile_version=:version AND adapter_version=:adapter FOR UPDATE",
            params,
        )

        def same_proof(value):
            return (
                canonical(json.loads(value) if isinstance(value, str) else value) == params["proof"]
            )

        if version and (
            version["payload_hash"] != prepared.profile_hash
            or not same_proof(version["source_proof_json"])
        ):
            raise OrbitError(
                409, "METRIC_PROFILE_IMMUTABLE_CONFLICT", "同一指标版本不得替换内容或来源"
            )
        if binding and (
            binding["profile_hash"] != prepared.profile_hash
            or binding["mapping_hash"] != prepared.attribution_hash
            or not same_proof(binding["source_proof_json"])
        ):
            raise OrbitError(
                409, "METRIC_PROFILE_IMMUTABLE_CONFLICT", "同一适配绑定不得替换映射或来源"
            )
        if version and head and head["current_version"] != profile["version"]:
            raise OrbitError(409, "METRIC_PROFILE_REVOKED", "历史版本不能重绑成当前指标来源")
        if version and binding:
            if (
                head is None
                or head["state"] != "ENABLED"
                or head["current_version"] != profile["version"]
                or binding["revoked_at"] is not None
            ):
                raise OrbitError(409, "METRIC_PROFILE_REVOKED", "旧发行不能重新激活撤销来源")
            return {
                "id": profile["id"],
                "version": profile["version"],
                "revision": head["revision"],
                "adapter_version": prepared.adapter_version,
            }
        if (head["revision"] if head else 0) != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        revision = expected + 1
        if revision > MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "指标配置版本已达上限")
        if not version:
            await session.execute(
                text(
                    "INSERT INTO orbit_metric_profile_version(tenant_id,"
                    "profile_id,version,payload_json,"
                    "payload_hash,source,authority_kind,source_config_id,"
                    "source_config_revision,source_connection_id,source_connection_revision,obs"
                    "erved_at,evidence_ref,"
                    "source_sha256,source_proof_json,created_by) "
                    "VALUES(:tenant,:id,:version,:profile,:profile_hash,"
                    ":source,:kind,:config,:config_revision,:connection,:connection_revision,:o"
                    "bserved,"
                    ":evidence,:source_sha,:proof,:actor)"
                ),
                params,
            )
        if not binding:
            await session.execute(
                text(
                    "INSERT INTO orbit_metric_profile_adapter(tenant_id,"
                    "profile_id,profile_version,adapter_version,"
                    "registry_revision,profile_hash,mapping_json,mapping_hash,source_proof_json) "
                    "VALUES(:tenant,:id,:version,:adapter,:registry,"
                    ":profile_hash,:mapping,:mapping_hash,:proof)"
                ),
                params,
            )
        if head:
            changed = await session.execute(
                text(
                    "UPDATE orbit_metric_profile_head SET "
                    "current_version=:version,revision=:revision,state='ENABLED',"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND "
                    "id=:id AND revision=:expected"
                ),
                params | {"revision": revision, "expected": expected},
            )
            if changed.rowcount != 1:
                raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        else:
            await session.execute(
                text(
                    "INSERT INTO orbit_metric_profile_head(tenant_id,id,"
                    "current_version,revision,state) "
                    "VALUES(:tenant,:id,:version,:revision,'ENABLED')"
                ),
                params | {"revision": revision},
            )
        await self._event(
            session,
            current,
            profile["id"],
            revision,
            "METRIC_PROFILE_PUBLISHED",
            request_id,
            {
                "version": profile["version"],
                "adapter_version": prepared.adapter_version,
                "profile_hash": prepared.profile_hash,
                "mapping_hash": prepared.attribution_hash,
                "source_sha256": prepared.proof.source_sha256,
            },
        )
        return {
            "id": profile["id"],
            "version": profile["version"],
            "revision": revision,
            "adapter_version": prepared.adapter_version,
        }

    async def _current_owner(self, session, owner_context):
        """共享配置的目标只核当前身份，不虚构目标launch.read或monitor.read动作。"""
        if type(owner_context.actor_id) is not int or owner_context.actor_id < 1:
            raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "目标拥有者当前身份不可用")
        row = await one(
            session,
            "SELECT s.user_id AS actor_id,s.tenant_id,s.data_role,b.id AS subject_id,b.team_id "
            "FROM orbit_user_scope s JOIN sys_user u ON u.user_id=s.user_id "
            "AND u.status='0' AND u.del_flag='0' "
            "JOIN sys_identity_subject i ON i.user_id=u.user_id AND i.auth_version>=1 "
            "JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1 "
            "JOIN orbit_business_user b ON b.tenant_id=s.tenant_id AND b.user_id=s.user_id "
            "AND b.enabled=1 AND b.invited=0 "
            "JOIN orbit_business_team bt ON bt.tenant_id=b.tenant_id "
            "AND bt.id=b.team_id AND bt.enabled=1 "
            "WHERE s.user_id=:owner AND s.enabled=1 FOR SHARE",
            {"owner": owner_context.actor_id},
        )
        fields = ("actor_id", "tenant_id", "data_role", "subject_id", "team_id")
        if (
            row is None
            or row["data_role"] not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}
            or any(row[key] != getattr(owner_context, key) for key in fields)
        ):
            raise OrbitError(
                404, "METRIC_PROFILE_UNAVAILABLE", "目标拥有者身份或租户团队范围已变化"
            )

    async def lock_exact(
        self,
        session,
        current,
        owner_context,
        profile_id,
        version,
        adapter_version,
        *,
        permission="launch.edit",
    ):
        transaction(session)
        if permission not in {"launch.read", "launch.create", "launch.edit", "launch.execute"}:
            raise ValueError("指标消费只能沿用原投放动作")
        if (
            not isinstance(current, BusinessContext)
            or not isinstance(owner_context, BusinessContext)
            or current.tenant_id != owner_context.tenant_id
        ):
            raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "指标配置不在当前双方租户范围")
        caller = await require_business_access(session, current.actor_id, "launch", permission)
        if caller != current:
            raise OrbitError(403, "PERMISSION_DENIED", "指标消费授权上下文已变化")
        await self._current_owner(session, owner_context)
        params = {
            "tenant": current.tenant_id,
            "id": uuid_field(profile_id, ("metric_profile_id",)),
            "version": version,
            "adapter": adapter_version,
        }
        if any(
            not isinstance(value, str) or not 1 <= len(value) <= 64
            for value in (version, adapter_version)
        ):
            raise OrbitError(422, "FIELD_INVALID", "需要明确指标及适配版本")
        metadata = await one(
            session,
            "SELECT "
            "source,source_config_id,source_config_revision,source_connection_id,source_connect"
            "ion_revision,source_proof_json "
            "FROM orbit_metric_profile_version "
            "WHERE tenant_id=:tenant AND profile_id=:id AND version=:version",
            params,
        )
        if metadata is None:
            raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "指标版本不存在或不可见")
        if metadata["source"] == "FIXTURE":
            await fixture_boundary(session)
        elif metadata["source"] == "META":
            proof_value = metadata["source_proof_json"]
            await validate_current_source(
                session,
                current.tenant_id,
                parse_source_proof(
                    json.loads(proof_value) if isinstance(proof_value, str) else proof_value, "META"
                ),
            )
        else:
            unavailable()
        await self._clock(session, current.tenant_id, write=False)
        row = await one(
            session,
            "SELECT h.current_version,h.state,v.payload_json,v.payload_hash,v.source,"
            "v.source_config_id,v.source_config_revision,v.source_connection_id,v.source_connec"
            "tion_revision,v.source_proof_json AS version_proof,"
            "a.source_proof_json AS adapter_proof,"
            "a.mapping_json,a.mapping_hash,a.profile_hash,a.registry_revision,a.revoked_at "
            "FROM orbit_metric_profile_head h JOIN "
            "orbit_metric_profile_version v ON v.tenant_id=h.tenant_id AND v.profile_id=h.id "
            "JOIN orbit_metric_profile_adapter a ON a.tenant_id=v.tenant_id "
            "AND a.profile_id=v.profile_id AND a.profile_version=v.version "
            "WHERE h.tenant_id=:tenant AND h.id=:id AND v.version=:version AND "
            "a.adapter_version=:adapter FOR SHARE",
            params,
        )
        if (
            row is None
            or row["state"] != "ENABLED"
            or row["current_version"] != version
            or row["revoked_at"] is not None
        ):
            raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "精确指标版本或适配映射不可用")
        if any(
            row[key] != metadata[key]
            for key in (
                "source",
                "source_config_id",
                "source_config_revision",
                "source_connection_id",
                "source_connection_revision",
            )
        ):
            unavailable()
        version_proof = (
            json.loads(row["version_proof"])
            if isinstance(row["version_proof"], str)
            else row["version_proof"]
        )
        adapter_proof = (
            json.loads(row["adapter_proof"])
            if isinstance(row["adapter_proof"], str)
            else row["adapter_proof"]
        )
        if canonical(version_proof) != canonical(adapter_proof):
            unavailable()
        try:
            proof = parse_source_proof(version_proof, row["source"])
            check_proof(proof, row["source"])
            if (
                proof.source_config_id != row["source_config_id"]
                or proof.source_config_revision != row["source_config_revision"]
                or proof.source_connection_id != row.get("source_connection_id")
                or proof.source_connection_revision != row.get("source_connection_revision")
            ):
                unavailable()
        except (KeyError, ValueError, TypeError):
            unavailable()
        profile = (
            json.loads(row["payload_json"])
            if isinstance(row["payload_json"], str)
            else row["payload_json"]
        )
        mapping = (
            json.loads(row["mapping_json"])
            if isinstance(row["mapping_json"], str)
            else row["mapping_json"]
        )
        if (
            hashlib.sha256(canonical(profile).encode()).hexdigest() != row["payload_hash"]
            or row["profile_hash"] != row["payload_hash"]
            or hashlib.sha256(canonical(mapping).encode()).hexdigest() != row["mapping_hash"]
            or profile.get("verified") is not True
        ):
            unavailable()
        validated = publication(profile, adapter_version, mapping, proof)
        if (
            validated.profile_hash != row["payload_hash"]
            or validated.attribution_hash != row["mapping_hash"]
            or profile["source"] != row["source"]
            or profile["id"] != profile_id
            or profile["version"] != version
        ):
            unavailable()
        return {
            "profile": profile,
            "profile_source_hash": row["payload_hash"],
            "adapter_version": adapter_version,
            "bound_profile_version": version,
            "registry_revision": row["registry_revision"],
            "attribution_spec": mapping,
        }

    async def revoke(self, session, current, profile_id, expected, request_id):
        await self._writer(session, current)
        await self._clock(session, current.tenant_id)
        params = {"tenant": current.tenant_id, "id": uuid_field(profile_id, ("profile_id",))}
        head = await one(
            session,
            "SELECT revision,state FROM orbit_metric_profile_head WHERE "
            "tenant_id=:tenant AND id=:id FOR UPDATE",
            params,
        )
        if head is None:
            raise OrbitError(404, "NOT_FOUND", "指标配置不存在")
        if head["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        if head["state"] == "DISABLED":
            return {"id": profile_id, "revision": expected}
        if expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "指标配置版本已达上限")
        changed = await session.execute(
            text(
                "UPDATE orbit_metric_profile_head SET state='DISABLED',revision=revision+1,"
                "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND "
                "id=:id AND revision=:expected"
            ),
            params | {"expected": expected},
        )
        if changed.rowcount != 1:
            raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        await self._event(
            session,
            current,
            profile_id,
            expected + 1,
            "METRIC_PROFILE_REVOKED",
            request_id,
            {"state": {"before": "ENABLED", "after": "DISABLED"}},
        )
        return {"id": profile_id, "revision": expected + 1}

    async def revoke_binding(
        self, session, current, profile_id, version, adapter_version, expected, request_id
    ):
        await self._writer(session, current)
        await self._clock(session, current.tenant_id)
        params = {
            "tenant": current.tenant_id,
            "id": uuid_field(profile_id, ("profile_id",)),
            "version": version,
            "adapter": adapter_version,
        }
        head = await one(
            session,
            "SELECT revision FROM orbit_metric_profile_head "
            "WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            params,
        )
        if head is None:
            raise OrbitError(404, "NOT_FOUND", "指标配置不存在")
        if head["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        row = await one(
            session,
            "SELECT revoked_at FROM orbit_metric_profile_adapter "
            "WHERE tenant_id=:tenant AND profile_id=:id AND profile_version=:version "
            "AND adapter_version=:adapter FOR UPDATE",
            params,
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "精确指标适配不存在")
        if row["revoked_at"] is not None:
            return {"id": profile_id, "revision": expected}
        if expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "指标配置版本已达上限")
        await session.execute(
            text(
                "UPDATE orbit_metric_profile_adapter SET revoked_at=UTC_TIMESTAMP(3) "
                "WHERE tenant_id=:tenant AND profile_id=:id AND profile_version=:version "
                "AND adapter_version=:adapter AND revoked_at IS NULL"
            ),
            params,
        )
        changed = await session.execute(
            text(
                "UPDATE orbit_metric_profile_head SET revision=revision+1,"
                "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id "
                "AND revision=:expected"
            ),
            params | {"expected": expected},
        )
        if changed.rowcount != 1:
            raise OrbitError(409, "REVISION_CONFLICT", "指标配置头已变化")
        await self._event(
            session,
            current,
            profile_id,
            expected + 1,
            "METRIC_PROFILE_ADAPTER_REVOKED",
            request_id,
            {"version": version, "adapter_version": adapter_version},
        )
        return {"id": profile_id, "revision": expected + 1}

    async def candidate_page(self, session, current, *, after="", limit=50):
        """内部keyset基础：不是已完成的原GET，其他未定义过滤器交公共入口显式处理。"""
        transaction(session)
        if not isinstance(current, BusinessContext):
            raise ValueError("需要当前读取上下文")
        fresh = await require_business_access(session, current.actor_id, "monitor", "monitor.read")
        if fresh != current:
            raise OrbitError(403, "PERMISSION_DENIED", "指标读取权限已变化")
        if limit not in {20, 50, 100, 200} or type(limit) is not int:
            raise OrbitError(422, "FIELD_INVALID", "每页数不受支持", "/page_size")
        if after:
            uuid_field(after, ("cursor",))
        water = await one(
            session,
            "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=:tenant FOR SHARE",
            {"tenant": current.tenant_id},
        )
        if water is None:
            raise OrbitError(503, "METRIC_PROFILE_INITIALIZATION_REQUIRED", "指标目录尚未初始化")
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT h.id,v.payload_json,v.source FROM orbit_metric_profile_head h "
                        "JOIN orbit_metric_profile_version v ON v.tenant_id=h.tenant_id "
                        "AND v.profile_id=h.id AND v.version=h.current_version "
                        "LEFT JOIN orbit_system_configuration c ON c.tenant_id=v.tenant_id "
                        "AND c.id=v.source_config_id "
                        + SOURCE_JOINS
                        + "WHERE h.tenant_id=:tenant AND h.state='ENABLED' AND h.id>:after AND "
                        + SOURCE_AVAILABLE
                        + " ORDER BY h.id LIMIT :limit"
                    ),
                    {"tenant": current.tenant_id, "after": after, "limit": limit + 1},
                )
            )
            .mappings()
            .all()
        )
        if any(row["source"] == "FIXTURE" for row in rows):
            await fixture_boundary(session)
        from orbit_api.launch_contract import parse_model
        from orbit_api.launch_execution_contract import MetricProfile

        items = [
            parse_model(
                canonical(
                    json.loads(row["payload_json"])
                    if isinstance(row["payload_json"], str)
                    else row["payload_json"]
                ).encode(),
                MetricProfile,
            )
            for row in rows[:limit]
        ]
        return {
            "items": items,
            "after": rows[limit - 1]["id"] if len(rows) > limit else None,
            "registry_revision": water["revision"],
        }


async def validate_current_source(session, tenant, proof):
    """发行/消费共享来源锁：版本、撤销、期限和BM原配置全部复验。"""
    check_proof(proof, "META")
    if proof.source_connection_id is not None:
        from orbit_api.account_platform import AccountReadFailure
        from orbit_api.meta_account_sources import connection_row

        try:
            row = await connection_row(
                session, tenant, proof.source_connection_id, proof.source_connection_revision
            )
        except AccountReadFailure:
            raise OrbitError(
                409, "METRIC_PROFILE_SOURCE_CHANGED", "指标连接已撤销、到期或变更"
            ) from None
        if row["kind"] != "BM":
            return
        identifier, revision = row["configuration_id"], row["configuration_revision"]
    else:
        identifier, revision = proof.source_config_id, proof.source_config_revision
    source = await one(
        session,
        "SELECT revision,enabled,section FROM orbit_system_configuration WHERE "
        "tenant_id=:tenant AND id=:id FOR SHARE",
        {"tenant": tenant, "id": identifier},
    )
    if (
        source is None
        or source["revision"] != revision
        or not source["enabled"]
        or source["section"] != "META_BM"
    ):
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "当前META来源已撤销或变更")


# 列表使用同一真实来源条件；连接撤销即时隐藏，旧META_BM来源仍兼容。
SOURCE_JOINS = (
    " LEFT JOIN orbit_meta_connection mc ON mc.tenant_id=v.tenant_id AND "
    "mc.id=v.source_connection_id "
    " LEFT JOIN orbit_system_configuration bc ON bc.tenant_id=mc.tenant_id AND "
    "bc.id=mc.configuration_id "
)
SOURCE_AVAILABLE = (
    "(v.source='FIXTURE' OR (v.source='META' AND ((v.source_connection_id IS NULL AND "
    "c.enabled=1 AND c.section='META_BM' AND c.revision=v.source_config_revision) "
    "OR (v.source_config_id IS NULL AND mc.status='ACTIVE' AND "
    "mc.revision=v.source_connection_revision AND mc.token_envelope IS NOT NULL "
    "AND (mc.expires_at IS NULL OR mc.expires_at>UTC_TIMESTAMP(3)) AND "
    "(mc.data_access_expires_at IS NULL OR mc.data_access_expires_at>UTC_TIMESTAMP(3)) "
    "AND (mc.kind='LOGIN' OR (mc.kind='BM' AND bc.enabled=1 AND bc.section='META_BM' AND "
    "bc.revision=mc.configuration_revision))))))"
)


async def validate_collection_source(session, tenant, proof, connection_id, connection_revision):
    """仅采集复用已核口径：同主体重授权不改映射，当前读取仍须独立真实账户收据。

    OAuth/BM接入服务只对同app/主体更新原连接ID；改变主体创建新连接。
    旧job自身connection/account-source版本仍精确匹配，不调用本函数放宽租约。
    """
    from orbit_api.account_platform import AccountReadFailure
    from orbit_api.meta_account_sources import connection_row

    check_proof(proof, "META")
    if proof.source_connection_id is None:
        await validate_current_source(session, tenant, proof)
        return
    if (
        connection_id != proof.source_connection_id
        or type(connection_revision) is not int
        or connection_revision < proof.source_connection_revision
    ):
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标口径来源与本次连接不连续")
    try:
        row = await connection_row(session, tenant, connection_id, connection_revision)
    except AccountReadFailure:
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "本次采集连接已失效") from None
    if row["kind"] == "BM":
        # BM还须核本轮配置，不把旧Token配置的验证状态沿用到新配置。
        source = await one(
            session,
            "SELECT revision,enabled,section,verification_status FROM "
            "orbit_system_configuration WHERE tenant_id=:tenant AND id=:id FOR SHARE",
            {"tenant": tenant, "id": row["configuration_id"]},
        )
        if (
            source is None
            or source["revision"] != row["configuration_revision"]
            or not source["enabled"]
            or source["section"] != "META_BM"
            or source["verification_status"] != "READ_VERIFIED"
        ):
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "本次BM读取配置不可用")
