"""待人工审核后显式运行的Windows所有者专项；导入无进程、端口或目录副作用。"""

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import time
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import psutil
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2] / ".runtime/tools/clamav-1.5.4"
PROTECTED_PID, PROTECTED_PORT, OWNED_PORT = 7492, 19310, 19311
MIN_AVAILABLE_BYTES, MIN_DISK_BYTES = 6 * 1024**3, 1024**3
WORK_SECONDS, CLEANUP_SECONDS = 360, 30
MATERIAL_SCANNER_OWNER_NATIVE_CASES = [
    "pythonMaterialScannerOwnerNativeResourceAndApprovedSourceGate",
    "pythonMaterialScannerOwnerNativeActualJobStartHealthyPngAndPersistentStarted",
    "pythonMaterialScannerOwnerNativeOccupied19311CannotStartSecondOwner",
    "pythonMaterialScannerOwnerNativeWithdrawJobCloseActualBirthExitAndProtectedUnchanged",
    "pythonMaterialScannerOwnerNativeActualStartedAudit1644CannotPublishAndClosesOwnedChild",
    "pythonMaterialScannerOwnerNativeFinalProtectedAttestationAndOwnedOnlyCleanup",
]


class ImmutablePngObjects:
    """固定内存bytes也遵循对象守卫协议；只允许同轮精确tenant/upload二元组。"""

    def __init__(self, tenant, upload, content):
        if any(
            not isinstance(value, str) or str(UUID(value)) != value for value in (tenant, upload)
        ):
            raise ValueError("内存对象夹具要求规范身份UUID")
        if not isinstance(content, bytes) or not 0 < len(content) <= 1024 * 1024:
            raise ValueError("内存安全PNG夹具必须是有界不可变bytes")
        self._identity, self._content = (tenant, upload), content

    def _require_identity(self, tenant, upload):
        if (tenant, upload) != self._identity:
            raise ValueError("内存对象夹具身份不匹配")

    def original(self, tenant, upload):
        self._require_identity(tenant, upload)
        return self

    def mutation_guard(self, tenant, upload):
        self._require_identity(tenant, upload)
        return nullcontext()  # bytes不可变，无磁盘写方；不能省略生产扫描器的协议调用。

    def open(self, mode):
        if mode != "rb":
            raise ValueError("内存安全PNG夹具只允许只读")
        return BytesIO(self._content)


def safe_scan_diagnostic(result):
    """仅固定枚举/错误码和proof存在性；禁止异常对象或路径进入断言日志。"""
    receipt = getattr(result, "receipt", None)
    state = getattr(receipt, "result", None)
    error = getattr(receipt, "error_code", None)
    return {
        "result": state
        if isinstance(state, str) and state in {"CLEAN", "INFECTED", "UNVERIFIED"}
        else "UNEXPECTED",
        "error_code": error
        if isinstance(error, str) and re.fullmatch(r"ANTIVIRUS_[A-Z_]{1,50}", error)
        else (None if error is None else "OTHER"),
        "proof_present": getattr(result, "proof", None) is not None,
    }


def validate_native_target(admin, database, *, platform=os.name):
    if (
        platform != "nt"
        or not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("原生所有者专项仅允许Windows本机13306 UUID隔离库")


def validate_owned_root(path, *, expected_root=ROOT):
    """只允许固定安装目录直属、未复用的UUID根；不接受用户自选安装目录。"""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("所有者夹具目录无效")
    if path.parent != expected_root or not re.fullmatch(r"owner-native-it-[a-f0-9]{32}", path.name):
        raise ValueError("所有者夹具必须位于固定UUID目录")
    # 已有目录只供finally复核，不允许链接穿越；首次创建另用exist_ok=False。
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            entry = item.lstat()
            if item.is_symlink() or getattr(entry, "st_file_attributes", 0) & 0x400:
                raise ValueError("所有者夹具目录拒绝链接或reparse")
    return path


def validate_resource_budget(available_bytes, free_disk_bytes):
    if (
        type(available_bytes) is not int
        or type(free_disk_bytes) is not int
        or available_bytes < MIN_AVAILABLE_BYTES
        or free_disk_bytes < MIN_DISK_BYTES
    ):
        raise ValueError("可用内存或磁盘不足，拒绝原生扫描进程专项")


def port_free(port=OWNED_PORT):
    if port != OWNED_PORT:
        raise ValueError("专项仅允许固定19311，不扫描其他端口")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            connection.bind(("127.0.0.1", OWNED_PORT))
        return True
    except OSError:
        return False


def _protected():
    from clamd_fixture_attestation import attest_fixture

    result = attest_fixture()
    if result["pid"] != PROTECTED_PID or result["listener"] != f"127.0.0.1:{PROTECTED_PORT}":
        raise ValueError("受保护原扫描夹具身份变化，拒绝原生专项")
    return result


def _sources(owned, deadline):
    from clamd_fixture_attestation import ARCHIVE_SHA256

    from orbit_api.material_antivirus import ClamdPolicy
    from orbit_api.material_scanner_owner_definition import (
        ScannerOwnerDefinition,
        file_hash,
        safe_path,
    )

    root = safe_path(ROOT, directory=True)
    if root != ROOT.resolve() or safe_path(owned, directory=True) != owned.resolve():
        raise ValueError("固定安装或自有目录身份异常")
    manifest_path = root / "trusted-fixture-manifest.json"
    manifest_sha = file_hash(manifest_path, 65536, deadline)
    manifest = json.loads(manifest_path.read_text("utf-8-sig"))
    if (
        manifest["engine_version"] != "1.5.4"
        or manifest["host"] != "127.0.0.1"
        or manifest["port"] != PROTECTED_PORT
        or manifest["official_distribution_gpg_fingerprint"]
        != "5BADCA2665EF59DCF8A23D8B707F0DB480836771"
    ):
        raise ValueError("固定已批准发行来源不匹配")
    archive = root / "clamav-1.5.4.win.x64.zip"
    if file_hash(archive, 512 * 1024**2, deadline) != ARCHIVE_SHA256:
        raise ValueError("固定官方发行归档摘要变化")
    executable = root / "unpacked/clamav-1.5.4.win.x64/clamd.exe"
    exe_sha = file_hash(executable, 256 * 1024**2, deadline)
    # _protected已把当前exe与固定已批准归档成员实际比较；此处仍逐文件钉住。
    protected = _protected()
    if protected["executable_sha256"] != exe_sha:
        raise ValueError("固定程序与批准归档成员不一致")
    database = root / "database"
    dbs = []
    for name in ("main", "daily", "bytecode"):
        expected = manifest["database"][name]["sha256"]
        if file_hash(database / (name + ".cvd"), 512 * 1024**2, deadline) != expected:
            raise ValueError("固定官方病毒库摘要变化")
        dbs.append((name + ".cvd", expected))
    config = owned / "clamd.conf"
    config.write_text(
        f"DatabaseDirectory {database}\nTCPSocket {OWNED_PORT}\nTCPAddr 127.0.0.1\n"
        f"Foreground yes\nTemporaryDirectory {owned}\n"
        "MaxFileSize 600M\nMaxScanSize 1000M\nStreamMaxLength 600M\n"
        "AlertExceedsMax yes\nMaxScanTime 30000\nMaxThreads 1\nMaxQueue 2\n",
        encoding="utf-8",
    )
    config_sha = file_hash(config, 65536, deadline)
    # 新receipt只是本轮来源绑定夹具；不伪造官方签名或重新验签结论。
    approval = owned / "approved-source-fixture.json"
    approval.write_text(
        json.dumps(
            {
                "scope": "local owned-process fixture; prior approval; no new GPG verification",
                "manifest_sha256": manifest_sha,
                "archive_sha256": ARCHIVE_SHA256,
                "executable_sha256": exe_sha,
                "database_sha256": dict(dbs),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    approval_sha = file_hash(approval, 65536, deadline)
    now = datetime.now(UTC)
    policy = ClamdPolicy(
        OWNED_PORT,
        "1.5.4",
        manifest["daily_db_version"],
        datetime.fromisoformat(manifest["daily_db_built_at"]),
        config_sha,
        600 * 1024**2,
        1000 * 1024**2,
        600 * 1024**2,
        True,
        deadline_seconds=30,
    )
    policy.validate(now)
    return ScannerOwnerDefinition(
        "native-owner-it",
        1,
        "原生受控实例隔离专项",
        root,
        owned,
        executable,
        exe_sha,
        config,
        config_sha,
        database,
        tuple(dbs),
        approval,
        approval_sha,
        now - timedelta(seconds=1),
        now + timedelta(minutes=10),
        policy,
        proof_ttl_seconds=300,
        startup_seconds=120,
        shutdown_seconds=10,
    )


def _same_process(pid, born):
    try:
        return round(psutil.Process(pid).create_time() * 1_000_000) == born
    except psutil.NoSuchProcess:
        return False


def run_material_scanner_owner_native_checks(admin, database, cases, *, progress=None):
    """仅主线审核授权后显式调用；与现有API/ClamD生命周期无接线。"""
    validate_native_target(admin, database)
    from orbit_api.errors import OrbitError
    from orbit_api.material_antivirus_runtime import RuntimeScanResult
    from orbit_api.material_scanner_owner import MaterialScannerOwner
    from orbit_api.material_scanner_owner_process import WindowsOwnerProcessAdapter
    from orbit_api.material_scanner_owner_store import create_owner_audit_sink
    from orbit_api.material_scanner_registry import MaterialScannerRegistry

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s
            AND TABLE_NAME IN ('orbit_scanner_owner_instance','orbit_scanner_owner_audit',
            'orbit_scanner_owner_outbox')""",
            (database,),
        )
        assert cursor.fetchone()[0] == 3, "原生专项要求037实际表"
    admin.commit()
    protected = _protected()
    validate_resource_budget(psutil.virtual_memory().available, shutil.disk_usage(ROOT).free)
    if not port_free():
        raise ValueError("固定19311已被占用，拒绝运行，不寻找替代端口")
    owned = validate_owned_root(ROOT / ("owner-native-it-" + uuid4().hex))
    owned.mkdir(exist_ok=False)
    started_at = time.monotonic()

    def emit(phase):
        item = {
            "scope": "owner-native-fixture",
            "phase": phase,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
        }
        if progress is None:
            print(json.dumps(item), flush=True)
        else:
            progress(item)

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def audit_count(instance):
        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT action FROM orbit_scanner_owner_audit
                WHERE instance_id=%s ORDER BY sequence_no""",
                (instance,),
            )
            actions = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                """SELECT COUNT(*) FROM orbit_scanner_owner_outbox o
                JOIN orbit_scanner_owner_audit a ON a.event_id=o.event_id WHERE a.instance_id=%s""",
                (instance,),
            )
            count = cursor.fetchone()[0]
        admin.commit()
        assert count == len(actions)
        return actions

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
        registry, owner, failed_owner, contender = MaterialScannerRegistry(), None, None, None
        captured, all_owned_identities = [], []
        sink = create_owner_audit_sink(sessions)

        class TrackingAdapter(WindowsOwnerProcessAdapter):
            def spawn(self, *args):
                result = super().spawn(*args)
                all_owned_identities.append((result.pid, result.created_at_us))
                return result

        async def stage(label, awaitable):
            emit(label + ":start")
            task = asyncio.create_task(awaitable)
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if done:
                        result = await task
                        emit(label + ":done")
                        return result
                    emit(label + ":waiting")
                    if psutil.virtual_memory().available < 3 * 1024**3:
                        raise ValueError("运行时可用内存低于3GiB，停止本轮自有任务")
            finally:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        async def audited(event):
            captured.append(dict(event))
            return await sink(event)

        try:
            async with asyncio.timeout(WORK_SECONDS):
                definition = await stage(
                    "approved-source-check",
                    asyncio.to_thread(_sources, owned, time.monotonic() + 45),
                )
                assert _protected() == protected
                cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[0])
                owner = MaterialScannerOwner(
                    registry, audit_sink=audited, adapter=TrackingAdapter()
                )
                binding = await stage("first-native-start", owner.start(definition))
                pid, born = binding.profile.pid, binding.profile.created_at_us
                assert pid != PROTECTED_PID and binding.profile.policy.port == OWNED_PORT
                assert audit_count(binding.profile.instance_id) == ["STARTING", "STARTED"]
                content = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5n8AAAAASUVORK5CYII="
                )

                tenant, upload = str(uuid4()), str(uuid4())
                objects = ImmutablePngObjects(tenant, upload, content)
                result = await stage(
                    "actual-owned-png-scan",
                    asyncio.wait_for(
                        asyncio.to_thread(
                            binding.scanner.scan,
                            objects,
                            tenant,
                            upload,
                            hashlib.sha256(content).hexdigest(),
                            len(content),
                        ),
                        35,
                    ),
                )
                assert isinstance(result, RuntimeScanResult) and result.receipt.result == "CLEAN", (
                    safe_scan_diagnostic(result)
                )
                assert (
                    result.proof is not None
                    and result.proof.instance_id == binding.profile.instance_id
                ), safe_scan_diagnostic(result)
                assert result.proof.created_at_us == born and await owner.monitor_once()
                cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[1])

                contender = MaterialScannerOwner(
                    MaterialScannerRegistry(), audit_sink=audited, adapter=TrackingAdapter()
                )
                try:
                    await contender.start(replace(definition, profile_id="native-owner-contender"))
                except OrbitError as error:
                    assert error.code == "SCANNER_OWNER_PORT_BUSY"
                else:
                    raise AssertionError("已占用19311不应启动第二进程")
                assert _protected() == protected and len(captured) == 2
                cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[2])

                assert await stage("first-native-job-close", owner.stop())
                assert not registry.candidates() and not _same_process(pid, born) and port_free()
                assert audit_count(binding.profile.instance_id) == [
                    "STARTING",
                    "STARTED",
                    "STOPPED",
                ]
                assert _protected() == protected
                cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[3])

                validate_resource_budget(
                    psutil.virtual_memory().available, shutil.disk_usage(ROOT).free
                )
                trigger = "owner_native_" + uuid4().hex
                with admin.cursor() as cursor:
                    cursor.execute(f"""CREATE TRIGGER {trigger}
                      BEFORE INSERT ON orbit_scanner_owner_audit
                      FOR EACH ROW BEGIN IF NEW.action='STARTED' THEN SIGNAL SQLSTATE '45000'
                      SET MESSAGE_TEXT='owner-native-fixture'; END IF; END""")
                admin.commit()
                failed_owner = MaterialScannerOwner(
                    registry, audit_sink=audited, adapter=TrackingAdapter()
                )
                second = replace(definition, profile_id="native-owner-audit-failure")
                try:
                    try:
                        await stage("second-native-start-audit-reject", failed_owner.start(second))
                    except OrbitError as error:
                        assert error.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"
                    else:
                        raise AssertionError("实际STARTED审计失败不得publish")
                    assert not registry.candidates() and port_free()
                    event = captured[-1]
                    assert event["action"] == "STARTED"
                    assert audit_count(event["instance_id"]) == ["STARTING"]
                    assert _protected() == protected
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute(f"DROP TRIGGER {trigger}")
                    admin.commit()
                cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[4])
        finally:
            # 即使超时/SQL/健康失败，也只调用本轮owner保留的Job/原生句柄，不杀数值PID。
            emit("owned-cleanup:start")
            try:
                async with asyncio.timeout(CLEANUP_SECONDS):
                    for current in (failed_owner, contender, owner):
                        if current is not None:
                            if current._owned is not None and current.registry.same_generation(
                                current._owned.binding
                            ):
                                current.registry.withdraw(current._owned.definition.profile_id)
                            if current._pending is not None and not current._pending.done():
                                await asyncio.shield(current._pending)
                            await current.stop()
            finally:
                await engine.dispose()
            assert all(not _same_process(pid, born) for pid, born in all_owned_identities)
            assert port_free() and _protected() == protected
            emit("owned-cleanup:verified")
        return {
            "actual_native_case_count": len(MATERIAL_SCANNER_OWNER_NATIVE_CASES),
            "protected_process_unchanged": True,
            "owned_port_released": True,
            "new_official_gpg_verification": False,
        }

    metrics = asyncio.run(run())
    # 不递归删除：仅删本轮两个已知文件，其他临时文件存在则保留供主线检查。
    validate_owned_root(owned)
    for name in ("clamd.conf", "approved-source-fixture.json"):
        item = owned / name
        if item.is_file() and not item.is_symlink():
            item.unlink()
    try:
        owned.rmdir()
        cleaned = True
    except OSError:
        cleaned = False
    metrics["owned_fixture_cleanup_complete"] = cleaned
    cases.append(MATERIAL_SCANNER_OWNER_NATIVE_CASES[5])
    return metrics
