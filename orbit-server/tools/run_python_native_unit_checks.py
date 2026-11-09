"""原若依人员写服务与请求时区纯单测：不加载私有配置、不连接数据库或Redis。"""

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

    # 仅满足导入模型的必填配置；本组所有外部操作均由原纯单测mock。
    # 即使意外访问MySQL，也只会尝试不存在的专用fixture库/账号，不能回退用户预览。
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

    (root / ".runtime").mkdir(exist_ok=True)
    return pytest.main(
        [
            "tests/module_admin/service/test_user_service.py",
            "tests/common/test_request_timezone.py",
            "tests/module_identity/service/test_password_null_guard.py",
            "-q",
            "-o",
            "asyncio_default_fixture_loop_scope=function",
            "--junitxml=" + str(root / ".runtime/native-directory-unit.xml"),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
