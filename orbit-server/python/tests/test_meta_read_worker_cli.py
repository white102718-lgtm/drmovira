import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def cli():
    spec = importlib.util.spec_from_file_location(
        "meta_read_cli", Path(__file__).resolve().parents[2] / "tools/run_meta_read_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_disabled_never_initializes_database():
    sources = SimpleNamespace(initialize=AsyncMock(), dispose_all=AsyncMock())
    result = await cli().execute(
        cli().arguments(["--once"]), values_provider=lambda: {}, data_sources=sources
    )
    assert result["code"] == "META_READ_WORKER_DISABLED"
    sources.initialize.assert_not_awaited()


def test_argument_errors_never_echo_secret(capsys):
    with pytest.raises(SystemExit):
        cli().arguments(["--once", "--token=secret-value"])
    assert "secret-value" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "currencies", [None, "USD", "[]", '["usd"]', '["USD","USD"]', "[1]", '["USD", ""]']
)
def test_enabled_requires_explicit_currency_json(currencies):
    with pytest.raises(ValueError):
        cli().configuration(
            {
                "ORBIT_PYTHON_META_WORKER_ENABLED": "true",
                "ORBIT_PYTHON_ACCOUNT_CURRENCIES": currencies,
                "ORBIT_META_GRAPH_VERSION": "v24.0",
            }
        )


@pytest.mark.asyncio
async def test_cycle_runs_import_metadata_backfill_schedule_and_metrics_without_policy_writes():
    m = cli()
    events = []

    class Worker:
        async def run_once(self, **kwargs):
            events.append("read")

    class Runtime:
        async def initial_backfills(self):
            events.append("backfill")

        async def schedule(self):
            events.append("schedule")

        async def run_one(self):
            events.append("metrics")

    async def tenants():
        yield "tenant"

    await m.cycle(Worker(), lambda tenant: Worker(), Runtime(), tenants, 2)
    assert events == ["read", "read", "backfill", "schedule", "metrics"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_execute_wires_workers_and_always_disposes(fail):
    m = cli()
    sources = SimpleNamespace(initialize=AsyncMock(), dispose_all=AsyncMock())
    captured = []
    worker = SimpleNamespace(
        run_once=AsyncMock(side_effect=RuntimeError("secret") if fail else None)
    )
    runtime = SimpleNamespace(
        initial_backfills=AsyncMock(), schedule=AsyncMock(), run_one=AsyncMock()
    )

    def importer(*args, **kw):
        captured.append((args, kw))
        return worker

    async def tenants():
        yield "tenant"

    values = {
        "ORBIT_PYTHON_META_WORKER_ENABLED": "true",
        "ORBIT_PYTHON_ACCOUNT_CURRENCIES": '["USD","EUR"]',
        "ORBIT_META_GRAPH_VERSION": "v24.0",
    }
    call = m.execute(
        m.arguments(["--once"]),
        values_provider=lambda: values,
        data_sources=sources,
        cipher_factory=lambda: "cipher",
        importer_factory=importer,
        sync_factory=importer,
        runtime_factory=lambda *args: runtime,
        tenants_factory=tenants,
    )
    if fail:
        with pytest.raises(RuntimeError):
            await call
    else:
        assert (await call)["cycles"] == 1
        assert len(captured) == 2
        assert captured[0][0][2] == ("USD", "EUR")
        assert captured[0][1] == {"meta_graph_version": "v24.0"}
        runtime.initial_backfills.assert_awaited_once()
        runtime.schedule.assert_awaited_once()
        runtime.run_one.assert_awaited_once()
    sources.initialize.assert_awaited_once_with(log_enabled=False)
    sources.dispose_all.assert_awaited_once()
