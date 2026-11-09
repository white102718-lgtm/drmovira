"""指标查询的当前授权与原账户范围消费，不额外要求账户列表权限。

仅供持有外层事务的服务端查询调用；历史事实仍须按冻结投手/团队求交。
此处不发行事实、不解析计划、不把五百计划账户上限套到监测范围。
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import text

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams
from orbit_api.scope_visibility_verdict import verified_snapshot


@dataclass(frozen=True, repr=False)
class MetricQueryScope:
    current: BusinessContext
    auth_version: int
    auth_fingerprint: str
    managed_team_ids: tuple[str, ...]
    snapshot_id: str | None
    snapshot_hash: str | None
    member_count: int | None


async def authorize_metric_scope(session, actor_id, snapshot_id):
    """只核monitor.read；非空快照沿原actor/授权版本/完整当前范围证明。

    返回的快照信息只可用于同事务的成员JOIN和查询凭证绑定，不能代替历史事实
    的冻结归属过滤。调用方每次分页/成功幂等重放仍须重新调用本方法。
    """
    if not session.in_transaction():
        raise ValueError("指标范围消费需要调用方外层事务")
    current = await require_business_access(session, actor_id, "monitor", "monitor.read")
    managed = tuple(sorted(set(await managed_teams(session, current))))
    version = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            {"actor": actor_id},
        )
    ).scalar_one_or_none()
    if type(version) is not int or not 1 <= version <= MAX_REVISION:
        raise OrbitError(409, "SCOPE_VERSION_INVALID", "真实授权版本不符合原合同范围")
    # 与原AccountScopeStore的指纹格式完全一致，才能消费同一个不可变快照。
    fingerprint = hashlib.sha256(
        canonical(
            [
                actor_id,
                current.tenant_id,
                current.subject_id,
                current.data_role,
                current.team_id,
                list(managed),
                version,
            ]
        ).encode()
    ).hexdigest()
    snapshot = None
    if snapshot_id is not None:
        snapshot = await verified_snapshot(session, current, version, fingerprint, snapshot_id)
    return MetricQueryScope(
        current,
        version,
        fingerprint,
        managed,
        snapshot["id"] if snapshot is not None else None,
        snapshot["members_hash"] if snapshot is not None else None,
        snapshot["member_count"] if snapshot is not None else None,
    )
