"""原身份资源GET，独立router由主线统一注册，无浏览器写入口。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from sqlalchemy import text

from orbit_api.account_identities_store import AccountIdentitiesStore, identifier, unavailable
from orbit_api.configuration_routes import _read_boundary

router = APIRouter(prefix="/api/v1/accounts", tags=["ORBIT账户身份资源"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


async def read_authoritative_identity(session, actor_id, account_id):
    """原GET只返回完整来源证明；旧分阶段库缺053时明确未就绪，不返回裸verified行。"""
    account_id = identifier(account_id, "/id")
    tables = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME IN('orbit_identity_capability_release',"
                "'orbit_identity_publication_provenance','orbit_identity_publication_ledger')"
            )
        )
    ).scalar_one()
    if tables != 3:
        # 先保留原动作/当前对象范围的403/404，迁移未就绪不能绕过权限或假称同步成功。
        await AccountIdentitiesStore().account(session, actor_id, account_id)
        unavailable("ACCOUNT_IDENTITY_PROVENANCE_UNAVAILABLE")
    # 新领域按来源→clock→当前账户顺序锁读；不能先调用旧get再补来源锁。
    from orbit_api.identity_publication_readmodel import IdentityPublicationReadmodel

    return await IdentityPublicationReadmodel().get(session, actor_id, account_id)


@router.get("/{account_id}/identities")
async def account_identities(account_id: str, request: Request, user: User):
    _read_boundary(request, set())
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await read_authoritative_identity(session, user.user.user_id, account_id)
