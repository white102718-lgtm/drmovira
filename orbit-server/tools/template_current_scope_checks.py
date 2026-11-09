"""真实RR旧视图后的模板范围撤回专项；仅主线UUID库，不启动服务。

3组直接调用真实Store/真实MySQL事务；HTTP只用于真实角色/模板准备。
不是HTTP在途竞态或完整原生认证验收，不修改任何旧断言或生产源码。
"""

import asyncio
import re
from uuid import uuid4

TEMPLATE_CURRENT_SCOPE_CASES = [
    "pythonTemplateCurrentManagerRevokedAfterRepeatableReadView",
    "pythonTemplateCurrentRecipientRevokedAfterRepeatableReadView",
    "pythonTemplateCurrentRecipientListIgnoresOldRepeatableReadView",
]


def guard_template_scope_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("模板范围专项仅允许13306本轮UUID测试库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际测试库与本轮UUID不一致")
    admin.commit()


def assert_current_scope_denied(error):
    assert (error.status, error.code) == (404, "NOT_FOUND"), {
        "actual_status": error.status,
        "actual_code": error.code,
    }


def run_template_current_scope_checks(client, admin, headers, password, cache, database, cases):
    guard_template_scope_target(admin, database)
    from sqlalchemy import URL, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    try:
        from account_scope_visibility_plan_checks import prepare_plan_identities
    except ImportError:
        from tools.account_scope_visibility_plan_checks import prepare_plan_identities

    from orbit_api.authorization import BusinessContext
    from orbit_api.errors import OrbitError
    from orbit_api.template_store import TemplateStore, recipient_sets

    identities = prepare_plan_identities(client, admin, headers, password, cache)
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    admin.commit()

    def checked(response, status):
        assert response.status_code == status, {
            "actual": response.status_code,
            "expected": status,
            "code": response.json().get("code"),
        }
        return response.json()

    # helper原账户read身份不扩展原角色；新角色通过真实API另授模板read。
    caps = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "模板当前范围" + uuid4().hex[:12],
                "menu_codes": ["launch"],
                "permission_codes": ["templates.read"],
            },
        ),
        201,
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role["id"]),
        )
        native_role = cursor.fetchone()[0]
        for key in ("TEAM_ADMIN", "USER"):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (identities[key]["actor_id"], native_role),
            )
    admin.commit()
    for key in ("TEAM_ADMIN", "USER"):
        checked(
            client.get("/api/v1/templates/capabilities", headers=identities[key]["headers"]), 200
        )

    user = identities["USER"]
    manager = identities["TEAM_ADMIN"]

    def template(visibility, recipients):
        cap = checked(client.get("/api/v1/templates/capabilities", headers=headers), 200)
        return checked(
            client.post(
                "/api/v1/templates",
                headers=headers
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={
                    "name": "RR范围" + uuid4().hex,
                    "description": "真实旧视图撤回专项",
                    "visibility": visibility,
                    "recipient_user_ids": recipients,
                    "campaigns": [{"local_id": str(uuid4()), "copies": 1, "adsets": []}],
                },
            ),
            201,
        )["id"]

    private = template("PRIVATE", [])
    shared = template("TEAM", [user["owner_user_id"]])

    def context(key):
        return BusinessContext(
            identities[key]["actor_id"],
            tenant,
            key,
            identities[key]["owner_user_id"],
            identities[key]["owner_team_id"],
        )

    def sql(statement, values):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                changed = cursor.rowcount
            admin.commit()
            return changed
        except BaseException:
            admin.rollback()
            raise

    def restore_manager():
        sql(
            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id,enabled) "
            "VALUES(%s,%s,%s,1) ON DUPLICATE KEY UPDATE enabled=1",
            (tenant, manager["actor_id"], manager["owner_team_id"]),
        )

    def restore_recipient():
        sql(
            "INSERT IGNORE INTO orbit_launch_template_recipient(tenant_id,template_id,user_id) "
            "VALUES(%s,%s,%s)",
            (tenant, shared, user["owner_user_id"]),
        )

    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decode(admin.user),
        password=decode(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def run():
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = TemplateStore(None)

        async def establish_old_view(session):
            await session.execute(text("SET SESSION innodb_lock_wait_timeout=3"))
            # 与successful_replay同类的真实普通SELECT；明确先读实际表而非SELECT常量。
            isolation = (await session.execute(text("SELECT @@transaction_isolation"))).scalar_one()
            assert isolation == "REPEATABLE-READ"
            values = {
                "tenant": tenant,
                "manager": manager["actor_id"],
                "team": manager["owner_team_id"],
                "template": shared,
                "recipient": user["owner_user_id"],
            }
            managed = (
                await session.execute(
                    text(
                        "SELECT enabled FROM orbit_business_team_manager WHERE tenant_id=:tenant "
                        "AND manager_user_id=:manager AND team_id=:team"
                    ),
                    values,
                )
            ).scalar_one()
            recipient = (
                await session.execute(
                    text(
                        "SELECT user_id FROM orbit_launch_template_recipient "
                        "WHERE tenant_id=:tenant "
                        "AND template_id=:template AND user_id=:recipient"
                    ),
                    values,
                )
            ).scalar_one()
            assert managed == 1 and recipient == user["owner_user_id"]

        async def require_denied(session, current, template_id):
            try:
                await store.row(session, current, template_id)
            except OrbitError as error:
                assert_current_scope_denied(error)
            else:
                raise AssertionError("当前范围已撤回，旧RR视图不得继续返回模板")

        try:
            async with sessions() as session, session.begin():
                await establish_old_view(session)
                try:
                    assert (
                        sql(
                            "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s "
                            "AND manager_user_id=%s AND team_id=%s",
                            (tenant, manager["actor_id"], manager["owner_team_id"]),
                        )
                        == 1
                    )
                    await require_denied(session, context("TEAM_ADMIN"), private)
                finally:
                    # 先退出SQL读取事务再恢复，避免新版guard持有gap锁时自等。
                    await session.rollback()
                    restore_manager()
            cases.append(TEMPLATE_CURRENT_SCOPE_CASES[0])

            async with sessions() as session, session.begin():
                await establish_old_view(session)
                try:
                    assert (
                        sql(
                            "DELETE FROM orbit_launch_template_recipient WHERE tenant_id=%s "
                            "AND template_id=%s AND user_id=%s",
                            (tenant, shared, user["owner_user_id"]),
                        )
                        == 1
                    )
                    await require_denied(session, context("USER"), shared)
                finally:
                    await session.rollback()
                    restore_recipient()
            cases.append(TEMPLATE_CURRENT_SCOPE_CASES[1])

            async with sessions() as session, session.begin():
                await establish_old_view(session)
                try:
                    assert (
                        sql(
                            "DELETE FROM orbit_launch_template_recipient WHERE tenant_id=%s "
                            "AND template_id=%s AND user_id=%s",
                            (tenant, shared, user["owner_user_id"]),
                        )
                        == 1
                    )
                    values = await recipient_sets(session, context("USER"), [shared])
                    assert values == {shared: []}, "当前成员列表不得返回已撤回的旧快照成员"
                finally:
                    await session.rollback()
                    restore_recipient()
            cases.append(TEMPLATE_CURRENT_SCOPE_CASES[2])
        finally:
            await engine.dispose()

    asyncio.run(run())
    return {"scope": "REAL_MYSQL_RR_STORE_NOT_HTTP_INFLIGHT", "platform_requests": 0}
