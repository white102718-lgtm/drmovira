"""浏览器技术夹具定位/独立登记护栏纯测；不执行SQL或HTTP。"""

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
sys.path.insert(0, TOOLS)
try:
    tool = importlib.import_module("metrics_browser_fixture")
finally:
    sys.path.remove(TOOLS)


def prepared_control(monkeypatch, tmp_path):
    root = tmp_path / "metrics-browser-fixture"
    monkeypatch.setattr(tool, "CONTROL_ROOT", root)
    run = str(uuid4())
    path = root / run / "control.json"
    path.parent.mkdir(parents=True)
    value = {
        "version": 1,
        "run_id": run,
        "database": "orbit_py_it_" + uuid4().hex,
        "tenant_id": str(uuid4()),
        "read_registry": "it_metric_read_" + uuid4().hex[:16],
        "expected_registry": "it_metric_expect_" + uuid4().hex[:16],
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path, value


@pytest.mark.parametrize(
    "patch",
    [
        {"version": True},
        {"version": 2},
        {"password": "forbidden"},
        {"tenant_id": "bad"},
        {"database": "production"},
        {"read_registry": "x;DROP"},
        {"expected_registry": "it_metric_expect_bad"},
        {"run_id": str(uuid4())},
    ],
)
def test_control_strict_schema_version_path_binding_and_random_tables(monkeypatch, tmp_path, patch):
    path, value = prepared_control(monkeypatch, tmp_path)
    path.write_text(json.dumps(value | patch), encoding="utf-8")
    with pytest.raises(OrbitError) as error:
        tool.load_control(path)
    assert error.value.status == 503


def test_control_accepts_only_fixed_root_run_uuid_control_filename(monkeypatch, tmp_path):
    path, value = prepared_control(monkeypatch, tmp_path)
    assert tool.load_control(path) == value
    for invalid in ["control.json", tmp_path / "control.json", path.with_name("other.json")]:
        with pytest.raises(OrbitError):
            tool.load_control(invalid)
    path.write_text('{"version":1,"version":1}', encoding="utf-8")
    with pytest.raises(OrbitError):
        tool.load_control(path)
    path.write_bytes(b"x" * 4097)
    with pytest.raises(OrbitError):
        tool.load_control(path)


@pytest.mark.parametrize("link_kind", ["symbolic", "junction"])
def test_control_rejects_linked_file_or_directory_before_open(monkeypatch, tmp_path, link_kind):
    path, _ = prepared_control(monkeypatch, tmp_path)
    if link_kind == "symbolic":
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda part: part == path.parent or original(part))
    else:
        monkeypatch.setattr(Path, "is_junction", lambda part: part == path.parent, raising=False)
    with pytest.raises(OrbitError):
        tool.load_control(path)


def test_parent_target_guard_precedes_fixture_seed_or_registry_writes(monkeypatch):
    touched = []
    monkeypatch.setattr(tool, "MetricFactSqlFixture", lambda *args: touched.append("fixture"))
    with pytest.raises(ValueError):
        tool.prepare_metrics_browser_fixture(
            None, SimpleNamespace(host="127.0.0.1", port=3306), {}, "", None, "invalid"
        )
    assert not touched


def test_publication_source_identity_is_present_in_initial_insert_never_updated_afterward():
    fixture = SimpleNamespace(
        tenant=str(uuid4()),
        now=datetime(2026, 11, 9, tzinfo=UTC),
        insert=Mock(side_effect=lambda table, row: row),
        sql=Mock(),
    )
    profile = {"id": str(uuid4()), "version": "observed-v001"}
    configuration = str(uuid4())
    value = tool.create_registered_publication(fixture, profile, configuration)
    fixture.insert.assert_called_once_with("orbit_metric_publication", value)
    fixture.sql.assert_not_called()
    assert value["source_config_id"] == configuration and value["source_config_revision"] == 1
    assert value["source_proof_json"] == '{"kind":"SQL_ONLY_NOT_PLATFORM"}'
    assert (
        value["profile_hash"] == tool.digest(profile) and value["authority_kind"] == "ISOLATED_TEST"
    )
    assert value["expected_cell_count"] == 4 and value["capture_sequence_max"] == 120


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,path", [(False, None), (True, None), ("True", "not_allowed"), (False, "not_allowed")]
)
async def test_lazy_provider_requires_explicit_flag_and_path_before_any_sql(enabled, path):
    session = SimpleNamespace(execute=AsyncMock())
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=str(uuid4())))
    provider = tool.LazyMetricsReadProvider(path, enabled=enabled)
    with pytest.raises(OrbitError):
        await provider.verify_publications(session, scope, {}, ())
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_missing_control_file_is_unavailable_without_database_access(monkeypatch, tmp_path):
    path, value = prepared_control(monkeypatch, tmp_path)
    path.unlink()
    session = session_for(value)
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=value["tenant_id"]))
    with pytest.raises(OrbitError):
        await tool.LazyMetricsReadProvider(path, enabled=True).verify_publications(
            session, scope, {}, ()
        )
    session.execute.assert_not_called()


def session_for(value, *, connection=False, actual=None):
    url = SimpleNamespace(host="127.0.0.1", port=13306, database=value["database"])
    bind = (
        SimpleNamespace(engine=SimpleNamespace(url=url)) if connection else SimpleNamespace(url=url)
    )
    return SimpleNamespace(
        bind=bind,
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one=lambda: actual or value["database"])
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("connection", [False, True])
async def test_lazy_provider_guards_actual_owned_database_then_delegates_registered_receipt(
    monkeypatch, tmp_path, connection
):
    path, value = prepared_control(monkeypatch, tmp_path)
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=value["tenant_id"]))
    session = session_for(value, connection=connection)
    verifier = AsyncMock(return_value=("registered-receipt",))
    monkeypatch.setattr(
        tool, "RegisteredSqlReadSource", lambda name: SimpleNamespace(verify_publications=verifier)
    )
    provider = tool.LazyMetricsReadProvider(path, enabled=True)
    heads = ({"id": "incoming-head-is-not-receipt"},)
    assert await provider.verify_publications(session, scope, {"q": "name"}, heads) == (
        "registered-receipt",
    )
    verifier.assert_awaited_once_with(session, scope, {"q": "name"}, heads)
    assert str(session.execute.call_args.args[0]) == "SELECT DATABASE()"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["tenant", "host", "port", "url_database", "actual_database"])
async def test_lazy_provider_never_delegates_outside_exact_uuid_database_or_tenant(
    monkeypatch, tmp_path, damage
):
    path, value = prepared_control(monkeypatch, tmp_path)
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=value["tenant_id"]))
    session = session_for(value, actual="wrong" if damage == "actual_database" else None)
    if damage == "tenant":
        scope.current.tenant_id = str(uuid4())
    if damage in {"host", "port", "url_database"}:
        setattr(
            session.bind.url,
            {"host": "host", "port": "port", "url_database": "database"}[damage],
            "wrong",
        )
    factory = AsyncMock()
    monkeypatch.setattr(tool, "RegisteredSqlReadSource", factory)
    with pytest.raises(OrbitError):
        await tool.LazyMetricsReadProvider(path, enabled=True).verify_publications(
            session, scope, {}, ()
        )
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_expected_wrapper_delegates_exact_registered_manifest_and_all_streams(
    monkeypatch, tmp_path
):
    path, value = prepared_control(monkeypatch, tmp_path)
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=value["tenant_id"]))
    session = session_for(value)
    saved = object()

    async def units(*args):
        yield ("registered-unit",)

    async def members(*args):
        yield ("registered-member",)

    delegate = SimpleNamespace(
        prepare_manifest=AsyncMock(return_value=saved),
        revalidate_manifest=AsyncMock(return_value=saved),
        iter_unit_batches=units,
        iter_membership_batches=members,
    )
    monkeypatch.setattr(tool, "RegisteredSqlExpected", lambda table: delegate)
    provider = tool.LazyMetricsExpectedProvider(path, enabled=True)
    assert await provider.prepare_manifest(session, scope, {"q": ""}, object()) is saved
    assert await provider.revalidate_manifest(session, scope, {}, saved) is saved
    assert [b async for b in provider.iter_unit_batches(session, scope, {}, saved)] == [
        ("registered-unit",)
    ]
    assert [b async for b in provider.iter_membership_batches(session, scope, {}, saved)] == [
        ("registered-member",)
    ]


def corpus():
    fixture = SimpleNamespace(
        tenant=str(uuid4()),
        owner=str(uuid4()),
        team=str(uuid4()),
        now=datetime(2026, 11, 9, tzinfo=UTC),
    )
    profile = {"id": str(uuid4()), "version": "observed-v001"}

    def tree():
        account = str(uuid4())
        return [
            {
                "id": str(uuid4()),
                "account_id": account,
                "entity_id": account if kind == "ACCOUNT" else str(uuid4()),
                "name": "SQL_ONLY_" + kind,
                "external_id": "000123",
            }
            for kind in tool.DATASETS
        ]

    trees = [tree() for _ in range(3)]
    ads = [trees[0][3]] + [
        {**trees[0][3], "id": str(uuid4()), "entity_id": str(uuid4()), "name": f"中文指标广告{i}"}
        for i in range(1, 21)
    ]
    renamed = {**ads[0], "id": str(uuid4()), "name": "中文指标名称%_!"}
    return fixture, profile, trees, ads, renamed


def test_finite_predeclared_query_set_exact_13_fields_and_no_cursor_authority():
    queries = list(tool.supported_queries(str(uuid4())))
    assert len(queries) == 460
    assert len({tool.metric_query_hash(value) for value in queries}) == 460
    assert all(
        len(value) == 13 and value["cursor"] is None and value["scope_snapshot_id"] is None
        for value in queries
    )
    assert {value["dataset"] for value in queries} == set(tool.DATASETS)


@pytest.mark.parametrize(
    "dataset,count", [("ACCOUNT", 6), ("CAMPAIGN", 4), ("ADSET", 4), ("AD", 44)]
)
def test_two_day_independent_complete_unit_roster_includes_empty_and_missing_currencies(
    dataset, count
):
    fixture, profile, trees, ads, renamed = corpus()
    units, members = tool.expected_streams(
        fixture, profile, trees, ads, renamed, tool.query(profile["id"], dataset=dataset)
    )
    assert len(units) == 6 and len(members) == count
    assert {unit.currency for unit in units} == {"USD", "EUR", "GBP"}
    assert sum(unit.entity_count for unit in units) == count
    assert all(
        unit.entity_hash
        == tool.stream_hash([member for member in members if member.key()[:2] == unit.key()])
        for unit in units
    )


def test_literal_query_keeps_true_same_entity_two_day_name_snapshots_and_no_match_units():
    fixture, profile, trees, ads, renamed = corpus()
    units, members = tool.expected_streams(
        fixture, profile, trees, ads, renamed, tool.query(profile["id"], q="%_!")
    )
    assert len(units) == 6 and len(members) == 2
    assert {member.entity_id for member in members} == {renamed["entity_id"]}
    assert {member.entity_snapshot_id for member in members} == {ads[0]["id"], renamed["id"]}
    empty_units, empty_members = tool.expected_streams(
        fixture, profile, trees, ads, renamed, tool.query(profile["id"], q="不存在的指标")
    )
    assert len(empty_units) == 6 and not empty_members
