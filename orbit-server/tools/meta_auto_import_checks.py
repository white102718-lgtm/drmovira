"""真实隔离MySQL分页/租约/回滚/归属验证；Graph是显式合成响应，不声明Meta外部通过。"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

CASES = [
    "metaAutoImportCallbackEnqueuesFrozenOwner",
    "metaAutoImportPaginationSurvivesRestartAndStaleLease",
    "metaAutoImportPageAuditFailureRollsBackCheckpointAndBatch",
    "metaAutoImportNullVendorCreatesRealRowsAndPreservesExistingOwnership",
    "metaAutoImportCurrentPermissionRevocationBlocksNetwork",
    "metaAutoImportManualNullVendorUsesOriginalAcceptanceAndWorker",
]


async def run_meta_auto_import_checks(sessions, cipher, tenant, connection, cases):
    from orbit_api.account_worker import AccountImportWorker
    from orbit_api.meta_auto_import import MetaAutoImportWorker, enqueue, latest_status
    from orbit_api.meta_read_adapter import GraphResponse, MetaReadAdapter

    async def task_row():
        async with sessions() as db, db.begin():
            return dict(
                (
                    await db.execute(
                        text(
                            "SELECT * FROM orbit_meta_auto_import WHERE tenant_id=:tenant AND "
                            "connection_id=:connection ORDER BY created_at DESC,id DESC LIMIT 1"
                        ),
                        dict(tenant=tenant, connection=connection),
                    )
                )
                .mappings()
                .one()
            )

    task = await task_row()
    assert task["state"] == "QUEUED" and task["actor_id"] == 1
    async with sessions() as db, db.begin():
        owner = (
            (
                await db.execute(
                    text(
                        "SELECT id,team_id FROM orbit_business_user WHERE tenant_id=:tenant AND "
                        "user_id=1"
                    ),
                    {"tenant": tenant},
                )
            )
            .mappings()
            .one()
        )
        assert task["owner_user_id"] == owner["id"] and task["owner_team_id"] == owner["team_id"]
        principal = (
            await db.execute(
                text(
                    "SELECT principal_id FROM orbit_meta_connection WHERE tenant_id=:tenant AND "
                    "id=:id"
                ),
                {"tenant": tenant, "id": connection},
            )
        ).scalar_one()
    cases.append(CASES[0])
    prefix = str(int(uuid4().hex[:12], 16))
    first, second = prefix + "1", prefix + "2"

    class Graph:
        calls = []

        async def request(self, method, path, parameters, token, *, maximum_bytes):
            assert method == "GET"
            self.calls.append((path, dict(parameters)))
            account_id = second if parameters.get("after") else first
            if "/act_" in path:
                account_id = path.rsplit("act_", 1)[1].split("/")[0]
            value = dict(
                id="act_" + account_id,
                account_id=account_id,
                name="自动导入隔离账户",
                currency="USD",
                timezone_name="UTC",
                account_status=1,
                amount_spent="1234",
                balance="567",
                business_name="隔离企业",
                business={"id": "987", "name": "隔离BM"},
                is_prepay_account=False,
                funding_source_details={"display_string": "Visa *1234"},
                disable_reason=0,
            )
            if path.endswith("/insights"):
                day = datetime.now(UTC).date().isoformat()
                payload = {
                    "data": [
                        {
                            "account_id": account_id,
                            "account_currency": "USD",
                            "date_start": day,
                            "date_stop": day,
                            "spend": "0.12",
                        }
                    ]
                }
            elif path.endswith("/me"):
                payload = {"id": principal, "name": "隔离授权主体"}
            elif path.endswith("/adaccounts"):
                payload = {"data": [value]}
                if not parameters.get("after"):
                    payload["paging"] = {
                        "cursors": {"after": "page-two"},
                        "next": "https://graph.facebook.com" + path + "?after=page-two",
                    }
            else:
                payload = value
            return GraphResponse(200, json.dumps(payload).encode())

    graph = Graph()

    def factory(configuration):
        return MetaReadAdapter(configuration, transport=graph)

    worker = MetaAutoImportWorker(sessions, cipher, "v24.0", adapter_factory=factory)
    assert await worker.run_once(limit=1) == 1
    task = await task_row()
    assert task["page_number"] == 1 and task["state"] == "QUEUED"
    old_claim = await worker.claim()
    async with sessions() as db, db.begin():
        await db.execute(
            text(
                "UPDATE orbit_meta_auto_import SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL "
                "121 SECOND WHERE id=:id"
            ),
            {"id": task["id"]},
        )
    resumed = MetaAutoImportWorker(sessions, cipher, "v24.0", adapter_factory=factory)
    new_claim = await resumed.claim()
    source = await resumed.preflight(new_claim)
    from orbit_api.meta_read_contract import ReadCheckpoint

    checkpoint = task["checkpoint_json"]
    checkpoint = json.loads(checkpoint) if isinstance(checkpoint, str) else checkpoint
    page = await factory(source.configuration).accounts_page(
        checkpoint=ReadCheckpoint(**checkpoint)
    )
    assert await worker.publish(old_claim, page) is False
    # 事务中断不能留下页批次或推进检查点；租约仍可恢复。
    async with sessions() as db, db.begin():
        await db.execute(
            text(
                "CREATE TRIGGER isolated_auto_import_audit_failure BEFORE INSERT ON "
                "orbit_account_event FOR EACH ROW SIGNAL SQLSTATE '45000' SET "
                "MESSAGE_TEXT='isolated rollback'"
            )
        )
    try:
        try:
            await resumed.publish(new_claim, page)
        except Exception:
            pass
        else:
            raise AssertionError("审计失败未回滚自动发现页")
    finally:
        async with sessions() as db, db.begin():
            await db.execute(text("DROP TRIGGER isolated_auto_import_audit_failure"))
    task = await task_row()
    assert task["page_number"] == 1
    async with sessions() as db, db.begin():
        assert (
            await db.execute(
                text("SELECT COUNT(*) FROM orbit_meta_auto_import_batch WHERE task_id=:id"),
                {"id": task["id"]},
            )
        ).scalar_one() == 1
    cases.append(CASES[2])
    assert await resumed.publish(new_claim, page) is True
    task = await task_row()
    assert task["page_number"] == 2 and task["state"] == "IMPORTING"
    async with sessions() as db, db.begin():
        batches = (await latest_status(db, tenant, connection))["batches"]
        assert len(batches) == 2
    cases.append(CASES[1])
    for batch in batches:
        importer = AccountImportWorker(
            sessions,
            cipher,
            {"USD"},
            target=(tenant, batch["id"]),
            meta_graph_version="v24.0",
            meta_adapter_factory=factory,
        )
        await importer.run_once(limit=10)
    async with sessions() as db, db.begin():
        status = await latest_status(db, tenant, connection)
        assert (
            status["state"] == "SUCCEEDED" and status["success_count"] == 2 and status["total"] == 2
        ), status
        accounts = [
            dict(row)
            for row in (
                await db.execute(
                    text(
                        "SELECT "
                        "id,external_id,owner_user_id,owner_team_id,"
                        "vendor_id,revision,details_json "
                        "FROM orbit_ad_account WHERE tenant_id=:tenant AND external_id IN "
                        "(:first,:second)"
                    ),
                    dict(tenant=tenant, first=first, second=second),
                )
            ).mappings()
        ]
        assert len(accounts) == 2 and all(
            row["vendor_id"] is None and row["owner_user_id"] == owner["id"] for row in accounts
        )
        for account in accounts:
            details = account["details_json"]
            details = json.loads(details) if isinstance(details, str) else details
            assert details["observations"]["payable"]["amount"] == "5.67"
            assert details["observations"]["lifetime_spend"]["amount"] == "12.34"
            assert details["observations"]["personal_profile"]["code"] == principal
            assert details["business_managers"] == [{"external_id": "987", "name": "隔离BM"}]
            assert details["source_config_id"] == connection
            assert (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_account_event WHERE tenant_id=:tenant AND "
                        "resource_id=:id AND action='ACCOUNT_BOUND'"
                    ),
                    {"tenant": tenant, "id": account["id"]},
                )
            ).scalar_one() == 1
        # 当前同步许可允许初次自动导入排队原SYNC；不是另造消费表或转化口径。
        assert (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_account_command WHERE tenant_id=:tenant AND "
                    "account_id IN (:first,:second) AND kind='SYNC'"
                ),
                {"tenant": tenant, "first": accounts[0]["id"], "second": accounts[1]["id"]},
            )
        ).scalar_one() == 2
        # 服务端再次发现同一批ID：保留既有账户归属、版本及来源，不触发重复创建。
        replay = dict(
            id=str(uuid4()),
            tenant_id=tenant,
            actor_id=1,
            owner_user_id=owner["id"],
            owner_team_id=owner["team_id"],
        )
        from orbit_api.meta_connection_service import lock_account_clock
        # 上面仅共享读，另起事务以固定clock在前的写锁顺序。
    from orbit_api.account_actions_sync import AccountSyncWorker

    await AccountSyncWorker(
        sessions, cipher, {"USD"}, tenant, meta_graph_version="v24.0", meta_adapter_factory=factory
    ).run_once(limit=10)
    async with sessions() as db, db.begin():
        for account in accounts:
            fact = (
                (
                    await db.execute(
                        text(
                            "SELECT amount,coverage FROM orbit_account_spend_day WHERE "
                            "tenant_id=:tenant AND account_id=:id AND business_date=UTC_DATE()"
                        ),
                        {"tenant": tenant, "id": account["id"]},
                    )
                )
                .mappings()
                .one()
            )
            assert str(fact["amount"]) == "0.120000" and fact["coverage"] == "COMPLETE"
            updated = (
                (
                    await db.execute(
                        text(
                            "SELECT revision,details_json FROM orbit_ad_account WHERE "
                            "tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": tenant, "id": account["id"]},
                    )
                )
                .mappings()
                .one()
            )
            account.update(dict(updated))
    # 没有转化指标策略时，公开手动SYNC仍需成功受理元数据/每日消费。
    from orbit_api.account_actions_store import AccountActionsStore
    from orbit_api.directory_tokens import DirectoryTokens

    actions = AccountActionsStore(DirectoryTokens(cipher))
    async with sessions() as db, db.begin():
        assert (
            await db.execute(
                text("SELECT COUNT(*) FROM orbit_meta_sync_policy WHERE tenant_id=:tenant"),
                {"tenant": tenant},
            )
        ).scalar_one() == 0
        assert (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_meta_connection_sync_policy WHERE tenant_id=:tenant"
                ),
                {"tenant": tenant},
            )
        ).scalar_one() == 0
        caps = await actions.capabilities(db, 1, "", accounts[0]["id"], "SYNC")
    async with sessions() as db, db.begin():
        ack = await actions.sync(
            db,
            1,
            accounts[0]["id"],
            caps["revision"],
            str(uuid4()),
            "",
            caps["csrf_token"],
            "无指标策略仍可同步账户",
            str(uuid4()),
        )
        assert ack["state"] == "WAITING_EXECUTOR"
        assert (
            await db.execute(
                text("SELECT COUNT(*) FROM orbit_meta_metric_job WHERE tenant_id=:tenant"),
                {"tenant": tenant},
            )
        ).scalar_one() == 0
    await AccountSyncWorker(
        sessions, cipher, {"USD"}, tenant, meta_graph_version="v24.0", meta_adapter_factory=factory
    ).run_once(limit=10)
    async with sessions() as db, db.begin():
        updated = (
            (
                await db.execute(
                    text(
                        "SELECT revision,details_json FROM orbit_ad_account "
                        "WHERE tenant_id=:tenant AND id=:id"
                    ),
                    {"tenant": tenant, "id": accounts[0]["id"]},
                )
            )
            .mappings()
            .one()
        )
        accounts[0].update(dict(updated))
    async with sessions() as db, db.begin():
        await lock_account_clock(db, tenant)
        # 模拟历史上已经分配给另一真实投放师的账户，重新授权不得抢占。
        other = (
            (
                await db.execute(
                    text(
                        "SELECT id,team_id FROM orbit_business_user WHERE tenant_id=:tenant "
                        "AND id<>:owner ORDER BY id LIMIT 1"
                    ),
                    {"tenant": tenant, "owner": owner["id"]},
                )
            )
            .mappings()
            .first()
        )
        assert other is not None, "隔离目录夹具缺少第二位投放师"
        chosen = accounts[0]
        await db.execute(
            text(
                "UPDATE orbit_ad_account SET owner_user_id=:owner,owner_team_id=:team,"
                "value_json=JSON_SET(value_json,'$.ownership.owner_user_id',:owner,"
                "'$.ownership.owner_team_id',:team) WHERE tenant_id=:tenant AND id=:id"
            ),
            {"tenant": tenant, "id": chosen["id"], "owner": other["id"], "team": other["team_id"]},
        )
        await db.execute(
            text(
                "UPDATE orbit_account_assignment SET owner_user_id=:owner,owner_team_id=:team "
                "WHERE tenant_id=:tenant AND account_id=:id"
            ),
            {"tenant": tenant, "id": chosen["id"], "owner": other["id"], "team": other["team_id"]},
        )
        chosen.update(owner_user_id=other["id"], owner_team_id=other["team_id"])
        await enqueue(db, replay, connection, 1, str(uuid4()))
    await worker.run_once(limit=2)
    async with sessions() as db, db.begin():
        replay_batches = (await latest_status(db, tenant, connection))["batches"]
    for batch in replay_batches:
        await AccountImportWorker(
            sessions,
            cipher,
            {"USD"},
            target=(tenant, batch["id"]),
            meta_graph_version="v24.0",
            meta_adapter_factory=factory,
        ).run_once(limit=10)
    async with sessions() as db, db.begin():
        after = [
            dict(row)
            for row in (
                await db.execute(
                    text(
                        "SELECT "
                        "id,external_id,owner_user_id,owner_team_id,"
                        "vendor_id,revision,details_json "
                        "FROM orbit_ad_account WHERE tenant_id=:tenant AND external_id IN "
                        "(:first,:second)"
                    ),
                    dict(tenant=tenant, first=first, second=second),
                )
            ).mappings()
        ]
        assert sorted(after, key=lambda r: r["id"]) == sorted(accounts, key=lambda r: r["id"])
    cases.append(CASES[3])
    # 修改冻结版本而非真实用户权限，等价模拟发起人权限版本已改变，不干扰其他验收会话。
    denied = dict(replay, id=str(uuid4()))
    async with sessions() as db, db.begin():
        await lock_account_clock(db, tenant)
        await enqueue(db, denied, connection, 1, str(uuid4()))
        await db.execute(
            text(
                "UPDATE orbit_meta_auto_import SET "
                "actor_auth_version=actor_auth_version+1 WHERE id=:id"
            ),
            {"id": denied["id"]},
        )
    count = len(graph.calls)
    await worker.run_once(limit=1)
    assert len(graph.calls) == count
    async with sessions() as db, db.begin():
        row = (
            (
                await db.execute(
                    text("SELECT state,error_code FROM orbit_meta_auto_import WHERE id=:id"),
                    {"id": denied["id"]},
                )
            )
            .mappings()
            .one()
        )
        assert (
            row["state"] == "FAILED" and row["error_code"] == "ACCOUNT_IMPORT_AUTHORIZATION_CHANGED"
        )
    cases.append(CASES[4])

    # 人工导入的原有受理路径也接受空户商，且既有账户可直接得到逐项结果。
    import tempfile

    from orbit_api.account_contract import AccountImport
    from orbit_api.account_import_store import AccountImportStore
    from orbit_api.account_objects import AccountImportObjects
    from orbit_api.directory_tokens import DirectoryTokens

    with tempfile.TemporaryDirectory(prefix="orbit-auto-import-input-") as folder:
        store = AccountImportStore(
            DirectoryTokens(cipher), AccountImportObjects(Path(folder).resolve())
        )
        authorization = "isolated-auto-import-session"
        async with sessions() as db, db.begin():
            caps = await store.capabilities(db, 1, authorization)
        async with sessions() as db, db.begin():
            accepted = await store.create(
                db,
                1,
                authorization,
                caps["csrf_token"],
                str(uuid4()),
                AccountImport(None, first, owner["id"], owner["team_id"]),
                str(uuid4()),
            )
        assert accepted["vendor_id"] is None and accepted["state"] == "QUEUED"
        await AccountImportWorker(
            sessions,
            cipher,
            {"USD"},
            target=(tenant, accepted["id"]),
            meta_graph_version="v24.0",
            meta_adapter_factory=factory,
        ).run_once(limit=1)
        async with sessions() as db, db.begin():
            completed = await store.get(db, 1, accepted["id"])
        assert completed["state"] == "SUCCEEDED"
        assert completed["rows"][0]["state"] == "ALREADY_EXISTS"
    cases.append(CASES[5])
