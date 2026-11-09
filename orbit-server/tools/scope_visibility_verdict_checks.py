"""043 独立真实 SQL/HTTP 专项；仅主线串行运行于本轮 UUID 隔离库。"""

import asyncio
import hashlib
import re
import sys
from datetime import datetime
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SCOPE_VISIBILITY_VERDICT_CASES = (
    "pythonScopeVerdictThreeActualRolesCreateOriginalReadySnapshots",
    "pythonScopeVerdictFirstCompleteValidationPublishesOnePositiveProof",
    "pythonScopeVerdictExactHitAvoidsLockedMemberAndDoesNotUseTimestampTtl",
    "pythonScopeVerdictAccountClockChangeRevalidatesWithoutRewritingFrozenMembers",
    "pythonScopeVerdictOneOwnershipLossRejectsWholeScopeWithoutNewProof",
    "pythonScopeVerdictOneMissingAccountRejectsWholeScopeWithoutNewProof",
    "pythonScopeVerdictForeignActorAndTenantCannotBorrowProof",
    "pythonScopeVerdictCurrentReadRevocationBlocksExistingPositiveProof",
    "pythonScopeVerdictEmptyFilterSnapshotRemainsValidWithoutPlanMinimum",
    "pythonScopeVerdictRealRepeatableReadOldAccountDoesNotAuthorizeCurrentOwner",
    "pythonScopeVerdictRealRepeatableReadRemovedManagerCannotAuthorizeForeignTeam",
    "pythonScopeVerdictRealRepeatableReadAddedManagerUsesCurrentManagedSet",
    "pythonScopeVerdictReadyMemberInsertUpdateDeleteAreDatabaseRejected",
    "pythonScopeVerdictReadySnapshotOriginalFieldsAndReadyDowngradeAreDatabaseRejected",
    "pythonScopeVerdictCommittedCleanupFlagReturns404DespiteExistingProof",
    "pythonScopeVerdictUnreadyMembersRemainEditableBeforeAtomicReadyPublication",
    "pythonScopeVerdictControlledFixtureCleanupDeletesProofMembersAndParentAtomically",
    "pythonScopeVerdictTwoSynchronizedActualMissesCommitExactlyOneProof",
)


def guard_database(admin, database):
    if (
        not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("范围证明专项只允许主线当前 UUID 独立 MySQL 库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("范围证明专项连接的实际数据库不匹配")


def assert_status(response, expected):
    assert response.status_code == expected, (
        "scope_verdict_http expected=" + str(expected) + " actual=" + str(response.status_code)
    )
    return response.json()


def sql_error_code(error):
    for candidate in (error, getattr(error, "orig", None)):
        args = getattr(candidate, "args", ())
        if args and type(args[0]) is int:
            return args[0]
    return None


def assert_guard_rejects(admin, statement, params):
    """即使护栏失效也回滚探测写入；异常只保留固定类型/数值码。"""
    admin.begin()
    try:
        with admin.cursor() as cursor:
            cursor.execute(statement, params)
    except Exception as error:
        admin.rollback()
        assert sql_error_code(error) == 1644, "scope_verdict_guard expected=1644 actual=" + str(
            sql_error_code(error)
        )
    else:
        admin.rollback()
        raise AssertionError("scope_verdict_guard expected_rejection actual_success")


def run_scope_visibility_verdict_checks(
    client, admin, headers, password, cache, database, cases, *, identities=None
):
    """18 个固定具名组；身份可由主线显式复用，避免旧 SQL 计划档重复占固定用户ID。"""
    guard_database(admin, database)
    from config.asyncmy_compat import install_windows_asyncmy_compat

    from orbit_api.account_scope_store import AccountScopeStore
    from orbit_api.directory_tokens import canonical
    from orbit_api.errors import OrbitError
    from orbit_api.scope_visibility_verdict import verified_snapshot

    if identities is None:
        from account_scope_visibility_plan_checks import prepare_plan_identities

        identities = prepare_plan_identities(client, admin, headers, password, cache)
    assert set(identities) == {"SUPER_ADMIN", "TEAM_ADMIN", "USER"}
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_owner, original_team = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s "
            "AND TRIGGER_NAME IN ('scope_snapshot_insert_guard','scope_snapshot_update_guard',"
            "'scope_snapshot_delete_guard','scope_member_insert_guard','scope_member_update_guard',"
            "'scope_member_delete_guard')",
            (database,),
        )
        assert cursor.fetchone()[0] == 6
        for identity in identities.values():
            cursor.execute(
                "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=%s",
                (identity["actor_id"],),
            )
            assert cursor.fetchone() == (
                tenant,
                identity["owner_user_id"],
                identity["owner_team_id"],
            ), "scope_verdict_identity_fixture_mismatch"
    marker = "Verdict-" + uuid4().hex
    extra_team, foreign_tenant = str(uuid4()), str(uuid4())
    account_ids = sorted(str(uuid4()) for _ in range(3))
    user = identities["USER"]
    manager = identities["TEAM_ADMIN"]
    tracked_snapshots = []

    def scalar(statement, params=()):
        with admin.cursor() as cursor:
            cursor.execute(statement, params)
            return cursor.fetchone()[0]

    def mutate_account(statement, params):
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s FOR UPDATE",
                    (tenant,),
                )
                cursor.fetchone()
                cursor.execute(statement, params)
                cursor.execute(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
            admin.commit()
        except Exception:
            admin.rollback()
            raise

    def management(enabled):
        with admin.cursor() as cursor:
            if enabled:
                cursor.execute(
                    "INSERT INTO orbit_business_team_manager"
                    "(tenant_id,manager_user_id,team_id) VALUES(%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE enabled=1",
                    (tenant, manager["actor_id"], extra_team),
                )
            else:
                cursor.execute(
                    "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s "
                    "AND manager_user_id=%s AND team_id=%s",
                    (tenant, manager["actor_id"], extra_team),
                )
        admin.commit()

    def create(identity, selected=None, *, empty=False):
        cap = assert_status(
            client.get("/api/v1/scope-snapshots/capabilities", headers=identity["headers"]), 200
        )
        body = {"mode": "IDS", "account_ids": selected or account_ids, "filter": None}
        if empty:
            body = {
                "mode": "FILTER",
                "account_ids": [],
                "filter": {
                    "q": marker + "-ABSENT",
                    "status": None,
                    "auth_status": None,
                    "operator_user_id": None,
                    "vendor_id": None,
                },
            }
        result = assert_status(
            client.post(
                "/api/v1/scope-snapshots",
                headers=identity["headers"]
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": uuid4().hex},
                json=body,
            ),
            201,
        )
        assert set(result) == {"id", "count", "scope_version", "hash", "created_at"}
        tracked_snapshots.append((tenant, result["id"]))
        return result

    def read(identity, snapshot, status=200):
        result = assert_status(
            client.get(
                "/api/v1/scope-snapshots/" + snapshot["id"] + "/members",
                headers=identity["headers"],
                params={"page_size": "20"},
                timeout=4,
            ),
            status,
        )
        if status == 200:
            assert set(result) == {"items", "next_cursor", "data_as_of", "scope_version"}
        return result

    def drop_proof(snapshot):
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orbit_scope_access_verdict WHERE tenant_id=%s AND snapshot_id=%s",
                (tenant, snapshot["id"]),
            )
        admin.commit()

    def cleanup(target_tenant, identifier):
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_account_scope_snapshot SET cleanup_requested=1 "
                    "WHERE tenant_id=%s AND id=%s AND ready=1",
                    (target_tenant, identifier),
                )
                for table in ("orbit_scope_access_verdict", "orbit_account_scope_member"):
                    cursor.execute(
                        "DELETE FROM " + table + " WHERE tenant_id=%s AND snapshot_id=%s",
                        (target_tenant, identifier),
                    )
                cursor.execute(
                    "DELETE FROM orbit_account_scope_snapshot WHERE tenant_id=%s AND id=%s",
                    (target_tenant, identifier),
                )
            admin.commit()
        except Exception:
            admin.rollback()
            raise

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    install_windows_asyncmy_compat()
    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def real_rr(snapshot, *, change, old_read, assert_old, expected):
        engine = create_async_engine(url, isolation_level="REPEATABLE READ", pool_size=2)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session, session.begin():
                isolation = (
                    await session.execute(text("SELECT @@transaction_isolation"))
                ).scalar_one()
                assert isolation == "REPEATABLE-READ"
                before = (await session.execute(text(old_read), {"tenant": tenant})).all()
                change()
                after = (await session.execute(text(old_read), {"tenant": tenant})).all()
                assert before == after and assert_old(before), (
                    "scope_verdict_old_rr_not_established"
                )
                current, version, digest = await AccountScopeStore(None).authorize(
                    session, manager["actor_id"]
                )
                try:
                    result = await verified_snapshot(
                        session, current, version, digest, snapshot["id"]
                    )
                except OrbitError as error:
                    assert (error.status, error.code) == expected
                else:
                    assert expected == (200, None) and result["id"] == snapshot["id"]
        finally:
            await engine.dispose()

    async def two_actual_misses(snapshot):
        engine = create_async_engine(url, pool_size=2, max_overflow=0)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        barrier, arrivals = asyncio.Barrier(2), []

        class GatedSession:
            def __init__(self, session):
                self.session = session

            def in_transaction(self):
                return self.session.in_transaction()

            async def execute(self, statement, params=None):
                if str(statement).startswith("SELECT 1 FROM orbit_account_scope_member"):
                    arrivals.append(1)
                    await asyncio.wait_for(barrier.wait(), timeout=5)
                return await self.session.execute(statement, params)

        async def worker():
            async with sessions() as session, session.begin():
                current, version, digest = await AccountScopeStore(None).authorize(session, 1)
                result = await verified_snapshot(
                    GatedSession(session), current, version, digest, snapshot["id"]
                )
                assert result["id"] == snapshot["id"]

        try:
            await asyncio.wait_for(asyncio.gather(worker(), worker()), timeout=10)
            assert len(arrivals) == 2, "scope_verdict_both_actual_misses_required"
        finally:
            await engine.dispose()

    starting_case_count = len(cases)
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
                (tenant, extra_team, marker),
            )
            cursor.executemany(
                "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
                "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
                "value_json,details_json,bound_at,created_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','UTC','UNKNOWN','UNKNOWN','{}','{}',"
                "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                [
                    (
                        tenant,
                        identifier,
                        str(uuid4().int),
                        marker,
                        marker,
                        user["owner_user_id"],
                        original_team,
                    )
                    for identifier in account_ids
                ],
            )
            cursor.execute(
                "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        admin.commit()
        snapshots = {role: create(identity) for role, identity in identities.items()}
        assert all(item["count"] == 3 for item in snapshots.values())
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[0])

        base = snapshots["SUPER_ADMIN"]
        drop_proof(base)
        actual = read(identities["SUPER_ADMIN"], base)
        assert len(actual["items"]) == 3
        assert (
            scalar(
                "SELECT COUNT(*) FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                "AND snapshot_id=%s",
                (tenant, base["id"]),
            )
            == 1
        )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[1])

        ancient = datetime(2000, 1, 1)
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_scope_access_verdict SET verified_at=%s "
                "WHERE tenant_id=%s AND snapshot_id=%s",
                (ancient, tenant, base["id"]),
            )
        admin.commit()
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM orbit_ad_account WHERE tenant_id=%s AND id=%s FOR UPDATE",
                    (tenant, account_ids[0]),
                )
                assert cursor.fetchone()
            # 真账户行保持 X 锁；若走完整 current FOR SHARE 扫描，会等锁而不能成功返回。
            read(identities["SUPER_ADMIN"], base)
            assert (
                scalar(
                    "SELECT verified_at FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                    "AND snapshot_id=%s",
                    (tenant, base["id"]),
                )
                == ancient
            )
        finally:
            admin.rollback()
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[2])

        mutate_account(
            "UPDATE orbit_ad_account SET name=%s,revision=revision+1 WHERE tenant_id=%s AND id=%s",
            (marker + "-NEW", tenant, account_ids[0]),
        )
        newer = read(identities["SUPER_ADMIN"], base)
        assert newer == actual
        assert scalar(
            "SELECT account_version FROM orbit_scope_access_verdict WHERE tenant_id=%s "
            "AND snapshot_id=%s",
            (tenant, base["id"]),
        ) == scalar("SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,))
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[3])

        user_scope = snapshots["USER"]
        read(user, user_scope)
        old_proof_version = scalar(
            "SELECT account_version FROM orbit_scope_access_verdict "
            "WHERE tenant_id=%s AND snapshot_id=%s",
            (tenant, user_scope["id"]),
        )
        mutate_account(
            "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
            (root_owner, tenant, account_ids[0]),
        )
        try:
            assert read(user, user_scope, 409)["code"] == "SCOPE_CHANGED"
            assert (
                scalar(
                    "SELECT account_version FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                    "AND snapshot_id=%s",
                    (tenant, user_scope["id"]),
                )
                == old_proof_version
            )
        finally:
            mutate_account(
                "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                (user["owner_user_id"], tenant, account_ids[0]),
            )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[4])

        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                (tenant, account_ids[0]),
            )
            missing_row = cursor.fetchone()
            columns = [value[0] for value in cursor.description]
            assert all(re.fullmatch(r"[a-z_]+", value) for value in columns)
        mutate_account(
            "DELETE FROM orbit_ad_account WHERE tenant_id=%s AND id=%s", (tenant, account_ids[0])
        )
        try:
            assert read(identities["SUPER_ADMIN"], base, 409)["code"] == "SCOPE_CHANGED"
        finally:
            mutate_account(
                "INSERT INTO orbit_ad_account("
                + ",".join(columns)
                + ") VALUES("
                + ",".join(["%s"] * len(columns))
                + ")",
                missing_row,
            )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[5])

        read(user, base, 404)
        foreign_id = str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_tenant(id,name) VALUES(%s,%s)", (foreign_tenant, marker)
            )
            cursor.execute(
                "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,"
                "scope_version,auth_fingerprint,request_key,request_hash,request_json,"
                "created_at) VALUES(%s,%s,1,1,%s,%s,%s,'{}',UTC_TIMESTAMP(3))",
                (foreign_tenant, foreign_id, "0" * 64, uuid4().hex, "0" * 64),
            )
            cursor.execute(
                "UPDATE orbit_account_scope_snapshot SET ready=1,member_count=0,"
                "members_hash=%s WHERE tenant_id=%s AND id=%s",
                (hashlib.sha256(b"[]").hexdigest(), foreign_tenant, foreign_id),
            )
        admin.commit()
        tracked_snapshots.append((foreign_tenant, foreign_id))
        read(identities["SUPER_ADMIN"], {"id": foreign_id}, 404)
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[6])

        read(user, user_scope)
        role = scalar("SELECT role_id FROM sys_user_role WHERE user_id=%s", (user["actor_id"],))
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31011", (role,))
        admin.commit()
        try:
            assert read(user, user_scope, 403)["code"] == "PERMISSION_DENIED"
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31011)", (role,)
                )
            admin.commit()
        read(user, user_scope)
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[7])

        empty = create(identities["SUPER_ADMIN"], empty=True)
        assert empty["count"] == 0 and read(identities["SUPER_ADMIN"], empty)["items"] == []
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[8])

        team_scope = snapshots["TEAM_ADMIN"]
        account_read = (
            "SELECT owner_team_id FROM orbit_ad_account WHERE tenant_id=:tenant "
            "AND id='" + account_ids[0] + "'"
        )

        def hide_from_team():
            mutate_account(
                "UPDATE orbit_ad_account SET owner_team_id=%s WHERE tenant_id=%s AND id=%s",
                (extra_team, tenant, account_ids[0]),
            )

        def restore_account():
            mutate_account(
                "UPDATE orbit_ad_account SET owner_team_id=%s WHERE tenant_id=%s AND id=%s",
                (original_team, tenant, account_ids[0]),
            )

        drop_proof(team_scope)
        try:
            asyncio.run(
                real_rr(
                    team_scope,
                    change=hide_from_team,
                    old_read=account_read,
                    assert_old=lambda rows: rows[0][0] == original_team,
                    expected=(409, "SCOPE_CHANGED"),
                )
            )
        finally:
            restore_account()
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[9])

        manager_read = (
            "SELECT team_id FROM orbit_business_team_manager WHERE tenant_id=:tenant "
            "AND manager_user_id=" + str(manager["actor_id"]) + " AND enabled=1 ORDER BY team_id"
        )
        management(True)
        drop_proof(team_scope)

        def remove_and_hide():
            management(False)
            hide_from_team()

        try:
            asyncio.run(
                real_rr(
                    team_scope,
                    change=remove_and_hide,
                    old_read=manager_read,
                    assert_old=lambda rows: extra_team in [row[0] for row in rows],
                    expected=(409, "SCOPE_CHANGED"),
                )
            )
        finally:
            management(False)
            restore_account()
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[10])

        management(True)
        hide_from_team()
        added_scope = create(manager)
        management(False)
        drop_proof(added_scope)
        try:
            asyncio.run(
                real_rr(
                    added_scope,
                    change=lambda: management(True),
                    old_read=manager_read,
                    assert_old=lambda rows: extra_team not in [row[0] for row in rows],
                    expected=(200, None),
                )
            )
        finally:
            management(False)
            restore_account()
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[11])

        assert_guard_rejects(
            admin,
            "INSERT INTO orbit_account_scope_member "
            "SELECT tenant_id,snapshot_id,%s,external_id,name,name_prefix,"
            "account_revision,owner_user_id,owner_team_id,currency "
            "FROM orbit_account_scope_member WHERE tenant_id=%s AND snapshot_id=%s "
            "LIMIT 1",
            (str(uuid4()), tenant, base["id"]),
        )
        assert_guard_rejects(
            admin,
            "UPDATE orbit_account_scope_member SET name=%s "
            "WHERE tenant_id=%s AND snapshot_id=%s LIMIT 1",
            (marker, tenant, base["id"]),
        )
        assert_guard_rejects(
            admin,
            "DELETE FROM orbit_account_scope_member WHERE tenant_id=%s AND snapshot_id=%s LIMIT 1",
            (tenant, base["id"]),
        )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[12])

        for field, value in (
            ("members_hash", "f" * 64),
            ("member_count", 2),
            ("ready", 0),
            ("request_key", uuid4().hex),
            ("created_at", ancient),
        ):
            assert_guard_rejects(
                admin,
                "UPDATE orbit_account_scope_snapshot SET "
                + field
                + "=%s WHERE tenant_id=%s AND id=%s",
                (value, tenant, base["id"]),
            )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[13])

        discarded = create(identities["SUPER_ADMIN"])
        read(identities["SUPER_ADMIN"], discarded)
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_account_scope_snapshot SET cleanup_requested=1 "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, discarded["id"]),
            )
        admin.commit()
        read(identities["SUPER_ADMIN"], discarded, 404)
        assert_guard_rejects(
            admin,
            "UPDATE orbit_account_scope_snapshot SET cleanup_requested=0 "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, discarded["id"]),
        )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[14])

        unready_id = str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,"
                "scope_version,auth_fingerprint,request_key,request_hash,request_json,"
                "created_at) SELECT tenant_id,%s,actor_id,scope_version,auth_fingerprint,"
                "%s,request_hash,request_json,created_at FROM orbit_account_scope_snapshot "
                "WHERE tenant_id=%s AND id=%s",
                (unready_id, uuid4().hex, tenant, base["id"]),
            )
            cursor.execute(
                "INSERT INTO orbit_account_scope_member SELECT tenant_id,%s,account_id,"
                "external_id,name,name_prefix,account_revision,owner_user_id,owner_team_id,"
                "currency FROM orbit_account_scope_member WHERE tenant_id=%s AND snapshot_id=%s",
                (unready_id, tenant, base["id"]),
            )
            cursor.execute(
                "UPDATE orbit_account_scope_member SET name=%s WHERE tenant_id=%s "
                "AND snapshot_id=%s LIMIT 1",
                (marker + "-UNREADY", tenant, unready_id),
            )
            cursor.execute(
                "DELETE FROM orbit_account_scope_member WHERE tenant_id=%s "
                "AND snapshot_id=%s LIMIT 1",
                (tenant, unready_id),
            )
            cursor.execute(
                "SELECT account_id,external_id,name,account_revision,owner_user_id,owner_team_id,"
                "currency FROM orbit_account_scope_member WHERE tenant_id=%s AND snapshot_id=%s "
                "ORDER BY account_id",
                (tenant, unready_id),
            )
            frozen_rows = [list(row) for row in cursor.fetchall()]
            assert len(frozen_rows) == 2
            frozen_hash = hashlib.sha256(canonical(frozen_rows).encode()).hexdigest()
            cursor.execute(
                "UPDATE orbit_account_scope_snapshot SET ready=1,member_count=2,"
                "members_hash=%s WHERE tenant_id=%s AND id=%s",
                (frozen_hash, tenant, unready_id),
            )
        admin.commit()
        tracked_snapshots.append((tenant, unready_id))
        assert len(read(identities["SUPER_ADMIN"], {"id": unready_id})["items"]) == 2
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[15])

        cleanup(tenant, discarded["id"])
        read(identities["SUPER_ADMIN"], discarded, 404)
        assert (
            scalar(
                "SELECT COUNT(*) FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                "AND snapshot_id=%s",
                (tenant, discarded["id"]),
            )
            == 0
        )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[16])

        drop_proof(base)
        asyncio.run(two_actual_misses(base))
        assert (
            scalar(
                "SELECT COUNT(*) FROM orbit_scope_access_verdict WHERE tenant_id=%s "
                "AND snapshot_id=%s",
                (tenant, base["id"]),
            )
            == 1
        )
        cases.append(SCOPE_VISIBILITY_VERDICT_CASES[17])
        return {
            "business_groups": len(SCOPE_VISIBILITY_VERDICT_CASES),
            "actual_roles": 3,
            "repeatable_read_cases": 3,
            "synchronized_misses": 2,
        }
    except Exception as error:
        raise AssertionError(
            "scope_verdict_group="
            + str(len(cases) - starting_case_count)
            + " error_type="
            + type(error).__name__
            + " code="
            + str(sql_error_code(error))
        ) from None
    finally:
        active_failure = sys.exception()
        try:
            admin.rollback()
            management(False)
            for target_tenant, snapshot_id in tracked_snapshots:
                cleanup(target_tenant, snapshot_id)
            mutate_account(
                "DELETE FROM orbit_ad_account WHERE tenant_id=%s AND name_prefix=%s",
                (tenant, marker),
            )
            with admin.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM orbit_business_team WHERE tenant_id=%s AND id=%s",
                    (tenant, extra_team),
                )
                cursor.execute("DELETE FROM orbit_tenant WHERE id=%s", (foreign_tenant,))
            admin.commit()
        except Exception as error:
            if active_failure is None:
                raise AssertionError(
                    "scope_verdict_cleanup error_type="
                    + type(error).__name__
                    + " code="
                    + str(sql_error_code(error))
                ) from None
