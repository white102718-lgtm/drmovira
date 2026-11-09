"""监测动作消费原范围的真实SQL专项；没有指标事实或监测HTTP成功声明。"""

import asyncio
import re
from uuid import uuid4

METRIC_SCOPE_CASES = [
    "pythonMetricScopeOriginalHttpSnapshotHas501FrozenAccounts",
    "pythonMetricScopeMonitorOnlyConsumesWholeScopeWithoutAccountRead",
    "pythonMetricScopeNullSelectorDoesNotRequireAccountRead",
    "pythonMetricScopeForeignActorCannotBorrowSnapshot",
    "pythonMetricScopeMonitorRevocationBlocksExistingPositiveProof",
    "pythonMetricScopeEmptyFrozenSelectionIsNotUnrestricted",
    "pythonMetricScopeOneLostAccountRejectsWholeScope",
]


def run_metric_scope_checks(client, admin, headers, password, cache, database, cases):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database or "") is None
    ):
        raise ValueError("监测范围专项仅允许13306本轮UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
    admin.commit()
    from account_scope_visibility_plan_checks import prepare_plan_identities
    from config.asyncmy_compat import install_windows_asyncmy_compat
    from sqlalchemy import URL
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from orbit_api.errors import OrbitError
    from orbit_api.metrics_scope_access import authorize_metric_scope

    install_windows_asyncmy_compat()
    identities = prepare_plan_identities(client, admin, headers, password, cache)
    user, manager = identities["USER"], identities["TEAM_ADMIN"]

    def sql(statement, values=(), *, fetch=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if fetch else cursor.rowcount
        admin.commit()
        return result

    def checked(response, expected):
        assert response.status_code == expected, {
            "expected": expected,
            "actual": response.status_code,
        }
        return response.json()

    tenant, root_owner = sql(
        "SELECT tenant_id,id FROM orbit_business_user WHERE user_id=1", fetch=True
    )[0]
    capabilities = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "监测范围-" + uuid4().hex[:12],
                "menu_codes": ["monitor"],
                "permission_codes": ["monitor.read"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        fetch=True,
    )[0][0]
    for identity in (user, manager):
        sql(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (identity["actor_id"], native_role),
        )
    account_ids = sorted(str(uuid4()) for _ in range(501))
    # 明确SQL账户技术样本，不冒充平台导入/授权成功。
    admin.begin()
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s FOR UPDATE", (tenant,)
            )
            cursor.fetchone()
            cursor.executemany(
                "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
                "value_json,details_json,bound_at,created_at) VALUES(%s,%s,%s,'监测范围SQL样本',"
                "'监测范围SQL样本',%s,%s,'USD','UTC','UNKNOWN','UNKNOWN','{}','{}',"
                "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                [
                    (
                        tenant,
                        identifier,
                        str(8800000 + index),
                        user["owner_user_id"],
                        user["owner_team_id"],
                    )
                    for index, identifier in enumerate(account_ids)
                ],
            )
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
    except BaseException:
        admin.rollback()
        raise

    def create(selected):
        cap = checked(
            client.get("/api/v1/scope-snapshots/capabilities", headers=user["headers"]), 200
        )
        body = {"mode": "IDS", "account_ids": selected, "filter": None}
        if not selected:
            # 原IDS必须非空；用明确无匹配的原FILTER冻结零账户。
            body = {
                "mode": "FILTER",
                "account_ids": [],
                "filter": {
                    "q": "不存在的监测范围-" + uuid4().hex,
                    "status": None,
                    "auth_status": None,
                    "operator_user_id": None,
                    "vendor_id": None,
                },
            }
        return checked(
            client.post(
                "/api/v1/scope-snapshots",
                headers=user["headers"]
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json=body,
            ),
            201,
        )

    selected, empty = create(account_ids), create([])
    assert selected["count"] == 501 and empty["count"] == 0
    cases.append(METRIC_SCOPE_CASES[0])
    account_grants = sql(
        "SELECT rm.role_id,rm.menu_id FROM sys_role_menu rm JOIN sys_user_role ur "
        "ON ur.role_id=rm.role_id WHERE ur.user_id=%s AND rm.menu_id=31011",
        (user["actor_id"],),
        fetch=True,
    )
    assert account_grants
    for role_id, menu in account_grants:
        sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s", (role_id, menu))

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username="root",
                password="",
                host="127.0.0.1",
                port=13306,
                database=database,
            ),
            echo=False,
            hide_parameters=True,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def consume(identifier, actor=None):
            async with sessions() as session, session.begin():
                return await authorize_metric_scope(session, actor or user["actor_id"], identifier)

        async def denied(identifier, status, code, *, actor=None):
            try:
                await consume(identifier, actor)
            except OrbitError as error:
                assert (error.status, error.code) == (status, code), {
                    "actual_status": error.status,
                    "actual_code": error.code,
                }
            else:
                raise AssertionError("预期整个监测范围消费明确拒绝")

        try:
            checked(
                client.get("/api/v1/scope-snapshots/capabilities", headers=user["headers"]), 403
            )
            complete = await consume(selected["id"])
            assert complete.member_count == 501 and complete.snapshot_hash == selected["hash"]
            assert complete.current.actor_id == user["actor_id"]
            cases.append(METRIC_SCOPE_CASES[1])
            unrestricted = await consume(None)
            assert unrestricted.snapshot_id is unrestricted.member_count is None
            cases.append(METRIC_SCOPE_CASES[2])
            await denied(selected["id"], 404, "NOT_FOUND", actor=manager["actor_id"])
            await denied(str(uuid4()), 404, "NOT_FOUND")
            cases.append(METRIC_SCOPE_CASES[3])
            sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31031", (native_role,))
            try:
                await denied(selected["id"], 403, "PERMISSION_DENIED")
            finally:
                sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31031)", (native_role,))
            cases.append(METRIC_SCOPE_CASES[4])
            zero = await consume(empty["id"])
            assert zero.member_count == 0 and zero.snapshot_id == empty["id"]
            cases.append(METRIC_SCOPE_CASES[5])
            sql(
                "UPDATE orbit_ad_account SET owner_user_id=%s,revision=revision+1 "
                "WHERE tenant_id=%s AND id=%s",
                (root_owner, tenant, account_ids[0]),
            )
            sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
            try:
                await denied(selected["id"], 409, "SCOPE_CHANGED")
            finally:
                sql(
                    "UPDATE orbit_ad_account SET owner_user_id=%s,revision=revision+1 "
                    "WHERE tenant_id=%s AND id=%s",
                    (user["owner_user_id"], tenant, account_ids[0]),
                )
                sql(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
            cases.append(METRIC_SCOPE_CASES[6])
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    finally:
        for grant in account_grants:
            sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", grant)
    return {"cases": 7, "selected_accounts": 501, "metrics_http_or_fact_publication": False}
