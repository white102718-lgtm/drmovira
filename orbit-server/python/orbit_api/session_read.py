"""当前会话只读取本人及本地有效角色并集，不要求系统人员管理权限。"""

from sqlalchemy import text

from orbit_api.cookie_identity import ensure_cookie_current
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _REGISTRY
from orbit_api.user_store import _COLUMNS, _FROM, UserStore


async def session_payload(session, identity):
    await ensure_cookie_current(session, identity.actor_id)
    row = (
        (
            await session.execute(
                text(
                    "SELECT " + _COLUMNS + _FROM + " WHERE b.user_id=:actor "
                    "AND b.tenant_id=:tenant FOR SHARE"
                ),
                {"actor": identity.actor_id, "tenant": identity.tenant_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise OrbitError(401, "SESSION_REQUIRED", "当前人员映射已失效")
    user = (await UserStore(None)._public(session, identity.tenant_id, [row]))[0]
    grants = {"menus": set(), "permissions": set()}
    for kind, table, column in (
        ("menus", "orbit_business_role_menu", "menu_code"),
        ("permissions", "orbit_business_role_action", "permission_code"),
    ):
        codes = (
            (
                await session.execute(
                    text(f"""SELECT grant_row.{column}
                    FROM sys_user_role ur
                    JOIN sys_role r ON r.role_id=ur.role_id AND r.status='0' AND r.del_flag='0'
                    JOIN orbit_business_role br ON br.native_role_id=r.role_id
                        AND br.tenant_id=:tenant
                    JOIN {table} grant_row ON grant_row.role_id=br.id
                        AND grant_row.tenant_id=br.tenant_id
                    WHERE ur.user_id=:actor FOR SHARE"""),
                    {"tenant": identity.tenant_id, "actor": identity.actor_id},
                )
            )
            .scalars()
            .all()
        )
        if not set(codes).issubset(set(_REGISTRY[kind])):
            raise OrbitError(409, "DIRECTORY_MAPPING_REQUIRED", "当前角色包含未登记的业务授权")
        grants[kind].update(codes)
    clock = (
        await session.execute(
            text("SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"),
            {"tenant": identity.tenant_id},
        )
    ).scalar_one()
    return {
        "user": user,
        "scope_version": clock,
        "menu_codes": sorted(grants["menus"]),
        "permission_codes": sorted(grants["permissions"]),
        "csrf_token": identity.csrf_token,
        "expires_at": identity.expires_at.isoformat(timespec="milliseconds") + "Z",
    }
