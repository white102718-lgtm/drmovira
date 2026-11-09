"""业务角色与原若依菜单的有限桥接；只编译已实现模块，不创建未实现页面。"""

from sqlalchemy import bindparam, text

SYSTEM_LEAVES = {
    "system.integrations.manage": 31081,
    "system.teams.manage": 31083,
    "system.roles.manage": 31084,
    "system.users.manage": 31082,
    "system.release.manage": 31086,
    "system.kill_switch": 31087,
    "system.audit.read": 31088,
    "system.dictionaries.manage": 31089,
    "system.read": 31090,
}

# 稳定编号由公共迁移统一注册；角色只编译本项目明确实现的菜单和动作。
BUSINESS_MENUS = {
    "rules": (
        31040,
        "",  # 062目录只负责导航，真实读取仍必须单独拥有31041动作。
        {
            "rules.read": 31041,
            "rules.create": 31042,
            "rules.edit": 31043,
            "rules.enable": 31044,
            "rules.pause": 31045,
            "rules.archive": 31046,
        },
    ),
    "monitor": (31030, "monitor.read", {"monitor.read": 31031}),
    "launch": (
        31020,
        "launch.read",
        {
            "launch.read": 31021,
            "launch.create": 31022,
            "launch.edit": 31023,
            "launch.execute": 31024,
            "launch.publish": 31025,
            "templates.read": 310201,
            "templates.create": 310202,
            "templates.edit": 310203,
            "templates.share": 310204,
            "templates.archive": 310205,
            "tasks.read": 310206,
        },
    ),
    "accounts": (
        31010,
        "accounts.read",
        {
            "accounts.read": 31011,
            "accounts.import": 31012,
            "accounts.assign": 31013,
            "accounts.sync": 31014,
            "accounts.unbind": 31015,
        },
    ),
    "assets": (
        31050,
        "",  # 065导航不授予素材读取；标签动作独立授权。
        {
            "assets.read": 31051,
            "assets.upload": 31052,
            "assets.edit": 31053,
            "assets.delete": 31054,
            "tags.read": 31055,
            "tags.create": 31056,
            "tags.edit": 31057,
            "tags.archive": 31058,
        },
    ),
    "environments": (
        31060,
        "",  # 设备目录仅导航；管理另核SUPER_ADMIN和精确动作。
        {
            "environments.read": 31061,
            "environments.enroll": 31062,
            "environments.revoke": 31063,
            "environments.probe": 31064,
        },
    ),
    "channels": (
        31070,
        "channels.read",
        {
            "channels.read": 31071,
            "channels.create": 31072,
            "channels.edit": 31073,
            "channels.assign": 31074,
            "channels.archive": 31075,
        },
    ),
}


def compiled_menu_ids(menu_codes, permission_codes):
    ids = {31000} if menu_codes else set()
    if "rules" in menu_codes:
        # 062实际父页入口与原六动作分开；仅有菜单不授予读取或创建编辑动作。
        ids.add(31047)
    if "monitor" in menu_codes and "monitor.read" in permission_codes:
        ids.update({310301, 310302})
    if "accounts.read" in permission_codes:
        # 隐藏账户范围二级页复用原读取动作；不增加第九个可见一级业务菜单。
        ids.add(31016)
    if "system" in menu_codes:
        ids.add(31080)
    ids.update(SYSTEM_LEAVES[code] for code in permission_codes if code in SYSTEM_LEAVES)
    for menu_code, (parent, _, actions) in BUSINESS_MENUS.items():
        if menu_code in menu_codes:
            ids.add(parent)
        ids.update(actions[code] for code in permission_codes if code in actions)
    return sorted(ids)


async def reject_native_business_role_mutation(session, role_ids):
    """定义维护走受控业务事务；原若依角色列表/其他原角色功能保留，防止双来源漂移。"""
    from exceptions.exception import ServiceException

    found = (
        await session.execute(
            text("""
        SELECT native_role_id FROM orbit_business_role WHERE native_role_id IN :ids FOR SHARE
    """).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(role_ids)},
        )
    ).first()
    if found:
        raise ServiceException(
            message="ORBIT业务角色请通过ORBIT功能角色入口维护，内置角色只允许复制"
        )
