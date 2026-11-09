"""启动本仓库隔离 MySQL8 / Redis 夹具；不接触系统服务或现有未知进程。"""

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def owned(port, pidfile, executable, required):
    """监听存在时必须同时证明 PID、可执行文件与工作区专属参数，不能借用其他服务。"""
    if not listening(port):
        return False
    if not pidfile.is_file():
        raise RuntimeError(f"端口 {port} 被未知进程占用")
    pid = int(pidfile.read_text().strip())
    command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
    listeners = subprocess.check_output(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], text=True
    ).split()
    # Redis 会重写进程标题，仅以 PID、监听地址与本工具保存的二进制来源确认。
    metadata = pidfile.with_suffix(".owner.json")
    identity = json.loads(metadata.read_text()) if metadata.is_file() else {}
    if set(listeners) != {str(pid)} or identity.get("binary") != str(executable):
        raise RuntimeError(f"端口 {port} 进程身份不匹配")
    if not all(value in command for value in required):
        raise RuntimeError(f"端口 {port} 进程参数不匹配")
    return True


def wait(port):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if listening(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"隔离端口 {port} 未就绪；请检查工作区日志")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql-home", type=Path, required=True)
    parser.add_argument("--redis-server", type=Path, required=True)
    args = parser.parse_args()
    mysql_home = args.mysql_home.resolve(strict=True)
    mysql = (mysql_home / "bin/mysqld").resolve(strict=True)
    redis = args.redis_server.resolve(strict=True)
    mysql_version = subprocess.check_output([str(mysql), "--version"], text=True).strip()
    redis_version = subprocess.check_output([str(redis), "--version"], text=True).strip()
    if "Ver 8." not in mysql_version or "Redis server" not in redis_version:
        raise RuntimeError("必须使用 MySQL8 与真实 Redis 服务端")
    mysql_root, redis_root = RUNTIME / "mysql-it", RUNTIME / "redis-it"
    for folder in (mysql_root, redis_root):
        folder.mkdir(parents=True, exist_ok=True)
        if not folder.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("隔离目录不能指向仓库之外")
        folder.chmod(0o700)
    data = mysql_root / "data"
    mysql_pid = mysql_root / "process.id"
    if not owned(13306, mysql_pid, mysql, [str(data)]):
        if not (data / "auto.cnf").is_file():
            if data.exists() and any(data.iterdir()):
                raise RuntimeError("MySQL 初始化目录非空，不覆盖或清理")
            subprocess.run(
                [
                    str(mysql),
                    "--no-defaults",
                    "--initialize-insecure",
                    f"--basedir={mysql_home}",
                    f"--datadir={data}",
                    f"--log-error={mysql_root / 'initialize.log'}",
                ],
                check=True,
            )
        # 空密码仅限短期回环测试夹具，与现有验收合同一致；不能用于部署。
        subprocess.run(
            [
                str(mysql),
                "--no-defaults",
                "--daemonize",
                f"--basedir={mysql_home}",
                f"--datadir={data}",
                "--bind-address=127.0.0.1",
                "--port=13306",
                "--mysqlx=OFF",
                "--default-time-zone=+00:00",
                f"--socket={mysql_root / 'mysql.sock'}",
                f"--pid-file={mysql_pid}",
                f"--log-error={mysql_root / 'error.log'}",
            ],
            check=True,
        )
        mysql_pid.with_suffix(".owner.json").write_text(json.dumps({"binary": str(mysql)}))
        wait(13306)
    redis_pid = redis_root / "process.id"
    if not owned(16379, redis_pid, redis, ["127.0.0.1:16379"]):
        subprocess.run(
            [
                str(redis),
                "--bind",
                "127.0.0.1",
                "--port",
                "16379",
                "--protected-mode",
                "yes",
                "--daemonize",
                "yes",
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                str(redis_root),
                "--pidfile",
                str(redis_pid),
                "--logfile",
                str(redis_root / "redis.log"),
            ],
            check=True,
        )
        redis_pid.with_suffix(".owner.json").write_text(json.dumps({"binary": str(redis)}))
        wait(16379)
    print(
        json.dumps(
            {
                "mysql": mysql_version,
                "redis": redis_version,
                "ports": [13306, 16379],
                "result": "READY",
            }
        )
    )


if __name__ == "__main__":
    main()
