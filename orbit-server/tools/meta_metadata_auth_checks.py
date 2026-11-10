"""原导入/元数据同步Worker真实SQL失效回写；Graph仅使用显式隔离transport。"""

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import context
from orbit_api.account_actions_store import AccountActionsStore
from orbit_api.account_actions_sync import AccountSyncWorker
from orbit_api.account_contract import AccountImport
from orbit_api.account_worker import AccountImportWorker
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.meta_account_sources import invalidate_meta_read_source, load_connection
from orbit_api.meta_metric_collection import one

CASE = "metaPipelineOriginalImportAndMetadataSyncAuthFailureCAS"


async def check_metadata_auth(
    sessions,
    cipher,
    tenant,
    service,
    connection,
    graph,
    adapter,
    account,
    imports,
    vendor_id,
    vendor,
):
    async def reauthorize():
        start = await service.start(
            1, "/orbit/accounts", str(uuid4()), str(uuid4()), connection["id"]
        )
        state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
        await service.callback(1, state, "isolated-code", str(uuid4()))
        async with sessions() as s:
            return await one(
                s,
                "SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant AND id=:id",
                {"tenant": tenant, "id": connection["id"]},
            )

    active = await reauthorize()
    sync = AccountSyncWorker(
        sessions, cipher, {"USD"}, tenant, meta_graph_version="v24.0", meta_adapter_factory=adapter
    )
    # 原手动同步旧命令冻结旧来源，先让真实恢复器拒绝，不能手改终态绕active约束。
    await sync.run_once()
    actions = AccountActionsStore(DirectoryTokens(cipher))
    async with sessions() as s, s.begin():
        caps = await actions.capabilities(s, 1, "", account["id"], "SYNC")
        await actions.sync(
            s,
            1,
            account["id"],
            caps["revision"],
            str(uuid4()),
            "",
            caps["csrf_token"],
            "隔离元数据认证失败",
            str(uuid4()),
        )
        old_source = await load_connection(
            s, cipher, tenant, connection["id"], active["revision"], "v24.0"
        )
    graph.auth_failed = True
    await sync.run_once()
    graph.auth_failed = False
    async with sessions() as s:
        expired = await one(
            s,
            "SELECT status,revision,(token_envelope IS NULL) cleared FROM "
            "orbit_meta_connection WHERE tenant_id=:tenant AND id=:id",
            {"tenant": tenant, "id": connection["id"]},
        )
        assert expired["status"] == "REAUTH_REQUIRED" and expired["cleared"]
        assert expired["revision"] == active["revision"] + 1
        command = await one(
            s,
            "SELECT state,last_error_code FROM orbit_account_command WHERE "
            "tenant_id=:tenant AND account_id=:account AND kind='SYNC' "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            {"tenant": tenant, "account": account["id"]},
        )
        assert command["state"] == "FAILED" and command["last_error_code"] == "META_AUTH_FAILED"
    active = await reauthorize()
    async with sessions() as s, s.begin():
        current, _ = await context(s, 1, "accounts.sync")
        assert not await invalidate_meta_read_source(
            s, current, old_source, "META_AUTH_FAILED", str(uuid4())
        )
        unchanged = await one(
            s,
            "SELECT status,revision FROM orbit_meta_connection WHERE tenant_id=:tenant AND id=:id",
            {"tenant": tenant, "id": connection["id"]},
        )
        assert unchanged["status"] == "ACTIVE" and unchanged["revision"] == active["revision"]

    async def new_import():
        external = str(uuid4().int % 10**24)
        async with sessions() as s, s.begin():
            caps = await imports.capabilities(s, 1, "")
            result = await imports.create(
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
                    "VALUES(:tenant,:batch,:connection,:revision,NULL,1)"
                ),
                {
                    "tenant": tenant,
                    "batch": result["id"],
                    "connection": connection["id"],
                    "revision": active["revision"],
                },
            )
        return result

    first, queued = await new_import(), await new_import()
    graph.auth_failed = True
    await AccountImportWorker(
        sessions,
        cipher,
        {"USD"},
        target=(tenant, first["id"]),
        meta_graph_version="v24.0",
        meta_adapter_factory=adapter,
    ).run_once()
    graph.auth_failed = False
    async with sessions() as s:
        expired = await one(
            s,
            "SELECT status,revision,(token_envelope IS NULL) cleared FROM "
            "orbit_meta_connection WHERE tenant_id=:tenant AND id=:id",
            {"tenant": tenant, "id": connection["id"]},
        )
        assert expired["status"] == "REAUTH_REQUIRED" and expired["cleared"]
        assert expired["revision"] == active["revision"] + 1
        row = await one(
            s,
            "SELECT state,account_id,JSON_UNQUOTE(JSON_EXTRACT(value_json,'$.error_code')) code "
            "FROM orbit_account_import_row WHERE tenant_id=:tenant AND batch_id=:batch",
            {"tenant": tenant, "batch": first["id"]},
        )
        assert (
            row["state"] == "FAILED"
            and row["account_id"] is None
            and row["code"] == "META_AUTH_FAILED"
        )
    before = graph.calls
    await AccountImportWorker(
        sessions,
        cipher,
        {"USD"},
        target=(tenant, queued["id"]),
        meta_graph_version="v24.0",
        meta_adapter_factory=adapter,
    ).run_once()
    assert graph.calls == before, "失效来源排队导入不得再次发送Token"
    async with sessions() as s:
        state = await one(
            s,
            "SELECT state,account_id FROM orbit_account_import_row "
            "WHERE tenant_id=:tenant AND batch_id=:batch",
            {"tenant": tenant, "batch": queued["id"]},
        )
        assert state["state"] == "FAILED" and state["account_id"] is None
