"""HTTP提供器协议纯测；不启动服务、数据库或CPU子进程。"""

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_launch_allocation_packet import prepare


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return (
        importlib.import_module("launch_allocation_http_fixture"),
        importlib.import_module("launch_allocation_http_provider_checks"),
    )


def test_explicit_fixture_produces_complete_original_packet_and_no_reference_claim(modules):
    from orbit_api.launch_allocation_runtime import _freeze

    fixture, _ = modules
    packet, _, _ = prepare()
    provider = fixture.IsolatedHttpAllocationProvider()
    result = asyncio.run(provider.capture(None, None, packet["plan"], packet["request"]))
    restored, _ = _freeze(result, packet["plan"], packet["request"], 1)
    assert provider.kind == "ISOLATED_TEST"
    assert restored["capability_version"] == "ISOLATED-HTTP-PROTOCOL-NOT-PLATFORM"
    assert set(restored["material_metadata"]) == set(packet["plan"]["asset_ids"])
    assert all(row["revision"] == 1 for row in restored["material_metadata"].values())

    async def publish():
        current, ticket = await provider.prepare_publication(None, None, restored, None)
        assert current == result and ticket is None
        assert await provider.publish_references() is None

    asyncio.run(publish())


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "business"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
    ],
)
def test_checker_rejects_non_exact_fixture_before_any_client_or_sql(modules, host, port, database):
    _, checks = modules
    admin = SimpleNamespace(host=host, port=port)
    with pytest.raises(ValueError):
        checks.run_launch_allocation_http_provider_checks(None, admin, {}, database, [])
    assert len(checks.LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES) == 8


def test_runtime_still_rejects_fixture_on_business_endpoint(modules):
    from sqlalchemy import URL

    from orbit_api.errors import OrbitError
    from orbit_api.launch_allocation_runtime import AllocationRuntime

    fixture, _ = modules
    session = SimpleNamespace(
        bind=SimpleNamespace(url=URL.create("mysql", host="127.0.0.1", port=3306))
    )
    with pytest.raises(OrbitError) as error:
        asyncio.run(
            AllocationRuntime(fixture.IsolatedHttpAllocationProvider()).require_provider(session)
        )
    assert error.value.code == "ALLOCATION_PROVIDER_UNAVAILABLE"
