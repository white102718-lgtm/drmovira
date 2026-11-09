"""由主任务串行运行的MySQL+本机TLS账户绑定专项；不访问真实Meta。"""

import asyncio
import json
import re
import tempfile
from datetime import UTC
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from account_platform_checks import local_graph
from sqlalchemy import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountWorkerZeroOrMultipleSourcesNeverGuessToken",
    "pythonAccountWorkerActualTlsMetadataAndAtomicOwnershipBinding",
    "pythonAccountWorkerAlreadyExistsNeverReadsOrReassigns",
    "pythonAccountWorkerSourceChangedAfterReadCannotBind",
    "pythonAccountWorkerAuditRollbackAndLeaseRecoveryNeverFakeSuccess",
    "pythonAccountWorkerInitialReadPlusThreeBoundedRetries",
]


def run_account_worker_checks(
    client, admin, headers, cipher, owner_user_id, owner_team_id, vendor_id, database, cases
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("账户Worker专项只允许当前独立MySQL夹具")
    from orbit_api.account_worker import AccountImportWorker

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    caps = client.get("/api/v1/account-imports/capabilities", headers=headers)
    assert caps.status_code == 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM orbit_system_configuration "
            "WHERE tenant_id=%s AND section='META_BM' AND enabled=1",
            (tenant,),
        )
        prior_sources = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "UPDATE orbit_system_configuration SET enabled=0 "
            "WHERE tenant_id=%s AND section='META_BM'",
            (tenant,),
        )

    def batch(external_id):
        response = client.post(
            "/api/v1/account-imports",
            headers=headers
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": "worker-account-" + uuid4().hex,
            },
            json={
                "vendor_id": vendor_id,
                "owner_user_id": owner_user_id,
                "owner_team_id": owner_team_id,
                "account_ids_text": external_id,
            },
        )
        assert response.status_code == 202
        return response.json()["id"]

    def row(identifier):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,attempts,value_json,claimed_at FROM orbit_account_import_row "
                "WHERE tenant_id=%s AND batch_id=%s ORDER BY token_index LIMIT 1",
                (tenant, identifier),
            )
            value = cursor.fetchone()
        public = json.loads(value[2]) if isinstance(value[2], (str, bytes)) else value[2]
        return value[0], value[1], public

    def source():
        identifier = str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_system_configuration
                (id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,verification_status)
                VALUES(%s,%s,'META_BM',%s,1,1,%s,%s,'READ_VERIFIED')""",
                (
                    identifier,
                    tenant,
                    "隔离账户来源-" + identifier,
                    json.dumps({"businessId": "42", "systemUserId": "7", "graphVersion": "v25.0"}),
                    json.dumps(
                        {
                            "accessToken": cipher.encrypt(
                                "fixture-secret-token", tenant, identifier, "accessToken"
                            )
                        }
                    ),
                ),
            )
        return identifier

    sources_created = []

    async def checks(graph):
        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        def worker(identifier):
            return AccountImportWorker(
                sessions,
                cipher,
                {"USD"},
                platform_factory=graph.factory,
                target=(tenant, identifier),
            )

        try:
            identifier = batch("700001")
            await worker(identifier).run_once(1)
            assert (
                row(identifier)[2]["error_code"] == "ACCOUNT_IMPORT_SOURCE_REQUIRED"
                and not graph.requests
            )
            first, second = source(), source()
            sources_created.extend([first, second])
            identifier = batch("700002")
            await worker(identifier).run_once(1)
            assert (
                row(identifier)[2]["error_code"] == "ACCOUNT_IMPORT_SOURCE_AMBIGUOUS"
                and not graph.requests
            )
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (second,)
                )
            cases.append(CASES[0])

            graph.external_id = "700003"
            identifier = batch(graph.external_id)
            await worker(identifier).run_once(1)
            state, attempts, result = row(identifier)
            assert state == "SUCCEEDED" and attempts == 1 and result["spend"]["amount"] is None
            assert result["observed_at"] is not None
            assert all(
                method == "GET"
                and "access_token" not in path
                and request_headers["Authorization"] == "Bearer fixture-secret-token"
                for method, path, request_headers in graph.requests
            )
            account = client.get("/api/v1/accounts/" + result["account_id"], headers=headers)
            assert account.status_code == 200 and account.json()["external_id"] == graph.external_id
            assert (
                account.json()["currency"] == "USD"
                and account.json()["timezone"]["id"] == "America/New_York"
            )
            assert account.json()["balance"]["amount"] is None
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT owner_user_id,owner_team_id,bound_at FROM orbit_ad_account "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, result["account_id"]),
                )
                owner, team, bound_at = cursor.fetchone()
                cursor.execute(
                    "SELECT owner_user_id,owner_team_id,starts_at,ends_at "
                    "FROM orbit_account_assignment WHERE tenant_id=%s AND account_id=%s",
                    (tenant, result["account_id"]),
                )
                history = cursor.fetchall()
            expected_start = (
                bound_at.replace(tzinfo=UTC)
                .astimezone(ZoneInfo("America/New_York"))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            assert owner == owner_user_id and team == owner_team_id
            assert list(history) == [(owner_user_id, owner_team_id, expected_start, None)]
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT resource_type,COUNT(*) FROM orbit_account_vendor_alias_snapshot "
                    "WHERE tenant_id=%s AND (resource_id=%s OR resource_id IN "
                    "(SELECT id FROM orbit_account_assignment "
                    "WHERE tenant_id=%s AND account_id=%s)) "
                    "GROUP BY resource_type",
                    (tenant, result["account_id"], tenant, result["account_id"]),
                )
                assert dict(cursor.fetchall()) == {"ACCOUNT_BINDING": 1, "IMPORT_ASSIGNMENT": 1}
            cases.append(CASES[1])

            before = len(graph.requests)
            identifier = batch(graph.external_id)
            graph.mode = "forbidden"
            await worker(identifier).run_once(1)
            assert row(identifier)[0] == "ALREADY_EXISTS" and len(graph.requests) == before
            graph.mode = "normal"
            cases.append(CASES[2])

            graph.external_id = "700004"
            identifier = batch(graph.external_id)
            target = worker(identifier)
            claim, touched = await target.claim_one()
            assert touched and claim is not None
            reader = graph.factory(claim.configuration)
            reader.preflight = lambda: target.preflight(claim)
            await reader.prepare(claim.identifiers)
            metadata = await reader.fetch_metadata(claim.external_id)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=revision+1 WHERE id=%s",
                    (first,),
                )
            assert await target.complete(claim, result=metadata)
            assert row(identifier)[2]["error_code"] == "ACCOUNT_IMPORT_SOURCE_CHANGED"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s AND external_id=%s",
                    (tenant, graph.external_id),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=1 WHERE id=%s", (first,)
                )
            cases.append(CASES[3])

            graph.external_id = "700005"
            identifier = batch(graph.external_id)
            target = worker(identifier)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER account_bind_audit_fail BEFORE INSERT ON orbit_account_event "
                    "FOR EACH ROW BEGIN IF NEW.action='ACCOUNT_BOUND' THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
                )
            try:
                await target.run_once(1)
            except SQLAlchemyError:
                pass
            else:
                raise AssertionError("审计故障应使账户绑定事务回滚")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS account_bind_audit_fail")
            assert row(identifier)[0] == "FETCHING"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_account_vendor_alias_snapshot "
                    "WHERE tenant_id=%s AND resource_type IN "
                    "('ACCOUNT_BINDING','IMPORT_ASSIGNMENT') AND request_id="
                    "(SELECT claim_request_id FROM orbit_account_import_row "
                    "WHERE tenant_id=%s AND batch_id=%s LIMIT 1)",
                    (tenant, tenant, identifier),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s AND external_id=%s",
                    (tenant, graph.external_id),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "UPDATE orbit_account_import_row "
                    "SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 121 SECOND "
                    "WHERE tenant_id=%s AND batch_id=%s",
                    (tenant, identifier),
                )
            assert await target.recover_interrupted(1) == 1
            assert row(identifier)[0] == "WAITING"
            before = len(graph.requests)
            assert (await target.run_once(1))["processed"] == 0 and len(graph.requests) == before
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_account_import_row "
                    "SET next_attempt_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
                    "WHERE tenant_id=%s AND batch_id=%s",
                    (tenant, identifier),
                )
            await target.run_once(1)
            assert row(identifier)[0] == "SUCCEEDED"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s AND external_id=%s",
                    (tenant, graph.external_id),
                )
                assert cursor.fetchone()[0] == 1
            cases.append(CASES[4])

            graph.external_id, graph.mode = "700006", "rate"
            identifier = batch(graph.external_id)
            target, before = worker(identifier), len(graph.requests)
            for attempt in range(1, 5):
                await target.run_once(1)
                state, attempts, result = row(identifier)
                assert attempts == attempt and state == ("WAITING" if attempt <= 3 else "FAILED")
                assert result["retryable"] is (attempt <= 3) and result["account_id"] is None
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_account_import_row "
                        "SET next_attempt_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
                        "WHERE tenant_id=%s AND batch_id=%s",
                        (tenant, identifier),
                    )
            assert (await target.run_once(1))["processed"] == 0
            assert len(graph.requests) == before + 4
            graph.mode = "normal"
            cases.append(CASES[5])
        finally:
            await engine.dispose()

    try:
        with (
            tempfile.TemporaryDirectory(prefix="orbit-account-graph-") as directory,
            local_graph(Path(directory)) as graph,
        ):
            asyncio.run(checks(graph))
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_bind_audit_fail")
            for identifier in sources_created:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (identifier,)
                )
            for identifier in prior_sources:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (identifier,)
                )
