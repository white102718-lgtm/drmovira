"""日历预期真实专项；无指标发行/实体清单/READY，不自行启动数据库。"""

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

if __package__:
    from .rule_simulation_access_checks import engine_url, guard_target
else:
    from rule_simulation_access_checks import engine_url, guard_target

RULE_SIMULATION_CALENDAR_CASES = (
    "pythonRuleCalendarOriginalReadOnlyUserThousandOneAccountsAndFourWindows",
    "pythonRuleCalendarActualSqlUtcOnceFourIanaWindowsAndTwoBatchBounds",
    "pythonRuleCalendarActualUnresolvedTimezoneKeepsEveryAccount",
    "pythonRuleCalendarOriginalNotNull1048DoesNotCreateZeroOrDefault",
    "pythonRuleCalendarEarlyStopCancellationAndConcurrentStreamHaveNoSummary",
    "pythonRuleCalendarForgedBatchesForeignSessionsAndOldTransactionsRejected",
    "pythonRuleCalendarOriginalEightTablesRemainIdenticalAndNoSimulationIssued",
)
NATIVE_ACTOR = 990671
WINDOWS = ("TODAY", "YESTERDAY", "LAST_3D", "LAST_7D")
TIME_SQL = "SELECT UTC_TIMESTAMP(6) AS evaluated_at"


@contextmanager
def count_calendar_time(session):
    """仅当前Session实例的固定语句计数，不记录SQL/参数，不改全局/连接池。"""
    original = session.execute
    counts = {"utc_reference_calls": 0}

    async def execute(statement, *args, **kwargs):
        if str(statement) == TIME_SQL:
            counts["utc_reference_calls"] += 1
        return await original(statement, *args, **kwargs)

    session.execute = execute
    try:
        yield counts
    finally:
        session.execute = original


@contextmanager
def count_profile_execute(session):
    """计方法调用而非仅等待，覆盖verified_profile不得补SQL的合同。"""
    original = session.execute
    count = {"execute_calls": 0}

    def execute(statement, *args, **kwargs):
        count["execute_calls"] += 1
        return original(statement, *args, **kwargs)

    session.execute = execute
    try:
        yield count
    finally:
        session.execute = original


def run_rule_simulation_calendar_checks(client, admin, headers, password, cache, database, cases):
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

    from orbit_api.rule_profile_references import RuleProfileBinding
    from orbit_api.rule_simulation_access import RuleSimulationAccessFacade
    from orbit_api.rule_simulation_expected_units import RuleSimulationExpectedUnits

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
    owner, username = str(uuid4()), "calacc_" + uuid4().hex[:10]
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
        timezone = ("America/Los_Angeles", "Asia/Shanghai", "Pacific/Kiritimati", "Europe/Berlin")[
            index % 4
        ]
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
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=966)
    cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": identifiers, "filter": None},
        ),
        201,
    )
    rules = []
    for window in WINDOWS:
        body = definition_body(
            "日历授权-" + uuid4().hex[:10], owner, team, scope["id"], profile["id"]
        )
        body["window"] = window
        cap = checked(
            client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"})
        )
        rule = checked(
            client.post(
                "/api/v1/rules",
                headers=headers
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json=body,
            ),
            201,
        )
        assert rule["revision"] == 1 and rule["window"] == window
        rules.append(rule)
    assert scope["count"] == 1001
    cases.append(RULE_SIMULATION_CALENDAR_CASES[0])

    frozen_profiles = {
        rule["id"]: sql(
            "SELECT metric_profile_id,metric_profile_version,metric_profile_hash "
            "FROM orbit_rule_version "
            "WHERE tenant_id=%s AND rule_id=%s AND revision=%s",
            (tenant, rule["id"], rule["revision"]),
            rows=True,
        )[0]
        for rule in rules
    }

    # 不变范围从全部fixture创建结束之后开始，不能把4条新Rule写入混入只读边界。
    def snapshot():
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", rows=True) for table in TABLES)

    before = snapshot()
    initial_sim_tables = sql(
        "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s "
        "AND TABLE_NAME LIKE %s",
        (database, "orbit_rule_simulation%"),
        rows=True,
    )[0][0]

    async def run():
        install_windows_asyncmy_compat()
        engine = create_async_engine(
            engine_url(admin, database),
            echo=False,
            hide_parameters=True,
            pool_size=2,
            max_overflow=0,
        )
        access = RuleSimulationAccessFacade()
        calendar = RuleSimulationExpectedUnits(access)

        async def consume(session, ticket, *, size=200):
            values, lengths = [], []
            async for parent in access.iter_account_batches(session, ticket, batch_size=size):
                async for batch in calendar.iter_units(session, ticket, parent):
                    calendar.assert_batch(session, ticket, batch)
                    assert 1 <= len(batch.units) <= 200
                    values.extend(batch.units)
                    lengths.append(len(batch.units))
            parent_summary = await access.finish(session, ticket)
            with count_profile_execute(session) as executes:
                binding = access.verified_profile(session, ticket, parent_summary)
            assert executes == {"execute_calls": 0}
            assert type(binding) is RuleProfileBinding
            assert (binding.profile_id, binding.version, binding.profile_hash) == frozen_profiles[
                ticket.rule_id
            ]
            summary = calendar.finish(session, ticket, parent_summary)
            calendar.assert_summary(session, ticket, summary)
            return values, lengths, summary

        try:
            async with engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT DATABASE()"))
                ).scalar_one() == database
            all_roots, reference = {}, None
            async with AsyncSession(engine) as session, session.begin():
                with count_calendar_time(session) as count:
                    for rule in rules:
                        expected_days = {
                            "TODAY": (0, 0),
                            "YESTERDAY": (1, 1),
                            "LAST_3D": (2, 0),
                            "LAST_7D": (6, 0),
                        }[rule["window"]]
                        for size in (200, 1000):
                            ticket = await access.open(
                                session, NATIVE_ACTOR, rule["id"], rule["revision"]
                            )
                            units, lengths, summary = await consume(session, ticket, size=size)
                            assert (
                                summary.account_count == 1001
                                and summary.unresolved_account_count == 0
                            )
                            assert summary.calendar_complete is True and max(lengths) <= 200
                            if reference is None:
                                reference = summary.evaluated_at
                            assert summary.evaluated_at == reference
                            actual = [
                                (
                                    unit.account_id,
                                    unit.business_date,
                                    unit.timezone_name,
                                    unit.currency,
                                    unit.window,
                                    unit.status,
                                    unit.reason_code,
                                )
                                for unit in units
                            ]
                            expected_rows = []
                            for identifier in identifiers:
                                currency, timezone = expected[identifier]
                                local_today = reference.astimezone(ZoneInfo(timezone)).date()
                                start, end = (
                                    local_today - timedelta(days=expected_days[0]),
                                    local_today - timedelta(days=expected_days[1]),
                                )
                                for offset in range((end - start).days + 1):
                                    expected_rows.append(
                                        (
                                            identifier,
                                            start + timedelta(days=offset),
                                            timezone,
                                            currency,
                                            rule["window"],
                                            "RESOLVED",
                                            None,
                                        )
                                    )
                            assert actual == expected_rows
                            assert (
                                len(actual)
                                == summary.resolved_unit_count
                                == 1001 * (expected_days[0] - expected_days[1] + 1)
                            )
                            if rule["id"] in all_roots:
                                assert summary.calendar_root == all_roots[rule["id"]]
                            all_roots[rule["id"]] = summary.calendar_root
                    assert count == {"utc_reference_calls": 1}
            assert snapshot() == before
            cases.append(RULE_SIMULATION_CALENDAR_CASES[1])

            rule = rules[0]
            original_timezone = expected[identifiers[0]][1]
            sql(
                "UPDATE orbit_ad_account SET timezone_id='not/a-zone' WHERE tenant_id=%s AND id=%s",
                (tenant, identifiers[0]),
            )
            try:
                async with AsyncSession(engine) as session, session.begin():
                    with count_calendar_time(session) as count:
                        ticket = await access.open(
                            session, NATIVE_ACTOR, rule["id"], rule["revision"]
                        )
                        units, _, summary = await consume(session, ticket, size=1000)
                        assert count == {"utc_reference_calls": 1}
                        assert summary.account_count == 1001 and summary.resolved_unit_count == 1000
                        assert (
                            summary.unresolved_account_count == 1
                            and summary.calendar_complete is False
                        )
                        assert (
                            len(units) == 1001
                            and [unit.account_id for unit in units] == identifiers
                        )
                        assert (
                            units[0].status == "UNRESOLVED_WINDOW"
                            and units[0].business_date is None
                        )
                        assert (
                            units[0].timezone_name == "not/a-zone"
                            and units[0].reason_code == "TIMEZONE_INVALID"
                        )
            finally:
                sql(
                    "UPDATE orbit_ad_account SET timezone_id=%s WHERE tenant_id=%s AND id=%s",
                    (original_timezone, tenant, identifiers[0]),
                )
            assert snapshot() == before
            cases.append(RULE_SIMULATION_CALENDAR_CASES[2])

            for field in ("currency", "timezone_id"):
                original_row = sql(
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
                    raise AssertionError("RULE_CALENDAR_NOT_NULL_REFUSAL_REQUIRED")
                finally:
                    admin.rollback()
                assert (
                    sql(
                        "SELECT currency,timezone_id FROM orbit_ad_account WHERE "
                        "tenant_id=%s AND id=%s",
                        (tenant, identifiers[0]),
                        rows=True,
                    )
                    == original_row
                )
            cases.append(RULE_SIMULATION_CALENDAR_CASES[3])

            for method in ("close", "cancel", "concurrent"):
                async with AsyncSession(engine) as session, session.begin():
                    with count_calendar_time(session) as count:
                        ticket = await access.open(
                            session, NATIVE_ACTOR, rule["id"], rule["revision"]
                        )
                        parents = access.iter_account_batches(session, ticket)
                        parent = await anext(parents)
                        units = calendar.iter_units(session, ticket, parent)
                        await anext(units)
                        if method == "concurrent":
                            try:
                                await anext(calendar.iter_units(session, ticket, parent))
                            except ValueError:
                                pass
                            else:
                                raise AssertionError("RULE_CALENDAR_CONCURRENT_ACCEPTED")
                        if method == "cancel":
                            try:
                                await units.athrow(asyncio.CancelledError())
                            except asyncio.CancelledError:
                                pass
                            else:
                                raise AssertionError("RULE_CALENDAR_CANCEL_SWALLOWED")
                        else:
                            await units.aclose()
                        # 父流真实继续EOF，证明不是因无父完整summary才拒绝。
                        async for _ in parents:
                            pass
                        complete = await access.finish(session, ticket)
                        try:
                            calendar.finish(session, ticket, complete)
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("RULE_CALENDAR_PARTIAL_FINISHED")
                        assert count == {"utc_reference_calls": 1}
            cases.append(RULE_SIMULATION_CALENDAR_CASES[4])

            async with AsyncSession(engine) as session:
                async with session.begin():
                    with count_calendar_time(session) as count:
                        ticket = await access.open(
                            session, NATIVE_ACTOR, rule["id"], rule["revision"]
                        )
                        parents = access.iter_account_batches(session, ticket)
                        parent = await anext(parents)
                        try:
                            await anext(
                                calendar.iter_units(session, ticket, replace(parent, accounts=()))
                            )
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("RULE_CALENDAR_FORGED_PARENT_ACCEPTED")
                        assert count == {"utc_reference_calls": 0}
                        stream = calendar.iter_units(session, ticket, parent)
                        batch = await anext(stream)
                        try:
                            calendar.assert_batch(session, ticket, replace(batch, units=()))
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("RULE_CALENDAR_FORGED_UNIT_ACCEPTED")
                        async with AsyncSession(engine) as other, other.begin():
                            try:
                                calendar.assert_batch(other, ticket, batch)
                            except ValueError:
                                pass
                            else:
                                raise AssertionError("RULE_CALENDAR_FOREIGN_SESSION_ACCEPTED")
                        await stream.aclose()
                        await parents.aclose()
                async with session.begin():
                    try:
                        calendar.assert_batch(session, ticket, batch)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("RULE_CALENDAR_OLD_TRANSACTION_ACCEPTED")
            cases.append(RULE_SIMULATION_CALENDAR_CASES[5])
            assert snapshot() == before
            assert (
                sql(
                    "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s "
                    "AND TABLE_NAME LIKE %s",
                    (database, "orbit_rule_simulation%"),
                    rows=True,
                )[0][0]
                == initial_sim_tables
            )
            cases.append(RULE_SIMULATION_CALENDAR_CASES[6])
        finally:
            await engine.dispose()

    asyncio.run(run())
    return {
        "account_count": 1001,
        "window_count": 4,
        "iana_zone_count": 4,
        "input_batch_sizes": [200, 1000],
        "output_max_batch_size": 200,
        "main_transaction_time_queries": 1,
        "technical_fixture_only": True,
        "source_issuer_verified": False,
        "simulation_http_called": False,
        "blocked_server_cancel_verified": False,
    }
