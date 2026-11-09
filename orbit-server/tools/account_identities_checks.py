"""旧023领域协议与新原GET边界；裸领域证据不能绕053旁证成为权威HTTP成功。

领域get/publish的时间、撤销、资源完整性及审计回滚保留；原GET成功由053完整fixture接力。
"""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountIdentitiesOriginalReadBoundaryAndUnsynced",
    "pythonAccountIdentitiesArbitraryVersionWithoutRegistryCannotPublish",
    "pythonAccountIdentitiesTrustedCompleteObservationStrictOriginalResponse",
    "pythonAccountIdentitiesRegistryRevocationFailsClosed",
    "pythonAccountIdentitiesSourceAndAccountRevisionDriftFailClosed",
    "pythonAccountIdentitiesKnownCredentialExpiryFailsClosed",
    "pythonAccountIdentitiesPayloadReplacementAndLateObservationRejected",
    "pythonAccountIdentitiesAuditFailureRollsBackHeadHistoryResourcesAndEvents",
    "pythonAccountIdentitiesOnlyCompleteObservedEmptyResourcesCanSucceed",
    "pythonAccountIdentitiesBareLegacyHeadCannotBypassPublicationProvenance",
]


def require_publication_schema(admin, database):
    """本工具与当前原GET接线同代；不能在through46旧schema伪跑权威读取回归。"""
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("身份领域专项必须使用本轮实际UUID库")
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s "
            "AND table_name IN ('orbit_identity_capability_release',"
            "'orbit_identity_publication_provenance','orbit_identity_publication_ledger')",
            (database,),
        )
        if cursor.fetchone()[0] != 3:
            raise ValueError("当前原身份HTTP回归必须明确应用053，不兼容裸023权威成功")


def run_account_identities_checks(
    client,
    admin,
    headers,
    actor_id,
    owner_user_id,
    owner_team_id,
    database,
    cases,
    cipher,
    denied_headers,
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("身份专项只允许本轮独立MySQL夹具")
    require_publication_schema(admin, database)
    from orbit_api.account_identities_store import AccountIdentitiesStore, fingerprint
    from orbit_api.errors import OrbitError

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
    account_id, source_id = str(uuid4()), str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orbit_ad_account "
            "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,"
            "timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,'身份受控','身份受控',%s,%s,'USD','Asia/Shanghai',"
            "'AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, account_id, str(10**22 + uuid4().int % 10**22), owner_user_id, owner_team_id),
        )
        cursor.execute(
            "INSERT INTO orbit_system_configuration "
            "(id,tenant_id,section,name,enabled,revision,settings_json,"
            "secrets_json,verification_status) "
            "VALUES(%s,%s,'META_BM','身份受控来源',1,1,'{}',%s,'READ_VERIFIED')",
            (
                source_id,
                tenant,
                json.dumps(
                    {
                        "accessToken": cipher.encrypt(
                            "fixture-only-not-platform-token", tenant, source_id, "accessToken"
                        )
                    }
                ),
            ),
        )
    path = "/api/v1/accounts/" + account_id + "/identities"

    def public_get():
        return client.get(path, headers=headers)

    def domain_get():
        """真实旧领域Store读取，不构造伪HTTP200，不继承为当前权威来源。"""

        async def execute():
            engine = create_async_engine(url, echo=False, hide_parameters=True)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                async with sessions() as session, session.begin():
                    return await AccountIdentitiesStore().get(session, actor_id, account_id)
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    def reject_domain_read(status):
        try:
            domain_get()
        except OrbitError as error:
            assert error.status == status
        else:
            raise AssertionError("旧领域当前读取必须拒绝已失效证据")

    def body(minutes=10, empty=False):
        observed = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=minutes)
        return {
            "account_id": account_id,
            "resources": []
            if empty
            else [
                {
                    "external_id": "00042",
                    "name": "受控主页",
                    "kind": "PAGE",
                    "usable": True,
                    "reason_code": None,
                }
            ],
            "capability_version": "fixture-resource-capability-v1",
            "observed_at": observed.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }

    def evidence(value, complete=True):
        identifier = str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_account_identity_evidence "
                "(tenant_id,id,account_id,account_revision,source_config_id,source_config_revision,"
                "capability_version,payload_hash,observed_at,complete,verified,"
                "evidence_ref,created_at) "
                "VALUES(%s,%s,%s,1,%s,1,%s,%s,%s,%s,1,'fixture-only-not-real-platform',"
                "UTC_TIMESTAMP(3))",
                (
                    tenant,
                    identifier,
                    account_id,
                    source_id,
                    value["capability_version"],
                    fingerprint(value),
                    datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
                    .astimezone(UTC)
                    .replace(tzinfo=None),
                    int(complete),
                ),
            )
        return identifier

    def publish(evidence_id, value, revision):
        async def execute():
            engine = create_async_engine(url, echo=False, hide_parameters=True)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                async with sessions() as session, session.begin():
                    return await AccountIdentitiesStore().publish(
                        session, actor_id, evidence_id, value, revision, str(uuid4())
                    )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    def reject(evidence_id, value, revision, status):
        try:
            publish(evidence_id, value, revision)
        except OrbitError as error:
            assert error.status == status
        else:
            raise AssertionError("身份观察必须拒绝无效证据或旧版本")

    assert client.get(path).status_code == 401
    assert client.get(path, headers=denied_headers).status_code == 403
    assert client.get(path + "?token=fixture", headers=headers).status_code == 400
    assert client.get("/api/v1/accounts/not-uuid/identities", headers=headers).status_code == 422
    assert (
        client.get("/api/v1/accounts/" + str(uuid4()) + "/identities", headers=headers).status_code
        == 404
    )
    assert public_get().status_code == 503
    assert public_get().json()["code"] == "ACCOUNT_IDENTITIES_UNSYNCED"
    cases.append(CASES[0])
    first = body()
    reject(str(uuid4()), first, 0, 503)
    cases.append(CASES[1])
    original = evidence(first)
    assert publish(original, first, 0) == {"revision": 1}
    assert domain_get() == first
    cases.append(CASES[2])
    bare = public_get()
    assert bare.status_code == 503 and bare.json()["code"] == "IDENTITY_PUBLICATION_SOURCE_RETRY"
    cases.append(CASES[9])
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_identity_evidence SET revoked_at=UTC_TIMESTAMP(3) "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, original),
        )
    reject_domain_read(503)
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_identity_evidence SET revoked_at=NULL "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, original),
        )
    cases.append(CASES[3])
    for table, identifier in (
        ("orbit_system_configuration", source_id),
        ("orbit_ad_account", account_id),
    ):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE " + table + " SET revision=revision+1 WHERE tenant_id=%s AND id=%s",
                (tenant, identifier),
            )
        reject_domain_read(503)
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE " + table + " SET revision=1 WHERE tenant_id=%s AND id=%s",
                (tenant, identifier),
            )
    cases.append(CASES[4])
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_identity_evidence "
            "SET credential_expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, original),
        )
    reject_domain_read(503)
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_identity_evidence SET credential_expires_at=NULL "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, original),
        )
    cases.append(CASES[5])
    newer = body(5)
    latest = evidence(newer)
    tampered = newer | {"resources": [newer["resources"][0] | {"usable": False}]}
    reject(latest, tampered, 1, 503)
    older = body(15)
    reject(evidence(older), older, 1, 409)
    cases.append(CASES[6])

    def state():
        result = []
        with admin.cursor() as cursor:
            for table in (
                "orbit_account_identity_head",
                "orbit_account_identity_history",
                "orbit_account_identity_resource",
                "orbit_account_event",
                "orbit_account_outbox",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                result.append(cursor.fetchone()[0])
            cursor.execute("SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,))
            result.append(cursor.fetchone()[0])
        return result

    before = state()
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER account_identity_audit_fail BEFORE INSERT ON orbit_account_event "
            "FOR EACH ROW BEGIN IF NEW.action='ACCOUNT_IDENTITIES_PUBLISHED' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
        )
    try:
        try:
            publish(latest, newer, 1)
        except DBAPIError as error:
            assert error.orig.args and error.orig.args[0] == 1644
        else:
            raise AssertionError("审计故障必须回滚身份快照与当前头")
        assert state() == before and domain_get() == first
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_identity_audit_fail")
    assert publish(latest, newer, 1) == {"revision": 2}
    cases.append(CASES[7])
    empty = body(1, empty=True)
    reject(evidence(empty, complete=False), empty, 2, 503)
    assert publish(evidence(empty), empty, 2) == {"revision": 3}
    assert domain_get() == empty
    assert public_get().status_code == 503
    cases.append(CASES[8])
