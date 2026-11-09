"""待主线审核串行执行的单Worker真实链；导入不启动进程/连接SQL/创建目录。"""

import asyncio
import hashlib
import json
import re
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import psutil
from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

OBJECT_BASE = Path(__file__).resolve().parents[1] / ".runtime/integration-objects"
# 仅异常诊断保留精确对象，不能把未知任务/engine丢弃后声称清理成功。
UNRESOLVED_CLEANUPS = []
MATERIAL_SCANNER_SUPERVISOR_CASES = [
    "pythonMaterialScannerSupervisorExplicitLoaderActualOwnerAndPersistentStarted",
    "pythonMaterialScannerSupervisorActualPngQueueReadyReceiptProofAndTenantSource",
    "pythonMaterialScannerSupervisorSeparateApiRegistryCannotRebuildFromAudit",
    "pythonMaterialScannerSupervisorPrivateDisableWithdrawStopsClaimingAndLeavesQueuedTask",
    "pythonMaterialScannerSupervisorActualShutdownOwnedBirthExitProtectedUnchanged",
]


class SupervisorCleanupUnverified(RuntimeError):
    def __init__(self, metrics, supervisor, tasks):
        super().__init__("监督器专项清理未获完整确认，保留本轮资源供主线检查")
        self.safe_metrics, self.supervisor, self.retained_tasks = metrics, supervisor, tasks
        self.engine = None


def _cleanup_tasks(supervisor, shutdown_task):
    values = {} if shutdown_task is None else {"shutdown": shutdown_task}
    if supervisor is None:
        return values
    values.update(
        {
            "inflight": getattr(supervisor, "_inflight", None),
            "owner_stop": getattr(supervisor, "_owner_stop_task", None),
            "supervisor_cleanup": getattr(supervisor, "_cleanup_task", None),
        }
    )
    owner = getattr(supervisor, "_owner", None)
    if owner is not None:
        values["owner_pending"] = getattr(owner, "_pending", None)
    return {name: task for name, task in values.items() if task is not None}


async def confirm_supervisor_cleanup(supervisor, verify_runtime, *, budget_seconds=30):
    """精确保留shutdown Task；预留强制withdraw后的句柄清理窗口，不取消worker。"""
    deadline = time.monotonic() + budget_seconds
    shutdown_task = None
    error = False
    if supervisor is not None:
        supervisor.accepting = False
        shutdown_task = asyncio.create_task(supervisor.shutdown())
        try:
            await asyncio.wait_for(asyncio.shield(shutdown_task), min(10, budget_seconds / 3))
        except TimeoutError:
            # 取消监督器的排空等待会触发其精确清理Task；不能取消内部scan/owner.stop。
            shutdown_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(shutdown_task), max(0.001, deadline - time.monotonic())
                )
            except asyncio.CancelledError:
                pass
            except Exception:
                error = True
        except Exception:
            error = True
    tasks = _cleanup_tasks(supervisor, shutdown_task)
    pending = [task for task in tasks.values() if not task.done()]
    if pending:
        await asyncio.wait(set(pending), timeout=max(0, deadline - time.monotonic()))
    # pending清理可能创建了新owner_stop_task，必须重新采集，不能只检查旧快照。
    tasks.update(_cleanup_tasks(supervisor, shutdown_task))
    pending_names = sorted(name for name, task in tasks.items() if not task.done())
    task_errors = []
    for name, task in tasks.items():
        if task.cancelled() and name != "shutdown":
            # 被取消的to_thread等待Task不能证明原生scan/processor线程已退出。
            task_errors.append(name)
        elif task.done() and not task.cancelled() and task.exception() is not None:
            task_errors.append(name)
    owner = getattr(supervisor, "_owner", None) if supervisor is not None else None
    handles_unconfirmed = bool(
        owner is not None
        and (
            getattr(owner, "_owned", None) is not None
            or getattr(owner, "_unclosed", [])
            or getattr(getattr(owner, "adapter", None), "_failed", [])
        )
    )
    try:
        runtime = verify_runtime()
        verified = all(
            runtime.get(field) is True
            for field in (
                "owned_births_exited",
                "owned_port_released",
                "protected_process_unchanged",
            )
        )
    except Exception:
        runtime, verified = {}, False
    metrics = {
        "cleanup_complete": not (error or pending_names or task_errors or handles_unconfirmed)
        and verified,
        "pending_roles": pending_names,
        "failed_roles": sorted(task_errors),
        "handles_unconfirmed": handles_unconfirmed,
        "owned_births_exited": runtime.get("owned_births_exited") is True,
        "owned_port_released": runtime.get("owned_port_released") is True,
        "protected_process_unchanged": runtime.get("protected_process_unchanged") is True,
    }
    if not metrics["cleanup_complete"]:
        problem = SupervisorCleanupUnverified(metrics, supervisor, tasks)
        UNRESOLVED_CLEANUPS.append(problem)
        raise problem
    return metrics


def validate_supervisor_object_root(path, *, base=OBJECT_BASE):
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or path.name != "materials"
        or path.parent.parent != base
        or not re.fullmatch(r"run-[a-f0-9]{32}", path.parent.name)
    ):
        raise ValueError("监督器对象根必须是本轮固定工作区UUID bundle/materials")
    for item in (path, *path.parents):
        data = item.lstat()
        if item.is_symlink() or getattr(data, "st_file_attributes", 0) & 0x400:
            raise ValueError("监督器对象根拒绝链接/reparse")
    if not path.is_dir() or any(path.iterdir()):
        raise ValueError("监督器对象根必须存在且初始为空")
    return path


def supervisor_fixture_values(definition):
    from orbit_api.material_scanner_owner_definition import OWNER_DEFINITIONS_KEY
    from orbit_api.material_scanner_owner_loader import OWNER_ENABLED_KEY

    payload = asdict(definition)
    payload.pop("profile_id")
    payload["database_files"] = dict(payload["database_files"])

    def encode(value):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError

    return {
        OWNER_ENABLED_KEY: "true",
        OWNER_DEFINITIONS_KEY: json.dumps({definition.profile_id: payload}, default=encode),
    }


def run_material_scanner_supervisor_checks(admin, database, object_root, cases, *, progress=None):
    from material_scanner_owner_native_checks import (
        CLEANUP_SECONDS,
        ROOT,
        WORK_SECONDS,
        _protected,
        _same_process,
        _sources,
        port_free,
        validate_native_target,
        validate_owned_root,
        validate_resource_budget,
    )

    validate_native_target(admin, database)
    object_root = validate_supervisor_object_root(Path(object_root))
    from orbit_api.authorization import require_business_access
    from orbit_api.errors import OrbitError
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_scanner_owner import MaterialScannerOwner
    from orbit_api.material_scanner_owner_loader import OWNER_ENABLED_KEY, load_owner_configuration
    from orbit_api.material_scanner_owner_process import WindowsOwnerProcessAdapter
    from orbit_api.material_scanner_owner_store import create_owner_audit_sink
    from orbit_api.material_scanner_registry import MaterialScannerRegistry
    from orbit_api.material_scanner_selection import select_scanner
    from orbit_api.material_scanner_supervisor import MaterialScannerSupervisor
    from orbit_api.material_security import clean_scan_ids

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner_id, team = cursor.fetchone()
        cursor.execute(
            """SELECT COUNT(*) FROM orbit_system_configuration
            WHERE tenant_id=%s AND section='MATERIAL_SCANNER'""",
            (tenant,),
        )
        assert cursor.fetchone()[0] == 0, "监督器专项要求本轮未创建的扫描配置，拒覆盖他人夹具"
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_material_job WHERE state IN ('PENDING','RUNNING')"
        )
        assert cursor.fetchone()[0] == 0, "监督器专项要求无其他排队/运行素材任务"
    admin.commit()
    protected = _protected()
    validate_resource_budget(psutil.virtual_memory().available, shutil.disk_usage(ROOT).free)
    if not port_free():
        raise ValueError("19311已占用，拒绝专项，不改占用者")
    owned = validate_owned_root(ROOT / ("owner-native-it-" + uuid4().hex))
    owned.mkdir(exist_ok=False)
    started_at = time.monotonic()
    identities = []

    def emit(phase):
        payload = {
            "scope": "scanner-supervisor-fixture",
            "phase": phase,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
        }
        if progress is None:
            print(json.dumps(payload), flush=True)
        else:
            progress(payload)

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

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
        objects = LocalMaterialObjects(object_root)
        registry, supervisor, configuration = MaterialScannerRegistry(), None, str(uuid4())
        events = []

        async def stage(name, awaitable):
            emit(name + ":start")
            task = asyncio.create_task(awaitable)
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if done:
                        result = await task
                        emit(name + ":done")
                        return result
                    emit(name + ":waiting")
                    if psutil.virtual_memory().available < 3 * 1024**3:
                        raise ValueError("运行可用内存低于3GiB，停止本轮自有任务")
            finally:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        class Adapter(WindowsOwnerProcessAdapter):
            def spawn(self, *args):
                result = super().spawn(*args)
                identities.append((result.pid, result.created_at_us))
                return result

        sink = create_owner_audit_sink(sessions)

        async def audited(event):
            events.append(dict(event))
            return await sink(event)

        def owner_factory(registry, *, audit_sink):
            return MaterialScannerOwner(registry, audit_sink=audit_sink, adapter=Adapter())

        async def png_fixture():
            asset, upload = str(uuid4()), str(uuid4())
            output = BytesIO()
            Image.new("RGB", (24, 24), "blue").save(output, "PNG")
            content = output.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            await asyncio.to_thread(objects.put_part, tenant, upload, 1, content, len(content))
            await asyncio.to_thread(
                objects.assemble,
                tenant,
                upload,
                [CompletedPart(part_number=1, etag=digest)],
                len(content),
                digest,
                "image/png",
            )
            async with sessions() as session, session.begin():
                context = await require_business_access(session, 1, "assets", "assets.upload")
                version = await actor_auth_version(session, 1)
                item = {
                    "id": asset,
                    "owner_user_id": owner_id,
                    "owner_team_id": team,
                    "sha256": digest,
                    "mime": "image/png",
                }
                await session.execute(
                    text("""INSERT INTO orbit_material_asset
                  (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                   sha256,byte_size,object_upload_id)
                  VALUES(:tenant,:id,:owner,:team,'正式监督器真实PNG',:category,'IMAGE',
                   'image/png','SCANNING',:sha,:size,:upload)"""),
                    {
                        "tenant": tenant,
                        "id": asset,
                        "owner": owner_id,
                        "team": team,
                        "category": "00000000-0000-4000-8000-000000000001",
                        "sha": digest,
                        "size": len(content),
                        "upload": upload,
                    },
                )
                await session.execute(
                    text("""INSERT INTO orbit_material_job
                  (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state)
                  VALUES(:tenant,:id,1,:version,:scope,'PENDING')"""),
                    {
                        "tenant": tenant,
                        "id": asset,
                        "version": version,
                        "scope": material_job_scope(context, item),
                    },
                )
            return asset, upload, digest, len(content)

        try:
            async with asyncio.timeout(WORK_SECONDS):
                definition = await stage(
                    "approved-source", asyncio.to_thread(_sources, owned, time.monotonic() + 45)
                )
                values = supervisor_fixture_values(definition)
                async with sessions() as session, session.begin():
                    await session.execute(
                        text("""INSERT INTO orbit_system_configuration
                      (id,tenant_id,section,name,enabled,revision,settings_json,secrets_json)
                      VALUES(:id,:tenant,'MATERIAL_SCANNER','正式监督器隔离配置',1,1,:settings,'{}')"""),
                        {
                            "id": configuration,
                            "tenant": tenant,
                            "settings": json.dumps({"profileId": definition.profile_id}),
                        },
                    )
                supervisor = MaterialScannerSupervisor(
                    registry=registry,
                    sessions=sessions,
                    objects=objects,
                    snapshot_provider=lambda: load_owner_configuration(lambda: dict(values)),
                    owner_factory=owner_factory,
                    audit_sink=audited,
                    drain_seconds=120,
                    cleanup_seconds=20,
                )
                assert await stage("supervisor-native-start", supervisor.start())
                assert supervisor.state == "RUNNING" and [item["action"] for item in events] == [
                    "STARTING",
                    "STARTED",
                ]
                assert (
                    len(identities) == 1 and identities[0][0] != 7492 and _protected() == protected
                )
                cases.append(MATERIAL_SCANNER_SUPERVISOR_CASES[0])

                asset, upload, digest, size = await png_fixture()
                assert await stage("actual-configured-worker-png", supervisor.run_once()) == [
                    {"asset_id": asset, "state": "READY"}
                ]
                binding = supervisor._binding
                async with sessions() as session:
                    state = (
                        await session.execute(
                            text("""SELECT state,error_code,preview_ready,width_px,height_px
                      FROM orbit_material_asset WHERE tenant_id=:tenant AND id=:id"""),
                            {"tenant": tenant, "id": asset},
                        )
                    ).one()
                    assert tuple(state) == ("READY", None, 1, 24, 24)
                    proofs = (
                        await session.execute(
                            text("""SELECT sr.result,sr.sha256,sr.byte_size,sr.error_code,
                      rp.profile_id,rp.profile_revision,rp.instance_id,rp.configuration_id,
                      rp.configuration_revision,rp.process_created_at_us
                      FROM orbit_material_scan_receipt sr JOIN orbit_material_scan_runtime_proof rp
                      ON rp.tenant_id=sr.tenant_id AND rp.asset_id=sr.asset_id
                      AND rp.receipt_id=sr.id
                      WHERE sr.tenant_id=:tenant AND sr.asset_id=:id"""),
                            {"tenant": tenant, "id": asset},
                        )
                    ).all()
                    assert len(proofs) == 1
                    assert tuple(proofs[0]) == (
                        "CLEAN",
                        digest,
                        size,
                        None,
                        definition.profile_id,
                        definition.revision,
                        binding.profile.instance_id,
                        configuration,
                        1,
                        binding.profile.created_at_us,
                    )
                    assert asset in await clean_scan_ids(session, tenant, [asset])
                assert objects.preview(tenant, upload).is_file()
                cases.append(MATERIAL_SCANNER_SUPERVISOR_CASES[1])

                api_registry = MaterialScannerRegistry()
                async with sessions() as session:
                    try:
                        await select_scanner(session, tenant, api_registry)
                    except OrbitError as error:
                        assert (
                            error.status == 503
                            and error.code == "SCANNER_CONFIGURATION_UNAVAILABLE"
                        )
                    else:
                        raise AssertionError("独立API不能从SQL审计复建本地scanner")
                assert not api_registry.candidates() and registry.candidates()
                cases.append(MATERIAL_SCANNER_SUPERVISOR_CASES[2])

                queued, *_ = await png_fixture()
                # 租户停用不是全局所有者停机授权；本工具另外显式关闭私有fixture配置。
                async with sessions() as session, session.begin():
                    await session.execute(
                        text("""UPDATE orbit_system_configuration SET enabled=0,revision=revision+1
                      WHERE tenant_id=:tenant AND id=:id"""),
                        {"tenant": tenant, "id": configuration},
                    )
                values[OWNER_ENABLED_KEY] = "false"
                assert (
                    await stage("private-disable-monitor-close", supervisor.monitor_once()) is False
                )
                assert (
                    supervisor.state == "FAILED"
                    and not supervisor.accepting
                    and not registry.candidates()
                )
                try:
                    await supervisor.run_once()
                except OrbitError as error:
                    assert error.code == "SCANNER_SUPERVISOR_UNAVAILABLE"
                else:
                    raise AssertionError("停用后不能领取新任务")
                async with sessions() as session:
                    job = (
                        await session.execute(
                            text("""SELECT state,claim_id FROM orbit_material_job
                      WHERE tenant_id=:tenant AND asset_id=:id"""),
                            {"tenant": tenant, "id": queued},
                        )
                    ).one()
                    count = (
                        await session.execute(
                            text("""SELECT COUNT(*) FROM orbit_material_scan_receipt
                      WHERE tenant_id=:tenant AND asset_id=:id"""),
                            {"tenant": tenant, "id": queued},
                        )
                    ).scalar_one()
                    assert tuple(job) == ("PENDING", None) and count == 0
                assert port_free() and _protected() == protected
                cases.append(MATERIAL_SCANNER_SUPERVISOR_CASES[3])
        finally:
            emit("supervisor-cleanup:start")
            try:
                cleanup_metrics = await confirm_supervisor_cleanup(
                    supervisor,
                    lambda: {
                        "owned_births_exited": all(
                            not _same_process(pid, born) for pid, born in identities
                        ),
                        "owned_port_released": port_free(),
                        "protected_process_unchanged": _protected() == protected,
                    },
                    budget_seconds=CLEANUP_SECONDS,
                )
            except SupervisorCleanupUnverified as problem:
                # 未确认停止时不dispose仍可能被inflight使用的SQL engine；不准主线删对象根。
                problem.engine = engine
                emit("supervisor-cleanup:unverified")
                raise
            await engine.dispose()
            emit("supervisor-cleanup:verified")
        assert supervisor is not None and supervisor.state == "FAILED"
        assert [item["action"] for item in events] == ["STARTING", "STARTED", "STOPPED"]
        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT action FROM orbit_scanner_owner_audit
              WHERE instance_id=%s ORDER BY sequence_no""",
                (events[0]["instance_id"],),
            )
            assert [row[0] for row in cursor.fetchall()] == ["STARTING", "STARTED", "STOPPED"]
            cursor.execute(
                """SELECT COUNT(*) FROM orbit_scanner_owner_outbox o
              JOIN orbit_scanner_owner_audit a ON a.event_id=o.event_id
              WHERE a.instance_id=%s""",
                (events[0]["instance_id"],),
            )
            assert cursor.fetchone()[0] == 3
        admin.commit()
        return {
            "case_count": 5,
            "separate_api_registry_unavailable": True,
            "actual_worker_ready": True,
            "protected_process_unchanged": True,
            "actual_private_env_modified": False,
            "cleanup_complete": cleanup_metrics["cleanup_complete"],
        }

    metrics = asyncio.run(run())
    validate_owned_root(owned)
    for name in ("clamd.conf", "approved-source-fixture.json"):
        path = owned / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    try:
        owned.rmdir()
        metrics["owned_config_directory_empty_removed"] = True
    except OSError:
        metrics["owned_config_directory_empty_removed"] = False
    # 对象根和原/预览文件由主线核对UUID后清理，本工具不递归删除任何目录。
    cases.append(MATERIAL_SCANNER_SUPERVISOR_CASES[4])
    return metrics
