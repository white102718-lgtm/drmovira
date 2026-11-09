"""规则独立实时动作与双方数据范围；不借monitor/launch/accounts的动作授权。"""

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import text

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams, validate_ownership
from orbit_api.rule_contract import MAX_SAFE, identifier

RULE_ACTIONS = frozenset(
    {
        "rules.read",
        "rules.create",
        "rules.edit",
        "rules.enable",
        "rules.pause",
        "rules.archive",
    }
)
_ISSUER = object()


def transaction(session):
    if not session.in_transaction():
        raise ValueError("规则引用须由外层事务持有来源和授权锁")
    return session.sync_session.get_transaction()


def _fingerprint(current, managed, version):
    # 与原私有snapshot根格式保持一致，不改变旧接口的creator专属范围。
    return hashlib.sha256(
        canonical(
            [
                current.actor_id,
                current.tenant_id,
                current.subject_id,
                current.data_role,
                current.team_id,
                list(managed),
                version,
            ]
        ).encode()
    ).hexdigest()


@dataclass(frozen=True, repr=False)
class RuleAccess:
    current: BusinessContext
    permission: str
    auth_version: int
    managed_team_ids: tuple[str, ...]
    auth_fingerprint: str
    _session: object = field(repr=False)
    _transaction: object = field(repr=False)
    _issuer: object = field(repr=False)


@dataclass(frozen=True, repr=False)
class OwnerScope:
    current: BusinessContext
    auth_version: int
    managed_team_ids: tuple[str, ...]
    auth_fingerprint: str
    _access: RuleAccess = field(repr=False)


def assert_access(session, access):
    if (
        not isinstance(access, RuleAccess)
        or access._issuer is not _ISSUER
        or access.permission not in RULE_ACTIONS
        or access._session is not session
        or access._transaction is not transaction(session)
    ):
        raise ValueError("规则引用必须使用同事务实时授权票据")


def assert_owner(session, access, owner):
    assert_access(session, access)
    if (
        not isinstance(owner, OwnerScope)
        or owner._access is not access
        or owner.current.tenant_id != access.current.tenant_id
    ):
        raise ValueError("规则拥有者不是当前双方授权票据")


def readable(current, managed, account):
    return (
        current.data_role == "SUPER_ADMIN"
        or account["owner_user_id"] == current.subject_id
        or current.data_role == "TEAM_ADMIN"
        and account["owner_team_id"] in managed
    )


def require_rule_visible(access, row):
    if not isinstance(access, RuleAccess) or access._issuer is not _ISSUER:
        raise ValueError("规则对象读取须使用实时授权票据")
    if (
        row is None
        or row.get("tenant_id") != access.current.tenant_id
        or not readable(access.current, access.managed_team_ids, row)
    ):
        raise OrbitError(404, "NOT_FOUND", "规则不存在或不在当前可读范围")


async def authorize_rule(session, actor, permission):
    tx = transaction(session)
    if permission not in RULE_ACTIONS:
        raise ValueError("只能使用原规则六动作")
    current = await require_business_access(session, actor, "rules", permission)
    managed = tuple(sorted(set(await managed_teams(session, current))))
    version = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            {"actor": actor},
        )
    ).scalar_one_or_none()
    if type(version) is not int or not 1 <= version <= MAX_SAFE:
        raise OrbitError(409, "SCOPE_VERSION_INVALID", "当前授权版本不可用")
    return RuleAccess(
        current,
        permission,
        version,
        managed,
        _fingerprint(current, managed, version),
        session,
        tx,
        _ISSUER,
    )


async def revalidate_access(session, access):
    assert_access(session, access)
    live = await authorize_rule(session, access.current.actor_id, access.permission)
    if live.current != access.current or live.auth_fingerprint != access.auth_fingerprint:
        raise OrbitError(403, "PERMISSION_DENIED", "规则当前权限或数据范围已变化")


async def revalidate_owner(session, access, owner):
    assert_owner(session, access, owner)
    await revalidate_access(session, access)
    live = await owner_scope(
        session,
        access,
        {
            "owner_user_id": owner.current.subject_id,
            "owner_team_id": owner.current.team_id,
        },
    )
    if live.current != owner.current or live.auth_fingerprint != owner.auth_fingerprint:
        raise OrbitError(409, "RULE_OWNER_SCOPE_CHANGED", "拥有者当前授权代际已变化")


async def owner_scope(session, access, ownership, *, for_write=False, previous=None):
    assert_access(session, access)
    owner_id = identifier(ownership["owner_user_id"], "/ownership/owner_user_id")
    team_id = identifier(ownership["owner_team_id"], "/ownership/owner_team_id")
    if for_write:
        if access.permission not in {"rules.create", "rules.edit"}:
            raise ValueError("规则归属写入只能使用原create/edit动作")
        converted = {"owner_team_id": team_id, "data_owner_user_ids": [owner_id]}
        original = (
            {
                "owner_team_id": previous["owner_team_id"],
                "data_owner_user_ids": [previous["owner_user_id"]],
            }
            if previous
            else None
        )
        # managed可读不自动等于可写：沿原显式归属指派规则复核。
        await validate_ownership(session, access.current, converted, previous=original)
    row = (
        (
            await session.execute(
                text(
                    "SELECT s.user_id AS actor_id,s.tenant_id,s.data_role,b.id AS subject_id,"
                    "b.team_id,i.auth_version FROM orbit_business_user b "
                    "JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0' "
                    "JOIN sys_identity_subject i ON i.user_id=u.user_id "
                    "JOIN orbit_user_scope s ON s.user_id=u.user_id "
                    "AND s.tenant_id=b.tenant_id AND s.enabled=1 "
                    "JOIN orbit_business_team bt ON bt.tenant_id=b.tenant_id "
                    "AND bt.id=b.team_id AND bt.enabled=1 "
                    "JOIN orbit_tenant t ON t.id=b.tenant_id AND t.enabled=1 "
                    "WHERE b.tenant_id=:tenant AND b.id=:owner AND b.team_id=:team "
                    "AND b.enabled=1 AND b.invited=0 FOR SHARE"
                ),
                {"tenant": access.current.tenant_id, "owner": owner_id, "team": team_id},
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or type(row["actor_id"]) is not int
        or row["actor_id"] < 1
        or row["tenant_id"] != access.current.tenant_id
        or row["subject_id"] != owner_id
        or row["team_id"] != team_id
        or row["data_role"] not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}
        or type(row["auth_version"]) is not int
        or not 1 <= row["auth_version"] <= MAX_SAFE
    ):
        raise OrbitError(409, "RULE_OWNER_SCOPE_CHANGED", "规则拥有者当前身份或团队不可用")
    current = BusinessContext(
        *(row[k] for k in ("actor_id", "tenant_id", "data_role", "subject_id", "team_id"))
    )
    managed = tuple(sorted(set(await managed_teams(session, current))))
    return OwnerScope(
        current,
        row["auth_version"],
        managed,
        _fingerprint(current, managed, row["auth_version"]),
        access,
    )
