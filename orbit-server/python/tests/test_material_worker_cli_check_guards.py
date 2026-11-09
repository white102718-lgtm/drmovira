"""子进程专项护栏纯测，不启动Python/ClamD或访问真实SQL/private配置。"""

import importlib.util
import json
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture
def checks():
    path = Path(__file__).resolve().parents[2] / "tools/material_worker_cli_checks.py"
    spec = importlib.util.spec_from_file_location("worker_cli_check_guards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_is_static_compilable_and_secret_is_only_serialized_memory_payload(checks):
    secret = "memory-only-test-secret"
    value = checks.payload_bytes({"ORBIT_PYTHON_JWT_SECRET_KEY": secret}, ["--once"])
    assert json.loads(value)["values"]["ORBIT_PYTHON_JWT_SECRET_KEY"] == secret
    assert secret not in checks.WRAPPER
    compile(checks.WRAPPER, "<fixed-cli-wrapper>", "exec")


@pytest.mark.parametrize(
    "values,argv",
    [
        ({"OTHER_SECRET": "x"}, ["--once"]),
        ([], ["--once"]),
        ({}, "--once"),
        ({}, [None]),
        ({}, ["x" * 129]),
        ({"ORBIT_PYTHON_TOO_LARGE": "x" * (1024 * 1024)}, ["--once"]),
    ],
)
def test_payload_rejects_foreign_namespace_or_unbounded_input(checks, values, argv):
    with pytest.raises(ValueError):
        checks.payload_bytes(values, argv)


@pytest.mark.parametrize(
    "raw",
    [
        b"private-password-not-json\n",
        b'{"result":"FAILED","code":"MATERIAL_WORKER_SECRET_VALUE"}\n',
        b'{"result":"COMPLETED","code":"MATERIAL_WORKER_COMPLETED","token":"secret"}\n',
        b'{"result":"PROBE","code":"MATERIAL_WORKER_CLI_PROBE","db_imported":true,"descendant_count":true}\n',
        b'{"result":"RUNNING","code":"MATERIAL_WORKER_CYCLE","cycles":1001}\n',
        b'{"result":"COMPLETED","code":"MATERIAL_WORKER_COMPLETED","cleanup_complete":1}\n',
    ],
)
def test_only_known_safe_json_protocol_can_reach_parent_diagnostics(checks, raw):
    with pytest.raises(ValueError) as error:
        checks.safe_records(raw)
    assert "private" not in str(error.value) and "secret" not in str(error.value)


def test_streaming_partial_line_waits_without_hiding_completed_invalid_line(checks):
    valid = b'{"result":"RUNNING","code":"MATERIAL_WORKER_CYCLE","cycles":1}\n'
    assert len(checks.safe_records(valid + b'{"part', complete=False)) == 1
    with pytest.raises(ValueError):
        checks.safe_records(valid + b"private-token\n", complete=False)


def test_bounded_pipe_does_not_grow_with_unbounded_child_output(checks):
    pipe = checks.BoundedPipe(BytesIO(b"x" * 70000))
    pipe.thread.join(timeout=1)
    assert not pipe.thread.is_alive() and len(pipe.data) == 65536 and pipe.overflow
    with pytest.raises(ValueError):
        pipe.snapshot()


def test_bounded_pipe_returns_complete_safe_frames_without_disk_file(checks):
    value = b'{"result":"IDLE","code":"MATERIAL_WORKER_IDLE","cleanup_complete":true}\n'
    pipe = checks.BoundedPipe(BytesIO(value))
    pipe.thread.join(timeout=1)
    assert checks.safe_records(pipe.snapshot())[0]["cleanup_complete"]


def test_import_has_no_process_file_or_database_side_effect(monkeypatch):
    import subprocess

    import psutil
    import sqlalchemy.ext.asyncio

    def forbidden(*args, **kwargs):
        pytest.fail("仅导入护栏不允许真实动作")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(psutil, "Process", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", forbidden)
    path = Path(__file__).resolve().parents[2] / "tools/material_worker_cli_checks.py"
    spec = importlib.util.spec_from_file_location("worker_cli_import_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.MATERIAL_WORKER_CLI_CASES) == 5


@pytest.mark.parametrize("assign_fails", [False, True])
def test_owned_cli_hidden_suspended_job_before_resume_and_stdin_only(
    monkeypatch, checks, assign_fails
):
    from types import SimpleNamespace

    import orbit_api.material_scanner_owner_process as native

    calls, arguments, writes = [], [], []

    class Kernel:
        def create(self):
            calls.append("job")
            return 57

        def assign(self, job, handle):
            assert (job, handle) == (57, 44)
            calls.append("assign")
            if assign_fails:
                raise ValueError("injected assign failure")

        def resume(self, handle):
            assert handle == 44
            calls.append("resume")

        def terminate_unassigned(self, handle):
            assert handle == 44
            calls.append("terminate-own-handle")

        def close(self, job):
            assert job == 57
            calls.append("close-own-job")

    class Stdin:
        def write(self, value):
            calls.append("write-stdin")
            writes.append(value)

        def close(self):
            calls.append("stdin-close")

    process = SimpleNamespace(
        pid=123, _handle=44, stdin=Stdin(), stdout=BytesIO(), stderr=BytesIO()
    )
    process.wait = lambda **kwargs: 0
    process.poll = lambda: 0

    def popen(args, **kwargs):
        calls.append("popen")
        arguments.append((args, kwargs))
        return process

    monkeypatch.setattr(native, "WindowsKillJob", Kernel)
    monkeypatch.setattr(checks.subprocess, "Popen", popen)
    monkeypatch.setattr(
        checks.psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 1.0)
    )
    values = {"ORBIT_PYTHON_JWT_SECRET_KEY": "only-in-memory"}
    if assign_fails:
        with pytest.raises(ValueError):
            checks.OwnedCli(values, ["--once"])
        assert calls == ["job", "popen", "assign", "terminate-own-handle", "close-own-job"]
        assert not writes
    else:
        child = checks.OwnedCli(values, ["--once"])
        child.close()
        assert calls == [
            "job",
            "popen",
            "assign",
            "resume",
            "write-stdin",
            "stdin-close",
            "close-own-job",
        ]
        assert json.loads(writes[0])["values"] == values
    args, kwargs = arguments[0]
    assert args == [checks.sys.executable, "-c", checks.WRAPPER]
    assert "only-in-memory" not in str(args) + str(kwargs)
    assert kwargs["creationflags"] == 0x08000004 and kwargs["shell"] is False
    assert checks.RETAINED_CLI_HANDLES and checks.RETAINED_CLI_HANDLES[-1].process is process


def test_diagnostic_contains_only_exit_and_validated_metadata(checks):
    rows = [
        {"result": "FAILED", "code": "MATERIAL_WORKER_FAILED", "cleanup_complete": False},
        {
            "result": "DIAGNOSTIC",
            "code": "MATERIAL_WORKER_CLI_DIAGNOSTIC",
            "exception_type": "ImportError",
            "source": "tools/run_material_worker.py",
            "line": 48,
        },
        {
            "result": "PROBE",
            "code": "MATERIAL_WORKER_CLI_PROBE",
            "db_imported": False,
            "descendant_count": 0,
            "baseline_children": [],
            "children": [],
        },
    ]
    summary = checks.safe_exit_diagnostic(1, rows, [])
    assert type(summary) is dict
    value = json.dumps(summary)
    assert '"returncode": 1' in value and '"exception_type": "ImportError"' in value
    assert '"db_imported": false' in value and "cleanup_complete" not in value
    assert "frame.f_locals" not in checks.WRAPPER and "str(error)" not in checks.WRAPPER


@pytest.mark.parametrize(
    "field,value",
    [
        ("exception_type", "private-secret"),
        ("source", "D:/private-secret"),
        ("line", True),
        ("line", 0),
        ("message", "private-secret"),
    ],
)
def test_diagnostic_rejects_exception_values_unknown_paths_and_extra_fields(checks, field, value):
    row = {
        "result": "DIAGNOSTIC",
        "code": "MATERIAL_WORKER_CLI_DIAGNOSTIC",
        "exception_type": "ValueError",
        "source": "<fixed-cli-wrapper>",
        "line": 1,
    }
    row[field] = value
    with pytest.raises(ValueError) as error:
        checks.safe_records(json.dumps(row).encode())
    assert "private-secret" not in str(error.value)


def test_wrapper_trace_never_uses_exception_values_or_frame_locals(checks):
    import ast

    tree = ast.parse(checks.WRAPPER)
    trace = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "trace"
    )
    text = ast.unparse(trace)
    assert "arg[0]" in text and "arg[1]" not in text and "arg[2]" not in text
    assert "f_locals" not in text and "f_globals" not in text
    assert "del events[:-8]" in text


def test_trace_collects_actual_owned_exception_without_value_and_bounds_records(checks):
    import sys

    namespace = {}
    # 仅构造静态诊断函数；截断点之前没有stdin、导入CLI、SQL或进程操作。
    exec(
        compile(checks.WRAPPER.split("import psutil\n", 1)[0], "<guard-prefix>", "exec"), namespace
    )
    path = str((checks.BACKEND / "tools/run_material_worker.py").resolve())
    source = compile("raise ValueError('fixture-secret-must-never-appear')", path, "exec")
    previous = sys.gettrace()
    try:
        sys.settrace(namespace["trace"])
        for _ in range(12):
            try:
                exec(source, {})
            except ValueError:
                pass
    finally:
        sys.settrace(previous)
    events = namespace["events"]
    assert len(events) == 8
    assert all(row["exception_type"] == "ValueError" and row["line"] == 1 for row in events)
    assert "fixture-secret" not in json.dumps(events)
    assert len(checks.safe_records(("\n".join(map(json.dumps, events))).encode())) == 8


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "private-path.exe"),
        ("pid", True),
        ("birth", 0),
        ("running", 1),
        ("cmdline", "secret-value"),
    ],
)
def test_probe_child_metadata_strictly_rejects_unknown_names_values_and_fields(
    checks, field, value
):
    child = {"name": "python.exe", "pid": 123, "birth": 1234567, "running": True}
    child[field] = value
    probe = {
        "result": "PROBE",
        "code": "MATERIAL_WORKER_CLI_PROBE",
        "db_imported": False,
        "descendant_count": 1,
        "baseline_children": [],
        "children": [child],
    }
    with pytest.raises(ValueError) as error:
        checks.safe_records(json.dumps(probe).encode())
    assert "secret-value" not in str(error.value) and "private-path" not in str(error.value)


def test_probe_contains_only_whitelisted_child_metadata_and_baseline(checks):
    child = {"name": "conhost.exe", "pid": 123, "birth": 1234567, "running": True}
    probe = {
        "result": "PROBE",
        "code": "MATERIAL_WORKER_CLI_PROBE",
        "db_imported": False,
        "descendant_count": 1,
        "baseline_children": [child],
        "children": [child],
    }
    assert checks.safe_records(json.dumps(probe).encode()) == [probe]
    assert checks.safe_exit_diagnostic(0, [probe], [])["records"][0]["children"] == [child]
    probe["descendant_count"] = 0
    with pytest.raises(ValueError):
        checks.safe_records(json.dumps(probe).encode())


def test_exact_windows_console_baseline_accepts_no_new_descendants(checks):
    row = {"name": "conhost.exe", "pid": 123, "birth": 1234567, "running": True}
    assert checks.unchanged_console_baseline({"baseline_children": [], "children": []})
    assert checks.unchanged_console_baseline({"baseline_children": [row], "children": [dict(row)]})


@pytest.mark.parametrize(
    "change",
    ["new-console", "changed-birth", "python-baseline", "clamd-after", "duplicate", "ended"],
)
def test_console_baseline_rejects_new_host_pid_reuse_or_worker(checks, change):
    row = {"name": "conhost.exe", "pid": 123, "birth": 1234567, "running": True}
    before, after = [dict(row)], [dict(row)]
    if change == "new-console":
        after.append(dict(row, pid=124))
    elif change == "changed-birth":
        after[0]["birth"] += 1
    elif change == "python-baseline":
        before[0]["name"] = after[0]["name"] = "python.exe"
    elif change == "clamd-after":
        after.append(dict(row, pid=125, name="clamd.exe"))
    elif change == "duplicate":
        before.append(dict(row))
        after.append(dict(row))
    else:
        after[0]["running"] = False
    assert not checks.unchanged_console_baseline({"baseline_children": before, "children": after})
