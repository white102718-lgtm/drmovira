"""真实MySQL认领/故障恢复与本机HTTPS通知；不会访问真实收件渠道。"""

import asyncio
import json
import re
import ssl
from uuid import uuid4

import httpcore
from sqlalchemy import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DELIVERY_CASES = [
    "pythonInvitationDeliveryRejectsRevokedAndChangedConfigurationBeforeSend",
    "pythonInvitationDeliveryActualHttpsSignedReceipt",
    "pythonInvitationDeliveryUnknownResponseNeverAutomaticallyResends",
    "pythonInvitationDeliveryConcurrentClaimAndInterruptedRecovery",
    "pythonInvitationDeliveryReceiptAuditFailureNeverResends",
]


def run_invitation_delivery_checks(admin, database, send, current, cipher, idp, cases, values):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("通知投递只能连接当前独立测试库")
    from orbit_api.invitation_delivery import InvitationDeliveryWorker
    from orbit_api.notification_http import DeliveryOutcome, NotificationHttp

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

    def queued():
        response = send(current()["revision"], "worker-invite-" + uuid4().hex)
        assert response.status_code == 200
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT d.id,d.notification_id,d.notification_revision FROM "
                "orbit_invitation_delivery d JOIN orbit_user_invitation i ON i.id=d.invitation_id "
                "JOIN orbit_business_user b ON b.user_id=i.user_id AND b.tenant_id=i.tenant_id "
                "WHERE i.status='ACTIVE' AND b.id=%s AND i.user_revision=%s AND d.status='QUEUED' "
                "ORDER BY d.created_at DESC,d.id DESC LIMIT 1",
                (response.json()["id"], response.json()["revision"]),
            )
            return cursor.fetchone()

    def state(identifier):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT status,revision,failure_code FROM orbit_invitation_delivery WHERE id=%s",
                (identifier,),
            )
            return cursor.fetchone()

    class LoopbackFixtureBackend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "orbit-idp.fixture.example" and port == 443
            return await httpcore.AnyIOBackend().connect_tcp("127.0.0.1", idp.port, **kwargs)

    async def checks():
        engine = create_async_engine(url, echo=False)
        worker = InvitationDeliveryWorker(
            async_sessionmaker(engine, expire_on_commit=False),
            cipher,
            "https://app.fixture.example",
            transport=NotificationHttp(
                network_backend=LoopbackFixtureBackend(),
                ssl_context=ssl.create_default_context(cadata=idp.ca_pem),
            ),
        )
        try:
            # 所有老邀请均已撤销；当前唯一有效邀请也因通知配置版本改变而不得发送。
            identifier, channel, version = queued()
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=revision+1 WHERE id=%s",
                    (channel,),
                )
            before = len(idp.notifications)
            result = await worker.run_once(100)
            assert result["accepted"] == 0 and result["failed"] > 0
            assert len(idp.notifications) == before and state(identifier)[0] == "FAILED"
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=%s,secrets_json=%s WHERE id=%s",
                    (
                        version,
                        json.dumps(
                            {
                                "webhookToken": cipher.encrypt(
                                    "fixture-notification-signing",
                                    "00000000-0000-0000-0000-000000000001",
                                    channel,
                                    "webhookToken",
                                )
                            }
                        ),
                        channel,
                    ),
                )
            cases.append(DELIVERY_CASES[0])

            identifier, _, _ = queued()
            result = await worker.run_once(1)
            assert result == {"claimed": 1, "accepted": 1, "failed": 0, "unknown": 0}
            assert state(identifier) == ("ACCEPTED", 3, None)
            body, headers = idp.notifications[-1]
            payload = json.loads(body)
            assert payload["activation_url"].startswith("https://app.fixture.example/invite#")
            assert headers["Idempotency-Key"] == identifier and headers.get("X-ORBIT-Signature")
            assert "fixture-notification-signing" not in repr(headers)
            cases.append(DELIVERY_CASES[1])

            identifier, _, _ = queued()
            idp.notification_mode = "disconnect"
            before = len(idp.notifications)
            assert (await worker.run_once(1))["unknown"] == 1
            assert state(identifier)[0] == "UNKNOWN"
            assert (await worker.run_once(100))["claimed"] == 0
            assert len(idp.notifications) == before + 1
            idp.notification_mode = "accepted"
            cases.append(DELIVERY_CASES[2])

            identifier, _, _ = queued()
            claims = await asyncio.gather(worker.claim_one(), worker.claim_one())
            active = [claim for _, claim in claims if claim is not None]
            assert len(active) == 1 and active[0].id == identifier
            assert await worker.recover_interrupted() == 0
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_invitation_delivery "
                    "SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 61 SECOND WHERE id=%s",
                    (identifier,),
                )
            assert await worker.recover_interrupted() == 1
            assert state(identifier) == ("UNKNOWN", 3, "WORKER_INTERRUPTED")
            assert not await worker.complete(active[0], DeliveryOutcome("ACCEPTED"))
            cases.append(DELIVERY_CASES[3])

            identifier, _, _ = queued()
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER delivery_audit_fail BEFORE INSERT ON orbit_auth_audit "
                    "FOR EACH ROW BEGIN IF NEW.action='DELIVERY_ACCEPTED' THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
                )
            before = len(idp.notifications)
            try:
                await worker.run_once(1)
            except SQLAlchemyError:
                pass
            else:
                raise AssertionError("审计故障必须使回执状态事务回滚")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS delivery_audit_fail")
            assert state(identifier)[:2] == ("SENDING", 2)
            assert len(idp.notifications) == before + 1
            assert (await worker.run_once(100))["claimed"] == 0
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_invitation_delivery "
                    "SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 61 SECOND WHERE id=%s",
                    (identifier,),
                )
            assert await worker.recover_interrupted() == 1
            assert state(identifier)[0] == "UNKNOWN"
            assert len(idp.notifications) == before + 1
            cases.append(DELIVERY_CASES[4])
        finally:
            idp.notification_mode = "accepted"
            await engine.dispose()

    asyncio.run(checks())
    from invitation_worker_cli_checks import run_invitation_worker_cli_checks

    run_invitation_worker_cli_checks(values, idp, queued, state, cases)
