"""原tasks.read实时权限与冻结归属；仍归launch菜单，不创设第九菜单。"""

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.errors import OrbitError
from orbit_api.launch_access import parameters, scope_clause
from orbit_api.reference_access import managed_teams
from orbit_api.task_contract import digest


async def authorize(session, actor):
    current = await require_business_access(session, actor, "launch", "tasks.read")
    teams = await managed_teams(session, current)
    version = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            {"actor": actor},
        )
    ).scalar_one()
    if type(version) is not int or not 1 <= version <= MAX_REVISION:
        raise OrbitError(409, "SCOPE_VERSION_INVALID", "真实身份授权版本不符合原合同")
    fingerprint = digest(
        [
            actor,
            current.tenant_id,
            current.subject_id,
            current.data_role,
            current.team_id,
            sorted(teams),
            version,
        ]
    )
    return current, version, fingerprint


async def clock(session, current, *, write=False):
    row = (
        (
            await session.execute(
                text(
                    "SELECT revision,UTC_TIMESTAMP(3) reference_at FROM orbit_task_clock WHERE "
                    "tenant_id=:tenant " + ("FOR UPDATE" if write else "FOR SHARE")
                ),
                parameters(current),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise OrbitError(503, "TASK_INITIALIZATION_REQUIRED", "真实任务迁移尚未完成")
    if not 1 <= row["revision"] < MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "任务列表版本不可继续推进")
    return row


def changed():
    raise OrbitError(409, "TASK_SNAPSHOT_CHANGED", "任务版本或当前授权已变化，请刷新")


async def task(session, current, identifier):
    row = (
        (
            await session.execute(
                text(
                    "SELECT t.* FROM orbit_task t WHERE t.tenant_id=:tenant AND t.id=:id "
                    "AND t.manifest_phase='COMPLETE' AND ("
                    + scope_clause(current, "t")
                    + ") FOR SHARE OF t"
                ),
                parameters(current) | {"id": identifier},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise OrbitError(404, "NOT_FOUND", "任务不存在或不在当前冻结归属范围")
    return row
