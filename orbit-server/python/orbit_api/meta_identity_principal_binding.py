"""配置主体与实际/me的独立绑定；不发行身份能力，不替代发布期当前授权/CAS。"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock, parameters
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_bound_observation import BoundMetaObservation
from orbit_api.meta_identity_facts_observation import BoundIdentityFacts, observe_identity_facts
from orbit_api.meta_launch_observation import MetaObservationFailure, external_id, utc_now
from orbit_api.meta_observation_registry import prepare_rows
from orbit_api.reference_access import managed_teams

_ISSUER = object()


def unavailable(code="META_PRINCIPAL_SOURCE_UNAVAILABLE"):
    raise OrbitError(503, code, "配置主体只读证据尚未就绪") from None


def changed():
    raise OrbitError(409, "META_PRINCIPAL_SOURCE_CHANGED", "原始观察来源或当前范围已变更") from None


@dataclass(frozen=True, repr=False)
class PrincipalBindingSource:
    bound: BoundMetaObservation = field(repr=False)
    system_user_id: str
    managed_team_ids: tuple[str, ...]
    captured_at: datetime
    source_sha256: str
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, repr=False)
class BoundPrincipalMatch:
    source: PrincipalBindingSource = field(repr=False)
    facts: BoundIdentityFacts = field(repr=False)
    principal_id: str
    evidence_sha256: str
    _issuer: object = field(repr=False, compare=False)
    # 只证明当前观察与配置字符串相符，不推断主体类型、Token scopes或资源可投。
    principal_matches: bool = field(default=True, init=False)
    principal_type_verified: bool = field(default=False, init=False)
    publication_revalidated: bool = field(default=False, init=False)
    durable: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)
    capability_version: None = field(default=None, init=False)
    policy_version: None = field(default=None, init=False)


def source_hash(source):
    value = {
        "schema_version": 1,
        "bound_sha256": source.bound.binding_sha256,
        "source_config_id": source.bound.source.configuration.source_config_id,
        "source_config_revision": source.bound.source.configuration.source_config_revision,
        "business_id": source.bound.source.configuration.business_id,
        "api_version": source.bound.source.configuration.api_version,
        "system_user_id": source.system_user_id,
        "managed_team_ids": source.managed_team_ids,
        "captured_at": source.captured_at.isoformat(),
    }
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def check_source(source):
    if not isinstance(source, PrincipalBindingSource) or source._issuer is not _ISSUER:
        unavailable()
    prepare_rows(source.bound)
    try:
        external_id(source.system_user_id)
        if source.source_sha256 != source_hash(source):
            unavailable()
    except (ValueError, TypeError, AttributeError, MetaObservationFailure):
        unavailable()


async def capture_identity_principal(sessions, actor, bound):
    """第二个自有短事务复核完整M1范围并绑定真实配置systemUserId，不执行网络。

    不修改M1兼容接口；调用者不能指定期望主体。配置→clock→当前managed→账户
    均当前锁读；开始于无事务session，禁止在未知外层锁序中复用。
    """
    prepare_rows(bound)
    previous = bound.source
    if type(actor) is not int or actor < 1 or actor != previous.actor_id:
        raise OrbitError(403, "PERMISSION_DENIED", "当前主体不能读取此来源")
    owned = sessions()
    # 在接管context前拒绝已有事务，避免__aexit__/close隐式回滚调用者的事务。
    if owned.in_transaction():
        raise ValueError("主体绑定捕获必须使用独立无事务session")
    async with owned as session:
        async with session.begin():
            current = await require_business_access(session, actor, "accounts", "accounts.sync")
            if (current.actor_id, current.tenant_id) != (actor, previous.tenant_id):
                raise OrbitError(403, "PERMISSION_DENIED", "当前主体不能读取此来源")
            version = (
                await session.execute(
                    text(
                        "SELECT auth_version FROM sys_identity_subject "
                        "WHERE user_id=:actor FOR SHARE"
                    ),
                    {"actor": actor},
                )
            ).scalar_one_or_none()
            sources = list(
                (
                    await session.execute(
                        text(
                            "SELECT id,revision,settings_json,secrets_json "
                            "FROM orbit_system_configuration "
                            "FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant AND section='META_BM' "
                            "AND enabled=1 AND verification_status='READ_VERIFIED' "
                            "ORDER BY id FOR SHARE"
                        ),
                        {"tenant": current.tenant_id},
                    )
                ).mappings()
            )
            if len(sources) != 1:
                unavailable()
            selected = sources[0]
            configuration = previous.configuration
            if (selected["id"], selected["revision"]) != (
                configuration.source_config_id,
                configuration.source_config_revision,
            ):
                changed()
            try:
                settings, secrets = (
                    _decode(selected["settings_json"]),
                    _decode(selected["secrets_json"]),
                )
                if not isinstance(settings, dict) or not isinstance(secrets, dict):
                    unavailable()
                if not secrets.get("accessToken"):
                    unavailable()
                system_user_id = external_id(settings.get("systemUserId"))
                if (settings.get("businessId"), settings.get("graphVersion")) != (
                    configuration.business_id,
                    configuration.api_version,
                ):
                    changed()
            except (TypeError, ValueError, MetaObservationFailure):
                unavailable()
            watermark = await clock(session, current)
            managed = tuple(sorted(set(await managed_teams(session, current))))
            identifiers = tuple(row.account_id for row in previous.accounts)
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT a.tenant_id,a.id,a.revision,a.external_id,a.owner_user_id,"
                            "a.owner_team_id,a.unbound_at FROM orbit_ad_account a WHERE "
                            "a.tenant_id=:tenant AND a.id IN :ids "
                            "ORDER BY a.id LIMIT 501 FOR SHARE OF a"
                        ).bindparams(bindparam("ids", expanding=True)),
                        parameters(current) | {"ids": identifiers},
                    )
                ).mappings()
            )
            if len(rows) != len(identifiers) or {row["id"] for row in rows} != set(identifiers):
                raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
            original = {row.account_id: row for row in previous.accounts}
            for row in rows:
                if (
                    row["tenant_id"] != current.tenant_id
                    or current.data_role != "SUPER_ADMIN"
                    and row["owner_user_id"] != current.subject_id
                    and not (current.data_role == "TEAM_ADMIN" and row["owner_team_id"] in managed)
                ):
                    raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
                old = original[row["id"]]
                if row["unbound_at"] is not None or (
                    row["revision"],
                    row["external_id"],
                    row["owner_user_id"],
                    row["owner_team_id"],
                ) != (old.account_revision, old.external_id, old.owner_user_id, old.owner_team_id):
                    changed()
            if (
                (current.subject_id, current.team_id, current.data_role)
                != (previous.subject_id, previous.team_id, previous.data_role)
                or type(version) is not int
                or version != previous.auth_version
                or type(watermark) is not int
                or watermark != previous.account_clock
            ):
                changed()
            captured = utc_now()
    # 已退出事务和session；不保留session/factory，更不能在持锁时发外网请求。
    source = PrincipalBindingSource(bound, system_user_id, managed, captured, "", _ISSUER)
    return PrincipalBindingSource(
        bound, system_user_id, managed, captured, source_hash(source), _ISSUER
    )


async def observe_identity_principal(source, selected, *, transport=None, limits=None):
    """事务外调用固定M3观察器；/me精确匹配仅产生配置主体绑定回执。"""
    check_source(source)
    facts = await observe_identity_facts(source.bound, selected, transport=transport, limits=limits)
    configuration = source.bound.source.configuration
    if (
        facts.source_binding_sha256 != source.bound.binding_sha256
        or facts.source_config_id != configuration.source_config_id
        or facts.source_config_revision != configuration.source_config_revision
        or facts.api_version != configuration.api_version
        or facts.business_id != configuration.business_id
    ):
        unavailable("META_PRINCIPAL_OBSERVATION_MISMATCH")
    if facts.principal_id is None:
        unavailable("META_PRINCIPAL_NOT_OBSERVED")
    if facts.principal_id != source.system_user_id:
        unavailable("META_PRINCIPAL_MISMATCH")
    evidence = hashlib.sha256(
        canonical(
            {
                "schema_version": 1,
                "source_sha256": source.source_sha256,
                "facts_sha256": facts.evidence_sha256,
                "principal_id": facts.principal_id,
                "principal_matches": True,
            }
        ).encode("utf-8")
    ).hexdigest()
    return BoundPrincipalMatch(source, facts, facts.principal_id, evidence, _ISSUER)
