"""密码策略MGET原生纯回归；只注入不可连接的隔离测试配置。"""

import os
import secrets
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    framework = root / "python/ruoyi_fastapi"
    os.chdir(framework)
    sys.path.insert(0, str(framework))
    from config.orbit_runtime import configure_isolated_fixture

    configure_isolated_fixture(
        {
            "ORBIT_PYTHON_DB_SOURCES": {
                "primary": {
                    "db_type": "mysql",
                    "db_host": "127.0.0.1",
                    "db_port": 13306,
                    "db_username": "unit",
                    "db_password": "",
                    "db_database": "orbit_py_it_unit_no_connection",
                }
            },
            "ORBIT_PYTHON_REDIS_HOST": "127.0.0.1",
            "ORBIT_PYTHON_REDIS_PORT": 16379,
            "ORBIT_PYTHON_REDIS_DATABASE": 15,
            "ORBIT_PYTHON_JWT_SECRET_KEY": secrets.token_hex(32),
            "ORBIT_PYTHON_LOGURU_STDOUT": False,
            "ORBIT_PYTHON_LOG_FILE_ENABLED": False,
        }
    )
    import pytest

    return pytest.main(
        [
            "tests/module_admin/service/test_login_password_policy_batch.py",
            "tests/module_admin/service/test_login_session_renewal.py",
            "tests/module_admin/service/test_login_service.py",
            "tests/module_admin/service/test_login_plugin_routes.py",
            "tests/module_admin/controller/test_login_logout.py",
            "-q",
            "-x",
            "-o",
            "asyncio_mode=auto",
            "-o",
            "asyncio_default_fixture_loop_scope=function",
            "--junitxml=" + str(root / ".runtime/native-password-policy-unit.xml"),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
