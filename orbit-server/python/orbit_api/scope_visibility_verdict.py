"""范围当前可见性的正向证明；只供已实时授权的服务端事务调用。"""

import hashlib
import re

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock, parameters
from orbit_api.account_identities_store import identifier
from orbit_api.authorization import BusinessContext
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams

PREDICATE_VERSION = 1
MAX_MEMBERS = 50_000
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _changed():
    raise OrbitError(409, "SCOPE_CHANGED", "账户范围授权已变化，请重新冻结选择")


def proof_matches(proof, expected):
    """旧一致性视图最多导致未命中；所有依赖完全相等才复用正向证明。"""
    return proof is not None and all(proof.get(key) == value for key, value in expected.items())


async def verified_snapshot(session, current, auth_version, auth_digest, snapshot_id):
    """返回完整原快照行；调用者必须先完成原 AccountScopeStore.authorize。

    不代替菜单/动作/当前身份检查，不代替计划消费时的拥有者、团队、币种求交。
    时钟共享锁及到期投影门禁每次重取并保持到外层事务结束；禁止独立提交。
    """
    if not session.in_transaction() or not isinstance(current, BusinessContext):
        raise ValueError("范围证明必须处于已授权的显式业务事务")
    if (
        type(auth_version) is not int
        or not 1 <= auth_version <= MAX_REVISION
        or not isinstance(auth_digest, str)
        or _HASH.fullmatch(auth_digest) is None
    ):
        raise ValueError("范围证明必须使用服务端当前授权版本和指纹")
    snapshot_id = identifier(snapshot_id, "/id")
    account_version = await clock(session, current)
    params = parameters(current) | {"id": snapshot_id}
    row = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_account_scope_snapshot WHERE tenant_id=:tenant "
                    "AND id=:id AND actor_id=:actor AND ready=1 AND cleanup_requested=0 FOR SHARE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["cleanup_requested"] != 0:
        raise OrbitError(404, "NOT_FOUND", "范围不存在或不属于当前会话人员")
    if row["scope_version"] != auth_version or row["auth_fingerprint"] != auth_digest:
        _changed()
    if (
        type(row["member_count"]) is not int
        or not 0 <= row["member_count"] <= MAX_MEMBERS
        or not isinstance(row["members_hash"], str)
        or _HASH.fullmatch(row["members_hash"]) is None
    ):
        _changed()
    expected = {
        "actor_id": current.actor_id,
        "auth_version": auth_version,
        "auth_digest": auth_digest,
        "account_version": account_version,
        "members_hash": row["members_hash"],
        "member_count": row["member_count"],
        "predicate_version": PREDICATE_VERSION,
    }
    # 不锁缺失证明行，避免并发未命中的 gap SHARE → INSERT 升级死锁。
    proof = (
        (
            await session.execute(
                text(
                    "SELECT actor_id,auth_version,auth_digest,account_version,members_hash,"
                    "member_count,predicate_version FROM orbit_scope_access_verdict "
                    "WHERE tenant_id=:tenant AND snapshot_id=:id AND actor_id=:actor"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if proof_matches(proof, expected):
        return dict(row)
    predicate = "1=1" if current.data_role == "SUPER_ADMIN" else "a.owner_user_id=:subject"
    if current.data_role == "TEAM_ADMIN":
        # 嵌套 EXISTS 不继承外层 OF a 锁；使用当前锁定管理集合，防旧 RR 关系误授予。
        managed = sorted(await managed_teams(session, current))
        refreshed_digest = hashlib.sha256(
            canonical(
                [
                    current.actor_id,
                    current.tenant_id,
                    current.subject_id,
                    current.data_role,
                    current.team_id,
                    managed,
                    auth_version,
                ]
            ).encode()
        ).hexdigest()
        if refreshed_digest != auth_digest:
            _changed()
        if managed:
            predicate += " OR a.owner_team_id IN :managed"
            params["managed"] = managed
    # 必须 current locking read：不能将 RR 事务旧读视图下的旧归属配上新时钟。
    statement = text(
        "SELECT 1 FROM orbit_account_scope_member m "
        "LEFT JOIN orbit_ad_account a ON a.tenant_id=m.tenant_id AND a.id=m.account_id "
        "WHERE m.tenant_id=:tenant AND m.snapshot_id=:id AND "
        "(a.id IS NULL OR NOT (" + predicate + ")) LIMIT 1 FOR SHARE OF a"
    )
    if "managed" in params:
        statement = statement.bindparams(bindparam("managed", expanding=True))
    invisible = (await session.execute(statement, params)).scalar_one_or_none()
    if invisible is not None:
        _changed()
    # 仅完整成功后写正向证明；每份快照/actor一行，不追加历史、不维护命中时间。
    await session.execute(
        text(
            "INSERT INTO orbit_scope_access_verdict "
            "(tenant_id,snapshot_id,actor_id,auth_version,auth_digest,account_version,"
            "members_hash,member_count,predicate_version,verified_at) VALUES "
            "(:tenant,:id,:actor_id,:auth_version,:auth_digest,:account_version,"
            ":members_hash,:member_count,:predicate_version,UTC_TIMESTAMP(3)) "
            "ON DUPLICATE KEY UPDATE auth_version=VALUES(auth_version),"
            "auth_digest=VALUES(auth_digest),account_version=VALUES(account_version),"
            "members_hash=VALUES(members_hash),member_count=VALUES(member_count),"
            "predicate_version=VALUES(predicate_version),verified_at=VALUES(verified_at)"
        ),
        params | expected,
    )
    return dict(row)
