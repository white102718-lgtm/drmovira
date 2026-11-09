"""环境关联可见性以当前账户为准，登记的历史owner不授予范围。"""

from sqlalchemy import text

from orbit_api.account_access import parameters, visible_clause
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams


async def query_rows(session, statement, values):
    return (await session.execute(text(statement), values)).mappings().all()


async def fingerprint(session, current, revision, size):
    import hashlib

    teams = await managed_teams(session, current)
    version = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            parameters(current),
        )
    ).scalar_one()
    directory = (
        await session.execute(
            text("SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"),
            parameters(current),
        )
    ).scalar_one()
    account = (
        await session.execute(
            text("SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant FOR SHARE"),
            parameters(current),
        )
    ).scalar_one()
    return hashlib.sha256(
        canonical(
            [
                current.tenant_id,
                current.actor_id,
                current.subject_id,
                current.data_role,
                current.team_id,
                sorted(teams),
                version,
                directory,
                account,
                revision,
                size,
            ]
        ).encode()
    ).hexdigest()


def visible(current):
    if current.data_role == "SUPER_ADMIN":
        return "b.unbound_at IS NULL"
    return (
        "b.unbound_at IS NULL AND a.unbound_at IS NULL AND g.state<>'REVOKED' "
        "AND b.owner_user_id=a.owner_user_id AND b.owner_team_id=a.owner_team_id "
        "AND ("
        # 外层FOR SHARE OF b,a,g不令子查询成为当前读；撤销管理范围不能沿旧RR快照保留。
        + visible_clause(current, "a").replace("AND tm.enabled=1)", "AND tm.enabled=1 FOR SHARE)")
        + ")"
    )


def cas(row, expected):
    if row["revision"] != expected:
        raise OrbitError(409, "REVISION_CONFLICT", "关联已变化，请重新读取")
    if expected >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "关联版本已达上限")
