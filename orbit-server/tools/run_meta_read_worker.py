"""显式Meta只读Worker；不随Web启动、不迁移数据库，不接受凭据参数。"""

import argparse
import asyncio
import json
import re
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def arguments(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, '{"result":"FAILED","code":"META_READ_WORKER_ARGUMENTS_INVALID"}\n')

    parser = SafeParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once", action="store_true")
    modes.add_argument("--serve", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--cycles", type=int)
    value = parser.parse_args(argv)
    if not 1 <= value.limit <= 100 or not 1 <= value.interval <= 3600:
        parser.error("bounds")
    if value.cycles is not None and (not value.serve or not 1 <= value.cycles <= 1000):
        parser.error("cycles")
    return value


def configuration(values):
    enabled = values.get("ORBIT_PYTHON_META_WORKER_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise ValueError("META_READ_WORKER_CONFIGURATION_INVALID")
    if enabled == "false":
        return None
    raw = values.get("ORBIT_PYTHON_ACCOUNT_CURRENCIES")
    try:
        currencies = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        raise ValueError("META_READ_WORKER_CONFIGURATION_INVALID") from None
    if (
        not isinstance(currencies, list)
        or not 1 <= len(currencies) <= 200
        or any(not isinstance(v, str) or re.fullmatch(r"[A-Z]{3}", v) is None for v in currencies)
        or len(set(currencies)) != len(currencies)
    ):
        raise ValueError("META_READ_WORKER_CONFIGURATION_INVALID")
    from orbit_api.meta_read_contract import validate_api_version

    version = validate_api_version(values.get("ORBIT_META_GRAPH_VERSION"))
    return tuple(currencies), version


async def cycle(importer, sync_factory, runtime, tenants, limit):
    await importer.run_once(limit=limit)
    async for tenant in tenants():
        await sync_factory(tenant).run_once(limit=limit)
    await runtime.initial_backfills()
    # schedule internally checks persisted scheduler_enabled; this CLI never changes policy.
    await runtime.schedule()
    await runtime.run_one()


async def execute(
    options,
    *,
    values_provider=None,
    data_sources=None,
    cipher_factory=None,
    importer_factory=None,
    sync_factory=None,
    runtime_factory=None,
    tenants_factory=None,
    stop=None,
    install_signals=False,
):
    sys.path[:0] = [str(ROOT / "python"), str(ROOT / "python/ruoyi_fastapi")]
    if values_provider is None:
        from config.orbit_runtime import private_values

        values_provider = private_values
    config = configuration(values_provider())
    if config is None:
        return {"result": "DISABLED", "code": "META_READ_WORKER_DISABLED", "cycles": 0}
    currencies, version = config
    if data_sources is None:
        from config.database import DataSourceRegistry

        data_sources = DataSourceRegistry
    if cipher_factory is None:
        from orbit_api.configuration_routes import credential_cipher

        cipher_factory = credential_cipher
    if importer_factory is None:
        from orbit_api.account_worker import AccountImportWorker

        importer_factory = AccountImportWorker
    if sync_factory is None:
        from orbit_api.account_actions_sync import AccountSyncWorker

        sync_factory = AccountSyncWorker
    if runtime_factory is None:
        from orbit_api.meta_sync_runtime import MetaSyncRuntime

        runtime_factory = MetaSyncRuntime
    stop, previous, count = stop or asyncio.Event(), {}, 0

    def sessions():
        return data_sources.session(log_sql=False)

    async def tenants():
        from sqlalchemy import text

        after = ""
        while True:
            async with sessions() as session:
                rows = (
                    (
                        await session.execute(
                            text(
                                "SELECT DISTINCT tenant_id FROM orbit_account_command "
                                "WHERE tenant_id>:after "
                                "AND kind='SYNC' AND active_kind='SYNC' "
                                "ORDER BY tenant_id LIMIT 100"
                            ),
                            {"after": after},
                        )
                    )
                    .scalars()
                    .all()
                )
            if not rows:
                return
            for tenant in rows:
                after = tenant
                yield tenant

    initialized = False
    try:
        if install_signals:
            loop = asyncio.get_running_loop()
            for value in (signal.SIGINT, signal.SIGTERM):
                previous[value] = signal.signal(
                    value, lambda *_: loop.call_soon_threadsafe(stop.set)
                )
        await data_sources.initialize(log_enabled=False)
        initialized = True
        cipher = cipher_factory()
        importer = importer_factory(sessions, cipher, currencies, meta_graph_version=version)
        runtime = runtime_factory(sessions, cipher, version)
        while not stop.is_set():
            # Stop on changed controlled policy before the next cycle.
            if configuration(values_provider()) != config:
                return {
                    "result": "STOPPED",
                    "code": "META_READ_WORKER_CONFIGURATION_CHANGED",
                    "cycles": count,
                }
            await cycle(
                importer,
                lambda tenant: sync_factory(
                    sessions, cipher, currencies, tenant, meta_graph_version=version
                ),
                runtime,
                tenants_factory or tenants,
                options.limit,
            )
            count += 1
            if options.once or (options.cycles is not None and count >= options.cycles):
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=options.interval)
            except TimeoutError:
                pass
        return {"result": "COMPLETED", "code": "META_READ_WORKER_CYCLE_COMPLETE", "cycles": count}
    finally:
        try:
            if initialized:
                await data_sources.dispose_all()
        finally:
            for value, handler in previous.items():
                signal.signal(value, handler)


def main(argv=None):
    options = arguments(argv)
    try:
        result = asyncio.run(execute(options, install_signals=True))
        print(json.dumps(result), flush=True)
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        print('{"result":"FAILED","code":"META_READ_WORKER_INTERRUPTED"}', flush=True)
        return 130
    except Exception:
        print('{"result":"FAILED","code":"META_READ_WORKER_FAILED"}', flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
