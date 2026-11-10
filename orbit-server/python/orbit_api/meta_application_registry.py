"""后台Meta应用选择：应用来源固定到租户配置及版本，不猜测其他凭据。"""

import hashlib

from sqlalchemy import text

from orbit_api.errors import OrbitError
from orbit_api.meta_connection_contract import application_from_configuration
from orbit_api.meta_connection_service import access


async def load_application(session, cipher, tenant, identifier, revision=None):
    row = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant AND "
                    "id=:id FOR SHARE"
                ),
                {"tenant": tenant, "id": identifier},
            )
        )
        .mappings()
        .first()
    )
    return application_from_configuration(row, cipher, expected_revision=revision)


async def verify_application(session, cipher, tenant, app):
    if app.configuration_id is not None:
        current = await load_application(
            session, cipher, tenant, app.configuration_id, app.configuration_revision
        )
        if current.app_id != app.app_id:
            raise OrbitError(409, "META_APP_CHANGED", "应用编号已变化，请重新授权")


async def resolve_application(
    sessions,
    cipher,
    actor,
    *,
    configuration_id=None,
    connection_id=None,
    state=None,
    reauthorize=False,
):
    """回调只能从一次性state查回应用，重新授权只能使用原连接绑定的应用。"""
    async with sessions() as session, session.begin():
        current = await access(session, actor)
        revision = None
        if connection_id or state is not None:
            if state is not None:
                if not isinstance(state, str) or not 20 <= len(state) <= 256:
                    raise OrbitError(400, "META_STATE_INVALID", "授权状态无效")
                table, clause, params = (
                    "orbit_meta_authorization_session",
                    "state_digest=:digest AND actor_id=:actor",
                    {"digest": hashlib.sha256(state.encode()).digest(), "actor": actor},
                )
            else:
                table, clause, params = ("orbit_meta_connection", "id=:id", {"id": connection_id})
                if current.data_role != "SUPER_ADMIN":
                    clause += " AND actor_id=:actor"
                    params["actor"] = actor
            row = (
                (
                    await session.execute(
                        text(
                            f"SELECT * FROM {table} WHERE tenant_id=:tenant AND {clause} FOR SHARE"
                        ),
                        params | {"tenant": current.tenant_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise OrbitError(404, "NOT_FOUND", "授权来源不存在或不可见")
            configuration_id = row["app_configuration_id"]
            revision = None if reauthorize else row["app_configuration_revision"]
        if configuration_id:
            app = await load_application(session, cipher, current.tenant_id, configuration_id, revision)
        else:
            from orbit_api.meta_connection_routes import application
            app = application()
        if (connection_id or state is not None) and row["app_id"] != app.app_id:
            raise OrbitError(409, "META_APP_CHANGED", "原连接应用编号已变化，请新建连接")
        return app


async def choices(session, cipher, actor):
    current = await access(session, actor)
    rows = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant AND "
                    "section='META_APP' AND enabled=1 ORDER BY name,id LIMIT 201"
                ),
                {"tenant": current.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > 200:
        raise OrbitError(422, "META_APP_LIMIT", "应用数量超过200，请停用不使用的应用")
    result = []
    for row in rows:
        try:
            app = application_from_configuration(row, cipher)
        except OrbitError:
            continue
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "app_id": app.app_id,
                "revision": row["revision"],
            }
        )
    return result
