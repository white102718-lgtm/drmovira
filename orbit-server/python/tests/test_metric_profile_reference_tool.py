"""指标原Plan HTTP工具目标护栏及真实DTO/精确依赖SQL样本纯测。"""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.launch_contract import parse_plan

PATH = Path(__file__).resolve().parents[2] / "tools/metric_profile_reference_checks.py"
spec = importlib.util.spec_from_file_location("metric_reference_guard", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TENANT = str(UUID(int=1))


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 32 + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_checker_and_seed_deny_before_http_or_database(host, port, database):
    admin = SimpleNamespace(
        host=host, port=port, cursor=Mock(side_effect=AssertionError("不能访问DB"))
    )
    client = Mock(side_effect=AssertionError("不能访问HTTP"))
    for function, arguments in (
        (
            module.run_metric_profile_reference_checks,
            (client, admin, {}, "unused", None, database, []),
        ),
        (module.seed_metric_reference_profile, (admin, database, TENANT)),
    ):
        with pytest.raises(ValueError):
            function(*arguments)
    admin.cursor.assert_not_called()
    client.assert_not_called()


class Cursor:
    def __init__(self, database, tenant=TENANT, old=None):
        self.database, self.tenant, self.old = database, tenant, old
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, values=None):
        self.statements.append((statement, values))

    def fetchone(self):
        sql = self.statements[-1][0]
        if sql == "SELECT DATABASE()":
            return (self.database,)
        if sql.startswith("SELECT tenant_id"):
            return (self.tenant,)
        if "FROM orbit_metric_profile_clock" in sql:
            return (3,)
        if "FROM orbit_metric_profile_head" in sql:
            return self.old
        raise AssertionError("未知fixture查询")


def admin_for(cursor):
    return SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=lambda: cursor, commit=Mock(), rollback=Mock()
    )


@pytest.mark.parametrize(
    "database,tenant", [("foreign_database", TENANT), ("orbit_py_it_" + "a" * 32, str(UUID(int=2)))]
)
def test_actual_database_and_current_root_tenant_are_checked_before_writes(
    monkeypatch, database, tenant
):
    monkeypatch.syspath_prepend(str(PATH.parent))
    cursor = Cursor(database, tenant)
    admin = admin_for(cursor)
    with pytest.raises(AssertionError):
        module.seed_metric_reference_profile(admin, "orbit_py_it_" + "a" * 32, TENANT)
    assert not any(sql.startswith(("INSERT ", "UPDATE ")) for sql, _ in cursor.statements)
    admin.rollback.assert_called_once()
    admin.commit.assert_not_called()


@pytest.mark.parametrize("old", [None, (3,)])
def test_seed_binds_exact_profile_hash_proof_observation_and_head_revision_same_transaction(
    monkeypatch, old
):
    monkeypatch.syspath_prepend(str(PATH.parent))
    database = "orbit_py_it_" + "a" * 32
    cursor = Cursor(database, old=old)
    admin = admin_for(cursor)
    profile, dependency = module.seed_metric_reference_profile(admin, database, TENANT)
    assert dependency["version"] == profile["version"]
    assert dependency["head_revision"] == (4 if old else 1)
    assert dependency["profile_hash"] == hashlib.sha256(canonical(profile).encode()).hexdigest()
    assert dependency["source_config_id"] is dependency["source_config_revision"] is None
    for statement, values in cursor.statements:
        if values is not None:
            assert statement.count("%s") == len(values)
    version = next(
        values
        for sql, values in cursor.statements
        if sql.startswith("INSERT INTO orbit_metric_profile_version")
    )
    proof = json.loads(version[-1])
    assert version[9].isoformat() == proof["observed_at"].replace("+00:00", "")
    assert version[5:7] == ("FIXTURE", "ISOLATED_TEST")
    admin.commit.assert_called_once()
    admin.rollback.assert_not_called()


def test_plan_fixture_is_actual_original_planwrite_and_only_original_adset_metric_field(
    monkeypatch,
):
    monkeypatch.syspath_prepend(str(PATH.parent))
    identifier = str(UUID(int=5))
    value = module.metric_reference_plan_fixture(
        {"id": str(UUID(int=6)), "team": str(UUID(int=7))}, identifier
    )
    checked = parse_plan(canonical(value).encode())
    assert checked["campaigns"][0]["adsets"][0]["metric_profile_id"] == identifier
    assert checked["asset_ids"] == checked["account_ids"] == checked["identity_bindings"] == []
    assert not checked["activate_after_create"] and "metric_profile_version" not in checked


def test_case_exports_are_exact_ten_unique_limited_http_groups():
    names = module.METRIC_PROFILE_REFERENCE_CASES
    assert len(names) == len(set(names)) == 10
    assert all(name.startswith("pythonMetricReference") for name in names)
    assert module.NATIVE_ACTOR == module.NATIVE_ROLE == 940430001


@pytest.fixture
def original_error_spec(monkeypatch):
    monkeypatch.syspath_prepend(str(PATH.parent))
    original = PATH.resolve().parents[2] / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
    return json.loads(original.read_text(encoding="utf-8"))


def permission_error():
    return {
        "code": "PERMISSION_DENIED",
        "message": "当前读取权限已撤销",
        "field_errors": [],
        "retryable": False,
        "request_id": str(UUID(int=8)),
    }


def test_permission_error_uses_original_exact_five_field_schema(original_error_spec):
    module.assert_metric_reference_permission_error(permission_error(), original_error_spec)


@pytest.mark.parametrize(
    "change",
    [
        {"field_errors": None},
        {
            "field_errors": [
                {
                    "path": "/",
                    "code": "PERMISSION_DENIED",
                    "message": "不应有字段错误",
                    "constraint": "",
                }
            ]
        },
        {"retryable": 0},
        {"retryable": True},
        {"request_id": "not-uuid"},
        {"message": ""},
        {"plan": {"id": str(UUID(int=9))}},
        {"code": "DIFFERENT"},
    ],
)
def test_permission_error_rejects_bad_types_business_data_and_unexpected_fields(
    original_error_spec, change
):
    with pytest.raises((AssertionError, ValueError)):
        module.assert_metric_reference_permission_error(
            permission_error() | change, original_error_spec
        )


def test_configuration_style_three_field_error_is_not_plan_contract(original_error_spec):
    value = permission_error()
    del value["field_errors"]
    del value["retryable"]
    with pytest.raises(AssertionError):
        module.assert_metric_reference_permission_error(value, original_error_spec)
