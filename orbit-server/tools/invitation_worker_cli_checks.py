"""主集成任务按队列调用：真实CLI子进程、隔离MySQL与本机TLS通道，不加载私有配置。"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_CASES = [
    "pythonInvitationWorkerCliRecoveryNeverSendsQueuedInvitation",
    "pythonInvitationWorkerCliActualHttpsAccepted",
    "pythonInvitationWorkerCliControlledTwoCycleRecovery",
    "pythonInvitationWorkerCliServeNeverResendsUnknown",
    "pythonInvitationWorkerCliStartupFailureRedactsSecrets",
]

# 测试注入只存在于子进程引导，生产CLI既不接收测试开关，也不读取进程通用变量。
BOOTSTRAP = """
import json, sys, ssl, runpy
from pathlib import Path
from config.orbit_runtime import configure_isolated_fixture
values=json.load(sys.stdin)
configure_isolated_fixture(values)
import httpcore
from orbit_api.notification_http import NotificationHttp
import orbit_api.invitation_delivery as delivery
class LocalNetwork(httpcore.AsyncNetworkBackend):
    async def connect_tcp(self, host, port, **kwargs):
        assert host=='orbit-idp.fixture.example' and port==443
        return await httpcore.AnyIOBackend().connect_tcp(
            '127.0.0.1', values['ORBIT_PYTHON_TEST_OIDC_PORT'], **kwargs)
context=ssl.create_default_context(cadata=values['ORBIT_PYTHON_TEST_OIDC_CA'])
delivery.NotificationHttp=lambda: NotificationHttp(
    network_backend=LocalNetwork(),ssl_context=context)
sys.path.insert(0,str(Path.cwd()/'tools'))
sys.argv=['tools/run_invitation_worker.py']+sys.argv[1:]
runpy.run_path('tools/run_invitation_worker.py',run_name='__main__')
"""


def invoke_worker_cli(values, arguments):
    """配置经stdin内存传输，不能进入命令行、磁盘文件或失败断言。"""
    sources = values.get("ORBIT_PYTHON_DB_SOURCES", {})
    if isinstance(sources, str):
        sources = json.loads(sources)
    if not sources or any(
        item.get("db_host") != "127.0.0.1"
        or item.get("db_port") != 13306
        or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", item.get("db_database", ""))
        for item in sources.values()
    ):
        raise ValueError("CLI集成只允许当前独立测试数据库")
    environment = os.environ | {
        "PYTHONPATH": os.pathsep.join([str(ROOT / "python"), str(ROOT / "python/ruoyi_fastapi")])
    }
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP, *arguments],
        cwd=ROOT,
        env=environment,
        input=json.dumps(values),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=45,
    )
    # 不把原始stdout/stderr写入证据或异常；只接受固定JSON计数回执。
    try:
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (ValueError, TypeError):
        raise AssertionError("CLI没有返回有效的脱敏JSON回执") from None
    if result.stderr.strip():
        raise AssertionError("CLI产生了非预期标准错误输出；原文不进入证据")
    return result.returncode, records


def run_invitation_worker_cli_checks(values, idp, queued, state, cases):
    """调用点需在通知配置/发起人仍有效时；queued和state复用当前投递专项夹具。"""
    identifier, _, _ = queued()
    before = len(idp.notifications)
    code, records = invoke_worker_cli(values, ["--recover", "--limit", "100"])
    assert code == 0 and len(records) == 1 and "recovered_unknown" in records[0]
    assert state(identifier)[0] == "QUEUED" and len(idp.notifications) == before
    cases.append(CLI_CASES[0])

    code, records = invoke_worker_cli(values, ["--send", "--limit", "100"])
    assert code == 0 and len(records) == 1 and records[0]["accepted"] == 1
    assert state(identifier)[0] == "ACCEPTED" and len(idp.notifications) == before + 1
    body, headers = idp.notifications[-1]
    assert json.loads(body)["delivery_id"] == identifier
    assert headers["Idempotency-Key"] == identifier and headers.get("X-ORBIT-Signature")
    cases.append(CLI_CASES[1])

    code, records = invoke_worker_cli(
        values, ["--recover", "--serve", "--cycles", "2", "--interval", "5"]
    )
    assert code == 0 and records == [{"recovered_unknown": 0}] * 2
    assert len(idp.notifications) == before + 1
    cases.append(CLI_CASES[2])

    identifier, _, _ = queued()
    before = len(idp.notifications)
    idp.notification_mode = "disconnect"
    try:
        code, records = invoke_worker_cli(
            values, ["--send", "--serve", "--cycles", "2", "--interval", "5", "--limit", "1"]
        )
    finally:
        idp.notification_mode = "accepted"
    assert code == 0 and len(records) == 2
    assert records[0]["claimed"] == 1 and records[0]["unknown"] == 1
    assert records[1]["claimed"] == 0 and state(identifier)[0] == "UNKNOWN"
    assert len(idp.notifications) == before + 1
    cases.append(CLI_CASES[3])

    invalid = values | {"ORBIT_PYTHON_PUBLIC_ORIGIN": "https://fixture-secret@invalid.example"}
    code, records = invoke_worker_cli(invalid, ["--send"])
    assert code == 1 and records == [{"result": "FAILED", "code": "INVITATION_WORKER_FAILED"}]
    cases.append(CLI_CASES[4])
