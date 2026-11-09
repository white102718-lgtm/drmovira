"""内置浏览器串行检查窗口；只复用本轮UUID库，秘密仅临时内存/系统临时文件。"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from rule_definition_checks import guard_rule_target

ROOT = Path(__file__).resolve().parents[1]


def run_rules_internal_browser_checkpoint(admin, database, password):
    """由主线实际操作UI后写入具名结果；窗口存在或HTTP可达不自动算通过。"""
    guard_rule_target(admin, database)
    with socket.socket() as guard:
        guard.bind(("127.0.0.1", 18084))
    control = Path(tempfile.mkdtemp(prefix="orbit-rules-browser-"))
    credential = control / "fixture-login.json"
    completed = control / "completed.json"
    log_path = ROOT / ".runtime/rules-internal-browser-vite.log"
    child = None
    try:
        # 是本轮随机夹具密码，不是用户环境配置；绝不打印或写进工作区。
        credential.write_text(json.dumps({"username": "admin", "password": password}), "utf-8")
        environment = os.environ.copy()
        environment["ORBIT_E2E_BACKEND_URL"] = "http://127.0.0.1:18083"
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("RULE_BROWSER_NODE_UNAVAILABLE")
        with log_path.open("wb") as log:
            child = subprocess.Popen(
                [
                    node,
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18084",
                    "--strictPort",
                ],
                cwd=ROOT.parent / "orbit-web",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            print(
                json.dumps(
                    {
                        "rules_internal_browser_control": str(control),
                        # Cookie不按端口隔离；独立host避免覆盖原127.0.0.1预览的登录Cookie。
                        "frontend": "http://localhost:18084",
                        "status": "PENDING_UI_CHECKS_NOT_PASS",
                    }
                ),
                flush=True,
            )
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError("RULE_BROWSER_FRONTEND_EXITED")
                if completed.is_file():
                    value = json.loads(completed.read_text(encoding="utf-8"))
                    if not isinstance(value, dict) or value.get("result") != "PASS":
                        raise RuntimeError("RULE_BROWSER_CHECKS_FAILED")
                    checks = value.get("checks")
                    if (
                        not isinstance(checks, list)
                        or not checks
                        or any(
                            not isinstance(item, dict)
                            or item.get("passed") is not True
                            or not isinstance(item.get("name"), str)
                            for item in checks
                        )
                    ):
                        raise RuntimeError("RULE_BROWSER_ACTUAL_CHECKS_REQUIRED")
                    return value
                time.sleep(0.5)
            raise TimeoutError("RULE_BROWSER_MANUAL_WINDOW_EXPIRED")
    finally:
        credential.unlink(missing_ok=True)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
