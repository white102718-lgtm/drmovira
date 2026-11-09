"""033真实持久Task/HTTP专项；ISOLATED_TEST不代表平台预检或生产执行。"""

import asyncio
import hashlib
import re
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TASK_CORE_CASES = [
    "pythonTaskCoreProductionProviderMissingBeforeAnyTaskWrite",
    "pythonTaskCoreRealPlanVersionAndFrozenOwnershipNotWorker",
    "pythonTaskCoreHalfManifestHiddenAndNoSendGate",
    "pythonTaskCoreSamePlanRevisionReplaysOneStableTask",
    "pythonTaskCoreOutOfOrderOrWrongHashChunkRejected",
    "pythonTaskCoreActualCompleteManifestStrictTaskAndFirstTwoHundred",
    "pythonTaskCoreAllNodesKeysetAndParentIdsMatchCompleteDag",
    "pythonTaskCoreSparseListActualCountAndThreeRoleScopes",
    "pythonTaskCoreStrictOriginalFiltersAndRealNodeKeyPrefix",
    "pythonTaskCoreForeignObjectsAndRevokedTaskReadDenied",
    "pythonTaskCoreNodeAndListCursorsBindQueryVersionAndCurrentScope",
    "pythonTaskCoreCorruptPersistedNodeCannotPublishFakeSuccess",
    "pythonTaskCoreAuditOutboxFailureRollsBackWholePublication",
    "pythonTaskCoreSourceVersionDriftCannotPublishOldManifest",
    "pythonTaskCoreCrossTaskParentForeignKeyRejected",
    "pythonTaskCoreRealInitialEventAuditOutboxAndIdempotentFinalize",
]
TASK_CORE_CAPACITY_CASES = [
    "pythonTaskCoreActualOneHundredThousandDagNodesPersistAndTraverseWholeHash",
    "pythonTaskCoreOverOneHundredThousandActualDagRejectedBeforeTaskCreation",
]


def prepare_identities(client, admin, headers, password, cache):
    from fixture_login import fixture_login

    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id IN(990370,990371,990372)")
        assert cursor.fetchone()[0] == 0, "Task专用身份ID已占用，拒绝覆盖"
    cap = client.get("/api/v1/roles/capabilities", headers=headers)
    assert cap.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": cap.json()["csrf_token"],
            "Idempotency-Key": "task-read-role-" + uuid4().hex,
        },
        json={
            "name": "Task只读专项-" + uuid4().hex[:12],
            "menu_codes": ["launch"],
            "permission_codes": ["tasks.read"],
        },
    )
    assert role.status_code == 201
    identities = {}
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        native_role = cursor.fetchone()[0]
        for native, data_role in ((990370, "TEAM_ADMIN"), (990371, "USER"), (990372, "USER")):
            owner, name = str(uuid4()), "task_reader_" + uuid4().hex[:12]
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,'任务只读夹具',%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (native, name, name + "@fixture.example.org"),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,%s)",
                (native, tenant, data_role),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
                "invited,created_at) VALUES(%s,%s,%s,%s,'任务只读夹具',0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team),
            )
            if data_role == "TEAM_ADMIN":
                cursor.execute(
                    "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
                    "VALUES(%s,%s,%s)",
                    (tenant, native, team),
                )
            identities[native] = {"actor_id": native, "owner": owner, "username": name}
    admin.commit()
    for identity in identities.values():
        login = fixture_login(
            client, cache, {"username": identity.pop("username"), "password": password}
        )
        assert login.status_code == 200 and login.json().get("token")
        identity["headers"] = {"Authorization": "Bearer " + login.json()["token"]}
        assert client.get("/api/v1/launch-plans", headers=identity["headers"]).status_code == 403
    return tenant, root_owner, team, native_role, identities


def run_task_core_checks(
    client, admin, headers, password, cache, database, cases, *, include_capacity=False
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("Task专项仅允许主线当前13306/UUID隔离库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
    tenant, root_owner, team, native_role, identities = prepare_identities(
        client, admin, headers, password, cache
    )
    owner = identities[990371]["owner"]
    own_headers, team_headers, other_headers = (
        identities[key]["headers"] for key in (990371, 990370, 990372)
    )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def main():
        from task_core_fixture import compile_dag, insert_plan, plan

        from orbit_api.errors import OrbitError
        from orbit_api.task_contract import CHUNK_SIZE, node_id, validate_dag
        from orbit_api.task_manifest import TaskManifestStore

        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = TaskManifestStore()

        async def call(operation):
            async with sessions() as session, session.begin():
                return await operation(session)

        async def denied(operation, status=409):
            try:
                await call(operation)
            except OrbitError as error:
                assert error.status == status
            else:
                raise AssertionError("应拒绝的Task操作未被拒绝")

        def get(task, identity=headers):
            return client.get("/api/v1/tasks/" + task, headers=identity)

        def task_page(identity=headers, **query):
            return client.get("/api/v1/tasks", params=query, headers=identity)

        async def new(*, copies=300, branches=None):
            value = plan(owner, team, copies=copies, branches=branches)
            graph = compile_dag(value)
            origin = await call(lambda s: insert_plan(s, tenant, value))
            identifier = await call(
                lambda s: store.begin(
                    s, 1, origin, 1, graph, str(uuid4()), producer="ISOLATED_TEST"
                )
            )
            return origin, identifier, graph, validate_dag(graph)

        async def persist(task, records):
            for offset in range(0, len(records), CHUNK_SIZE):
                await call(
                    lambda s, offset=offset: store.append(
                        s, 1, task, offset // CHUNK_SIZE, records[offset : offset + CHUNK_SIZE]
                    )
                )

        try:
            await denied(lambda s: store.begin(s, 1, str(uuid4()), 1, None, str(uuid4())), 503)
            cases.append(TASK_CORE_CASES[0])
            origin, task, graph, records = await new()
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT owner_user_id,owner_team_id,source_plan_id,source_revision,"
                    "producer_kind FROM orbit_task WHERE tenant_id=%s AND id=%s",
                    (tenant, task),
                )
                assert cursor.fetchone() == (owner, team, origin, 1, "ISOLATED_TEST")
            assert owner != root_owner
            cases.append(TASK_CORE_CASES[1])
            assert get(task).status_code == 404
            await call(lambda s: store.append(s, 1, task, 0, records[:CHUNK_SIZE]))
            assert get(task).status_code == 404
            assert task_page().json()["items"] == []
            await denied(lambda s: store.finalize(s, 1, task))
            cases.append(TASK_CORE_CASES[2])
            replay = await call(
                lambda s: store.begin(
                    s, 1, origin, 1, graph, str(uuid4()), producer="ISOLATED_TEST"
                )
            )
            assert replay == task
            concurrent = await asyncio.gather(
                *[
                    call(
                        lambda s: store.begin(
                            s, 1, origin, 1, graph, str(uuid4()), producer="ISOLATED_TEST"
                        )
                    )
                    for _ in range(2)
                ]
            )
            assert concurrent == [task, task]
            await call(lambda s: store.append(s, 1, task, 0, records[:CHUNK_SIZE]))
            cases.append(TASK_CORE_CASES[3])
            await denied(lambda s: store.append(s, 1, task, 2, records[1000:]))
            bad = [dict(row) for row in records[500:1000]]
            bad[0]["purpose"] = "WRONG_HASH"
            await denied(lambda s: store.append(s, 1, task, 1, bad))
            await persist(task, records)
            cases.append(TASK_CORE_CASES[4])
            await call(lambda s: store.finalize(s, 1, task))
            response = get(task)
            assert response.status_code == 200
            result = response.json()
            task_keys = {
                "id",
                "revision",
                "ownership",
                "state",
                "nodes",
                "latest_event_id",
                "needs_manual_reconciliation",
                "created_at",
                "node_count",
                "next_node_cursor",
                "execution_mode",
            }
            node_keys = {
                "id",
                "node_key",
                "parent_ids",
                "kind",
                "state",
                "external_id",
                "attempt",
                "error_code",
                "error_message",
                "retryable",
                "configuration_state",
                "delivery_state",
                "updated_at",
                "execution_mode",
            }
            assert set(result) == task_keys and len(result["nodes"]) == 200
            assert result["node_count"] == len(records) == 1206
            assert result["ownership"] == {"owner_user_id": owner, "owner_team_id": team}
            assert result["state"] == "QUEUED" and result["next_node_cursor"]
            for node in result["nodes"]:
                assert set(node) == node_keys and node["state"] == "QUEUED"
                assert node["external_id"] is None and node["attempt"] == 0
                assert (
                    node["configuration_state"] == "UNVERIFIED"
                    and node["delivery_state"] == "UNKNOWN"
                )
            assert response.headers["cache-control"] == "no-store"
            cases.append(TASK_CORE_CASES[5])

            def traverse(identifier, initial, expected, *, page_size=50):
                collected = list(initial["nodes"])
                cursor = initial["next_node_cursor"]
                while cursor:
                    page_query = {"cursor": cursor}
                    if page_size != 50:
                        page_query["page_size"] = page_size
                    response = client.get(
                        f"/api/v1/tasks/{identifier}/nodes",
                        params=page_query,
                        headers=own_headers,
                    )
                    assert response.status_code == 200
                    page = response.json()
                    assert set(page) == {"items", "next_cursor", "data_as_of", "scope_version"}
                    collected.extend(page["items"])
                    cursor = page["next_cursor"]
                assert [row["node_key"] for row in collected] == [
                    row["node_key"] for row in expected
                ]
                assert len({row["id"] for row in collected}) == len(expected)
                for actual, frozen in zip(collected, expected, strict=True):
                    assert actual["id"] == node_id(identifier, frozen["node_key"])
                    assert actual["parent_ids"] == [
                        node_id(identifier, parent) for parent in frozen["parent_keys"]
                    ]
                return collected

            traverse(task, get(task, own_headers).json(), records)
            cases.append(TASK_CORE_CASES[6])
            for _ in range(20):
                _, small, _, small_records = await new(copies=1)
                await persist(small, small_records)
                await call(lambda s, small=small: store.finalize(s, 1, small))
            for identity in (headers, own_headers, team_headers):
                listing = task_page(identity, page_size=20)
                assert listing.status_code == 200
                assert len(listing.json()["items"]) == 20 and listing.json()["next_cursor"]
                for item in listing.json()["items"]:
                    assert set(item) == task_keys and item["nodes"] == []
                    assert item["node_count"] > 0 and item["next_node_cursor"]
            assert task_page(other_headers).json()["items"] == []
            assert get(task, team_headers).status_code == get(task, own_headers).status_code == 200
            assert get(task, other_headers).status_code == 404
            cases.append(TASK_CORE_CASES[7])

            for query in (
                {"q": "name"},
                {"date_from": "2026-01-01"},
                {"channel_id": str(uuid4())},
                {"metric_profile_id": str(uuid4())},
                {"entity_type": "AD"},
                {"status": "SCHEDULED"},
            ):
                invalid_filter = task_page(**query)
                assert invalid_filter.status_code == 422
                assert invalid_filter.json()["code"] == "FIELD_VALIDATION_FAILED"
                assert invalid_filter.json()["field_errors"][0]["path"] == "/" + next(iter(query))
            assert task_page(unrecognized="x").status_code == 400
            for invalid_q in ("x" * 101, "a\nb", "\u200b", "   "):
                invalid_text = client.get(
                    f"/api/v1/tasks/{task}/nodes", params={"q": invalid_q}, headers=own_headers
                )
                assert invalid_text.status_code == 422
                assert invalid_text.json()["code"] == "FIELD_VALIDATION_FAILED"
                assert invalid_text.json()["field_errors"][0]["path"] == "/q"
            assert task_page(operator_user_id=identities[990372]["owner"]).json()["items"] == []
            prefix = records[0]["node_key"][:30]
            filtered = client.get(
                f"/api/v1/tasks/{task}/nodes", params={"q": prefix}, headers=own_headers
            )
            assert filtered.status_code == 200 and filtered.json()["items"]
            assert all(row["node_key"].startswith(prefix) for row in filtered.json()["items"])
            cases.append(TASK_CORE_CASES[8])
            assert get(str(uuid4()), own_headers).status_code == 404
            assert get(task, own_headers | {"X-Target-Tenant": str(uuid4())}).status_code == 403
            with admin.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=310206", (native_role,)
                )
            admin.commit()
            try:
                assert get(task, own_headers).status_code == 403
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,310206)",
                        (native_role,),
                    )
                admin.commit()
            cases.append(TASK_CORE_CASES[9])

            node_cursor = result["next_node_cursor"]
            assert (
                client.get(
                    f"/api/v1/tasks/{task}/nodes",
                    params={"cursor": node_cursor, "page_size": 200},
                    headers=headers,
                ).status_code
                == 409
            )
            own_detail = get(task, own_headers).json()
            # root签名cursor不能借给USER，即使该USER确实拥有任务。
            assert (
                client.get(
                    f"/api/v1/tasks/{task}/nodes",
                    params={"cursor": node_cursor},
                    headers=own_headers,
                ).status_code
                == 409
            )
            traverse(task, own_detail, records)
            listing = task_page(own_headers, page_size=20).json()
            assert (
                task_page(
                    own_headers, page_size=20, cursor=listing["next_cursor"], status="QUEUED"
                ).status_code
                == 409
            )
            cases.append(TASK_CORE_CASES[10])

            _, corrupt, _, corrupt_records = await new(copies=1)
            await persist(corrupt, corrupt_records)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_task_node SET external_id='123' "
                    "WHERE tenant_id=%s AND task_id=%s LIMIT 1",
                    (tenant, corrupt),
                )
            admin.commit()
            await denied(lambda s: store.finalize(s, 1, corrupt))
            assert get(corrupt).status_code == 404
            # 035允许历史全NULL读取；发布不能猜头，部分NULL必须数据库CHECK拒绝。
            from pymysql.err import MySQLError

            try:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_task SET dag_schema_version=NULL "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, task),
                    )
                admin.commit()
            except MySQLError as failure:
                admin.rollback()
                assert failure.args[0] == 3819
            else:
                raise AssertionError("DAG头部分NULL未被CHECK拒绝")
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_task SET dag_schema_version=NULL,plan_input_hash=NULL,"
                    "allocation_input_hash=NULL WHERE tenant_id=%s AND id=%s",
                    (tenant, task),
                )
            admin.commit()
            try:
                assert get(task, own_headers).status_code == 200
                await denied(lambda s: store.finalize(s, 1, task))
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_task SET dag_schema_version=%s,plan_input_hash=%s,"
                        "allocation_input_hash=%s WHERE tenant_id=%s AND id=%s",
                        (
                            graph.schema_version,
                            graph.plan_input_hash,
                            graph.allocation_input_hash,
                            tenant,
                            task,
                        ),
                    )
                admin.commit()
            cases.append(TASK_CORE_CASES[11])

            _, rollback_task, _, rollback_records = await new(copies=1)
            await persist(rollback_task, rollback_records)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER task_core_fixture_fail BEFORE INSERT ON orbit_task_outbox "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'"
                )
            try:
                try:
                    await call(lambda s: store.finalize(s, 1, rollback_task))
                except DBAPIError as failure:
                    assert failure.orig.args[0] == 1644
                else:
                    raise AssertionError("审计outbox故障没有回滚")
                assert get(rollback_task).status_code == 404
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_task_event WHERE tenant_id=%s AND task_id=%s",
                        (tenant, rollback_task),
                    )
                    assert cursor.fetchone()[0] == 0
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER task_core_fixture_fail")
            await call(lambda s: store.finalize(s, 1, rollback_task))
            cases.append(TASK_CORE_CASES[12])

            drift_origin, drift_task, _, drift_records = await new(copies=1)
            await persist(drift_task, drift_records)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_launch_plan SET revision=2 WHERE tenant_id=%s AND id=%s",
                    (tenant, drift_origin),
                )
            admin.commit()
            await denied(lambda s: store.finalize(s, 1, drift_task))
            # 已完整Task所有权来自原版本，当前计划转属不重写历史读取。
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_launch_plan SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                    (root_owner, tenant, origin),
                )
            admin.commit()
            assert get(task, own_headers).json()["ownership"]["owner_user_id"] == owner
            cases.append(TASK_CORE_CASES[13])

            from pymysql.err import IntegrityError

            try:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO orbit_task_edge(tenant_id,task_id,child_id,parent_id) "
                        "VALUES(%s,%s,%s,%s)",
                        (
                            tenant,
                            task,
                            node_id(task, records[1]["node_key"]),
                            node_id(rollback_task, rollback_records[0]["node_key"]),
                        ),
                    )
                admin.commit()
            except IntegrityError as failure:
                admin.rollback()
                assert failure.args[0] == 1452
            else:
                raise AssertionError("跨Task父边未被拒绝")
            cases.append(TASK_CORE_CASES[14])
            await call(lambda s: store.finalize(s, 1, rollback_task))
            with admin.cursor() as cursor:
                for table in ("orbit_task_event", "orbit_task_audit", "orbit_task_outbox"):
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s AND task_id=%s",
                        (tenant, rollback_task),
                    )
                    assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "SELECT sequence,task_revision,state,node_id FROM orbit_task_event "
                    "WHERE tenant_id=%s AND task_id=%s",
                    (tenant, rollback_task),
                )
                assert cursor.fetchone() == (1, 1, "QUEUED", None)
            cases.append(TASK_CORE_CASES[15])

            if include_capacity:
                _, huge, huge_graph, huge_records = await new(branches=7142)
                assert len(huge_records) == huge_graph.total_dag_node_count == 100000
                await persist(huge, huge_records)
                await call(lambda s: store.finalize(s, 1, huge))
                assert len(get(huge, own_headers).json()["nodes"]) == 200
                first = client.get(
                    f"/api/v1/tasks/{huge}/nodes", params={"page_size": 200}, headers=own_headers
                )
                assert first.status_code == 200
                actual = traverse(
                    huge,
                    {
                        "nodes": first.json()["items"],
                        "next_node_cursor": first.json()["next_cursor"],
                    },
                    huge_records,
                    page_size=200,
                )
                expected_hash = hashlib.sha256(
                    "\n".join(row["node_key"] for row in huge_records).encode()
                ).hexdigest()
                actual_hash = hashlib.sha256(
                    "\n".join(row["node_key"] for row in actual).encode()
                ).hexdigest()
                assert actual_hash == expected_hash
                cases.append(TASK_CORE_CAPACITY_CASES[0])
                try:
                    compile_dag(plan(owner, team, branches=7143))
                except OrbitError as failure:
                    assert failure.code == "PLAN_NODE_LIMIT"
                else:
                    raise AssertionError("超过十万真实DAG未被拒绝")
                cases.append(TASK_CORE_CAPACITY_CASES[1])
        finally:
            await engine.dispose()

    asyncio.run(main())
