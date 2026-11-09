"""ORBIT运行配置边界：只读指定私有文件，不继承参考项目或上游样例凭据。"""

import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

PRIVATE_ENV = Path("D:/progress/adpulse-power-system/.env.local")
_fixture: ContextVar[dict[str, Any] | None] = ContextVar("orbit_fixture", default=None)
TEST_MYSQL_PORT = 13306
TEST_REDIS_PORT = 16379
TEST_REDIS_DATABASE = 15
MIN_SIGNING_KEY_LENGTH = 32


class OrbitSettings(BaseSettings):
    """上游模型保留字段校验，但只能从显式ORBIT输入构造，不读取进程通用DB/JWT变量。"""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def configure_isolated_fixture(values: dict[str, Any]) -> None:
    """仅测试引导使用；硬限制临时MySQL与Redis，不能指向用户预览或参考项目。"""
    sources = values.get("ORBIT_PYTHON_DB_SOURCES", {})
    if isinstance(sources, str):
        sources = json.loads(sources)
    if not sources:
        raise ValueError("测试数据源缺失")
    for source in sources.values():
        if (
            source.get("db_host") != "127.0.0.1"
            or source.get("db_port") != TEST_MYSQL_PORT
            or not source.get("db_database", "").startswith("orbit_py_it_")
        ):
            raise ValueError("测试数据源不在独立夹具范围")
    if (
        values.get("ORBIT_PYTHON_REDIS_HOST") != "127.0.0.1"
        or values.get("ORBIT_PYTHON_REDIS_PORT") != TEST_REDIS_PORT
        or values.get("ORBIT_PYTHON_REDIS_DATABASE") != TEST_REDIS_DATABASE
    ):
        raise ValueError("测试缓存不在独立夹具范围")
    _fixture.set(dict(values))


def private_values() -> dict[str, Any]:
    """禁用dotenv插值，防止ORBIT变量引用参考项目的密码或其他进程环境。"""
    fixture = _fixture.get()
    if fixture is not None:
        return dict(fixture)
    if not PRIVATE_ENV.is_file():
        raise RuntimeError("ORBIT私有配置尚未提供")
    return {
        key: value
        for key, value in dotenv_values(PRIVATE_ENV, interpolate=False).items()
        if key.startswith("ORBIT_PYTHON_") and value is not None
    }


def construct(model: type[OrbitSettings], values: dict[str, Any]) -> OrbitSettings:
    """把命名空间中的白名单字段传入模型；异常只返回配置模型名，不回显凭据。"""
    explicit = {
        field: values[f"ORBIT_PYTHON_{field.upper()}"]
        for field in model.model_fields
        if f"ORBIT_PYTHON_{field.upper()}" in values
    }
    defaults: dict[str, dict[str, Any]] = {
        "AppSettings": {
            "app_name": "ORBIT",
            "app_env": "orbit",
            "app_root_path": "",
            "app_host": "127.0.0.1",
            "app_port": 18083,
            "app_reload": False,
            "app_ip_location_query": False,
            "app_current_user_cache_enabled": False,
            "app_default_enabled_plugins": "",
        },
        "TransportCryptoSettings": {
            "transport_crypto_enabled": False,
            "transport_crypto_mode": "off",
        },
    }
    required = {
        "DataBaseSettings": {"db_sources"},
        "JwtSettings": {"jwt_secret_key"},
        "RedisSettings": {"redis_host", "redis_port", "redis_database"},
    }
    if not required.get(model.__name__, set()).issubset(explicit):
        raise RuntimeError(f"ORBIT Python配置缺少必填项：{model.__name__}")
    if (
        model.__name__ == "JwtSettings"
        and len(str(explicit.get("jwt_secret_key", ""))) < MIN_SIGNING_KEY_LENGTH
    ):
        raise RuntimeError("ORBIT Python登录签名配置无效")
    try:
        return model(**(defaults.get(model.__name__, {}) | explicit))
    except Exception:
        raise RuntimeError(f"ORBIT Python配置无效：{model.__name__}") from None
