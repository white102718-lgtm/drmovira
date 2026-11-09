"""049生命周期纯替身验证；不计MySQL、临时表隔离或Metrics HTTP验收。"""

import asyncio
import base64
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from test_metrics_query_resume import PersistedSession, persisted
from test_metrics_query_store import (
    NOW,
    OWNER,
    TENANT,
    FakeResult,
    RegisteredPureSource,
    head,
    query,
    scope,
)

from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_result_contract import (
    ExpectedUnitManifest,
    ExpectedUnitProvider,
    QuerySourceIdentity,
)
from orbit_api.metrics_query_result_store import (
    MetricsQueryResultStore,
    ResultBuildBudget,
    _owned_result_connection,
    _StageTicket,
    _TemporaryStage,
    digest,
)
from orbit_api.metrics_query_store import MetricsQueryStore, metric_query_hash

EMPTY = hashlib.sha256().hexdigest()


class Expected(ExpectedUnitProvider):
    kind = "ISOLATED_TEST"

    def __init__(self, value):
        self.value = value

    async def prepare_manifest(self, *args):
        return self.value

    async def revalidate_manifest(self, *args):
        return self.value

    async def iter_unit_batches(self, *args):
        if False:
            yield ()

    async def iter_membership_batches(self, *args):
        if False:
            yield ()


class BuildSession(PersistedSession):
    def __init__(self, source, header):
        super().__init__([source], header)
        self.connection_value = SimpleNamespace()
        # claim使用弱引用，正常AsyncConnection同样支持弱引用。
        self.connection_value = type("Connection", (), {})()
        self.update_count = 1
        self.existing = []
        self.unit_projection_pages = []
        self.total_projection_pages = []
        self.ready_rows, self.ready_totals = [], []

    async def connection(self):
        return self.connection_value

    async def execute(self, statement, values=None):
        sql = str(statement)
        if "_unit_sum u JOIN" in sql:
            return FakeResult(
                self.unit_projection_pages.pop(0) if self.unit_projection_pages else []
            )
        if "_total_unit u JOIN" in sql:
            return FakeResult(
                self.total_projection_pages.pop(0) if self.total_projection_pages else []
            )
        if "FROM orbit_metric_query_sorted_row WHERE" in sql:
            self.calls.append((sql, dict(values)))
            return FakeResult(
                [item for item in self.ready_rows if item["ordinal"] > values["after"]][
                    : values["size"]
                ]
            )
        if "FROM orbit_metric_query_total WHERE" in sql:
            self.calls.append((sql, dict(values)))
            return FakeResult(self.ready_totals)
        if "FROM orbit_metric_query_request r" in sql:
            self.calls.append((sql, dict(values)))
            return FakeResult(self.existing)
        if sql.lstrip().startswith(("UPDATE ", "DELETE ", "INSERT ")):
            captured = [dict(item) for item in values] if type(values) is list else dict(values)
            self.calls.append((sql, captured))
            return SimpleNamespace(
                rowcount=len(values) if type(values) is list else self.update_count
            )
        return await super().execute(statement, values)


def fixture(monkeypatch, **changes):
    source = head()
    row = persisted(
        source,
        **(
            {
                "expected_unit_hash": EMPTY,
                "expected_membership_hash": EMPTY,
                "expected_cell_count": 0,
                "expected_account_count": 0,
                "algorithm_version": (
                    "orbit-metric-result-v1-coverage6-down-ratios6-half-up-stale-null"
                ),
                "expected_membership_count": 0,
                "build_generation": 1,
                "build_token_hash": "f" * 64,
                "lease_until": NOW.replace(tzinfo=None),
            }
            | changes
        ),
    )
    session = BuildSession(source, row)
    manifest = ExpectedUnitManifest(
        QuerySourceIdentity(
            TENANT,
            source["id"],
            source["generation"],
            source["profile_id"],
            source["profile_version"],
            source["profile_hash"],
            "ISOLATED_TEST",
        ),
        1,
        OWNER,
        1,
        "d" * 64,
        metric_query_hash(query()),
        "AD",
        __import__("datetime").date(2026, 1, 1),
        __import__("datetime").date(2026, 1, 2),
        None,
        None,
        None,
        0,
        EMPTY,
        0,
        EMPTY,
    )
    auth = AsyncMock(return_value=scope())
    monkeypatch.setattr("orbit_api.metrics_query_store.authorize_metric_scope", auth)
    monkeypatch.setattr("orbit_api.metrics_query_result_store.authorize_metric_scope", auth)
    monkeypatch.setattr("orbit_api.metrics_query_store.fixture_boundary", AsyncMock())
    read = MetricsQueryStore(RegisteredPureSource([source]), clock=lambda: NOW)
    store = MetricsQueryResultStore(read, Expected(manifest), clock=lambda: NOW)
    return store, session, row


def test_claim_deletes_old_children_before_generation_cas_and_binds_old_nonce(monkeypatch):
    async def run():
        store, session, row = fixture(monkeypatch)
        ticket = await store.claim(session, 1, row["id"])
        assert ticket is not None
        deletions = [
            (index, sql, values)
            for index, (sql, values) in enumerate(session.calls)
            if sql.startswith("DELETE c")
        ]
        update = next(
            (index, sql, values)
            for index, (sql, values) in enumerate(session.calls)
            if sql.lstrip().startswith("UPDATE orbit_metric_query_snapshot")
        )
        assert len(deletions) == 3 and max(item[0] for item in deletions) < update[0]
        for _, sql, values in deletions:
            assert "q.build_token_hash=:token" in sql and "c.build_generation=:generation" in sql
            assert values["tenant"] == TENANT and values["query_id"] == row["id"]
            assert values["generation"] == 1 and values["token"] == "f" * 64
        assert update[2]["next_generation"] == 2
        assert update[2]["next_token"] != row["build_token_hash"]
        await store.fail(session, ticket, "METRICS_DATA_UNVERIFIED")
        failure = session.calls[-1]
        assert "build_token_hash=:token" in failure[0] and failure[1]["generation"] == 2
        session.connection_value = type("OtherConnection", (), {})()
        with pytest.raises(OrbitError) as error:
            await store.fail(session, ticket, "METRICS_DATA_UNVERIFIED")
        assert error.value.status == 409

    asyncio.run(run())


@pytest.mark.parametrize(
    "state,lease,expected",
    [
        ("READY", NOW.replace(tzinfo=None), None),
        ("BUILDING", NOW.replace(tzinfo=None) + timedelta(seconds=1), 409),
        ("FAILED", NOW.replace(tzinfo=None), 503),
    ],
)
def test_ready_not_deleted_and_live_lease_busy_and_failed_intent_retained(
    monkeypatch, state, lease, expected
):
    async def run():
        store, session, row = fixture(monkeypatch, state=state, lease_until=lease)
        if expected is None:
            assert await store.claim(session, 1, row["id"]) is None
        else:
            with pytest.raises(OrbitError) as error:
                await store.claim(session, 1, row["id"])
            assert error.value.status == expected
        assert not any(sql.startswith("DELETE c") for sql, _ in session.calls)

    asyncio.run(run())


def test_provider_manifest_drift_fails_before_any_child_delete(monkeypatch):
    async def run():
        store, session, row = fixture(monkeypatch)
        store.expected_provider.value = replace(store.expected_provider.value, unit_hash="a" * 64)
        with pytest.raises(OrbitError) as error:
            await store.claim(session, 1, row["id"])
        assert error.value.status == 503
        assert not any(sql.startswith("DELETE c") for sql, _ in session.calls)

    asyncio.run(run())


@pytest.mark.parametrize("key", ["stable-original-key", "original key with spaces"])
def test_prepare_persists_original_input_and_both_independent_roots(monkeypatch, key):
    async def run():
        store, session, _ = fixture(monkeypatch)
        original = query()
        result = await store.prepare(session, 1, original, key, str(uuid4()))
        assert result["state"] == "BUILDING" and result["replayed"] is False
        insert = next(
            (sql, values)
            for sql, values in session.calls
            if "INSERT INTO orbit_metric_query_snapshot(" in sql
        )
        assert insert[1]["unit_hash"] == EMPTY and insert[1]["member_hash"] == EMPTY
        assert insert[1]["unit_count"] == 0 and insert[1]["member_count"] == 0
        assert original == query() and original["cursor"] is None
        assert not any("202" in sql or "orbit_task" in sql for sql, _ in session.calls)

    asyncio.run(run())


def test_default_result_store_does_zero_sql(monkeypatch):
    async def run():
        store = MetricsQueryResultStore()
        session = SimpleNamespace(execute=AsyncMock())
        with pytest.raises(OrbitError) as error:
            await store.prepare(session, 1, query(), "original-key", str(uuid4()))
        assert error.value.status == 503
        session.execute.assert_not_called()

    asyncio.run(run())


class Connection:
    def __init__(self):
        self.sql = []
        self.active = True
        self.rollback = AsyncMock(side_effect=self._rollback)
        self.invalidate = AsyncMock()
        self.fail_drop = False
        self.invalidated = False
        self.closed = False
        self.cid = 123
        self.sync_connection = SimpleNamespace(detach=Mock())

    def _rollback(self):
        self.active = False

    def in_transaction(self):
        return self.active

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.sql.append(sql)
        self.active = True
        if self.fail_drop and sql.startswith("DROP "):
            raise RuntimeError("fixed-test-error")
        if sql == "SELECT CONNECTION_ID()":
            return SimpleNamespace(scalar_one=lambda: self.cid)


class OwnedSettingsConnection:
    """只模拟会话设置/物理身份，不能作为服务端取消证明。"""

    def __init__(self):
        self.identifier, self.timeout = 123, 50
        self.invalidated = self.closed = self.active = False
        self.calls = []
        self.sync_connection = SimpleNamespace(detach=Mock())
        self.break_restore = False

    async def execute(self, statement, parameters=None):
        assert not self.invalidated, "失效连接禁止自动重连后execute"
        self.active = True
        sql = str(statement)
        self.calls.append((sql, parameters))
        if sql.startswith("SELECT CONNECTION_ID()"):
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(
                    one=lambda: {
                        "connection_id": self.identifier,
                        "lock_wait_timeout": self.timeout,
                    }
                )
            )
        assert sql == "SET SESSION innodb_lock_wait_timeout=:seconds"
        if parameters["seconds"] == 50 and self.break_restore:
            raise RuntimeError("固定恢复故障")
        self.timeout = parameters["seconds"]

    def in_transaction(self):
        return self.active

    async def commit(self):
        self.active = False

    async def rollback(self):
        self.active = False

    async def close(self):
        self.closed = True

    async def invalidate(self):
        self.invalidated = True


def test_owned_session_one_second_lock_wait_restores_exact_original_cid_before_pool():
    async def run():
        connection = OwnedSettingsConnection()
        async with _owned_result_connection(
            SimpleNamespace(connect=AsyncMock(return_value=connection))
        ) as owned:
            assert owned is connection and connection.timeout == 1 and not connection.active
            connection.active = True
        assert connection.timeout == 50 and connection.closed and not connection.invalidated
        assert [
            params["seconds"] for sql, params in connection.calls if sql.startswith("SET ")
        ] == [1, 50]
        assert all("GLOBAL" not in sql for sql, _ in connection.calls)

    asyncio.run(run())


def test_owned_cancel_invalidated_connection_never_reconnects_for_restore_or_hides_cancel():
    async def run():
        connection = OwnedSettingsConnection()
        with pytest.raises(asyncio.CancelledError):
            async with _owned_result_connection(
                SimpleNamespace(connect=AsyncMock(return_value=connection))
            ):
                count = len(connection.calls)
                connection.invalidated = True
                raise asyncio.CancelledError
        assert len(connection.calls) == count and connection.closed
        assert connection.timeout == 1  # 旧物理会话只依一秒服务端上限，不以新CID复位。

    asyncio.run(run())


def test_owned_cancellation_between_sql_statements_also_discards_original_physical_connection():
    async def run():
        connection = OwnedSettingsConnection()
        with pytest.raises(asyncio.CancelledError):
            async with _owned_result_connection(
                SimpleNamespace(connect=AsyncMock(return_value=connection))
            ):
                assert not connection.active and not connection.invalidated
                raise asyncio.CancelledError
        assert connection.invalidated and connection.closed
        connection.sync_connection.detach.assert_called_once()
        assert [
            params["seconds"] for sql, params in connection.calls if sql.startswith("SET ")
        ] == [1]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["identity", "restore"])
def test_owned_settings_cleanup_failure_does_not_return_unknown_connection_to_pool(failure):
    async def run():
        connection = OwnedSettingsConnection()
        with pytest.raises(OrbitError) as error:
            async with _owned_result_connection(
                SimpleNamespace(connect=AsyncMock(return_value=connection))
            ):
                if failure == "identity":
                    connection.identifier += 1
                else:
                    connection.break_restore = True
        assert error.value.code == "METRICS_STAGE_CLEANUP_UNVERIFIED"
        assert connection.invalidated and connection.closed
        connection.sync_connection.detach.assert_called_once()
        if failure == "identity":
            assert [
                params["seconds"] for sql, params in connection.calls if sql.startswith("SET ")
            ] == [1]

    asyncio.run(run())


@pytest.mark.parametrize("timeout", [0, True, 1073741825])
def test_owned_settings_invalid_initial_values_fail_before_business_yield(timeout):
    async def run():
        connection = OwnedSettingsConnection()
        connection.timeout = timeout
        with pytest.raises(OrbitError):
            async with _owned_result_connection(
                SimpleNamespace(connect=AsyncMock(return_value=connection))
            ):
                pytest.fail("未核验设置不可进入业务事务")
        assert connection.closed and connection.invalidated
        assert not any(sql.startswith("SET ") for sql, _ in connection.calls)

    asyncio.run(run())


def test_temporary_tables_exact_reverse_cleanup_and_repeat_close_noop():
    async def run():
        connection = Connection()
        stage = _TemporaryStage(connection)
        unit = await stage.create("unit", "(id INT) ENGINE=InnoDB")
        member = await stage.create("member", "(id INT) ENGINE=InnoDB")
        await stage.close()
        count = len(connection.sql)
        await stage.close()
        assert len(connection.sql) == count
        assert [sql for sql in connection.sql if sql.startswith("DROP ")] == [
            f"DROP TEMPORARY TABLE IF EXISTS {member}",
            f"DROP TEMPORARY TABLE IF EXISTS {unit}",
        ]
        assert stage.closed and not connection.active and stage.cleanup_verified
        assert stage.cleanup_state == "DROPPED" and stage.connection_id == 123
        connection.invalidate.assert_not_called()

    asyncio.run(run())


def test_failed_cleanup_invalidates_connection_and_never_silently_returns_pool():
    async def run():
        connection = Connection()
        stage = _TemporaryStage(connection)
        await stage.create("unit", "(id INT)")
        connection.fail_drop = True
        with pytest.raises(OrbitError) as error:
            await stage.close()
        assert error.value.code == "METRICS_STAGE_CLEANUP_UNVERIFIED"
        connection.invalidate.assert_awaited_once()
        connection.sync_connection.detach.assert_called_once()
        assert stage.closed and not stage.cleanup_verified and stage.cleanup_state == "FAILED"

    asyncio.run(run())


def test_repeated_cancel_waits_for_exact_temp_cleanup_before_connection_can_return():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        class Gated(Connection):
            async def execute(self, statement, parameters=None):
                if str(statement).startswith("DROP "):
                    entered.set()
                    await release.wait()
                return await super().execute(statement, parameters)

        connection = Gated()
        stage = _TemporaryStage(connection)
        await stage.create("unit", "(id INT)")
        task = asyncio.create_task(stage.close())
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not stage.closed
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stage.closed and not connection.active
        assert sum(sql.startswith("DROP ") for sql in connection.sql) == 1

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["invalidated", "different-server-cid"])
def test_invalid_or_replaced_connection_never_drops_tables_on_new_server_session(failure):
    async def run():
        connection = Connection()
        stage = _TemporaryStage(connection)
        await stage.create("unit", "(id INT)")
        before = len(connection.sql)
        if failure == "invalidated":
            connection.invalidated = True
        else:
            connection.cid = 124
        with pytest.raises(OrbitError) as error:
            await stage.close()
        assert error.value.code == "METRICS_STAGE_CLEANUP_UNVERIFIED"
        assert not any(sql.startswith("DROP ") for sql in connection.sql[before:])
        if failure == "invalidated":
            assert len(connection.sql) == before
        assert stage.connection_id == 123 and not stage.cleanup_verified

    asyncio.run(run())


def test_slow_invalidation_is_bounded_and_no_owned_cleanup_task_survives():
    async def run():
        connection = Connection()
        stopped = asyncio.Event()

        async def slow_invalidate():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        connection.invalidate = slow_invalidate
        stage = _TemporaryStage(connection)
        await stage.create("unit", "(id INT)")
        connection.fail_drop = True
        before = set(asyncio.all_tasks())
        started = asyncio.get_running_loop().time()
        with pytest.raises(OrbitError) as error:
            await stage.close()
        assert error.value.code == "METRICS_STAGE_CLEANUP_UNVERIFIED"
        assert asyncio.get_running_loop().time() - started < 2
        assert stopped.is_set() and not (set(asyncio.all_tasks()) - before)
        assert stage.closed and not stage.cleanup_verified
        connection.sync_connection.detach.assert_called_once()

    asyncio.run(run())


@pytest.mark.parametrize("dataset", ["ACCOUNT", "CAMPAIGN", "ADSET", "AD"])
@pytest.mark.parametrize("granularity", ["SUMMARY", "DAY"])
def test_all_cells_missing_but_real_name_receipt_projects_unknown_null_sources(
    monkeypatch, dataset, granularity
):
    from datetime import date

    async def run():
        store, session, row = fixture(monkeypatch)
        store.budget = ResultBuildBudget(10000, 10000, 10000000, 10000000, 30)
        ticket = await store.claim(session, 1, row["id"])
        context = await store.read.resume_persisted_query(session, 1, row["id"])
        metadata = dict(await store.read.describe_context(session, context))
        metadata["query"] = query(dataset=dataset, granularity=granularity)
        metadata["data_as_of"] = NOW.replace(tzinfo=None)
        stage = _TemporaryStage(session.connection_value)
        handle = _StageTicket()
        store._stages[handle] = (ticket, stage, metadata)
        business_day = date(2026, 1, 1)
        group_day = business_day if granularity == "DAY" else date(1000, 1, 1)
        entity = str(uuid4())
        item = {
            "entity_id": entity,
            "currency": "USD",
            "group_day": group_day,
            "account_id": str(uuid4()),
            "business_date": business_day,
            "unit_complete": 0,
            "critical_complete": 0,
            "observed_at": None,
            "account_count": 1,
            "ad_count": 0,
            "owner_team_id": None,
            "operator_user_id": OWNER,
            "channel_id": None,
            "product_name_snapshot": None,
            "name": "受信历史名",
            "name_day": business_day,
            "name_sequence": 120,
            "name_observed": NOW - timedelta(days=1),
            "dimension_id": str(uuid4()),
            **{
                field: None
                for field in (
                    "spend",
                    "impressions",
                    "clicks",
                    "registrations",
                    "purchases",
                    "purchase_value",
                )
            },
        }
        session.unit_projection_pages = [[item]]
        await store._project_rows(session, handle)
        inserted = next(
            values for sql, values in session.calls if f"INSERT INTO {stage.names['result']}" in sql
        )
        assert len(inserted) == 1
        payload = json.loads(inserted[0]["payload"])
        assert payload["entity_id"] == entity and payload["name"] == "受信历史名"
        assert payload["quality"] == "UNKNOWN" and payload["coverage"] == "0"
        assert payload["business_date"] == (
            business_day.isoformat() if granularity == "DAY" else None
        )
        assert all(value is None for value in payload["values"].values())
        assert len(payload) == 15
        session.total_projection_pages = [[item]]
        await store._project_totals(session, handle)
        total = next(
            values for sql, values in session.calls if f"INSERT INTO {stage.names['total']}" in sql
        )
        total_payload = json.loads(total["payload"])
        assert len(total_payload) == 8 and total_payload["coverage"] == "0"
        assert total_payload["missing_count"] == 1 and total_payload["account_count"] == 1
        assert all(value is None for value in total_payload["values"].values())

    asyncio.run(run())


def ready_fixture(monkeypatch, size=20):
    from test_metrics_query_result import built_row, built_total

    store, session, row = fixture(monkeypatch, state="READY")
    body = query(page_size=size)
    row["query_json"], row["query_hash"] = canonical(body), metric_query_hash(body)
    row.update(
        expected_cell_count=1,
        expected_account_count=1,
        expected_membership_count=size + 1,
        row_count=size + 1,
        totals_count=1,
        missing_count=0,
        data_as_of=NOW.replace(tzinfo=None),
        rows_hash="c" * 64,
    )
    store.expected_provider.value = replace(
        store.expected_provider.value,
        query_hash=row["query_hash"],
        unit_count=1,
        membership_count=size + 1,
    )
    store.tokens = DirectoryTokens(
        CredentialCipher("fixture", {"fixture": base64.b64encode(b"x" * 32).decode()})
    )
    for ordinal in range(1, size + 2):
        payload = built_row() | {
            "tenant_id": TENANT,
            "metric_profile_id": row["profile_id"],
            "entity_id": str(uuid4()),
            "name": f"原快照{ordinal}",
        }
        encoded = canonical(payload).encode()
        session.ready_rows.append(
            {
                "ordinal": ordinal,
                "payload_json": encoded.decode(),
                "payload_hash": hashlib.sha256(encoded).hexdigest(),
                "payload_bytes": len(encoded),
                "row_key_hash": digest(["AD", payload["entity_id"], "USD", None]),
            }
        )
    total = built_total() | {
        "tenant_id": TENANT,
        "metric_profile_id": row["profile_id"],
        "ad_count": size + 1,
    }
    for field, value in (
        ("spend", 100),
        ("impressions", 1000),
        ("clicks", 10),
        ("registrations", 3),
        ("purchases", 2),
        ("purchase_value", 250),
    ):
        total["values"][field] = str(value * (size + 1))
    encoded = canonical(total).encode()
    session.ready_totals = [
        {
            "currency": "USD",
            "profile_id": row["profile_id"],
            "payload_json": encoded.decode(),
            "payload_hash": hashlib.sha256(encoded).hexdigest(),
        }
    ]
    row["totals_hash"] = hashlib.sha256(
        canonical(["USD", row["profile_id"], session.ready_totals[0]["payload_hash"]]).encode()
        + b"\n"
    ).hexdigest()
    return store, session, row, body


@pytest.mark.parametrize("size", [20, 50, 100, 200])
def test_ready_pages_read_frozen_ordinal_and_same_whole_filter_totals(size, monkeypatch):
    async def run():
        store, session, row, body = ready_fixture(monkeypatch, size)
        first = await store.page(session, 1, row["id"], body, "Bearer unit-session")
        assert len(first["items"]) == size and first["next_cursor"] is not None
        second = await store.page(
            session, 1, row["id"], body | {"cursor": first["next_cursor"]}, "Bearer unit-session"
        )
        assert len(second["items"]) == 1 and second["next_cursor"] is None
        assert first["totals"] == second["totals"] and second["totals"][0]["ad_count"] == size + 1
        assert len({item["entity_id"] for item in first["items"] + second["items"]}) == size + 1
        row_sql = [
            sql for sql, _ in session.calls if "FROM orbit_metric_query_sorted_row WHERE" in sql
        ]
        assert all("ordinal>:after" in sql and "OFFSET" not in sql for sql in row_sql)

    asyncio.run(run())


@pytest.mark.parametrize(
    "change", ["session", "query", "tamper", "total-root", "row-key", "missing-row"]
)
def test_ready_page_rejects_rebound_cursor_or_corrupt_frozen_result(monkeypatch, change):
    async def run():
        store, session, row, body = ready_fixture(monkeypatch)
        first = await store.page(session, 1, row["id"], body, "Bearer unit-session")
        next_body, authorization = body | {"cursor": first["next_cursor"]}, "Bearer unit-session"
        if change == "session":
            authorization = "Bearer other-session"
        elif change == "query":
            next_body["q"] = "changed"
        elif change == "tamper":
            next_body["cursor"] = first["next_cursor"][:-1] + "!"
        elif change == "total-root":
            row["totals_hash"] = "a" * 64
        elif change == "row-key":
            session.ready_rows[-1]["row_key_hash"] = "a" * 64
        else:
            session.ready_rows.pop()
        with pytest.raises(OrbitError) as error:
            await store.page(session, 1, row["id"], next_body, authorization)
        assert error.value.status == (
            400 if change == "tamper" else 409 if change in {"session", "query"} else 503
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    ("cell", "expected_spend", "expected_registrations", "complete"),
    [
        ("complete", 0, None, 1),
        ("short_stream", None, None, 1),
        ("missing", None, None, 0),
        ("empty_mask", 0, None, 1),
        ("unverified_members", None, None, 1),
        ("nonempty_members", None, None, 1),
        ("missing_spend", None, None, 1),
    ],
)
def test_filtered_empty_totals_need_independent_members_and_complete_per_field_proof(
    monkeypatch, cell, expected_spend, expected_registrations, complete
):
    """执行实际生成的聚合SELECT；SQLite替身不计MySQL临时表/来源验收。"""
    import sqlite3

    from orbit_api.metrics_query_result_store import STAGE_NAMES

    async def run():
        store, session, _ = fixture(monkeypatch)
        handle = _StageTicket()
        definitions = {}

        async def create(kind, definition, *args):
            definitions[kind] = definition
            return names[kind]

        names = {kind: "t_" + kind for kind in STAGE_NAMES}
        stage = SimpleNamespace(names=names, create=create)
        store._stages[handle] = (object(), stage, {"query": query(q="不存在")})
        monkeypatch.setattr(store, "_claim", AsyncMock())
        monkeypatch.setattr(store, "_project_rows", AsyncMock())
        monkeypatch.setattr(store, "_project_totals", AsyncMock())
        monkeypatch.setattr(
            "orbit_api.metrics_query_result_store.rows", AsyncMock(return_value=[{"count": 0}])
        )
        await store.aggregate_stage(session, handle)
        # 固定白名单临时表参与原有反向清理，proof不能复用同一TEMP表自连接。
        assert "cell_field_proof" in STAGE_NAMES
        assert definitions["cell_field_proof"].count("FROM t_fact") == 1
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(
                "CREATE TABLE t_unit(currency TEXT,account_id TEXT,business_date TEXT,"
                "members_verified INTEGER,entity_count INTEGER);"
                "CREATE TABLE t_cell(id TEXT,account_id TEXT,business_date TEXT,"
                "empty_result INTEGER,"
                "empty_field_mask INTEGER,critical_complete INTEGER,oldest_observed_at TEXT,"
                "fact_count INTEGER);"
                "CREATE TABLE t_fact(cell_id TEXT,spend NUMERIC,impressions NUMERIC,clicks NUMERIC,"
                "registrations NUMERIC,purchases NUMERIC,purchase_value NUMERIC);"
                "CREATE TABLE t_filtered(entity_id TEXT,account_id TEXT,business_date TEXT,"
                "spend NUMERIC,impressions NUMERIC,clicks NUMERIC,registrations NUMERIC,"
                "purchases NUMERIC,purchase_value NUMERIC);"
            )
            connection.execute(
                "INSERT INTO t_unit VALUES('USD','account','2026-01-01',?,?)",
                (int(cell != "unverified_members"), int(cell == "nonempty_members")),
            )
            if cell != "missing":
                empty = cell == "empty_mask"
                connection.execute(
                    "INSERT INTO t_cell VALUES('cell','account','2026-01-01',?,?,1,"
                    "'2026-01-01T00:00:00Z',?)",
                    (int(empty), 1 if empty else 0, 0 if empty else 2),
                )
                if not empty:
                    for _ in range(1 if cell == "short_stream" else 2):
                        connection.execute(
                            "INSERT INTO t_fact VALUES('cell',?,2,3,NULL,4,5)",
                            (None if cell == "missing_spend" else 10,),
                        )
            proof_select = definitions["cell_field_proof"].split(" AS\n", 1)[1]
            connection.execute("CREATE TABLE t_cell_field_proof AS " + proof_select)
            total_select = definitions["total_unit"].split(" AS\n", 1)[1]
            result = connection.execute(total_select)
            value = dict(
                zip((item[0] for item in result.description), result.fetchone(), strict=True)
            )
            assert value["unit_complete"] == complete
            assert value["spend"] == expected_spend
            assert value["registrations"] == expected_registrations
        finally:
            connection.close()

    asyncio.run(run())
