"""仅独立MySQL验收库：两条已真实发布来源的连接策略隔离，不制造TRUSTED口径。"""

from uuid import uuid4

from orbit_api.errors import OrbitError
from orbit_api.meta_sync_store import policy_access, read_policy, save_policy
from orbit_api.metric_profile_store import fixture_boundary


async def check_connection_policies(sessions, actor, selections, *, account_ids=None):
    """selections为两项(connection_id,profile_id,adapter_version)，由外部真实来源fixture准备。"""
    if len(selections) != 2 or len({item[0] for item in selections}) != 2:
        raise ValueError("需要两条不同连接的已发布口径")
    receipts = []
    for connection, profile, adapter in selections:
        async with sessions() as session, session.begin():
            await fixture_boundary(session)
            current = await policy_access(session, actor)
            old = await read_policy(session, current, connection_id=connection)
            value = dict(
                profile_id=profile,
                adapter_version=adapter,
                scheduler_enabled=False,
                revision=old["revision"] if old else 0,
            )
            key = "connection-policy-" + str(uuid4())
            saved = await save_policy(
                session, current, value, key, str(uuid4()), connection_id=connection
            )
            assert saved["profile_id"] == profile and saved["scheduler_enabled"] is False
            receipts.append((connection, value, key, saved))
    async with sessions() as session, session.begin():
        await fixture_boundary(session)
        current = await policy_access(session, actor)
        for connection, value, key, saved in receipts:
            row = await read_policy(session, current, connection_id=connection)
            assert row["profile_id"] == value["profile_id"] and row["revision"] == saved["revision"]
            assert (
                await save_policy(
                    session, current, value, key, str(uuid4()), connection_id=connection
                )
                == saved
            )
    async with sessions() as session, session.begin():
        current = await policy_access(session, actor)
        connection, value, key, saved = receipts[0]
        try:
            await save_policy(
                session, current, value, key, str(uuid4()), connection_id=receipts[1][0]
            )
        except OrbitError as error:
            assert error.code == "IDEMPOTENCY_CONFLICT"
        else:
            raise AssertionError("跨连接重放不得命中其他连接策略")
    async with sessions() as session, session.begin():
        current = await policy_access(session, actor)
        wrong = dict(receipts[0][1], revision=receipts[1][3]["revision"])
        try:
            await save_policy(
                session,
                current,
                wrong,
                "wrong-source-" + str(uuid4()),
                str(uuid4()),
                connection_id=receipts[1][0],
            )
        except OrbitError as error:
            assert error.code == "METRIC_PROFILE_SOURCE_CHANGED"
        else:
            raise AssertionError("当前连接不得使用另一连接的指标证明")
    cases = [
        "two_connection_policy_independent",
        "connection_policy_idempotent_replay",
        "connection_policy_cross_target_key_rejected",
        "connection_policy_wrong_source_rejected",
    ]

    if account_ids is not None:
        from sqlalchemy import text

        from orbit_api.meta_sync_runtime import enqueue_metrics

        if len(account_ids) != 2:
            raise ValueError("需提供两条连接各自已绑定账户")
        for account_id, (connection, profile, adapter) in zip(account_ids, selections, strict=True):
            async with sessions() as session, session.begin():
                await fixture_boundary(session)
                current = await policy_access(session, actor)
                account = (
                    (
                        await session.execute(
                            text(
                                "SELECT id,timezone_id FROM orbit_ad_account "
                                "WHERE tenant_id=:tenant AND id=:id"
                            ),
                            {"tenant": current.tenant_id, "id": account_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                job = await enqueue_metrics(session, current, account, str(uuid4()), days=7)
                assert job["profile_id"] == profile and job["connection_id"] == connection
                assert job["adapter_version"] == adapter
        cases.append("two_connection_enqueue_uses_own_policy")
    return cases
