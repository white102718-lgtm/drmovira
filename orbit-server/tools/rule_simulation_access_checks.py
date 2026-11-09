"""有界模拟授权真实专项：原HTTP建图+直接facade，无模拟/source发行。

仅root串行本轮13306 UUID库；不加载env/启动服务/修改sealed版本。
"""

import asyncio
import hashlib
import re
from dataclasses import replace
from uuid import uuid4

RULE_SIMULATION_ACCESS_CASES = (
    "pythonRuleSimulationAccessOnlyRulesReadNativeAndOriginalThousandOneScope",
    "pythonRuleSimulationAccessTwoBatchBoundsCompleteRootAndCurrentMetadata",
    "pythonRuleSimulationAccessActualNotNullRejectionAndInvalidTimezoneNoDefault",
    "pythonRuleSimulationAccessEarlyStopCancelReplacementAndTransactionIsolation",
    "pythonRuleSimulationAccessRenameAndAccountRevisionKeepOriginalIdentityRoot",
    "pythonRuleSimulationAccessCurrentReadRevokedAndBothOwnerScopesReject",
    "pythonRuleSimulationAccessLegalRuleUpdateAndOldRepeatableReadCurrentCas",
    "pythonRuleSimulationAccessExactFrozenProfileVersionNeverSilentlyRebound",
)
NATIVE_ACTOR = 990670


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) is None
    ):
        raise ValueError("SIM_ACCESS_ISOLATED_UUID_REQUIRED")


def engine_url(admin, database):
    guard_target(admin, database)
    from sqlalchemy import URL

    def value(name):
        raw = getattr(admin, name)
        if type(raw) is bytes:
            return raw.decode("utf-8")
        if type(raw) is not str:
            raise ValueError("SIM_ACCESS_CONNECTION_VALUE_INVALID")
        return raw

    return URL.create(
        "mysql+asyncmy",
        host="127.0.0.1",
        port=13306,
        database=database,
        username=value("user"),
        password=value("password"),
    )


def run_rule_simulation_access_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import TABLES, definition_body
        from .rule_editor_checks import checked
    else:
        from fixture_login import fixture_login
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import TABLES, definition_body
        from rule_editor_checks import checked
    import pymysql
    from config.asyncmy_compat import install_windows_asyncmy_compat
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from orbit_api.directory_tokens import canonical
    from orbit_api.errors import OrbitError
    from orbit_api.rule_simulation_access import RuleSimulationAccessFacade

    def sql(statement, values=(), *, rows=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                answer = cursor.fetchall() if rows else cursor.rowcount
            admin.commit()
            return answer
        except BaseException:
            admin.rollback()
            raise

    if sql("SELECT DATABASE()", rows=True) != ((database,),):
        raise ValueError("SIM_ACCESS_ACTUAL_DATABASE_REQUIRED")
    tenant, root_owner, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", rows=True
    )[0]
    assert (
        sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (NATIVE_ACTOR,), rows=True)[0][0] == 0
    )
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "模拟只读-" + uuid4().hex[:9],
                "menu_codes": ["rules"],
                "permission_codes": ["rules.read"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        rows=True,
    )[0][0]
    owner, username = str(uuid4()), "simacc_" + uuid4().hex[:10]
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
        "SELECT %s,%s,'模拟范围只读',%s,password,'0','0' FROM sys_user WHERE user_id=1",
        (NATIVE_ACTOR, username, username + "@fixture.example.org"),
    )
    sql(
        "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
        "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
        (NATIVE_ACTOR, str(uuid4())),
    )
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (NATIVE_ACTOR, native_role))
    sql(
        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
        (NATIVE_ACTOR, tenant),
    )
    sql(
        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,invited,"
        "created_at) "
        "VALUES(%s,%s,%s,%s,'模拟只读',0,UTC_TIMESTAMP(3))",
        (tenant, owner, NATIVE_ACTOR, team),
    )
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    login = checked(fixture_login(client, cache, {"username": username, "password": password}))
    user_headers = {"Authorization": "Bearer " + login["token"]}
    response = client.get("/getInfo", headers=user_headers)
    assert response.status_code == 200
    permissions = response.json()["permissions"]
    assert "rules.read" in permissions and "*:*:*" not in permissions
    assert not any(
        permission.startswith(("accounts.", "monitor.", "launch.", "system.users"))
        for permission in permissions
    )
    assert not any(
        permission in permissions for permission in ("rules.create", "rules.edit", "rules.enable")
    )
    identifiers = sorted(str(uuid4()) for _ in range(1001))
    expected = {}
    records = []
    for index, identifier in enumerate(identifiers):
        currency = "USD" if index % 2 == 0 else "EUR"
        timezone = "America/New_York" if index % 2 == 0 else "Asia/Shanghai"
        expected[identifier] = (currency, timezone)
        records.append(
            (tenant, identifier, "000" + str(uuid4().int), owner, team, currency, timezone)
        )
    admin.begin()
    try:
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                "owner_user_id,owner_team_id,currency,timezone_id,auth_status,"
                "account_status,value_json,details_json,bound_at,created_at) "
                "VALUES(%s,%s,%s,'SIM_ACCESS_SQL_ONLY','SIM_ACCESS_SQL_ONLY',%s,%s,%s,%s,"
                "'UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                records,
            )
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
    except BaseException:
        admin.rollback()
        raise
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=964)
    cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": identifiers, "filter": None},
        ),
        201,
    )
    body = definition_body("模拟授权-" + uuid4().hex[:10], owner, team, scope["id"], profile["id"])
    cap = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"})
    )
    rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=body,
        ),
        201,
    )
    assert scope["count"] == 1001 and rule["revision"] == 1
    cases.append(RULE_SIMULATION_ACCESS_CASES[0])

    def snapshot():
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", rows=True) for table in TABLES)

    async def run():
        install_windows_asyncmy_compat()
        engine = create_async_engine(
            engine_url(admin, database),
            echo=False,
            hide_parameters=True,
            pool_size=2,
            max_overflow=0,
        )
        facade = RuleSimulationAccessFacade()

        async def read(actor=NATIVE_ACTOR, *, size=200, expected_revision=None):
            async with AsyncSession(engine) as session, session.begin():
                ticket = await facade.open(
                    session, actor, rule["id"], expected_revision or rule["revision"]
                )
                values = []
                async for batch in facade.iter_account_batches(session, ticket, batch_size=size):
                    facade.assert_batch(session, ticket, batch)
                    values.extend(batch.accounts)
                summary = await facade.finish(session, ticket)
                facade.assert_summary(session, ticket, summary)
                return values, summary

        async def rejected(actor, code, *, revision=None):
            try:
                await read(actor, expected_revision=revision)
            except OrbitError as error:
                assert (error.status, error.code) == (
                    403 if code == "PERMISSION_DENIED" else 409,
                    code,
                )
            else:
                raise AssertionError("SIM_ACCESS_EXPECTED_CURRENT_REJECTION")

        try:
            async with engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT DATABASE()"))
                ).scalar_one() == database
            before = snapshot()
            root_hash = hashlib.sha256(canonical(identifiers).encode()).hexdigest()
            for size in (200, 1000):
                values, summary = await read(size=size)
                assert [value.account_id for value in values] == identifiers
                assert summary.count == 1001 and summary.member_hash == root_hash
                assert summary.timezone_invalid_count == summary.currency_unknown_count == 0
                assert [(value.currency, value.timezone_name) for value in values] == [
                    expected[id] for id in identifiers
                ]
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[1])

            # 原账户列NOT NULL：不伪造实际NULL分支/不改schema或SQL mode。
            for field in ("currency", "timezone_id"):
                original = sql(
                    "SELECT currency,timezone_id FROM orbit_ad_account WHERE tenant_id=%s "
                    "AND id=%s",
                    (tenant, identifiers[0]),
                    rows=True,
                )
                admin.begin()
                try:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_ad_account SET "
                            + field
                            + "=NULL WHERE tenant_id=%s AND id=%s",
                            (tenant, identifiers[0]),
                        )
                except pymysql.MySQLError as error:
                    assert error.args[0] == 1048
                else:
                    raise AssertionError("SIM_ACCESS_EXPECTED_NOT_NULL_1048")
                finally:
                    admin.rollback()
                assert (
                    sql(
                        "SELECT currency,timezone_id FROM orbit_ad_account WHERE "
                        "tenant_id=%s AND id=%s",
                        (tenant, identifiers[0]),
                        rows=True,
                    )
                    == original
                )
            original_timezone = expected[identifiers[0]][1]
            sql(
                "UPDATE orbit_ad_account SET timezone_id='not/a-zone' WHERE tenant_id=%s AND id=%s",
                (tenant, identifiers[0]),
            )
            try:
                values, summary = await read()
                assert (
                    values[0].timezone_name == "not/a-zone"
                    and values[0].timezone_error == "TIMEZONE_INVALID"
                )
                assert summary.timezone_invalid_count == 1
            finally:
                sql(
                    "UPDATE orbit_ad_account SET timezone_id=%s WHERE tenant_id=%s AND id=%s",
                    (original_timezone, tenant, identifiers[0]),
                )
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[2])

            async with AsyncSession(engine) as session:
                async with session.begin():
                    ticket = await facade.open(session, NATIVE_ACTOR, rule["id"], rule["revision"])
                    stream = facade.iter_account_batches(session, ticket)
                    batch = await anext(stream)
                    for operation in (
                        lambda: facade.assert_batch(session, ticket, replace(batch, accounts=())),
                    ):
                        try:
                            operation()
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("SIM_ACCESS_FORGED_BATCH_ACCEPTED")
                    try:
                        await facade.finish(session, ticket)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("SIM_ACCESS_EARLY_FINISH_ACCEPTED")
                    async with AsyncSession(engine) as other, other.begin():
                        try:
                            await anext(facade.iter_account_batches(other, ticket))
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("SIM_ACCESS_FOREIGN_SESSION_ACCEPTED")
                    try:
                        await anext(facade.iter_account_batches(session, ticket))
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("SIM_ACCESS_REPEATED_STREAM_ACCEPTED")
                    # 取消实际generator（不声称阻塞SQL/server连接取消专项）。
                    try:
                        await stream.athrow(asyncio.CancelledError())
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("SIM_ACCESS_CANCELLATION_SWALLOWED")
                    try:
                        await facade.finish(session, ticket)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("SIM_ACCESS_CANCELLED_FINISH_ACCEPTED")
                async with session.begin():
                    try:
                        await anext(facade.iter_account_batches(session, ticket))
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("SIM_ACCESS_OLD_TRANSACTION_ACCEPTED")
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[3])

            sql(
                "UPDATE orbit_ad_account SET name='普通改名',name_prefix='普通改名',"
                "revision=revision+1 WHERE tenant_id=%s AND id=%s",
                (tenant, identifiers[0]),
            )
            values, summary = await read()
            assert values[0].revision == 2 and summary.member_hash == root_hash
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[4])

            sql(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                (NATIVE_ACTOR, native_role),
            )
            try:
                await rejected(NATIVE_ACTOR, "PERMISSION_DENIED")
            finally:
                sql(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                    (NATIVE_ACTOR, native_role),
                )
            sql(
                "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                (root_owner, tenant, identifiers[-1]),
            )
            try:
                # root caller可读，但Rule owner USER不再能读最后成员；不能只核调用者。
                await rejected(1, "RULE_ACCOUNT_SCOPE_CHANGED")
                await rejected(NATIVE_ACTOR, "RULE_ACCOUNT_SCOPE_CHANGED")
            finally:
                sql(
                    "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                    (owner, tenant, identifiers[-1]),
                )
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[5])

            async with AsyncSession(engine) as session, session.begin():
                # 建立旧RR快照但不先持Rule SHARE，允许另真实HTTP合法完成更新。
                old = (
                    await session.execute(
                        text(
                            "SELECT revision FROM orbit_rule_head WHERE tenant_id=:tenant "
                            "AND id=:id"
                        ),
                        {"tenant": tenant, "id": rule["id"]},
                    )
                ).scalar_one()
                assert old == 1
                updated_body = {**body, "name": body["name"] + "-合法更新"}
                update_cap = checked(
                    client.get(
                        "/api/v1/rules/capabilities", headers=headers, params={"action": "UPDATE"}
                    )
                )
                updated = checked(
                    await asyncio.to_thread(
                        client.put,
                        "/api/v1/rules/" + rule["id"],
                        headers=headers
                        | {
                            "X-CSRF-Token": update_cap["csrf_token"],
                            "Idempotency-Key": str(uuid4()),
                            "If-Match": '"1"',
                        },
                        json=updated_body,
                    )
                )
                assert updated["revision"] == 2
                try:
                    await facade.open(session, NATIVE_ACTOR, rule["id"], 1)
                except OrbitError as error:
                    assert (error.status, error.code) == (409, "RULE_SOURCE_CHANGED")
                else:
                    raise AssertionError("SIM_ACCESS_OLD_RR_HEAD_ACCEPTED")
            rule.update(updated)
            before = snapshot()
            await rejected(NATIVE_ACTOR, "REVISION_CONFLICT", revision=1)
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[6])

            seed_metric_reference_profile(
                admin, database, tenant, index=965, identifier=profile["id"]
            )
            await rejected(NATIVE_ACTOR, "METRIC_PROFILE_VERSION_CHANGED")
            assert snapshot() == before
            cases.append(RULE_SIMULATION_ACCESS_CASES[7])
        finally:
            await engine.dispose()

    asyncio.run(run())
    return {
        "account_count": 1001,
        "batch_sizes": [200, 1000],
        "technical_fixture_only": True,
        "source_issuer_verified": False,
        "simulation_http_called": False,
        "null_branch_sql_reachable": False,
        "blocked_server_cancel_verified": False,
        "locked_concurrent_rule_write_verified": False,
    }
