"""素材处理授权快照只关联发起身份和该素材，不使用全租户目录水位误取消正常任务。"""

import hashlib

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError


def material_job_scope(context, asset):
    return hashlib.sha256(
        canonical(
            [
                "MATERIAL_PROCESS_V1",
                context.tenant_id,
                context.actor_id,
                context.subject_id,
                context.team_id,
                context.data_role,
                "assets.upload",
                asset["id"],
                asset["owner_user_id"],
                asset["owner_team_id"],
                asset["sha256"],
                asset["mime"],
            ]
        ).encode()
    ).hexdigest()


async def actor_auth_version(session, actor_id):
    value = (
        await session.execute(
            text("""SELECT auth_version FROM sys_identity_subject
        WHERE user_id=:actor FOR SHARE"""),
            {"actor": actor_id},
        )
    ).scalar_one_or_none()
    if value is None:
        raise OrbitError(403, "AUTHORIZATION_CHANGED", "素材任务发起身份已失效")
    return value


async def validate_job_actor(session, job):
    """先授权并锁身份，再锁素材clock，保持与交互操作一致的锁顺序。"""
    try:
        context = await require_business_access(
            session, job["actor_id"], "assets", "assets.upload", acting_subject=False
        )
        version = await actor_auth_version(session, job["actor_id"])
        asset = {**job, "id": job["asset_id"]}
        if (
            version != job["actor_auth_version"]
            or context.tenant_id != job["tenant_id"]
            or material_job_scope(context, asset) != job["scope_digest"]
        ):
            raise OrbitError(403, "AUTHORIZATION_CHANGED", "素材任务授权快照已变化")
        return True
    except OrbitError as error:
        if error.status not in {401, 403, 404}:
            raise
        return False
