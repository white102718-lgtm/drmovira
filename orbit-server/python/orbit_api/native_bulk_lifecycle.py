"""原技术用户导入/删除与业务目录的边界，不将技术用户自动创建成业务身份。"""

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError
from orbit_api.native_directory import _context


async def guard_native_bulk_lifecycle(session, operation, identifiers):
    """整批预检在任何DAO写入前完成；映射人员只能通过带业务状态/版本的ORBIT入口维护。"""
    from exceptions.exception import ServiceException

    if operation not in {"USER_DELETE", "USER_IMPORT"}:
        raise ValueError("未知原人员批量操作")
    context = await _context(session)
    if context is not None and context.data_role != "SUPER_ADMIN":
        raise OrbitError(403, "PERMISSION_DENIED", "原技术人员批量维护需要超级管理员权限")
    if operation == "USER_DELETE":
        try:
            values = sorted({int(identifier) for identifier in identifiers})
            if any(not 0 < identifier < 2**63 for identifier in values):
                raise ValueError
        except (ValueError, TypeError):
            raise ServiceException(message="用户编号无效") from None
        column = "user_id"
    else:
        if any(
            not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers
        ):
            raise ServiceException(message="导入登录名称不能为空且必须为文本")
        # 登录名是原框架标识；不使用联系方式或新增的文本规范化规则改写登录名。
        values = sorted(set(identifiers))
        column = "user_name"
    for start in range(0, len(values), 200):
        rows = (
            await session.execute(
                text(
                    "SELECT u.user_id, (EXISTS(SELECT 1 FROM orbit_user_scope s "
                    "WHERE s.user_id=u.user_id) OR EXISTS(SELECT 1 FROM orbit_business_user b "
                    "WHERE b.user_id=u.user_id)) AS business_managed "
                    "FROM sys_user u WHERE u." + column + " IN :identifiers FOR UPDATE"
                ).bindparams(bindparam("identifiers", expanding=True)),
                {"identifiers": values[start : start + 200]},
            )
        ).mappings()
        if any(row["business_managed"] for row in rows):
            raise ServiceException(
                message="业务人员请通过ORBIT人员页面编辑或停用，原技术用户导入和删除不支持业务人员"
            )
