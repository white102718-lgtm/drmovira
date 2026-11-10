"""同租户第二读取来源：真实OAuth/账户导入/口径发行，网络仍明确隔离Graph。"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_contract import AccountImport
from orbit_api.account_worker import AccountImportWorker
from orbit_api.configuration import ConfigurationWrite
from orbit_api.configuration_store import ConfigurationStore
from orbit_api.meta_connection_contract import MetaApplication, ValidatedGrant
from orbit_api.meta_connection_service import MetaConnectionService
from orbit_api.meta_metric_collection import one
from orbit_api.meta_metric_profile_source import MetaMetricProfileService
from orbit_api.metric_profile_store import fixture_boundary


async def prepare_second_connection(
    sessions, cipher, tenant, graph, adapter, imports, vendor_id, vendor
):
    external = str(uuid4().int % 10**24)
    async with sessions() as s, s.begin():
        await fixture_boundary(s)

    class OAuth:
        async def exchange(self, code):
            assert code == "isolated-code"
            return "pipeline-second-isolated-token", ValidatedGrant(
                external,
                ("ads_read",),
                datetime.now(UTC) + timedelta(hours=2),
                datetime.now(UTC) + timedelta(days=1),
            )

    service = MetaConnectionService(
        sessions, cipher, MetaApplication("123", "isolated-secret", "v24.0", "456"), OAuth()
    )
    start = await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()))
    state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
    await service.callback(1, state, "isolated-code", str(uuid4()))
    async with sessions() as s, s.begin():
        connection = await one(
            s,
            "SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant AND principal_id=:id",
            {"tenant": tenant, "id": external},
        )
        caps = await imports.capabilities(s, 1, "")
        batch = await imports.create(
            s,
            1,
            "",
            caps["csrf_token"],
            str(uuid4()),
            AccountImport(
                vendor_id, external, vendor["data_owner_user_ids"][0], vendor["owner_team_id"]
            ),
            str(uuid4()),
        )
        await s.execute(
            text(
                "INSERT INTO orbit_meta_import_source "
                "(tenant_id,batch_id,connection_id,connection_revision,channel_id,revision) "
                "VALUES(:tenant,:batch,:connection,1,NULL,1)"
            ),
            {"tenant": tenant, "batch": batch["id"], "connection": connection["id"]},
        )
    previous = graph.external
    graph.external = external
    try:
        await AccountImportWorker(
            sessions,
            cipher,
            {"USD"},
            target=(tenant, batch["id"]),
            meta_graph_version="v24.0",
            meta_adapter_factory=adapter,
        ).run_once()
        async with sessions() as s, s.begin():
            account = await one(
                s,
                "SELECT * FROM orbit_ad_account WHERE tenant_id=:tenant AND external_id=:external",
                {"tenant": tenant, "external": external},
            )
            assert account is not None
            config = await ConfigurationStore(cipher).save(
                s,
                1,
                str(uuid4()),
                ConfigurationWrite(
                    section="METRICS",
                    name="第二读取口径" + external,
                    enabled=True,
                    settings=dict(
                        intervalMinutes=15,
                        lookbackDays=7,
                        profileVersion="pipeline-second-v1",
                        registerActionType="complete_registration",
                        purchaseActionType="purchase",
                        valueActionType="purchase",
                    ),
                    secrets={},
                    reason="隔离双来源验收",
                ),
                request_id=str(uuid4()),
            )
        await MetaMetricProfileService(sessions, cipher, "v24.0", adapter_factory=adapter).publish(
            1,
            dict(
                configuration_id=config["id"],
                configuration_revision=config["revision"],
                connection_id=connection["id"],
                connection_revision=1,
                account_id=external,
                attribution_windows=["7d_click", "1d_view"],
                action_report_time="conversion",
                maturity_days=28,
                expected_revision=0,
            ),
            str(uuid4()),
            str(uuid4()),
        )
        return connection, config, account
    finally:
        graph.external = previous
