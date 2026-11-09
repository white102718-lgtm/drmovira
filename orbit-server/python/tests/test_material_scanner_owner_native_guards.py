"""原生专项的护栏纯测；不调用run入口，不打开真实socket或进程。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def native():
    path = Path(__file__).resolve().parents[2] / "tools/material_scanner_owner_native_checks.py"
    spec = importlib.util.spec_from_file_location("owner_native_guards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "platform,host,port,database",
    [
        ("posix", "127.0.0.1", 13306, "orbit_py_it_" + "a" * 32),
        ("nt", "remote.example", 13306, "orbit_py_it_" + "a" * 32),
        ("nt", "127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("nt", "127.0.0.1", 13306, "production"),
        ("nt", "127.0.0.1", 13306, "orbit_py_it_bad"),
        ("nt", "127.0.0.1", 13306, None),
    ],
)
def test_native_target_rejects_other_os_remote_shared_or_non_uuid_db(
    native, platform, host, port, database
):
    with pytest.raises(ValueError):
        native.validate_native_target(
            SimpleNamespace(host=host, port=port), database, platform=platform
        )


def test_native_target_accepts_only_explicit_guard_without_connecting(native):
    native.validate_native_target(
        SimpleNamespace(host="127.0.0.1", port=13306), "orbit_py_it_" + "a" * 32, platform="nt"
    )


@pytest.mark.parametrize(
    "available,disk",
    [(0, 2**40), (6 * 1024**3 - 1, 2**40), (2**40, 1024**3 - 1), (True, 2**40), (2**40, False)],
)
def test_resource_gate_is_strict_and_never_rounds_low_memory_up(native, available, disk):
    with pytest.raises(ValueError):
        native.validate_resource_budget(available, disk)


def test_exact_minimum_resource_budget_is_permitted(native):
    native.validate_resource_budget(6 * 1024**3, 1024**3)


@pytest.mark.parametrize(
    "name",
    [
        "..",
        "clamd.conf",
        "owner-native-it-existing",
        "owner-native-it-" + "A" * 32,
        "owner-native-it-" + "a" * 31,
    ],
)
def test_owned_path_must_have_exact_uuid_name_under_fixed_parent(native, tmp_path, name):
    with pytest.raises(ValueError):
        native.validate_owned_root(tmp_path / name, expected_root=tmp_path)


def test_owned_path_rejects_sibling_and_relative_without_creating_anything(native, tmp_path):
    target = tmp_path / "owner-native-it-"  # 名称不足不是合法目录
    with pytest.raises(ValueError):
        native.validate_owned_root(target, expected_root=tmp_path.parent)
    with pytest.raises(ValueError):
        native.validate_owned_root(Path("owner-native-it-" + "a" * 32), expected_root=tmp_path)
    valid = tmp_path / ("owner-native-it-" + "a" * 32)
    assert native.validate_owned_root(valid, expected_root=tmp_path) == valid
    assert not valid.exists()


@pytest.mark.parametrize("busy", [True, False])
def test_port_preflight_uses_only19311_and_never_terminates_listener(native, monkeypatch, busy):
    seen = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            seen.append("closed")

        def settimeout(self, value):
            assert value == 1

        def setsockopt(self, *args):
            pass

        def bind(self, address):
            seen.append(address)
            if busy:
                raise OSError("injected occupied port")

    monkeypatch.setattr(native.socket, "socket", lambda *args: Socket())
    assert native.port_free() is (not busy)
    assert seen == [("127.0.0.1", 19311), "closed"]
    with pytest.raises(ValueError):
        native.port_free(19310)


@pytest.mark.parametrize("pid,listener", [(123, "127.0.0.1:19310"), (7492, "127.0.0.1:19311")])
def test_protected_attestation_drift_rejects_without_adoption(native, monkeypatch, pid, listener):
    monkeypatch.setitem(
        sys.modules,
        "clamd_fixture_attestation",
        SimpleNamespace(attest_fixture=lambda: {"pid": pid, "listener": listener}),
    )
    with pytest.raises(ValueError):
        native._protected()


def test_protected_attestation_is_read_only_result(native, monkeypatch):
    expected = {"pid": 7492, "listener": "127.0.0.1:19310", "process_created_at_epoch": 1.0}
    monkeypatch.setitem(
        sys.modules,
        "clamd_fixture_attestation",
        SimpleNamespace(attest_fixture=lambda: dict(expected)),
    )
    assert native._protected() == expected


def test_import_has_no_process_socket_or_directory_creation(monkeypatch):
    import socket
    import subprocess

    import psutil

    def forbidden(*args, **kwargs):
        pytest.fail("工具导入不得执行进程/网络/目录创建")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(psutil, "Process", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    path = Path(__file__).resolve().parents[2] / "tools/material_scanner_owner_native_checks.py"
    spec = importlib.util.spec_from_file_location("owner_native_import_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PROTECTED_PID == 7492 and module.OWNED_PORT == 19311


def test_immutable_png_object_complete_protocol_binds_one_tenant_upload_pair(native):
    from uuid import uuid4

    tenant, upload = str(uuid4()), str(uuid4())
    content = b"immutable safe fixture"
    objects = native.ImmutablePngObjects(tenant, upload, content)
    with objects.mutation_guard(tenant, upload):
        with objects.original(tenant, upload).open("rb") as first:
            assert first.read() == content
        with objects.original(tenant, upload).open("rb") as second:
            assert second.read() == content


@pytest.mark.parametrize(
    "method,pair",
    [
        ("original", ("tenant", "upload")),
        ("mutation_guard", ("tenant", "upload")),
        ("original", ("other-tenant", "other-upload")),
        ("mutation_guard", ("other-tenant", "other-upload")),
    ],
)
def test_immutable_png_wrong_identity_refused_before_guard_or_open(native, method, pair):
    from uuid import uuid4

    tenant, upload = str(uuid4()), str(uuid4())
    objects = native.ImmutablePngObjects(tenant, upload, b"immutable")
    supplied = (tenant, str(uuid4())) if pair[0] == "tenant" else (str(uuid4()), upload)
    with pytest.raises(ValueError):
        getattr(objects, method)(*supplied)


@pytest.mark.parametrize("mode", ["wb", "r", "r+b"])
def test_immutable_png_cannot_open_write_or_text_mode(native, mode):
    from uuid import uuid4

    objects = native.ImmutablePngObjects(str(uuid4()), str(uuid4()), b"immutable")
    with pytest.raises(ValueError):
        objects.open(mode)


def test_scan_diagnostic_exposes_only_result_code_and_proof_presence(native):
    result = SimpleNamespace(
        receipt=SimpleNamespace(
            result="UNVERIFIED", error_code="ANTIVIRUS_RUNTIME_UNVERIFIED", path="private-path"
        ),
        proof=None,
    )
    assert native.safe_scan_diagnostic(result) == {
        "result": "UNVERIFIED",
        "error_code": "ANTIVIRUS_RUNTIME_UNVERIFIED",
        "proof_present": False,
    }
    result.receipt.result = {"path": "private-path"}
    result.receipt.error_code = "private/path-or-token"
    assert native.safe_scan_diagnostic(result) == {
        "result": "UNEXPECTED",
        "error_code": "OTHER",
        "proof_present": False,
    }


def test_memory_fixture_rejects_mutable_bytes(native):
    from uuid import uuid4

    with pytest.raises(ValueError):
        native.ImmutablePngObjects(str(uuid4()), str(uuid4()), bytearray(b"mutable"))
