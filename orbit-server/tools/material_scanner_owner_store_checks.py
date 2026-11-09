"""037真实MySQL短事务专项；仅UUID隔离库，无HTTP运维写入口或真实进程动作。"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_SCANNER_OWNER_STORE_CASES = [
    "pythonMaterialScannerOwnerActualStartingAuditOutboxAtomicSafeFields",
    "pythonMaterialScannerOwnerActualLifecycleOrderAndBoundedSequenceRead",
    "pythonMaterialScannerOwnerExactReplayNoDuplicateAuditOrOutbox",
    "pythonMaterialScannerOwnerEventIdPayloadConflictCannotRewriteHistory",
    "pythonMaterialScannerOwnerDifferentEventSameActionCannotDuplicate",
    "pythonMaterialScannerOwnerSourceChangeCannotRebindExistingInstance",
    "pythonMaterialScannerOwnerIllegalOrderTimeRegressionAndAlternateTerminalRejected",
    "pythonMaterialScannerOwnerAudit1644RollsBackInstanceAuditAndOutbox",
    "pythonMaterialScannerOwnerOutbox1644RollbackRetryCommitsExactlyOnce",
    "pythonMaterialScannerOwnerConcurrentDuplicateOneEventOneReplay",
    "pythonMaterialScannerOwnerOutboxForeignKeyAndGlobalInstanceUniqueness",
    "pythonMaterialScannerOwnerActualExplainSequenceAndPendingWatermarks",
    "pythonMaterialScannerOwnerInjectedProcessCannotPublishWhenActualAuditCommitFails",
]


def validate_owner_store_target(admin, database):
    if (
        not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("037仅允许主线本机13306 UUID隔离数据库")


def run_material_scanner_owner_store_checks(admin, database, cases):
    validate_owner_store_target(admin, database)
    from orbit_api.errors import OrbitError
    from orbit_api.material_scanner_owner_store import (
        SOURCE_FIELDS,
        append_owner_event,
        create_owner_audit_sink,
        read_owner_events,
    )

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database, "实际数据库不是传入的UUID隔离库"
    admin.commit()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def fixture():
        return {
            "event_id": str(uuid4()),
            "profile_id": "owner-it-" + uuid4().hex[:12],
            "definition_revision": 1,
            "instance_id": str(uuid4()),
            "action": "STARTING",
            "occurred_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            **{field: "a" * 64 for field in SOURCE_FIELDS},
        }

    def next_event(original, action, step):
        return {
            **original,
            "event_id": str(uuid4()),
            "action": action,
            "occurred_at": (
                datetime.fromisoformat(original["occurred_at"]) + timedelta(microseconds=step)
            ).isoformat(),
        }

    def snapshot(event):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,sequence_no FROM orbit_scanner_owner_instance WHERE instance_id=%s",
                (event["instance_id"],),
            )
            head = cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_scanner_owner_audit WHERE instance_id=%s",
                (event["instance_id"],),
            )
            audit = cursor.fetchone()[0]
            cursor.execute(
                """SELECT COUNT(*) FROM orbit_scanner_owner_outbox o
                JOIN orbit_scanner_owner_audit a ON a.event_id=o.event_id WHERE a.instance_id=%s""",
                (event["instance_id"],),
            )
            outbox = cursor.fetchone()[0]
        admin.commit()
        return head, audit, outbox

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        sink = create_owner_audit_sink(sessions)

        async def append(event):
            async with sessions() as session, session.begin():
                return await append_owner_event(session, event)

        async def rejected(event, code):
            try:
                await append(event)
            except OrbitError as error:
                assert error.status == 503 and error.code == code, (error.status, error.code)
            else:
                raise AssertionError("037必须拒绝不一致事件")

        try:
            original = fixture()
            first = await sink(original)
            assert not first.replayed and first.sequence_no == 1
            assert snapshot(original) == (("STARTING", 1), 1, 1)
            with admin.cursor() as cursor:
                cursor.execute(
                    """SELECT COLUMN_NAME FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=%s AND TABLE_NAME='orbit_scanner_owner_audit'""",
                    (database,),
                )
                columns = {row[0] for row in cursor.fetchall()}
                assert not columns.intersection(
                    {
                        "pid",
                        "port",
                        "config_file",
                        "executable",
                        "password",
                        "token",
                        "request_json",
                    }
                )
            admin.commit()
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[0])

            started = next_event(original, "STARTED", 1)
            stopped = next_event(original, "STOPPED", 2)
            await append(started)
            await append(stopped)
            async with sessions() as session:
                first_page = await read_owner_events(
                    session, original["profile_id"], 1, original["instance_id"], limit=1
                )
                rest = await read_owner_events(
                    session,
                    original["profile_id"],
                    1,
                    original["instance_id"],
                    after_sequence=1,
                    limit=2,
                )
            assert [row["sequence_no"] for row in first_page + rest] == [1, 2, 3]
            assert [row["action"] for row in first_page + rest] == [
                "STARTING",
                "STARTED",
                "STOPPED",
            ]
            assert snapshot(original) == (("STOPPED", 3), 3, 3)
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[1])

            before = snapshot(original)
            replay = await append(original)
            assert replay.replayed and snapshot(original) == before
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[2])
            await rejected(
                {**original, "occurred_at": started["occurred_at"]}, "SCANNER_OWNER_AUDIT_CONFLICT"
            )
            assert snapshot(original) == before
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[3])
            await rejected({**original, "event_id": str(uuid4())}, "SCANNER_OWNER_AUDIT_CONFLICT")
            assert snapshot(original) == before
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[4])
            await rejected(
                {**original, "source_sha256": "b" * 64}, "SCANNER_OWNER_AUDIT_SOURCE_CHANGED"
            )
            assert snapshot(original) == before
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[5])

            unordered = fixture()
            await rejected(
                next_event(unordered, "STARTED", 1), "SCANNER_OWNER_AUDIT_SOURCE_CHANGED"
            )
            assert snapshot(unordered) == (None, 0, 0)
            await append(unordered)
            await rejected(
                next_event(unordered, "STOPPED", 1), "SCANNER_OWNER_AUDIT_SEQUENCE_INVALID"
            )
            backwards = next_event(unordered, "STARTED", -1)
            await rejected(backwards, "SCANNER_OWNER_AUDIT_SEQUENCE_INVALID")
            await rejected(
                next_event(original, "INVALIDATED", 3), "SCANNER_OWNER_AUDIT_SEQUENCE_INVALID"
            )
            assert snapshot(unordered) == (("STARTING", 1), 1, 1) and snapshot(original) == before
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[6])

            for index, table in (
                (7, "orbit_scanner_owner_audit"),
                (8, "orbit_scanner_owner_outbox"),
            ):
                rollback = fixture()
                trigger = "owner037_" + uuid4().hex
                with admin.cursor() as cursor:
                    cursor.execute(f"""CREATE TRIGGER {trigger} BEFORE INSERT ON {table}
                      FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='owner037-fixture'""")
                admin.commit()
                try:
                    try:
                        await append(rollback)
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1644
                    else:
                        raise AssertionError("实际SQL触发器必须抛出1644")
                    assert snapshot(rollback) == (None, 0, 0)
                    try:
                        await sink(rollback)
                    except OrbitError as error:
                        assert (
                            error.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE" and error.status == 503
                        )
                    else:
                        raise AssertionError("真实1644错误必须阻止成功返回")
                    assert snapshot(rollback) == (None, 0, 0)
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute(f"DROP TRIGGER {trigger}")
                    admin.commit()
                retry = await sink(rollback)
                assert not retry.replayed and snapshot(rollback) == (("STARTING", 1), 1, 1)
                assert (await sink(rollback)).replayed and snapshot(rollback) == (
                    ("STARTING", 1),
                    1,
                    1,
                )
                cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[index])

            duplicate = fixture()
            results = await asyncio.gather(append(duplicate), append(duplicate))
            assert sorted(row.replayed for row in results) == [False, True]
            assert snapshot(duplicate) == (("STARTING", 1), 1, 1)
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[9])

            async with sessions() as session:
                try:
                    async with session.begin():
                        await session.execute(
                            text("INSERT INTO orbit_scanner_owner_outbox(event_id) VALUES(:id)"),
                            {"id": str(uuid4())},
                        )
                except DBAPIError as error:
                    assert error.orig.args[0] == 1452
                else:
                    raise AssertionError("孤立outbox必须外键拒绝")
            reused = {**duplicate, "event_id": str(uuid4()), "profile_id": "different-owner"}
            await rejected(reused, "SCANNER_OWNER_AUDIT_SOURCE_CHANGED")
            assert snapshot(duplicate) == (("STARTING", 1), 1, 1)
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[10])

            with admin.cursor() as cursor:
                cursor.execute(
                    """EXPLAIN SELECT event_id,sequence_no FROM orbit_scanner_owner_audit
                  WHERE profile_id=%s AND definition_revision=1 AND instance_id=%s
                  AND sequence_no>0 ORDER BY sequence_no LIMIT 2""",
                    (original["profile_id"], original["instance_id"]),
                )
                columns = [item[0] for item in cursor.description]
                explain = dict(zip(columns, cursor.fetchone(), strict=True))
                assert explain["key"] == "uq_scanner_owner_sequence" and explain["type"] in {
                    "range",
                    "ref",
                }, (explain["key"], explain["type"])
                cursor.execute("""EXPLAIN SELECT event_id FROM orbit_scanner_owner_outbox
                  WHERE processed_at IS NULL ORDER BY created_at,event_id LIMIT 200""")
                columns = [item[0] for item in cursor.description]
                pending = dict(zip(columns, cursor.fetchone(), strict=True))
                assert pending["key"] == "idx_scanner_owner_outbox_pending" and pending["type"] in {
                    "ref",
                    "range",
                }, (pending["key"], pending["type"])
            admin.commit()
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[11])

            # 只有数据库审计是真实组件；全部进程/健康/文件I/O显式替身，不冒充原生启动。
            from pathlib import Path
            from types import SimpleNamespace

            from orbit_api.material_antivirus import ClamdPolicy
            from orbit_api.material_scanner_owner import MaterialScannerOwner
            from orbit_api.material_scanner_owner_definition import ScannerOwnerDefinition
            from orbit_api.material_scanner_registry import (
                MaterialScannerRegistry,
                ScannerProbeResult,
            )

            observed, process_events = [], []
            registry = MaterialScannerRegistry()

            class ProcessFixture:
                def require_job_support(self):
                    pass

                def port_available(self, *args):
                    return True

                def spawn(self, *args):
                    process_events.append("injected-spawn")
                    return SimpleNamespace(
                        pid=123,
                        created_at_us=int(
                            (datetime.now(UTC) - timedelta(seconds=1)).timestamp() * 1_000_000
                        ),
                    )

                def alive(self, *args):
                    return True

                def close_owned(self, *args):
                    assert not registry.candidates()
                    process_events.append("injected-close")

            async def audit(event):
                observed.append(dict(event))
                return await sink(event)

            async def health(scanner, deadline):
                private = MaterialScannerRegistry()
                return ScannerProbeResult(
                    "READ_VERIFIED",
                    "注入纯处理夹具非实际扫描",
                    private.publish(scanner, "内部SQL夹具"),
                )

            now = datetime.now(UTC)
            root = Path.cwd().resolve() / ".never-created-owner-sql-fixture"
            definition = ScannerOwnerDefinition(
                "owner-sql-no-process",
                1,
                "SQL提交失败拒绝发布夹具",
                root,
                root / "owned",
                root / "not-executable.exe",
                "a" * 64,
                root / "owned/config",
                "b" * 64,
                root / "database",
                tuple((name, "c" * 64) for name in ("main.cvd", "daily.cvd", "bytecode.cvd")),
                root / "unread-approval",
                "d" * 64,
                now - timedelta(seconds=1),
                now + timedelta(minutes=10),
                ClamdPolicy(
                    19311,
                    "1.5.4",
                    28177,
                    now - timedelta(hours=1),
                    "b" * 64,
                    600 * 1024**2,
                    1000 * 1024**2,
                    600 * 1024**2,
                    True,
                ),
            )
            owner = MaterialScannerOwner(
                registry,
                audit_sink=audit,
                adapter=ProcessFixture(),
                files_verifier=lambda *args: "e" * 64,
                health=health,
            )
            trigger = "owner037_" + uuid4().hex
            with admin.cursor() as cursor:
                cursor.execute(f"""CREATE TRIGGER {trigger}
                  BEFORE INSERT ON orbit_scanner_owner_audit
                  FOR EACH ROW BEGIN IF NEW.action='STARTED' THEN
                  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='owner037-fixture'; END IF; END""")
            admin.commit()
            try:
                try:
                    await owner.start(definition)
                except OrbitError as error:
                    assert error.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"
                else:
                    raise AssertionError("实际持久审计失败不得发布")
                assert [row["action"] for row in observed] == ["STARTING", "STARTED"]
                assert process_events == ["injected-spawn", "injected-close"]
                assert not registry.candidates() and snapshot(observed[0]) == (
                    ("STARTING", 1),
                    1,
                    1,
                )
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER {trigger}")
                admin.commit()
            cases.append(MATERIAL_SCANNER_OWNER_STORE_CASES[12])
            return {
                "case_count": len(MATERIAL_SCANNER_OWNER_STORE_CASES),
                "sequence_index": explain["key"],
                "outbox_index": pending["key"],
                "actual_process_start_tested": False,
            }
        finally:
            await engine.dispose()

    return asyncio.run(run())
