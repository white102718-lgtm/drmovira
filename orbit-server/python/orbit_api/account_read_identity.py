"""账户只读列表/详情专属原认证短会话；不结束其它依赖的共享事务。"""

from typing import Annotated

from config.database import DataSourceRegistry
from fastapi import Depends, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService, oauth2_scheme


async def account_read_identity(
    request: Request, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> CurrentUserModel | None:
    """完整调用原认证，原DTO全部构造后先退出自有session再交给只读业务。

    不复制user_id、不重建/序列化CurrentUserModel，也不触碰注入共享session。
    原生token前后校验、策略、Cookie及认证排除规则均由原入口处理。
    """
    async with DataSourceRegistry.session(log_sql=False) as owned_session:
        current = await LoginService.get_current_user(request, token, owned_session)
        # 原服务已把user/dept/role物化为Pydantic DTO；保留exclude/private及同对象语义。
    return current
