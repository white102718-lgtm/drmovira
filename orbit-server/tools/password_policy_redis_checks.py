"""独占16379/DB15的真实Redis密码策略读取；不连接私有配置或业务数据库。"""

import asyncio
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


async def check():
    sys.path.insert(0, str(ROOT / "python/ruoyi_fastapi"))
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
    from module_admin.service.login_service import LoginService
    from redis.asyncio import Redis
    from redis.exceptions import ResponseError

    keys = tuple(
        "sys_config:sys.account." + name
        for name in ("chrtype", "initPasswordModify", "passwordValidateDays")
    )
    report = {
        "status": "RUNNING",
        "executed_at": datetime.now(UTC).isoformat(),
        "scope": "ISOLATED_REAL_REDIS_POLICY_ONLY_NOT_CAPACITY_OR_PLATFORM_ACCEPTANCE",
        "cases": [],
        "cancel_after_send": "NOT_MEASURED_HERE_PURE_PROTOCOL_SEPARATE",
        "source_sha256": {
            "login_service": hashlib.sha256(
                (ROOT / "python/ruoyi_fastapi/module_admin/service/login_service.py").read_bytes()
            ).hexdigest(),
            "tool": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    }
    async with Redis(host="127.0.0.1", port=16379, db=15, decode_responses=True) as cache:
        assert await cache.ping() and await cache.dbsize() == 0, "EXCLUSIVE_EMPTY_FIXTURE_REQUIRED"
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=cache)))
        try:
            assert await LoginService._read_password_policy(request, None) == ("0", False, False)
            report["cases"].append("missing_defaults")
            await cache.mset(dict(zip(keys, ("7", "1", "30"), strict=True)))
            assert await LoginService._read_password_policy(request, None) == ("7", True, True)
            report["cases"].append("normal_values_and_missing_password_date")
            await cache.set(keys[2], "invalid-days")
            try:
                await LoginService._read_password_policy(request, None)
            except ValueError:
                report["cases"].append("invalid_days_still_raises")
            else:
                raise AssertionError("INVALID_POLICY_SILENTLY_DEFAULTED")
            for index, key in enumerate(keys):
                await cache.delete(*keys)
                await cache.mset(dict(zip(keys, ("7", "1", "30"), strict=True)))
                await cache.delete(key)
                await cache.lpush(key, "isolated-type-probe")
                try:
                    await LoginService._read_password_policy(request, None)
                except ResponseError as error:
                    assert "WRONGTYPE" in str(error)
                    report["cases"].append("wrong_type_key_" + str(index + 1))
                else:
                    raise AssertionError("WRONG_TYPE_SILENTLY_DEFAULTED")
            await cache.delete(*keys)
            await cache.mset(dict(zip(keys, ("3", "0", "0"), strict=True)))
            assert await LoginService._read_password_policy(request, None) == ("3", False, False)
            report["cases"].append("connection_reusable_after_errors")
            await cache.set(keys[0], "5")
            assert await LoginService._read_password_policy(request, None) == ("5", False, False)
            report["cases"].append("next_request_observes_configuration_change")
            report["status"] = "PASS"
        except Exception as error:
            report["status"] = "FAIL"
            report["failure_type"] = type(error).__name__
        finally:
            # 仅清理本工具在先验空库中创建的固定三键，绝不FLUSHDB。
            await cache.delete(*keys)
            report["remaining_keys"] = await cache.dbsize()
            if report["remaining_keys"] != 0:
                report["status"] = "FAILED_FIXTURE_NOT_EMPTY"
    (ROOT / "docs/orbit/evidence/python-password-policy-redis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
