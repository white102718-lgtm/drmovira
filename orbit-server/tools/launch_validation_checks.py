"""原validate真实隔离SQL/HTTP专项；无平台调用，fixture不是生产authority。"""

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from launch_validation_fixture import PREFIX, IsolatedValidationProvider, control_directory

LAUNCH_VALIDATION_BASELINE_CASES = [
    "pythonLaunchValidationOriginalFieldsAndRequiredHeaders",
    "pythonLaunchValidationDefaultProductionProviderMissing503NoWrites",
    "pythonLaunchValidationCurrentActionAndForeignObjectDenied",
    "pythonLaunchValidationCsrfBoundToCurrentSession",
    "pythonLaunchValidationBlockedRequestsNeverCreateTaskOrValidation",
]
LAUNCH_VALIDATION_CASES = [
    "pythonLaunchValidationPersistentSuccessOriginalTenFieldsSourceHead",
    "pythonLaunchValidationSuccessfulReplayBeforeOldCAS",
    "pythonLaunchValidationNewKeyRefreshWithoutRebindingSourceNamesAllocation",
    "pythonLaunchValidationBusinessInvalidDraftActualCountsBudgetAudit",
    "pythonLaunchValidationInvalidClearsPreviouslyValidatedState",
    "pythonLaunchValidationSameKeyDifferentPayloadConflict",
    "pythonLaunchValidationConcurrentCASOneWinner",
    "pythonLaunchValidationCurrentSourceVersionMismatchRejected",
    "pythonLaunchValidationCurrentActionRevocationStopsReplay",
    "pythonLaunchValidationActualAllocationItemsTamperingWithoutHeaderChange",
    "pythonLaunchValidationActualNameItemsTamperingWithoutHeaderChange",
    "pythonLaunchValidationOutbox1644RollsBackWholeTransaction",
    "pythonLaunchValidationSuccessfulRecordExactCheckAndForeignKey",
    "pythonLaunchValidationSourceClockChangeDuringCaptureRejected",
    "pythonLaunchValidationActualSqlCaptureTtlBeforeEqualAfter",
    "pythonLaunchValidationActualSqlShanghaiMidnightBeforeEqual",
]


def run_launch_validation_checks(
    client,
    admin,
    headers,
    password,
    cache,
    database,
    cases,
    *,
    include_provider=False,
    cipher=None,
    control_dir=None,
):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("预检专项只允许主线本轮13306/UUID隔离库")
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_expansion import ad_slots, campaign_slots

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM orbit_task")
        initial_tasks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orbit_launch_validation")
        initial_validations = cursor.fetchone()[0]

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
            "code": response.json().get("code"),
        }
        return response.json()

    def write(revision=1, key=None, identity=headers):
        caps = checked(client.get("/api/v1/launch-plans/capabilities", headers=identity), 200)
        return identity | {
            "Idempotency-Key": key or str(uuid4()),
            "If-Match": f'"{revision}"',
            "X-CSRF-Token": caps["csrf_token"],
        }

    def new(mode="SUCCESS", *, plan_owner=owner):
        from task_core_fixture import plan as plan_fixture

        value = plan_fixture(plan_owner, team, copies=2)
        value["name"] = PREFIX + mode + "_" + uuid4().hex[:12]
        group = value["campaigns"][0]["adsets"][0]
        value["campaigns"][0]["budget"] = {
            "owner": "CAMPAIGN",
            "type": "DAILY",
            "amount": "12.34",
            "currency": "USD",
            "spend_cap": None,
        }
        value["identity_bindings"] = [
            {
                "account_id": value["account_ids"][0],
                "page_id": "123456",
                "groups": [
                    {
                        "adset_local_id": group["local_id"],
                        "pixel_id": "234567",
                        "conversion_event": "PURCHASE",
                        "application_id": None,
                        "object_store_url": None,
                    }
                ],
                "ad_overrides": [],
            }
        ]
        identifier, allocation, names = str(uuid4()), str(uuid4()), str(uuid4())
        payload = canonical(value)
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATE(UTC_TIMESTAMP(3)+INTERVAL 8 HOUR)")
            day = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO "
                """
                orbit_launch_plan(tenant_id, id, owner_user_id, owner_team_id, name,
                state, revision, payload_json, payload_hash, payload_bytes,
                account_count, asset_count, created_at, updated_at)
                """
                " "
                "VALUES(%s,%s,%s,%s,%s,'DRAFT',1,%s,%s,%s,1,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                (
                    tenant,
                    identifier,
                    plan_owner,
                    team,
                    value["name"],
                    payload,
                    digest(value),
                    len(payload.encode()),
                ),
            )
            cursor.execute(
                "INSERT INTO "
                """
                orbit_launch_plan_version(tenant_id, plan_id, revision, payload_json,
                payload_hash, dependency_json, created_at, created_by)
                """
                " VALUES(%s,%s,1,%s,%s,'{}',UTC_TIMESTAMP(3),1)",
                (tenant, identifier, payload, digest(value)),
            )
            cursor.execute(
                "INSERT INTO "
                """
                orbit_launch_allocation(tenant_id, id, plan_id, plan_revision, state,
                task_id, algorithm_version, seed, input_hash, warnings_json, active,
                created_at, updated_at)
                """
                " "
                """
                VALUES(%s, %s, %s, 1, 'SUCCEEDED', NULL, 'allocation-v1', 0, %s, '[]',
                1, UTC_TIMESTAMP(3), UTC_TIMESTAMP(3))
                """,
                (tenant, allocation, identifier, digest([identifier, "fixture-allocation"])),
            )
            cursor.executemany(
                "INSERT INTO "
                """
                orbit_launch_allocation_item(tenant_id, allocation_id, ordinal,
                slot_key, account_id, asset_id, asset_revision, asset_sha256)
                """
                " VALUES(%s,%s,%s,%s,%s,%s,1,%s)",
                [
                    (
                        tenant,
                        allocation,
                        n,
                        slot.key,
                        slot.account_id,
                        value["asset_ids"][0],
                        "a" * 64,
                    )
                    for n, slot in enumerate(ad_slots(value))
                ],
            )
            cursor.execute(
                "INSERT INTO "
                """
                orbit_launch_name_reservation(tenant_id, id, plan_id, plan_revision,
                naming_date, source_hash, created_at)
                """
                " VALUES(%s,%s,%s,1,%s,%s,UTC_TIMESTAMP(3))",
                (tenant, names, identifier, day, digest([identifier, "fixture-names"])),
            )
            cursor.executemany(
                "INSERT INTO "
                "orbit_launch_name_item(tenant_id,reservation_id,ordinal,slot_key,name,sequence)"
                " VALUES(%s,%s,%s,%s,%s,%s)",
                [
                    (
                        tenant,
                        names,
                        n,
                        "/".join(map(str, slot)),
                        f"隔离协议_{day:%Y%m%d}_{n + 1:04d}",
                        n + 1,
                    )
                    for n, slot in enumerate(campaign_slots(value))
                ],
            )
        admin.commit()
        return {
            "id": identifier,
            "value": value,
            "body": {"allocation_id": allocation, "name_reservation_id": names},
        }

    def validate(item, *, head=None, body=None):
        return client.post(
            "/api/v1/launch-plans/" + item["id"] + "/validate",
            headers=head or write(),
            json=body if body is not None else item["body"],
        )

    def state(item):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,revision FROM orbit_launch_plan WHERE tenant_id=%s AND id=%s",
                (tenant, item["id"]),
            )
            return cursor.fetchone()

    def snapshot():
        with admin.cursor() as cursor:
            output = []
            for table in (
                "orbit_launch_plan",
                "orbit_launch_plan_version",
                "orbit_launch_validation",
                "orbit_launch_clock",
                "orbit_launch_event",
                "orbit_launch_outbox",
                "orbit_launch_idempotency",
                "orbit_task",
            ):
                cursor.execute("SELECT * FROM " + table)
                output.append(tuple(sorted(cursor.fetchall(), key=repr)))
            return tuple(output)

    # 专属用户/角色来自真实角色API，native映射在受控唯一ID；不借其他专项身份。
    from fixture_login import fixture_login

    native = 990462
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,))
        assert cursor.fetchone()[0] == 0, "预检专属身份已占用，拒绝覆盖"
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "预检协议角色-" + uuid4().hex[:10],
                "menu_codes": ["launch"],
                "permission_codes": ["launch.read", "launch.edit"],
            },
        ),
        201,
    )
    subject, username = str(uuid4()), "validation_" + uuid4().hex[:12]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role["id"]),
        )
        role_native = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO "
            "sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'隔离预检投手',%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, username, username + "@fixture.example.org"),
        )
        cursor.execute(
            "INSERT INTO "
            "sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, role_native)
        )
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, tenant),
        )
        cursor.execute(
            "INSERT INTO "
            "orbit_business_user(tenant_id,id,user_id,team_id,display_name,invited,created_at)"
            " VALUES(%s,%s,%s,%s,'隔离预检投手',0,UTC_TIMESTAMP(3))",
            (tenant, subject, native, team),
        )
    admin.commit()
    login = checked(fixture_login(client, cache, {"username": username, "password": password}), 200)
    user_headers = {"Authorization": "Bearer " + login["token"]}

    def revoke(enabled):
        with admin.cursor() as cursor:
            if enabled:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31023)", (role_native,)
                )
            else:
                cursor.execute(
                    "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31023", (role_native,)
                )
        admin.commit()

    if not include_provider:
        item = new()
        original = snapshot()
        checked(validate(item, body=item["body"] | {"verified": True}), 400)
        checked(
            validate(
                item,
                head=headers
                | {"Idempotency-Key": str(uuid4()), "X-CSRF-Token": write()["X-CSRF-Token"]},
            ),
            400,
        )
        assert snapshot() == original
        cases.append(LAUNCH_VALIDATION_BASELINE_CASES[0])
        result = checked(validate(item), 503)
        assert (
            result["code"] == "LAUNCH_VALIDATION_AUTHORITY_UNAVAILABLE" and snapshot() == original
        )
        cases.append(LAUNCH_VALIDATION_BASELINE_CASES[1])
        own = new(plan_owner=subject)
        own_write = write(identity=user_headers)
        revoke(False)
        try:
            checked(validate(own, head=own_write), 403)
        finally:
            revoke(True)
        checked(validate(item, head=write(identity=user_headers)), 404)
        cases.append(LAUNCH_VALIDATION_BASELINE_CASES[2])
        bad = write() | {"X-CSRF-Token": "invalid-format-token"}
        checked(validate(item, head=bad), 403)
        cases.append(LAUNCH_VALIDATION_BASELINE_CASES[3])
        with admin.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM orbit_launch_validation")
            assert cursor.fetchone()[0] == initial_validations
            cursor.execute("SELECT COUNT(*) FROM orbit_task")
            assert cursor.fetchone()[0] == initial_tasks
        cases.append(LAUNCH_VALIDATION_BASELINE_CASES[4])
        return {"blocked_cases": [], "platform_requests": 0}

    item, key = new(), write()
    result = checked(validate(item, head=key), 200)
    assert (
        set(result)
        == {
            "valid",
            "hash",
            "expires_at",
            "errors",
            "campaign_count",
            "adset_count",
            "ad_count",
            "budget_totals",
            "scope_version",
            "total_dag_node_count",
        }
        and result["valid"]
    )
    assert (
        result["ad_count"] == 2
        and result["budget_totals"] == [{"currency": "USD", "amount": "12.34"}]
        and state(item) == ("VALIDATED", 2)
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT source_revision,validated_head_revision FROM "
            "orbit_launch_validation WHERE tenant_id=%s AND plan_id=%s",
            (tenant, item["id"]),
        )
        assert cursor.fetchone() == (1, 2)
        cursor.execute(
            """
            SELECT provider_kind, TIMESTAMPDIFF(MICROSECOND, validated_at,
            expires_at), JSON_UNQUOTE(JSON_EXTRACT(summary_json,
            '$.hash'))=validation_hash FROM orbit_launch_validation WHERE
            tenant_id=%s AND plan_id=%s
            """,
            (tenant, item["id"]),
        )
        assert cursor.fetchone() == ("ISOLATED_TEST", 900000000, 1)
    cases.append(LAUNCH_VALIDATION_CASES[0])
    before = snapshot()
    assert checked(validate(item, head=key), 200) == result and snapshot() == before
    cases.append(LAUNCH_VALIDATION_CASES[1])
    refreshed = checked(validate(item, head=write(2)), 200)
    assert refreshed["hash"] == result["hash"] and state(item) == ("VALIDATED", 3)
    with admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_revision, allocation_id, name_reservation_id FROM
            orbit_launch_validation WHERE tenant_id=%s AND plan_id=%s ORDER BY
            validated_head_revision
            """,
            (tenant, item["id"]),
        )
        assert (
            cursor.fetchall()
            == ((1, item["body"]["allocation_id"], item["body"]["name_reservation_id"]),) * 2
        )
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_launch_plan_version WHERE tenant_id=%s AND plan_id=%s",
            (tenant, item["id"]),
        )
        assert cursor.fetchone()[0] == 1
    cases.append(LAUNCH_VALIDATION_CASES[2])
    invalid = new("INVALID")
    bad = checked(validate(invalid), 200)
    assert (
        not bad["valid"]
        and bad["hash"] is None
        and bad["expires_at"] is None
        and bad["ad_count"] == 2
        and bad["budget_totals"] == [{"currency": "USD", "amount": "12.34"}]
        and state(invalid) == ("DRAFT", 1)
    )
    cases.append(LAUNCH_VALIDATION_CASES[3])
    with admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM orbit_launch_event e JOIN orbit_launch_outbox o
            ON o.tenant_id=e.tenant_id AND o.event_id=e.id WHERE e.tenant_id=%s
            AND e.resource_id=%s AND e.action='plan.validate.invalid'
            """,
            (tenant, invalid["id"]),
        )
        assert cursor.fetchone()[0] == 1
    previously_valid = new("ONCE")
    assert checked(validate(previously_valid), 200)["valid"]
    assert not checked(validate(previously_valid, head=write(2)), 200)["valid"] and state(
        previously_valid
    ) == (
        "DRAFT",
        3,
    )
    cases.append(LAUNCH_VALIDATION_CASES[4])
    checked(validate(item, head=key, body=item["body"] | {"allocation_id": str(uuid4())}), 409)
    cases.append(LAUNCH_VALIDATION_CASES[5])
    concurrent = new()
    h1, h2 = write(), write()
    with ThreadPoolExecutor(max_workers=2) as executor:
        answers = [
            future.result()
            for future in (
                executor.submit(validate, concurrent, head=h1),
                executor.submit(validate, concurrent, head=h2),
            )
        ]
    assert sorted(response.status_code for response in answers) == [200, 409]
    assert state(concurrent) == ("VALIDATED", 2)
    cases.append(LAUNCH_VALIDATION_CASES[6])
    stale = new()
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_launch_allocation SET plan_revision=2 WHERE tenant_id=%s AND id=%s",
            (tenant, stale["body"]["allocation_id"]),
        )
    admin.commit()
    try:
        checked(validate(stale), 409)
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_allocation SET plan_revision=1 WHERE tenant_id=%s AND id=%s",
                (tenant, stale["body"]["allocation_id"]),
            )
        admin.commit()
    cases.append(LAUNCH_VALIDATION_CASES[7])
    own = new(plan_owner=subject)
    replay_key = write(identity=user_headers)
    checked(validate(own, head=replay_key), 200)
    revoke(False)
    try:
        checked(validate(own, head=replay_key), 403)
    finally:
        revoke(True)
    cases.append(LAUNCH_VALIDATION_CASES[8])

    directory = control_directory(database, control_dir)

    def barrier(mode, mutate, restore):
        target = new(mode + "_BARRIER")
        ready, release = (
            directory / (target["id"] + ".ready"),
            directory / (target["id"] + ".release"),
        )
        head = write()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(validate, target, head=head)
            started = time.monotonic()
            mutated = False
            try:
                while not ready.exists():
                    assert time.monotonic() - started < 7, "受控capture握手未就绪"
                    if future.done():
                        raise AssertionError(
                            {"phase": "capture_ready", "status": future.result().status_code}
                        )
                    time.sleep(0.025)
                mutated = True
                mutate(target)
                admin.commit()
                release.write_text("release", encoding="ascii")
                checked(future.result(timeout=8), 409)
                assert state(target) == ("DRAFT", 1)
            finally:
                release.write_text("release", encoding="ascii")
                if mutated:
                    restore(target)
                    admin.commit()
                if not future.done():
                    future.result(timeout=8)
                ready.unlink(missing_ok=True)
                release.unlink(missing_ok=True)

    for column, expression, reverse in (
        ("asset_revision", "asset_revision+1", "asset_revision-1"),
        ("slot_key", "CONCAT(slot_key,'/tamper')", "LEFT(slot_key,CHAR_LENGTH(slot_key)-7)"),
    ):

        def mutate(target, column=column, expression=expression):
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE orbit_launch_allocation_item SET {column}={expression} "
                    "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                    (tenant, target["body"]["allocation_id"]),
                )

        def restore(target, column=column, reverse=reverse):
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE orbit_launch_allocation_item SET {column}={reverse} "
                    "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                    (tenant, target["body"]["allocation_id"]),
                )

        barrier("ITEM", mutate, restore)
    for column, plan_field in (("account_id", "account_ids"), ("asset_id", "asset_ids")):

        def mutate(target, column=column):
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE orbit_launch_allocation_item SET {column}=%s "
                    "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                    (str(uuid4()), tenant, target["body"]["allocation_id"]),
                )

        def restore(target, column=column, plan_field=plan_field):
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE orbit_launch_allocation_item SET {column}=%s "
                    "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                    (target["value"][plan_field][0], tenant, target["body"]["allocation_id"]),
                )

        barrier("ITEM", mutate, restore)

    def allocation_set_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                SELECT ordinal, slot_key, account_id, asset_id, asset_revision,
                asset_sha256 FROM orbit_launch_allocation_item WHERE tenant_id=%s AND
                allocation_id=%s ORDER BY ordinal
                """,
                (tenant, target["body"]["allocation_id"]),
            )
            target["saved_items"] = cursor.fetchall()
            cursor.execute(
                "DELETE FROM orbit_launch_allocation_item WHERE tenant_id=%s AND allocation_id=%s",
                (tenant, target["body"]["allocation_id"]),
            )

    def allocation_set_restore(target):
        with admin.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO orbit_launch_allocation_item(tenant_id, allocation_id,
                ordinal, slot_key, account_id, asset_id, asset_revision, asset_sha256)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (tenant, target["body"]["allocation_id"], *row)
                    for row in target.get("saved_items", ())
                ],
            )

    barrier("ITEM", allocation_set_mutate, allocation_set_restore)

    def allocation_extra_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO orbit_launch_allocation_item(tenant_id, allocation_id,
                ordinal, slot_key, account_id, asset_id, asset_revision, asset_sha256)
                SELECT tenant_id, allocation_id, 9999, slot_key, account_id, asset_id,
                asset_revision, asset_sha256 FROM orbit_launch_allocation_item WHERE
                tenant_id=%s AND allocation_id=%s AND ordinal=0
                """,
                (tenant, target["body"]["allocation_id"]),
            )

    def allocation_extra_restore(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM orbit_launch_allocation_item WHERE tenant_id=%s AND
                allocation_id=%s AND ordinal=9999
                """,
                (tenant, target["body"]["allocation_id"]),
            )

    barrier("ITEM", allocation_extra_mutate, allocation_extra_restore)
    cases.append(LAUNCH_VALIDATION_CASES[9])

    def names_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_name_item SET "
                "name=CONCAT(name,'tamper'),sequence=sequence+100 WHERE tenant_id=%s AND "
                "reservation_id=%s AND ordinal=0",
                (tenant, target["body"]["name_reservation_id"]),
            )

    def names_restore(target):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_name_item SET "
                "name=LEFT(name,CHAR_LENGTH(name)-6),sequence=sequence-100 WHERE "
                "tenant_id=%s AND reservation_id=%s AND ordinal=0",
                (tenant, target["body"]["name_reservation_id"]),
            )

    barrier("ITEM", names_mutate, names_restore)

    def names_set_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                SELECT ordinal, slot_key, name, sequence FROM orbit_launch_name_item
                WHERE tenant_id=%s AND reservation_id=%s ORDER BY ordinal
                """,
                (tenant, target["body"]["name_reservation_id"]),
            )
            target["saved_names"] = cursor.fetchall()
            cursor.execute(
                "DELETE FROM orbit_launch_name_item WHERE tenant_id=%s AND reservation_id=%s",
                (tenant, target["body"]["name_reservation_id"]),
            )

    def names_set_restore(target):
        with admin.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO orbit_launch_name_item(tenant_id, reservation_id, ordinal,
                slot_key, name, sequence) VALUES(%s, %s, %s, %s, %s, %s)
                """,
                [
                    (tenant, target["body"]["name_reservation_id"], *row)
                    for row in target.get("saved_names", ())
                ],
            )

    barrier("ITEM", names_set_mutate, names_set_restore)

    def names_extra_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO orbit_launch_name_item(tenant_id, reservation_id, ordinal,
                slot_key, name, sequence) SELECT tenant_id, reservation_id, 9999,
                slot_key, name, sequence FROM orbit_launch_name_item WHERE
                tenant_id=%s AND reservation_id=%s AND ordinal=0
                """,
                (tenant, target["body"]["name_reservation_id"]),
            )

    def names_extra_restore(target):
        with admin.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM orbit_launch_name_item WHERE tenant_id=%s AND
                reservation_id=%s AND ordinal=9999
                """,
                (tenant, target["body"]["name_reservation_id"]),
            )

    barrier("ITEM", names_extra_mutate, names_extra_restore)
    cases.append(LAUNCH_VALIDATION_CASES[10])
    fault = new()
    fault_head = write()
    before = snapshot()
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER validation_fixture_fail BEFORE INSERT ON "
            "orbit_launch_outbox FOR EACH ROW SIGNAL SQLSTATE '45000' SET "
            "MESSAGE_TEXT='ISOLATED_VALIDATION_1644'"
        )
    try:
        from pymysql.err import MySQLError

        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orbit_launch_outbox(tenant_id, event_id, state,
                    created_at) VALUES(%s, %s, 'PENDING', UTC_TIMESTAMP(3))
                    """,
                    (tenant, str(uuid4())),
                )
        except MySQLError as failure:
            assert failure.args[0] == 1644
        else:
            raise AssertionError("1644故障注入未实际触发")
        finally:
            admin.rollback()
        checked(validate(fault, head=fault_head), 503)
        assert snapshot() == before
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER validation_fixture_fail")
    cases.append(LAUNCH_VALIDATION_CASES[11])
    from pymysql.err import MySQLError

    for statement, errorcode in (
        (
            "UPDATE orbit_launch_validation SET expires_at=validated_at+INTERVAL 1 "
            "SECOND WHERE tenant_id=%s AND plan_id=%s",
            3819,
        ),
        (
            "UPDATE orbit_launch_validation SET "
            "allocation_id='00000000-0000-0000-0000-000000000001' WHERE tenant_id=%s "
            "AND plan_id=%s",
            1452,
        ),
    ):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, (tenant, item["id"]))
        except MySQLError as failure:
            assert failure.args[0] == errorcode
        else:
            raise AssertionError("预检DB约束未拒绝坏记录")
        finally:
            admin.rollback()
    cases.append(LAUNCH_VALIDATION_CASES[12])

    def scope_mutate(target):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )

    def scope_restore(target):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision-1 WHERE tenant_id=%s", (tenant,)
            )

    barrier("SCOPE", scope_mutate, scope_restore)
    cases.append(LAUNCH_VALIDATION_CASES[13])

    blocked = []
    if cipher is None:
        blocked = LAUNCH_VALIDATION_CASES[14:]
    else:
        from sqlalchemy import URL, text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from orbit_api.directory_tokens import DirectoryTokens
        from orbit_api.errors import OrbitError
        from orbit_api.launch_validation_store import LaunchValidationStore

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

        async def boundaries():
            engine = create_async_engine(url, echo=False)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            tokens = DirectoryTokens(cipher)
            store = LaunchValidationStore(tokens, IsolatedValidationProvider(sessions))

            def timed_factory(at):
                class Timed:
                    def __init__(self):
                        self.session = sessions()

                    def __getattr__(self, name):
                        return getattr(self.session, name)

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        await self.session.close()

                    @asynccontextmanager
                    async def begin(self):
                        try:
                            async with self.session.begin():
                                await self.session.execute(text("SET time_zone='+00:00'"))
                                await self.session.execute(
                                    text("SET timestamp=:value"),
                                    {
                                        "value": Decimal(
                                            int(at.timestamp()) * 1000 + at.microsecond // 1000
                                        )
                                        / Decimal(1000)
                                    },
                                )
                                actual = (
                                    await self.session.execute(text("SELECT UTC_TIMESTAMP(3)"))
                                ).scalar_one()
                                assert actual == at.replace(tzinfo=None)
                                yield
                        finally:
                            await self.session.execute(text("SET timestamp=0"))
                            await self.session.rollback()

                return Timed

            async def boundary(start, end, should_succeed):
                target = new("TIME")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_launch_name_reservation SET naming_date=%s WHERE "
                        "tenant_id=%s AND id=%s",
                        (
                            (start + timedelta(hours=8)).date(),
                            tenant,
                            target["body"]["name_reservation_id"],
                        ),
                    )
                admin.commit()
                auth, key = headers["Authorization"], str(uuid4())
                csrf = tokens.issue(
                    "DIRECTORY_CSRF_V1", {"binding": tokens.session_binding(auth, 1, tenant)}
                )
                prepared = await store.prepare(
                    timed_factory(start), 1, auth, csrf, key, target["body"], target["id"], 1
                )
                factory = timed_factory(end)
                try:
                    async with factory() as session, session.begin():
                        result = await store.validate(
                            session,
                            1,
                            auth,
                            csrf,
                            key,
                            target["body"],
                            target["id"],
                            1,
                            str(uuid4()),
                            prepared,
                        )
                        assert should_succeed and result["valid"]
                except OrbitError as error:
                    assert (
                        not should_succeed and error.status == 409 and error.code == "STALE_PREVIEW"
                    )
                assert state(target) == (("VALIDATED", 2) if should_succeed else ("DRAFT", 1))

            try:
                start = datetime(2027, 1, 8, 8, tzinfo=UTC)
                for offset in (-1, 0, 1):
                    await boundary(
                        start, start + timedelta(minutes=15, milliseconds=offset), offset == -1
                    )
                cases.append(LAUNCH_VALIDATION_CASES[14])
                start = datetime(2027, 1, 8, 15, 59, 58, tzinfo=UTC)
                await boundary(start, datetime(2027, 1, 8, 15, 59, 59, 999000, tzinfo=UTC), True)
                await boundary(start, datetime(2027, 1, 8, 16, tzinfo=UTC), False)
                cases.append(LAUNCH_VALIDATION_CASES[15])
            finally:
                await engine.dispose()

        asyncio.run(boundaries())
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_task")
        assert cursor.fetchone()[0] == initial_tasks
    return {
        "blocked_cases": blocked,
        "platform_requests": 0,
        "clock_scope": "SQL_SESSION_TIME_INJECTION_NOT_NATURAL_HTTP_WAIT",
    }
