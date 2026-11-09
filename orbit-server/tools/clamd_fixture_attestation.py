"""本机隔离ClamD实例证明；不把VERSION当作实际启动配置证明，不用于生产配置。"""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import psutil

ROOT = Path(__file__).resolve().parents[2] / ".runtime/tools/clamav-1.5.4"
ARCHIVE_SHA256 = "0d9e0228b2674137ea1a2853566c98a0278ad52ab2582c3d6dbd75373848c395"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def attest_fixture():
    """仅固定的官方已验签发行包、启动命令、文件和监听PID全部一致才返回。"""
    manifest = json.loads((ROOT / "trusted-fixture-manifest.json").read_text("utf-8"))
    archive = ROOT / "clamav-1.5.4.win.x64.zip"
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError("隔离扫描发行包指纹变化，拒绝运行")
    executable = ROOT / "unpacked/clamav-1.5.4.win.x64/clamd.exe"
    with ZipFile(archive) as bundle:
        members = [name for name in bundle.namelist() if name.endswith("/clamd.exe")]
        if len(members) != 1:
            raise ValueError("隔离扫描发行包成员异常")
        with bundle.open(members[0]) as stream:
            expected_executable = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest(executable) != expected_executable:
        raise ValueError("扫描进程文件与已验签发行包不一致")
    config = ROOT / "clamd.conf"
    if digest(config) != manifest["config_sha256"]:
        raise ValueError("扫描实际配置文件已变化")
    process = psutil.Process(int((ROOT / "clamd.pid").read_text("utf-8-sig").strip()))
    if Path(process.exe()).resolve() != executable.resolve():
        raise ValueError("扫描PID不是本任务启动的固定进程")
    command = process.cmdline()
    if (
        len(command) != 2
        or command[1].replace("\\", "/").lower()
        != ("--config-file=" + str(config.resolve()).replace("\\", "/")).lower()
    ):
        raise ValueError("扫描进程启动配置不一致")
    if config.stat().st_mtime > process.create_time():
        raise ValueError("配置文件晚于进程启动，不能证明实际生效")
    listeners = [
        (entry.laddr.ip, entry.laddr.port)
        for entry in process.net_connections(kind="tcp")
        if entry.status == psutil.CONN_LISTEN
    ]
    if listeners != [("127.0.0.1", manifest["port"])]:
        raise ValueError("扫描监听端口不属于已证明的隔离进程")
    return {
        "pid": process.pid,
        "process_created_at_epoch": process.create_time(),
        "executable_sha256": expected_executable,
        "archive_sha256": ARCHIVE_SHA256,
        "config_sha256": manifest["config_sha256"],
        "listener": "127.0.0.1:" + str(manifest["port"]),
        "scope": "fixed local fixture process only; not production lifecycle attestation",
    }
