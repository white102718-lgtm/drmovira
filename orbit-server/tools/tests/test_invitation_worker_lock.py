"""真实独立子进程争锁和进程退出释放；不启动任何用户服务。"""

import os
import subprocess
import sys
from pathlib import Path


def test_process_lock_rejects_second_process_and_releases_after_exit(tmp_path):
    environment = os.environ | {"PYTHONPATH": str(Path(__file__).parents[1])}
    code = (
        "from pathlib import Path; import sys; "
        "from invitation_worker_lock import worker_lock; "
        "lock=worker_lock(Path(sys.argv[1])); lock.__enter__(); "
        "print('LOCKED',flush=True); sys.stdin.readline()"
    )
    command = [sys.executable, "-c", code, str(tmp_path / "worker.lock")]
    first = subprocess.Popen(
        command, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    try:
        assert first.stdout.readline().strip() == b"LOCKED"
        second = subprocess.run(
            command, env=environment, input=b"\n", capture_output=True, timeout=10
        )
        assert second.returncode != 0 and b"WorkerAlreadyRunning" in second.stderr
    finally:
        first.communicate(b"\n", timeout=10)
    third = subprocess.run(command, env=environment, input=b"\n", capture_output=True, timeout=10)
    assert third.returncode == 0 and third.stdout.strip() == b"LOCKED"
