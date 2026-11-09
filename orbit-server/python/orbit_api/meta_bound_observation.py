"""原accounts.sync授权下的临时来源绑定；不发布身份、不持久化、不授予执行权。

捕获自行结束短事务才返回；锁序沿现同步：授权→账户clock→有序账户→配置。
最终发布必须重新授权及CAS，此快照绝不表示观察完成时来源仍然当前。
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock, parameters
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import (
    SAFE_INTEGER,
    MetaLaunchObservation,
    MetaLaunchObserver,
    MetaLaunchReadConfiguration,
    MetaObservationFailure,
    external_id,
    utc_now,
)
from orbit_api.reference_access import managed_teams

_ISSUER = object()


def unavailable():
    raise OrbitError(503, "META_BOUND_SOURCE_UNAVAILABLE", "只读来源绑定尚未就绪") from None


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            unavailable()
    except ValueError:
        unavailable()
    return value


def revision(value):
    if type(value) is not int or not 1 <= value <= SAFE_INTEGER:
        unavailable()
    return value


@dataclass(frozen=True, repr=False)
class MetaAccountBinding:
    account_id: str
    account_revision: int
    external_id: str
    owner_user_id: str
    owner_team_id: str


@dataclass(frozen=True, repr=False)
class MetaSourceSnapshot:
    tenant_id: str
    actor_id: int
    subject_id: str
    team_id: str
    data_role: str
    auth_version: int
    permission: str
    account_clock: int
    captured_at: datetime
    accounts: tuple[MetaAccountBinding, ...]
    configuration: MetaLaunchReadConfiguration = field(repr=False)
    binding_sha256: str
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, repr=False)
class BoundMetaObservation:
    """只证明本次读包对应捕获的来源；不是最终CAS或持久发布回执。"""

    source: MetaSourceSnapshot = field(repr=False)
    observation: MetaLaunchObservation = field(repr=False)
    binding_sha256: str
    publication_revalidated: bool = field(default=False, init=False)
    durable: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)


def binding_document(snapshot):
    return {
        "schema_version": 1,
        "tenant_id": snapshot.tenant_id,
        "actor_id": snapshot.actor_id,
        "subject_id": snapshot.subject_id,
        "team_id": snapshot.team_id,
        "data_role": snapshot.data_role,
        "auth_version": snapshot.auth_version,
        "permission": snapshot.permission,
        "account_clock": snapshot.account_clock,
        "captured_at": snapshot.captured_at.isoformat(),
        "source_config_id": snapshot.configuration.source_config_id,
        "source_config_revision": snapshot.configuration.source_config_revision,
        "business_id": snapshot.configuration.business_id,
        "api_version": snapshot.configuration.api_version,
        "accounts": [
            {
                "id": row.account_id,
                "revision": row.account_revision,
                "external_id": row.external_id,
                "owner_user_id": row.owner_user_id,
                "owner_team_id": row.owner_team_id,
            }
            for row in snapshot.accounts
        ],
    }


def binding_hash(snapshot):
    return hashlib.sha256(canonical(binding_document(snapshot)).encode("utf-8")).hexdigest()


async def capture_meta_source(sessions, actor, account_ids, *, cipher, permission="accounts.sync"):
    """sessions为新session工厂；只支持原同步动作，不借read/launch动作扩权。

    不接受外部传入tenant、source或Token。沿原SYNC选择唯一启用READ_VERIFIED来源，
    该标签仅允许尝试读取，不表示生产身份/策略权威。所有事务退出后才签发临时包。
    """
    if permission != "accounts.sync":
        raise ValueError("当前来源捕获仅支持accounts.sync")
    if type(actor) is not int or actor < 1:
        raise OrbitError(403, "PERMISSION_DENIED", "当前主体无效")
    if not isinstance(account_ids, (list, tuple)) or not 1 <= len(account_ids) <= 500:
        raise OrbitError(422, "FIELD_VALIDATION_FAILED", "账户数量必须为1至500", "/account_ids")
    identifiers = tuple(sorted(identifier(value) for value in account_ids))
    if len(set(identifiers)) != len(identifiers):
        raise OrbitError(422, "DUPLICATE_VALUE", "账户UUID不能重复", "/account_ids")
    async with sessions() as session:
        # 禁止工厂复用已有事务，避免提交/回滚调用者工作或持锁执行网络。
        if session.in_transaction():
            raise ValueError("来源捕获必须使用独立无事务session")
        async with session.begin():
            current = await require_business_access(session, actor, "accounts", permission)
            if current.actor_id != actor:
                unavailable()
            identifier(current.tenant_id)
            identifier(current.subject_id)
            identifier(current.team_id)
            version = revision(
                (
                    await session.execute(
                        text(
                            "SELECT auth_version FROM sys_identity_subject "
                            "WHERE user_id=:actor FOR SHARE"
                        ),
                        {"actor": actor},
                    )
                ).scalar_one_or_none()
            )
            watermark = revision(await clock(session, current))
            # 外层FOR SHARE不会令nested EXISTS当前锁读；显式集合锁避免旧RR授权。
            managed = set(await managed_teams(session, current))
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT a.tenant_id,a.id,a.revision,a.external_id,a.owner_user_id,"
                            "a.owner_team_id,a.unbound_at FROM orbit_ad_account a "
                            "WHERE a.tenant_id=:tenant AND a.id IN :ids "
                            "ORDER BY a.id LIMIT 501 FOR SHARE OF a"
                        ).bindparams(bindparam("ids", expanding=True)),
                        parameters(current) | {"ids": identifiers},
                    )
                ).mappings()
            )
            if len(rows) != len(identifiers) or {row["id"] for row in rows} != set(identifiers):
                raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
            bindings = []
            for row in rows:
                if (
                    current.data_role != "SUPER_ADMIN"
                    and row["owner_user_id"] != current.subject_id
                    and not (current.data_role == "TEAM_ADMIN" and row["owner_team_id"] in managed)
                ):
                    raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
                if row["tenant_id"] != current.tenant_id or row["unbound_at"] is not None:
                    unavailable()
                try:
                    external_id(row["external_id"])
                except MetaObservationFailure:
                    unavailable()
                bindings.append(
                    MetaAccountBinding(
                        identifier(row["id"]),
                        revision(row["revision"]),
                        row["external_id"],
                        identifier(row["owner_user_id"]),
                        identifier(row["owner_team_id"]),
                    )
                )
            if len({row.external_id for row in bindings}) != len(bindings):
                unavailable()
            sources = list(
                (
                    await session.execute(
                        text(
                            "SELECT id,revision,settings_json,secrets_json "
                            "FROM orbit_system_configuration "
                            "WHERE tenant_id=:tenant AND section='META_BM' AND enabled=1 "
                            "AND verification_status='READ_VERIFIED' ORDER BY id LIMIT 2 FOR SHARE"
                        ),
                        {"tenant": current.tenant_id},
                    )
                ).mappings()
            )
            if len(sources) != 1:
                unavailable()
            try:
                source = sources[0]
                settings, encrypted = (
                    _decode(source["settings_json"]),
                    _decode(source["secrets_json"]),
                )
                if not isinstance(settings, dict) or not isinstance(encrypted, dict):
                    unavailable()
                if not encrypted.get("accessToken") or not cipher.ready:
                    unavailable()
                configuration = MetaLaunchReadConfiguration(
                    identifier(source["id"]),
                    revision(source["revision"]),
                    settings.get("businessId"),
                    settings.get("graphVersion"),
                    cipher.decrypt_internal(
                        encrypted["accessToken"], current.tenant_id, source["id"], "accessToken"
                    ),
                )
                configuration.validate()
            except Exception:
                # 解密器/结构异常不得泄漏密文、Token或来源正文；取消等BaseException继续传播。
                unavailable()
            values = dict(
                tenant_id=current.tenant_id,
                actor_id=actor,
                subject_id=current.subject_id,
                team_id=current.team_id,
                data_role=current.data_role,
                auth_version=version,
                permission=permission,
                account_clock=watermark,
                captured_at=utc_now(),
                accounts=tuple(sorted(bindings, key=lambda row: row.account_id)),
                configuration=configuration,
            )
    # 这里已经退出事务和session；snapshot不持有任何session/transaction对象。
    preliminary = MetaSourceSnapshot(**values, binding_sha256="", _issuer=_ISSUER)
    return MetaSourceSnapshot(**values, binding_sha256=binding_hash(preliminary), _issuer=_ISSUER)


async def observe_meta_source(snapshot, *, transport=None, limits=None):
    """临时网络读取；当前授权/账户/源是否已变更必须由未来publisher另作CAS。

    digest用于检测误绑定，不是外部签名或authority；本函数没有持久写入路径。
    """
    if (
        not isinstance(snapshot, MetaSourceSnapshot)
        or snapshot._issuer is not _ISSUER
        or snapshot.permission != "accounts.sync"
        or snapshot.binding_sha256 != binding_hash(snapshot)
    ):
        unavailable()
    observation = await MetaLaunchObserver(
        snapshot.configuration, transport=transport, limits=limits
    ).observe(tuple(row.external_id for row in snapshot.accounts))
    configuration = snapshot.configuration
    if (
        observation.source_config_id != configuration.source_config_id
        or observation.source_config_revision != configuration.source_config_revision
        or observation.business_id != configuration.business_id
        or observation.api_version != configuration.api_version
        or tuple(row.external_id for row in observation.accounts)
        != tuple(sorted(row.external_id for row in snapshot.accounts))
    ):
        unavailable()
    combined = hashlib.sha256(
        canonical([snapshot.binding_sha256, observation.evidence_sha256]).encode("utf-8")
    ).hexdigest()
    return BoundMetaObservation(snapshot, observation, combined)
