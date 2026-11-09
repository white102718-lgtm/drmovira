"""执行工具协议自检；替身不替代真实HTTP/SQL、CLEAN或平台验收。"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from tools.launch_execution_checks import (
    EXECUTION_CASES,
    clocked_sessions,
    epoch_seconds,
    run_launch_execution_checks,
)
from tools.launch_execution_fixture import (
    IsolatedExecutionProvider,
    IsolatedExecutionValidationProvider,
    create_protocol_plan,
)
from tools.launch_validation_fixture import IsolatedValidationProvider

from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.launch_access import digest
from orbit_api.launch_execution_contract import iter_execution_nodes
from orbit_api.launch_execution_store import ExecutionInput
from orbit_api.launch_expansion import ad_slots
from orbit_api.launch_plan_source import PlanSource
from orbit_api.launch_validation_contract import freeze_validation
from orbit_api.launch_validation_store import ObservationReference, ValidationEvidence


class Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, args=None):
        self.calls.append((sql, args))

    def executemany(self, sql, args):
        self.calls.append((sql, args))

    def fetchone(self):
        return (date(2026, 11, 8),)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "ordinary"),
    ],
)
def test_execution_tool_refuses_nonisolated_database_before_io(host, port, database):
    connection = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        run_launch_execution_checks(
            None, connection, {}, None, None, database, [], control_dir=None, cipher=object()
        )
    connection.cursor.assert_not_called()


def test_clock_precision_and_distinct_honest_case_names():
    value = datetime(2026, 11, 8, 15, 59, 59, 999000, tzinfo=UTC)
    assert epoch_seconds(value) % 1 == Decimal("0.999")
    assert len(EXECUTION_CASES) == len(set(EXECUTION_CASES)) == 16
    assert all("Production" not in name for name in EXECUTION_CASES)


@pytest.mark.asyncio
async def test_clock_session_binds_decimal_numeric_instead_of_quoted_string():
    """SET timestamp要求数值；同时核驱动实际escape协议，不能仅比较文本值。"""
    import pymysql.converters

    connection = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), in_transaction=lambda: False
    )

    def sessions():
        return AsyncContext(connection)

    point = datetime(2026, 11, 8, 15, 59, 59, 999000, tzinfo=UTC)
    async with clocked_sessions(sessions, point)():
        pass
    sql, parameters = connection.execute.await_args_list[0].args
    assert str(sql) == "SET SESSION timestamp=:value"
    assert isinstance(parameters["value"], Decimal)
    escaped = pymysql.converters.escape_item(parameters["value"], "utf8mb4")
    assert escaped == str(epoch_seconds(point)) and not escaped.startswith("'")
    assert str(connection.execute.await_args_list[-1].args[0]) == "SET SESSION timestamp=0"


def test_tools_import_under_actual_framework_child_directory_without_repository_pythonpath():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    script = (
        "import sys;sys.path[:0]="
        + repr([str(root / "tools"), str(root / "python")])
        + ";import launch_execution_fixture,launch_execution_checks;"
        "assert len(launch_execution_checks.EXECUTION_CASES)==16;print('IMPORT_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root / "python" / "ruoyi_fastapi",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, "子进程工具导入失败"
    assert result.stdout.strip() == "IMPORT_OK"


@pytest.mark.asyncio
async def test_execution_validation_subclass_changes_only_marked_capture_not_old_packet(
    monkeypatch,
):
    evidence = ValidationEvidence(
        "a" * 64,
        1,
        1,
        (),
        (),
        canonical({"channel_snapshot": {"authority": "ISOLATED_TEST"}}).encode(),
    )
    monkeypatch.setattr(IsolatedValidationProvider, "capture", AsyncMock(return_value=evidence))
    implementation = IsolatedExecutionValidationProvider(None)
    plain = SimpleNamespace(source=SimpleNamespace(payload=lambda: {"name": "plain"}))
    assert await implementation.capture(plain) is evidence
    marked = SimpleNamespace(
        source=SimpleNamespace(payload=lambda: {"name": "fixture_EXECUTE_TEST"})
    )
    actual = await implementation.capture(marked)
    assert json.loads(actual.freeze_arguments_json)["channel_snapshot"]["type"] == "WEBSITE"
    assert "type" not in json.loads(evidence.freeze_arguments_json)["channel_snapshot"]


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
async def test_fixture_full_capture_compiles_actual_sql_plan_shape_without_placeholder_commands(
    monkeypatch,
):
    cursor = Cursor()
    admin = SimpleNamespace(cursor=lambda: cursor, commit=Mock())
    tenant, owner, team = (str(uuid4()) for _ in range(3))
    item = create_protocol_plan(admin, tenant, owner, team)
    value = item["value"]
    allocation_call = next(
        args for sql, args in cursor.calls if "INSERT INTO orbit_launch_allocation(" in sql
    )
    name_rows = next(
        args for sql, args in cursor.calls if "INSERT INTO orbit_launch_name_item(" in sql
    )
    from tools.task_core_fixture import compile_dag

    arguments = {
        "allocation": {
            "id": item["body"]["allocation_id"],
            "plan_id": item["id"],
            "plan_revision": 1,
            "state": "SUCCEEDED",
            "task_id": None,
            "algorithm_version": "allocation-v1",
            "seed": 0,
            "input_hash": allocation_call[-1],
            "warnings": [],
            "items": [
                {
                    "slot_key": slot.key,
                    "account_id": slot.account_id,
                    "asset_id": value["asset_ids"][0],
                    "asset_revision": 1,
                }
                for slot in ad_slots(value)
            ],
        },
        "name_reservation": {
            "id": item["body"]["name_reservation_id"],
            "plan_revision": 1,
            "naming_date": "2026-11-08",
            "items": [
                {"slot_key": row[3], "name": row[4], "sequence": str(row[5])} for row in name_rows
            ],
        },
        "capability_version": "ISOLATED_PROTOCOL_NOT_PLATFORM",
        "policy_version": "ISOLATED_POLICY_NOT_PRODUCTION",
        "scope_version": 1,
        "channel_snapshot": {
            "fixture_plan_id": item["id"],
            "authority": "ISOLATED_TEST",
            "type": "WEBSITE",
        },
        "product_snapshot": {"fixture_plan_id": item["id"], "authority": "ISOLATED_TEST"},
        "currency": "USD",
    }
    now = datetime(2026, 11, 8, 9, tzinfo=UTC)
    validation = freeze_validation(
        value,
        plan_id=item["id"],
        source_revision=1,
        total_dag_node_count=compile_dag(value).total_dag_node_count,
        validated_at=now,
        **arguments,
    )
    source = PlanSource(tenant, item["id"], 1, 2, digest(value), canonical(value).encode())
    current = BusinessContext(1, tenant, "SUPER", owner, team)
    observations = (
        ObservationReference("ALLOCATION", arguments["allocation"]["id"], 1),
        ObservationReference("NAME_RESERVATION", arguments["name_reservation"]["id"], 1),
        ObservationReference("SCOPE", tenant, 1),
    )
    evidence = ValidationEvidence(
        "a" * 64,
        1,
        validation.total_dag_node_count,
        (),
        observations,
        canonical(arguments | {"total_dag_node_count": validation.total_dag_node_count}).encode(),
    )
    monkeypatch.setattr(
        IsolatedExecutionValidationProvider, "capture", AsyncMock(return_value=evidence)
    )
    rows = Mock()
    rows.mappings.return_value.first.return_value = item["body"]
    session = SimpleNamespace(
        bind=SimpleNamespace(url=SimpleNamespace(host="127.0.0.1", port=13306)),
        execute=AsyncMock(
            side_effect=[
                Mock(scalar_one=lambda: "orbit_py_it_" + "a" * 32),
                rows,
                Mock(scalar_one=lambda: now),
            ]
        ),
        begin=lambda: AsyncContext(None),
    )
    provider = IsolatedExecutionProvider(lambda: AsyncContext(session))
    result = await provider.capture(
        ExecutionInput(
            current,
            source,
            str(uuid4()),
            validation,
            canonical({"hash": validation.hash, "activate_ack": False}).encode(),
        )
    )
    nodes = list(iter_execution_nodes(result.prepared))
    assert len(nodes) == validation.total_dag_node_count
    assert all(isinstance(node["resolved_configuration"], dict) for node in nodes)
    assert any(node["resolved_configuration"].get("name") == name_rows[0][4] for node in nodes)
    assert result.prepared.execution_authorized is False
