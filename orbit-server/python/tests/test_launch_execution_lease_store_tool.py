"""窄Store真实工具护栏/固定证据协议；无DB、无HTTP或引擎连接。"""

import hashlib
import importlib
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import URL
from test_launch_execution_lease_contract import NOW, binding, fact

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError

module = importlib.import_module("tools.launch_execution_lease_store_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("192.0.2.1", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", "13306", DATABASE),
        ("127.0.0.1", 13306.0, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE[:-1]),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_tool_denies_wrong_target_before_http_or_database(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        module.run_execution_lease_store_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


@pytest.mark.parametrize("flag", [0, 1, "true", None])
def test_append_scope_requires_explicit_boolean_not_inferred_from_environment(flag):
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        module.run_execution_lease_store_checks(
            client, admin, {}, "unused", None, DATABASE, [], include_append=flag
        )
    admin.cursor.assert_not_called()
    assert not client.mock_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,port,database",
    [("localhost", 13306, DATABASE), ("127.0.0.1", 3306, DATABASE), ("127.0.0.1", 13306, "orbit")],
)
async def test_technical_authority_itself_cannot_be_reused_in_production(host, port, database):
    attempt = binding()
    authority = module.IsolatedLeaseEvidenceAuthority(database, {attempt.node_id: attempt}, {})
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            engine=SimpleNamespace(
                url=URL.create("mysql+asyncmy", host=host, port=port, database=database)
            )
        ),
        execute=AsyncMock(),
    )
    with pytest.raises(OrbitError) as error:
        await authority.authorize(session, 1, attempt, module.LeaseOperation.RECOVER_EXPIRED)
    assert error.value.code == "ISOLATED_LEASE_AUTHORITY_REJECTED"
    session.execute.assert_not_awaited()


def technical_fact():
    original = fact()
    document = module.evidence_document(
        original.binding,
        original.event_id,
        original.kind,
        original.phase,
        original.source,
        original.occurred_at,
        original.external_id,
    )
    encoded = canonical(document).encode()
    return replace(original, evidence_sha256=hashlib.sha256(encoded).hexdigest()), encoded


@pytest.mark.asyncio
async def test_actual_fixed_document_must_match_before_typed_receipt():
    record, encoded = technical_fact()
    authority = module.IsolatedLeaseEvidenceAuthority(
        DATABASE, {record.binding.node_id: record.binding}, {record.event_id: encoded}
    )
    receipt = await authority.verify_fact(None, record, recorded_at=NOW)
    assert receipt.fact == record and receipt.recorded_at == NOW
    assert authority.verified == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("part", ["classification", "request_correlation", "submitted"])
async def test_matching_sha_alone_cannot_validate_different_raw_fixture_observation(part):
    record, encoded = technical_fact()
    document = json.loads(encoded)
    document["fixture_observation"][part] = "altered-technical-observation"
    changed = canonical(document).encode()
    # SHA本身完全匹配，但实际观察语义和原精确事件不符，必须拒绝。
    record = replace(record, evidence_sha256=hashlib.sha256(changed).hexdigest())
    authority = module.IsolatedLeaseEvidenceAuthority(
        DATABASE, {record.binding.node_id: record.binding}, {record.event_id: changed}
    )
    with pytest.raises(OrbitError) as error:
        await authority.verify_fact(None, record, recorded_at=NOW)
    assert error.value.code == "ISOLATED_LEASE_EVIDENCE_REJECTED"
    assert authority.verified == 0


@pytest.mark.asyncio
async def test_fact_with_same_evidence_hash_but_different_unique_object_is_rejected():
    record, encoded = technical_fact()
    authority = module.IsolatedLeaseEvidenceAuthority(
        DATABASE, {record.binding.node_id: record.binding}, {record.event_id: encoded}
    )
    with pytest.raises(OrbitError):
        await authority.verify_fact(None, replace(record, external_id="999"), recorded_at=NOW)


def test_fixture_source_sql_parameters_match_actual_placeholder_count_before_engine(monkeypatch):
    """只检查SQL样本构造的参数形状，不模拟数据库约束或完整039来源成功。"""
    from datetime import datetime
    from uuid import UUID

    def uid(value):
        return str(UUID(int=value))

    task = {
        "id": uid(4),
        "state": "QUEUED",
        "revision": 1,
        "node_count": 10,
        "execution_mode": "META_API",
    }

    class Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, parameters=()):
            assert sql.count("%s") == len(parameters)
            if sql == "SELECT DATABASE()":
                self.rows = ((DATABASE,),)
            elif sql.startswith("SELECT tenant_id,id,team_id"):
                self.rows = ((uid(1), uid(2), uid(3)),)
            elif sql.startswith("SELECT id,manifest_hash"):
                self.rows = ((uid(5), "a" * 64, "b" * 64, "c" * 64, 1, uid(2), 1),)
            elif sql.startswith("SELECT node_id,resolved_configuration_hash"):
                self.rows = tuple((uid(10 + n), "d" * 64) for n in range(4))
            elif sql.startswith("SELECT manifest_phase"):
                self.rows = (("COMPLETE", 10, 10),)
            elif sql == "SELECT UTC_TIMESTAMP(3)":
                self.rows = ((datetime(2026, 11, 9, 8),),)
            else:
                self.rows = ()

        def executemany(self, sql, rows):
            for parameters in rows:
                assert sql.count("%s") == len(parameters)

        def fetchall(self):
            return self.rows

    def response(value, status):
        return SimpleNamespace(status_code=status, json=lambda: value)

    client = SimpleNamespace(
        get=lambda *_args, **_kwargs: response({"csrf_token": "fixture"}, 200),
        post=lambda path, **_kwargs: (
            response({"valid": True, "hash": "f" * 64}, 200)
            if path.endswith("/validate")
            else response(task, 202)
        ),
    )
    admin = SimpleNamespace(
        host="127.0.0.1",
        port=13306,
        user=b"fixture",
        password=b"memory-only",
        cursor=Cursor,
        begin=Mock(),
        commit=Mock(),
        rollback=Mock(),
    )
    monkeypatch.setattr(module, "create_protocol_plan", lambda *_args: {"id": uid(6), "body": {}})

    class StopBeforeEngine(Exception):
        pass

    def no_engine(*_args, **_kwargs):
        raise StopBeforeEngine

    monkeypatch.setattr(module, "create_async_engine", no_engine)
    with pytest.raises(StopBeforeEngine):
        module.run_execution_lease_store_checks(client, admin, {}, "unused", None, DATABASE, [])
    assert admin.begin.call_count == 2  # 运行样本与首条事实均明确begin。


@pytest.mark.asyncio
@pytest.mark.parametrize("bind_kind", ["engine", "connection"])
async def test_authority_accepts_engine_and_owned_connection_bind_with_actual_database_guard(
    bind_kind,
):
    attempt = binding()
    authority = module.IsolatedLeaseEvidenceAuthority(DATABASE, {attempt.node_id: attempt}, {})
    engine = SimpleNamespace(
        url=URL.create("mysql+asyncmy", host="127.0.0.1", port=13306, database=DATABASE)
    )
    engine.engine = engine
    bound = engine if bind_kind == "engine" else SimpleNamespace(engine=engine)
    result = Mock()
    result.scalar_one.return_value = DATABASE
    session = SimpleNamespace(
        get_bind=Mock(return_value=bound), execute=AsyncMock(return_value=result)
    )
    grant = await authority.authorize(
        session, attempt.actor_id, attempt, module.LeaseOperation.HISTORICAL_FACT
    )
    assert grant == module.LeaseAuthorityGrant(
        attempt.actor_id, attempt, module.LeaseOperation.HISTORICAL_FACT
    )
    session.get_bind.assert_called_once_with()
    session.execute.assert_awaited_once()
    assert str(session.execute.await_args.args[0]) == "SELECT DATABASE()"


@pytest.mark.asyncio
async def test_authority_connection_bind_still_rejects_actual_database_mismatch():
    attempt = binding()
    authority = module.IsolatedLeaseEvidenceAuthority(DATABASE, {attempt.node_id: attempt}, {})
    result = Mock()
    result.scalar_one.return_value = "orbit_py_it_" + "b" * 32
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            engine=SimpleNamespace(
                url=URL.create("mysql+asyncmy", host="127.0.0.1", port=13306, database=DATABASE)
            )
        ),
        execute=AsyncMock(return_value=result),
    )
    with pytest.raises(OrbitError) as error:
        await authority.authorize(
            session, attempt.actor_id, attempt, module.LeaseOperation.HISTORICAL_FACT
        )
    assert error.value.code == "ISOLATED_LEASE_AUTHORITY_REJECTED"
