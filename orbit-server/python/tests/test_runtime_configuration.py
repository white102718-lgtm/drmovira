"""Python新底座私有配置边界，防止沿用参考项目和Java预览的环境信息。"""

import json
from contextvars import ContextVar

import pytest
from config import orbit_runtime as runtime


@pytest.fixture(autouse=True)
def isolated_configuration_source(monkeypatch):
    monkeypatch.setattr(runtime, "_fixture", ContextVar("test_fixture", default=None))


def fixture_values():
    return {
        "ORBIT_PYTHON_DB_SOURCES": {
            "primary": {
                "db_type": "mysql",
                "db_host": "127.0.0.1",
                "db_port": 13306,
                "db_database": "orbit_py_it_fixture",
                "db_username": "root",
                "db_password": "",
            }
        },
        "ORBIT_PYTHON_REDIS_HOST": "127.0.0.1",
        "ORBIT_PYTHON_REDIS_PORT": 16379,
        "ORBIT_PYTHON_REDIS_DATABASE": 15,
    }


def test_private_file_filters_namespace_and_never_interpolates_reference_secret(
    tmp_path, monkeypatch
):
    source = tmp_path / "private.env"
    source.write_text(
        "REFERENCE_PASSWORD=fixture-private\nDB_PASSWORD=other\n"
        'ORBIT_DB_PASSWORD=old-java\nORBIT_PYTHON_DB_PASSWORD="${REFERENCE_PASSWORD}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "PRIVATE_ENV", source)
    monkeypatch.setenv("ORBIT_PYTHON_DB_PASSWORD", "process-must-not-win")
    assert runtime.private_values() == {"ORBIT_PYTHON_DB_PASSWORD": "${REFERENCE_PASSWORD}"}


@pytest.mark.parametrize("name", ["DB_PASSWORD", "JWT_SECRET_KEY", "ORBIT_PYTHON_JWT_SECRET_KEY"])
def test_generic_or_process_environment_cannot_override_explicit_settings(name, monkeypatch):
    class Settings(runtime.OrbitSettings):
        jwt_secret_key: str = "explicit-only"

    monkeypatch.setenv(name, "unrelated-secret")
    assert runtime.construct(Settings, {}).jwt_secret_key == "explicit-only"


def test_missing_private_file_fails_without_falling_back_to_working_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runtime, "PRIVATE_ENV", tmp_path / "missing")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("DB_PASSWORD=unsafe\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ORBIT私有配置尚未提供"):
        runtime.private_values()


@pytest.mark.parametrize(
    "field,value",
    [
        ("db_host", "remote.example"),
        ("db_port", 13307),
        ("db_database", "orbit_preview"),
        ("db_database", "adpulse"),
    ],
)
def test_fixture_rejects_preview_and_other_databases(field, value):
    values = fixture_values()
    values["ORBIT_PYTHON_DB_SOURCES"]["primary"][field] = value
    with pytest.raises(ValueError, match="独立夹具"):
        runtime.configure_isolated_fixture(values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ORBIT_PYTHON_REDIS_HOST", "remote.example"),
        ("ORBIT_PYTHON_REDIS_PORT", 16380),
        ("ORBIT_PYTHON_REDIS_DATABASE", 0),
    ],
)
def test_fixture_rejects_preview_or_nonexclusive_redis(field, value):
    values = fixture_values()
    values[field] = value
    with pytest.raises(ValueError, match="独立夹具"):
        runtime.configure_isolated_fixture(values)


def test_fixture_accepts_json_source_and_returns_defensive_copy():
    values = fixture_values()
    values["ORBIT_PYTHON_DB_SOURCES"] = json.dumps(values["ORBIT_PYTHON_DB_SOURCES"])
    runtime.configure_isolated_fixture(values)
    first = runtime.private_values()
    first["ORBIT_PYTHON_REDIS_PORT"] = 1
    assert runtime.private_values()["ORBIT_PYTHON_REDIS_PORT"] == 16379


def test_required_jwt_key_has_no_generated_or_short_fallback():
    class JwtSettings(runtime.OrbitSettings):
        jwt_secret_key: str = "not-allowed-default"

    for values in ({}, {"ORBIT_PYTHON_JWT_SECRET_KEY": "short"}):
        with pytest.raises(RuntimeError):
            runtime.construct(JwtSettings, values)
    assert (
        runtime.construct(JwtSettings, {"ORBIT_PYTHON_JWT_SECRET_KEY": "x" * 32}).jwt_secret_key
        == "x" * 32
    )


def test_configuration_errors_do_not_echo_input_secrets():
    class DataBaseSettings(runtime.OrbitSettings):
        db_sources: int

    with pytest.raises(RuntimeError) as error:
        runtime.construct(DataBaseSettings, {"ORBIT_PYTHON_DB_SOURCES": "fixture-secret-value"})
    assert "fixture-secret-value" not in str(error.value)
    assert error.value.__cause__ is None


def test_controlled_meta_app_keys_are_loaded_without_legacy_credentials(tmp_path, monkeypatch):
    source = tmp_path / "meta.env"
    source.write_text(
        "ORBIT_META_APP_ID=123\nORBIT_META_APP_SECRET=fixture-only\nORBIT_META_GRAPH_VERSION=v24.0\nORBIT_META_LOGIN_CONFIG_ID=456\nORBIT_DB_PASSWORD=must-not-load\n"
    )
    monkeypatch.setattr(runtime, "PRIVATE_ENV", source)
    values = runtime.private_values()
    assert values["ORBIT_META_APP_ID"] == "123"
    assert values["ORBIT_META_GRAPH_VERSION"] == "v24.0"
    assert "ORBIT_DB_PASSWORD" not in values
