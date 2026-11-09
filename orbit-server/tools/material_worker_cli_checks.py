"""待主线审核的真实CLI子进程专项；secret仅stdin内存，导入不执行进程或SQL。"""

import asyncio
import copy
import json
import shutil
import subprocess
import sys
import threading
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import psutil
from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND = Path(__file__).resolve().parents[1]
RETAINED_CLI_HANDLES = []
MATERIAL_WORKER_CLI_CASES = [
    "pythonMaterialWorkerCliDisabledZeroDatabaseAndZeroNativeProcess",
    "pythonMaterialWorkerCliInvalidArgumentsCannotEchoInertTokenSentinel",
    "pythonMaterialWorkerCliActualOncePngReadyAllProofSourcesAndCleanup",
    "pythonMaterialWorkerCliTwoProcessesFixedLockPreventsSecondEngine",
    "pythonMaterialWorkerCliFiniteServeCyclesAndOwnedOnlyFinalCleanup",
]

# 固定代码不含任何凭据或本轮路径；values和argv只能由父进程stdin传入。
DIAGNOSTIC_SOURCES = {
    "tools/run_material_worker.py",
    "python/orbit_api/material_scanner_owner_loader.py",
    "python/ruoyi_fastapi/config/orbit_runtime.py",
    "<fixed-cli-wrapper>",
}
CHILD_EXECUTABLE_NAMES = {"python.exe", "pythonw.exe", "conhost.exe", "clamd.exe", "UNKNOWN"}
DIAGNOSTIC_TYPES = {
    "ImportError",
    "ModuleNotFoundError",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "AttributeError",
    "KeyError",
    "OSError",
    "PermissionError",
    "FileNotFoundError",
    "SyntaxError",
    "NameError",
    "Exception",
}

WRAPPER = r"""
import builtins,json,sys
from pathlib import Path
root=Path.cwd().resolve()
sys.path[:0]=[str(root/'python'),str(root/'python/ruoyi_fastapi'),str(root/'tools')]
sources={str((root/name).resolve()):name for name in (
    'tools/run_material_worker.py',
    'python/orbit_api/material_scanner_owner_loader.py',
    'python/ruoyi_fastapi/config/orbit_runtime.py')}
known_types={builtins.__dict__[name]:name for name in (
    'ImportError','ModuleNotFoundError','ValueError','TypeError','RuntimeError',
    'AttributeError','KeyError','OSError','PermissionError','FileNotFoundError',
    'SyntaxError','NameError','Exception')}
events=[]
def trace(frame,event,arg):
    source=sources.get(frame.f_code.co_filename)
    if event=='exception' and source is not None:
        events.append({'result':'DIAGNOSTIC','code':'MATERIAL_WORKER_CLI_DIAGNOSTIC',
                       'exception_type':known_types.get(arg[0],'Exception'),
                       'source':source,'line':frame.f_lineno})
        del events[:-8]
    return trace
import psutil
def child_snapshot():
    children=[]
    for child in psutil.Process().children(recursive=True):
        try:
            name=Path(child.exe()).name.lower()
            if name not in {'python.exe','pythonw.exe','conhost.exe','clamd.exe'}:
                name='UNKNOWN'
            children.append({'name':name,'pid':child.pid,
                             'birth':round(child.create_time()*1000000),
                             'running':child.is_running()})
        except psutil.NoSuchProcess:
            continue
    return sorted(children,key=lambda row:(row['pid'],row['birth']))
baseline_children=child_snapshot()
code=1
sys.settrace(trace)
try:
    raw=sys.stdin.buffer.read(1048577)
    if len(raw)>1048576:
        raise SystemExit(2)
    payload=json.loads(raw)
    from config.orbit_runtime import configure_isolated_fixture
    configure_isolated_fixture(payload['values'])
    import run_material_worker
    code=run_material_worker.main(payload['argv'])
except SystemExit as error:
    code=error.code if type(error.code) is int else 2
except Exception as error:
    tb=error.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename!='<string>':
        tb=tb.tb_next
    events.append({'result':'DIAGNOSTIC','code':'MATERIAL_WORKER_CLI_DIAGNOSTIC',
                   'exception_type':known_types.get(type(error),'Exception'),
                   'source':'<fixed-cli-wrapper>','line':tb.tb_lineno if tb else 1})
finally:
    sys.settrace(None)
if code!=0:
    for event in events[-8:]:
        print(json.dumps(event),flush=True)
after_children=child_snapshot()
print(json.dumps({'result':'PROBE','code':'MATERIAL_WORKER_CLI_PROBE',
                  'db_imported':'config.database' in sys.modules,
                  'descendant_count':len(after_children),
                  'baseline_children':baseline_children,'children':after_children}),flush=True)
raise SystemExit(code)
"""


def payload_bytes(values, argv):
    if not isinstance(values, dict) or any(
        not isinstance(key, str) or not key.startswith("ORBIT_PYTHON_") for key in values
    ):
        raise ValueError("CLI夹具只能传本轮ORBIT命名空间")
    if not isinstance(argv, list) or any(
        not isinstance(value, str) or len(value) > 128 for value in argv
    ):
        raise ValueError("CLI夹具参数形状无效")
    raw = json.dumps({"values": values, "argv": argv}).encode()
    if len(raw) > 1024 * 1024:
        raise ValueError("CLI内存夹具超限")
    return raw


def safe_records(raw, *, complete=True):
    """拒任意人类日志/未知字段，不在错误中回显可能含秘密的stdout/stderr。"""
    if len(raw) > 65536:
        raise ValueError("CLI输出超限")
    try:
        lines = raw.decode("utf-8").splitlines()
        if not complete and raw and not raw.endswith(b"\n"):
            lines = lines[:-1]
        records = []
        for line in lines:
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("result") not in {
                "RUNNING",
                "COMPLETED",
                "IDLE",
                "STOPPED",
                "DISABLED",
                "FAILED",
                "PROBE",
                "DIAGNOSTIC",
            }:
                raise ValueError
            code = row.get("code")
            accepted = {
                "DISABLED",
                "CYCLE",
                "COMPLETED",
                "IDLE",
                "STOPPED",
                "FAILED",
                "INTERRUPTED",
                "CANCELLED",
                "MONITOR_FAILED",
                "SUPERVISOR_FAILED",
                "CLEANUP_UNVERIFIED",
                "ARGUMENTS_INVALID",
                "CLI_PROBE",
                "CLI_DIAGNOSTIC",
            }
            if not isinstance(code, str) or code not in {
                "MATERIAL_WORKER_" + item for item in accepted
            }:
                raise ValueError
            allowed = {
                "result",
                "code",
                "cycles",
                "processed",
                "ready",
                "failed",
                "cleanup_complete",
            }
            if row["result"] == "PROBE":
                allowed = {
                    "result",
                    "code",
                    "db_imported",
                    "descendant_count",
                    "baseline_children",
                    "children",
                }
                if (
                    type(row.get("db_imported")) is not bool
                    or type(row.get("descendant_count")) is not int
                ):
                    raise ValueError
                if set(row) != allowed or code != "MATERIAL_WORKER_CLI_PROBE":
                    raise ValueError
                for key in ("baseline_children", "children"):
                    children = row[key]
                    if type(children) is not list or len(children) > 1000:
                        raise ValueError
                    for child in children:
                        if (
                            type(child) is not dict
                            or set(child) != {"name", "pid", "birth", "running"}
                            or child["name"] not in CHILD_EXECUTABLE_NAMES
                            or type(child["pid"]) is not int
                            or not 0 < child["pid"] <= 2**32
                            or type(child["birth"]) is not int
                            or not 0 < child["birth"] < 2**63
                            or type(child["running"]) is not bool
                        ):
                            raise ValueError
                if row["descendant_count"] != len(row["children"]):
                    raise ValueError
            if row["result"] == "DIAGNOSTIC":
                allowed = {"result", "code", "exception_type", "source", "line"}
                if (
                    set(row) != allowed
                    or code != "MATERIAL_WORKER_CLI_DIAGNOSTIC"
                    or row.get("exception_type") not in DIAGNOSTIC_TYPES
                    or row.get("source") not in DIAGNOSTIC_SOURCES
                    or type(row.get("line")) is not int
                    or not 1 <= row["line"] <= 100000
                ):
                    raise ValueError
            if set(row) - allowed:
                raise ValueError
            for field in ("cycles", "processed", "ready", "failed", "descendant_count"):
                if field in row and (type(row[field]) is not int or not 0 <= row[field] <= 1000):
                    raise ValueError
            if "cleanup_complete" in row and type(row["cleanup_complete"]) is not bool:
                raise ValueError
            records.append(row)
        return records
    except (UnicodeError, ValueError, TypeError):
        raise ValueError("CLI输出不符合安全JSON协议") from None


def unchanged_console_baseline(probe):
    """Windows启动时已存在的console host只按原完整身份集合放行，禁止新增工作后代。"""
    baseline, after = probe["baseline_children"], probe["children"]
    identities = {(row["pid"], row["birth"]) for row in baseline}
    return (
        len(identities) == len(baseline)
        and all(row["name"] == "conhost.exe" and row["running"] is True for row in baseline)
        and sorted(baseline, key=lambda row: (row["pid"], row["birth"]))
        == sorted(after, key=lambda row: (row["pid"], row["birth"]))
    )


def safe_exit_diagnostic(returncode, out, err):
    """仅接收已通过严格解析的JSON；绝不读取或展示原始管道字节。"""
    rows = safe_records(("\n".join(json.dumps(row) for row in out + err)).encode())
    summary = {"returncode": returncode, "records": []}
    for row in rows:
        value = {key: row[key] for key in ("result", "code")}
        if row["result"] == "PROBE":
            value.update(
                {
                    key: row[key]
                    for key in ("db_imported", "descendant_count", "baseline_children", "children")
                }
            )
        if row["result"] == "DIAGNOSTIC":
            value.update({key: row[key] for key in ("exception_type", "source", "line")})
        summary["records"].append(value)
    return summary


class BoundedPipe:
    def __init__(self, stream):
        self.stream, self.data, self.lock, self.overflow = (
            stream,
            bytearray(),
            threading.Lock(),
            False,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.error = False
        self.thread.start()

    def _read(self):
        try:
            while block := self.stream.read1(4096):
                with self.lock:
                    remaining = 65536 - len(self.data)
                    self.data.extend(block[: max(0, remaining)])
                    if len(block) > remaining:
                        self.overflow = True
        except Exception:
            self.error = True

    def snapshot(self):
        with self.lock:
            if self.overflow or self.error:
                raise ValueError("CLI输出超限，拒继续")
            return bytes(self.data)


class OwnedCli:
    """保留自建Job/Popen原生句柄；只清理本轮Python及其子孙，不按PID杀进程。"""

    def __init__(self, values, argv):
        from orbit_api.material_scanner_owner_process import WindowsKillJob

        self.kernel = WindowsKillJob()
        self.job, self.process, self.closed = self.kernel.create(), None, False
        self.out = self.err = None
        RETAINED_CLI_HANDLES.append(self)
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-c", WRAPPER],
                cwd=BACKEND,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                creationflags=0x08000004,
            )
            self.pid, self.born = (
                self.process.pid,
                round(psutil.Process(self.process.pid).create_time() * 1_000_000),
            )
            self.kernel.assign(self.job, int(self.process._handle))
            self.kernel.resume(int(self.process._handle))
            self.out, self.err = BoundedPipe(self.process.stdout), BoundedPipe(self.process.stderr)
            self.process.stdin.write(payload_bytes(values, argv))
            self.process.stdin.close()
        except BaseException:
            try:
                if self.process is not None:
                    self.kernel.terminate_unassigned(int(self.process._handle))
            finally:
                self.close()
            raise

    def close(self, timeout=10):
        deadline = time.monotonic() + timeout
        if not self.closed:
            self.kernel.close(self.job)
            self.closed = True
        if self.process is not None:
            self.process.wait(timeout=max(0.001, deadline - time.monotonic()))
        for stream in (self.out, self.err):
            if stream is not None:
                stream.thread.join(timeout=max(0, min(2, deadline - time.monotonic())))
                if stream.thread.is_alive():
                    raise RuntimeError("CLI管道读取尚未结束")

    def records(self):
        return safe_records(self.out.snapshot()), safe_records(self.err.snapshot())


def run_material_worker_cli_checks(admin, database, object_root, fixture_values, cases):
    from material_scanner_owner_native_checks import (
        ROOT,
        _protected,
        _same_process,
        _sources,
        port_free,
        validate_native_target,
        validate_owned_root,
        validate_resource_budget,
    )
    from material_scanner_supervisor_checks import (
        supervisor_fixture_values,
        validate_supervisor_object_root,
    )

    validate_native_target(admin, database)
    object_root = validate_supervisor_object_root(Path(object_root))
    from orbit_api.material_scanner_owner_definition import OWNER_DEFINITIONS_KEY
    from orbit_api.material_scanner_owner_loader import OWNER_ENABLED_KEY

    values = copy.deepcopy(fixture_values)
    payload_bytes(values, ["--once"])
    # 不连接/载入真实私有env；子进程configure_isolated_fixture也会强制13306/16379/15。
    sources = values.get("ORBIT_PYTHON_DB_SOURCES")
    sources = json.loads(sources) if isinstance(sources, str) else sources
    if (
        not isinstance(sources, dict)
        or not sources
        or any(
            item.get("db_host") != "127.0.0.1"
            or item.get("db_port") != 13306
            or item.get("db_database") != database
            for item in sources.values()
        )
    ):
        raise ValueError("CLI子进程数据源不等于当前UUID库")
    if (
        values.get("ORBIT_PYTHON_REDIS_HOST") != "127.0.0.1"
        or values.get("ORBIT_PYTHON_REDIS_PORT") != 16379
        or values.get("ORBIT_PYTHON_REDIS_DATABASE") != 15
    ):
        raise ValueError("CLI子进程缓存必须为独立夹具")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute(
            """SELECT COUNT(*) FROM orbit_system_configuration
            WHERE tenant_id=%s AND section='MATERIAL_SCANNER'""",
            (tenant,),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_material_job WHERE state IN('PENDING','RUNNING')"
        )
        assert cursor.fetchone()[0] == 0
    admin.commit()
    protected = _protected()
    validate_resource_budget(psutil.virtual_memory().available, shutil.disk_usage(ROOT).free)
    if not port_free():
        raise ValueError("19311占用，拒绝CLI专项")
    owned = validate_owned_root(ROOT / ("owner-native-it-" + uuid4().hex))
    owned.mkdir(exist_ok=False)
    start, children = time.monotonic(), []

    def phase(name):
        print(
            json.dumps(
                {
                    "scope": "material-worker-cli-fixture",
                    "phase": name,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                }
            ),
            flush=True,
        )

    def wait(child, *, condition=None):
        last = 0
        while True:
            elapsed = time.monotonic() - start
            if elapsed > 360:
                raise TimeoutError("CLI专项总工作窗口到期")
            if elapsed - last >= 10:
                phase("waiting-child")
                last = elapsed
                if psutil.virtual_memory().available < 3 * 1024**3:
                    raise ValueError("运行内存低于安全门限")
            if condition is not None and condition():
                return
            child.out.snapshot()
            child.err.snapshot()
            if child.process.poll() is not None:
                child.close()
                return
            time.sleep(0.05)

    def spawn(argv, selected=values):
        child = OwnedCli(selected, argv)
        children.append(child)
        return child

    def completed(child, expected):
        wait(child)
        out, err = child.records()
        if child.process.returncode != expected:
            print(
                json.dumps(
                    {
                        "scope": "material-worker-cli-fixture",
                        "phase": "safe-exit-diagnostic",
                        **safe_exit_diagnostic(child.process.returncode, out, err),
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
        assert child.process.returncode == expected, "CLI退出码不符"
        probe = [row for row in out if row["result"] == "PROBE"]
        if len(probe) != 1 or not unchanged_console_baseline(probe[0]):
            print(
                json.dumps(
                    {
                        "scope": "material-worker-cli-fixture",
                        "phase": "safe-probe-diagnostic",
                        **safe_exit_diagnostic(child.process.returncode, out, err),
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
        assert len(probe) == 1 and unchanged_console_baseline(probe[0])
        child.observed_identities = {
            (row["pid"], row["birth"])
            for key in ("baseline_children", "children")
            for row in probe[0][key]
        }
        assert child.closed and child.process.poll() is not None
        assert all(not _same_process(*identity) for identity in child.observed_identities), (
            "自有Job关闭后console或工作后代身份仍在运行"
        )
        return (
            [row for row in out if row["result"] not in {"PROBE", "DIAGNOSTIC"}],
            [row for row in err if row["result"] != "DIAGNOSTIC"],
            probe[0],
        )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    try:
        phase("disabled")
        disabled = dict(values)
        disabled.pop(OWNER_ENABLED_KEY, None)
        disabled.pop(OWNER_DEFINITIONS_KEY, None)
        out, err, probe = completed(spawn(["--once"], disabled), 0)
        assert (
            not err
            and len(out) == 1
            and out[0]["result"] == "DISABLED"
            and out[0]["cleanup_complete"] is True
        )
        assert not probe["db_imported"] and port_free() and _protected() == protected
        cases.append(MATERIAL_WORKER_CLI_CASES[0])

        phase("invalid-argv")
        out, err, probe = completed(
            spawn(["--once", "--token", "inert-argv-sentinel"], disabled), 2
        )
        assert not out and len(err) == 1 and err[0]["code"] == "MATERIAL_WORKER_ARGUMENTS_INVALID"
        assert not probe["db_imported"] and port_free()
        cases.append(MATERIAL_WORKER_CLI_CASES[1])

        phase("prepare-owner-and-png")
        definition = _sources(owned, time.monotonic() + 45)
        values.update(supervisor_fixture_values(definition))
        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"] = str(object_root)
        config, asset, upload = str(uuid4()), str(uuid4()), str(uuid4())

        async def seed():
            from orbit_api.authorization import require_business_access
            from orbit_api.material_contract import CompletedPart
            from orbit_api.material_job_policy import actor_auth_version, material_job_scope
            from orbit_api.material_objects import LocalMaterialObjects

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
            try:
                buffer = BytesIO()
                Image.new("RGB", (24, 24), "green").save(buffer, "PNG")
                content = buffer.getvalue()
                import hashlib

                digest = hashlib.sha256(content).hexdigest()
                objects = LocalMaterialObjects(object_root)
                objects.put_part(tenant, upload, 1, content, len(content))
                objects.assemble(
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
                    await session.execute(
                        text("""INSERT INTO orbit_system_configuration
                      (id,tenant_id,section,name,enabled,revision,settings_json,secrets_json)
                      VALUES(:id,:tenant,'MATERIAL_SCANNER','真实CLI扫描配置',1,1,:settings,'{}')"""),
                        {
                            "id": config,
                            "tenant": tenant,
                            "settings": json.dumps({"profileId": definition.profile_id}),
                        },
                    )
                    await session.execute(
                        text("""INSERT INTO orbit_material_asset
                      (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,byte_size,object_upload_id)
                      VALUES(:tenant,:id,:owner,:team,'CLI实际PNG',:category,'IMAGE','image/png','SCANNING',:sha,:size,:upload)"""),
                        {
                            "tenant": tenant,
                            "id": asset,
                            "owner": owner,
                            "team": team,
                            "category": "00000000-0000-4000-8000-000000000001",
                            "sha": digest,
                            "size": len(content),
                            "upload": upload,
                        },
                    )
                    item = {
                        "id": asset,
                        "owner_user_id": owner,
                        "owner_team_id": team,
                        "sha256": digest,
                        "mime": "image/png",
                    }
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
                return digest, len(content)
            finally:
                await engine.dispose()

        digest, size = asyncio.run(seed())
        phase("actual-once")
        validate_resource_budget(psutil.virtual_memory().available, shutil.disk_usage(ROOT).free)
        once = spawn(["--once"])
        out, err, probe = completed(once, 0)
        assert not err and len(out) == 1 and out[0]["result"] == "COMPLETED"
        assert out[0]["ready"] == 1 and out[0]["failed"] == 0 and out[0]["cleanup_complete"] is True
        assert probe["db_imported"] and port_free()
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,preview_ready FROM orbit_material_asset WHERE tenant_id=%s AND id=%s",
                (tenant, asset),
            )
            assert cursor.fetchone() == ("READY", 1)
            cursor.execute(
                """SELECT sr.result,sr.sha256,sr.byte_size,rp.configuration_id,
                rp.configuration_revision,rp.profile_id,rp.instance_id
                FROM orbit_material_scan_receipt sr JOIN orbit_material_scan_runtime_proof rp
                ON rp.tenant_id=sr.tenant_id AND rp.asset_id=sr.asset_id AND rp.receipt_id=sr.id
                WHERE sr.tenant_id=%s AND sr.asset_id=%s""",
                (tenant, asset),
            )
            rows = cursor.fetchall()
            assert len(rows) == 1 and rows[0][:6] == (
                "CLEAN",
                digest,
                size,
                config,
                1,
                definition.profile_id,
            )
            cursor.execute(
                """SELECT action FROM orbit_scanner_owner_audit
                WHERE instance_id=%s ORDER BY sequence_no""",
                (rows[0][6],),
            )
            assert [row[0] for row in cursor.fetchall()] == ["STARTING", "STARTED", "STOPPED"]
            cursor.execute(
                """SELECT COUNT(*) FROM orbit_scanner_owner_outbox o
                JOIN orbit_scanner_owner_audit a ON a.event_id=o.event_id
                WHERE a.instance_id=%s""",
                (rows[0][6],),
            )
            assert cursor.fetchone()[0] == 3
        admin.commit()
        cases.append(MATERIAL_WORKER_CLI_CASES[2])

        phase("serve-lock-contention")
        validate_resource_budget(psutil.virtual_memory().available, shutil.disk_usage(ROOT).free)
        serving = spawn(["--serve", "--cycles", "2", "--interval", "30"])

        def first_cycle():
            return any(
                row.get("code") == "MATERIAL_WORKER_CYCLE"
                for row in safe_records(serving.out.snapshot(), complete=False)
            )

        wait(serving, condition=first_cycle)
        assert serving.process.poll() is None, "serve未保持到锁争用阶段"
        descendants = psutil.Process(serving.pid).children(recursive=True)
        engines = [
            item
            for item in descendants
            if Path(item.exe()).resolve() == definition.executable.resolve()
        ]
        assert len(engines) == 1 and engines[0].pid != 7492
        engine_identity = engines[0].pid, round(engines[0].create_time() * 1_000_000)
        contender = spawn(["--once"])
        contender_out, contender_err, contender_probe = completed(contender, 1)
        assert (
            not contender_err and len(contender_out) == 1 and contender_out[0]["result"] == "FAILED"
        )
        assert not contender_probe["db_imported"] and _same_process(*engine_identity)
        assert _protected() == protected
        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) FROM orbit_scanner_owner_instance
                WHERE profile_id=%s""",
                (definition.profile_id,),
            )
            assert cursor.fetchone()[0] == 2, "争用者不能登记第三个owner"
        admin.commit()
        cases.append(MATERIAL_WORKER_CLI_CASES[3])

        phase("finite-serve-cleanup")
        out, err, probe = completed(serving, 0)
        terminal = [row for row in out if row["result"] != "RUNNING"]
        assert not err and len(terminal) == 1 and terminal[0]["result"] == "IDLE"
        assert terminal[0]["cycles"] == 2 and terminal[0]["cleanup_complete"] is True
        assert not _same_process(*engine_identity) and port_free() and _protected() == protected
        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT state,sequence_no FROM orbit_scanner_owner_instance
                WHERE profile_id=%s""",
                (definition.profile_id,),
            )
            states = cursor.fetchall()
            assert len(states) == 2 and all(row == ("STOPPED", 3) for row in states)
        admin.commit()
    finally:
        phase("owned-python-jobs-cleanup")
        errors = []
        deadline = time.monotonic() + 30
        for child in reversed(children):
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                child.close(timeout=max(0.001, min(10, deadline - time.monotonic())))
            except Exception:
                errors.append(True)
        if (
            errors
            or any(child.process is not None and child.process.poll() is None for child in children)
            or any(
                _same_process(*identity)
                for child in children
                for identity in getattr(child, "observed_identities", set())
            )
            or not port_free()
            or _protected() != protected
        ):
            raise RuntimeError("CLI清理未完整确认，保留精确自有句柄与本轮资源")
    validate_owned_root(owned)
    for name in ("clamd.conf", "approved-source-fixture.json"):
        item = owned / name
        if item.is_file() and not item.is_symlink():
            item.unlink()
    try:
        owned.rmdir()
    except OSError:
        pass
    cases.append(MATERIAL_WORKER_CLI_CASES[4])
    return {
        "case_count": 5,
        "cleanup_complete": True,
        "protected_process_unchanged": True,
        "secret_transport": "memory-stdin-only",
        "windows_console_baseline": "exact-conhost-pid-birth-only",
        "new_worker_descendants_after_completion": 0,
        "external_signal_graceful_tested": False,
    }
