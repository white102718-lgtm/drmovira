"""主任务串行执行的18列MySQL/HTTP专项；受控SQL数据不是生产平台采集证据。"""

import asyncio
import json
import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountDetailsUnknownFieldsAndOriginalAccountSchema",
    "pythonAccountDetailsActualDailyAggregationCompleteZeroAndMissingCoverage",
    "pythonAccountDetailsDateWindowNeverChangesBillingOrAccountMembership",
    "pythonAccountDetailsSignedCursorAndPublicationInvalidation",
    "pythonAccountDetailsLiveReferenceNameNeverInventsAlias",
    "pythonAccountDetailsLatePublicationCannotOverwriteFacts",
    "pythonAccountDetailsAuditFailureRollsBackFactsHistoryAndWatermark",
    "pythonAccountDetailsInvalidDatesAndInvisibleIdsFailExplicitly",
    "pythonAccountDetailsOriginalCoreUsesSameObservedValues",
    "pythonAccountDetailsReadOwnerOptionsFromVisibleAccountScope",
    "pythonAccountDetailsMiddayAmbiguityNeverAwardsZeroClockOwner",
    "pythonAccountDetailsLaterMetricsKeepFrozenAttributionAndHistory",
    "pythonAccountDetailsActualDstDayUsesFullIanaInterval",
]


def run_account_details_checks(
    client,
    admin,
    headers,
    actor_id,
    owner_user_id,
    owner_team_id,
    vendor_id,
    database,
    cases,
    cipher,
):
    """需through015并注册独立router；真实sync/read动作权限，固定隔离库及独占触发器。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("账户详情专项只允许当前独立MySQL夹具")
    from orbit_api.account_details_store import AccountDetailsStore
    from orbit_api.directory_tokens import DirectoryTokens

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
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
    marker = "详情受控-" + uuid4().hex
    identifiers = sorted(str(uuid4()) for _ in range(21))
    with admin.cursor() as cursor:
        for index, identifier in enumerate(identifiers):
            external = str(10**22 + uuid4().int % 10**22)
            cursor.execute(
                "INSERT INTO orbit_ad_account "
                "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,vendor_id,"
                "currency,timezone_id,auth_status,account_status,value_json,"
                "details_json,bound_at,created_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'USD',%s,'UNKNOWN','UNKNOWN','{}',"
                "'{}',%s,UTC_TIMESTAMP(3))",
                (
                    tenant,
                    identifier,
                    external,
                    marker,
                    marker,
                    owner_user_id,
                    owner_team_id,
                    vendor_id,
                    "America/New_York"
                    if index == 0
                    else "America/Los_Angeles"
                    if index == 1
                    else "UTC",
                    datetime(2026, 1, 1),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_account_assignment "
                "(tenant_id,id,account_id,owner_user_id,owner_team_id,"
                "vendor_id,starts_at,reason) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,'受控SQL消费验收夹具，非生产平台绑定')",
                (
                    tenant,
                    str(uuid4()),
                    identifier,
                    owner_user_id,
                    owner_team_id,
                    vendor_id,
                    datetime(2026, 1, 1),
                ),
            )
        cursor.execute(
            "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )

    async def publish(facts=(), observations=(), expected=None):
        engine = create_async_engine(url, echo=False)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session, session.begin():
                store = AccountDetailsStore(DirectoryTokens(cipher))
                watermark = await store.watermark(session, tenant)
                return await store.publish(
                    session,
                    actor_id,
                    watermark["revision"] if expected is None else expected,
                    facts=facts,
                    observations=observations,
                )
        finally:
            await engine.dispose()

    def read(**extra):
        query = {
            "q": marker,
            "page_size": "20",
            "date_from": "2026-03-07",
            "date_to": "2026-03-08",
        } | extra
        response = client.get("/api/v1/accounts/extended", headers=headers, params=query)
        assert response.status_code == 200
        return response.json()

    def detail(index=0, **extra):
        response = client.get(
            "/api/v1/accounts/" + identifiers[index] + "/details",
            headers=headers,
            params={"date_from": "2026-03-07", "date_to": "2026-03-08"} | extra,
        )
        assert response.status_code == 200
        return response.json()

    def fact(index, date, value, **extra):
        return {
            "account_id": identifiers[index],
            "business_date": date,
            "amount": value,
            "coverage": "COMPLETE" if value is not None else "PARTIAL",
            "currency": "USD",
            "source": "VERIFIED_INGESTION",
            "observed_at": "2026-03-09T12:00:00Z",
        } | extra

    def counts():
        result = []
        with admin.cursor() as cursor:
            for table in (
                "orbit_account_spend_day",
                "orbit_account_spend_day_history",
                "orbit_account_details_current",
                "orbit_account_details_history",
                "orbit_account_event",
                "orbit_account_outbox",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                result.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT revision,snapshot_id FROM orbit_account_details_clock WHERE tenant_id=%s",
                (tenant,),
            )
            result.append(cursor.fetchone())
        return result

    before = read()
    assert len(before["items"]) == 20 and before["next_cursor"]
    assert all(r["account"]["spend"]["amount"] is None for r in before["items"])
    assert all(r["details"]["personal_profile"]["observed_at"] is None for r in before["items"])
    original = client.get("/api/v1/accounts/" + identifiers[0], headers=headers)
    assert (
        original.status_code == 200
        and len(original.json()) == 14
        and "details" not in original.json()
    )
    cases.append(CASES[0])

    facts = [
        fact(0, "2026-03-07", "0"),
        fact(0, "2026-03-08", "12.345678"),
        fact(1, "2026-03-07", None),
        fact(2, "2026-03-07", "0"),
        fact(2, "2026-03-08", "0"),
    ]

    def money(value, kind):
        return {
            "amount": value,
            "currency": "USD",
            "kind": kind,
            "status": "SYNCED",
            "source": "VERIFIED_INGESTION",
            "business_date": None,
            "observed_at": "2026-03-09T12:00:00Z",
        }

    publication = asyncio.run(
        publish(
            facts,
            [
                {
                    "account_id": identifiers[0],
                    "observations": {
                        "balance": money("20", "UNKNOWN"),
                        "payable": money("100", "BILL"),
                        "lifetime_spend": money("200", "SPEND"),
                    },
                }
            ],
        )
    )
    first, second, zero = detail(0), detail(1), detail(2)
    assert first["account"]["spend"]["amount"] == "12.345678"
    assert first["details"]["spend_window"]["coverage"] == "COMPLETE"
    assert second["account"]["spend"]["amount"] is None
    assert second["details"]["spend_window"]["coverage"] == "PARTIAL"
    assert zero["account"]["spend"]["amount"] == "0.000000"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT owner_user_id,owner_team_id FROM orbit_account_spend_day "
            "WHERE tenant_id=%s AND account_id=%s",
            (tenant, identifiers[0]),
        )
        assert all(row == (owner_user_id, owner_team_id) for row in cursor.fetchall())
    cases.append(CASES[1])

    different = detail(0, date_from="2026-03-01", date_to="2026-03-01")
    assert different["account"]["spend"]["amount"] is None
    assert different["details"]["payable"] == first["details"]["payable"]
    assert different["details"]["lifetime_spend"] == first["details"]["lifetime_spend"]
    assert len(read()["items"]) == 20
    cases.append(CASES[2])

    stale = client.get(
        "/api/v1/accounts/extended",
        headers=headers,
        params={
            "q": marker,
            "page_size": "20",
            "date_from": "2026-03-07",
            "date_to": "2026-03-08",
            "cursor": before["next_cursor"],
        },
    )
    assert stale.status_code == 409
    new = read()
    tail = read(cursor=new["next_cursor"])
    assert [r["account"]["id"] for r in new["items"] + tail["items"]] == identifiers
    assert (
        tail["data_as_of"] == new["data_as_of"]
        and tail["metric_snapshot_id"] == publication["snapshot_id"]
    )
    cases.append(CASES[3])

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT value_json FROM orbit_reference_record WHERE tenant_id=%s AND id=%s",
            (tenant, vendor_id),
        )
        original_vendor = cursor.fetchone()[0]
        vendor = (
            json.loads(original_vendor)
            if isinstance(original_vendor, (str, bytes))
            else dict(original_vendor)
        )
    try:
        vendor["name"] = "完整当前资料" * 10
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_reference_record SET value_json=%s WHERE tenant_id=%s AND id=%s",
                (json.dumps(vendor), tenant, vendor_id),
            )
            cursor.execute(
                "UPDATE orbit_reference_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        updated = detail(0)
        assert updated["details"]["vendor_display"]["name"] == vendor["name"]
        assert updated["details"]["vendor_display"]["source"] == "REFERENCE_CATALOG"
        assert updated["account"]["vendor_alias"] is None
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_reference_record SET value_json=%s WHERE tenant_id=%s AND id=%s",
                (original_vendor, tenant, vendor_id),
            )
            cursor.execute(
                "UPDATE orbit_reference_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    cases.append(CASES[4])

    from orbit_api.errors import OrbitError

    baseline = counts()
    try:
        asyncio.run(publish([fact(0, "2026-03-08", "999")]))
    except OrbitError as error:
        assert error.code == "OBSERVATION_STALE"
    else:
        raise AssertionError("重复/迟到观测必须拒绝")
    assert counts() == baseline and detail(0)["account"]["spend"]["amount"] == "12.345678"
    cases.append(CASES[5])

    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER account_details_audit_fail BEFORE INSERT ON orbit_account_event "
            "FOR EACH ROW BEGIN IF NEW.action='ACCOUNT_OBSERVATIONS_PUBLISHED' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
        )
    try:
        from sqlalchemy.exc import SQLAlchemyError

        try:
            asyncio.run(publish([fact(0, "2026-03-08", "25", observed_at="2026-03-10T12:00:00Z")]))
        except SQLAlchemyError:
            pass
        else:
            raise AssertionError("审计故障必须回滚发布事务")
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_details_audit_fail")
    assert counts() == baseline
    cases.append(CASES[6])

    for query in [
        {"mode": "TODAY", "date_from": "2026-03-08"},
        {"date_from": "2026-03-09", "date_to": "2026-03-08"},
        {"mode": "created_at"},
    ]:
        assert (
            client.get("/api/v1/accounts/extended", headers=headers, params=query).status_code
            == 422
        )
    assert (
        client.get("/api/v1/accounts/" + str(uuid4()) + "/details", headers=headers).status_code
        == 404
    )
    assert client.get("/api/v1/accounts/bad/details", headers=headers).status_code == 422
    cases.append(CASES[7])

    original = client.get(
        "/api/v1/accounts",
        headers=headers,
        params={"q": marker, "page_size": "20", "date_from": "2026-03-07", "date_to": "2026-03-08"},
    )
    assert original.status_code == 200
    extended = read()
    for core, enriched in zip(original.json()["items"], extended["items"], strict=True):
        assert len(core) == 14
        assert all(
            core[key] == enriched["account"][key]
            for key in ("id", "balance", "spend", "vendor_alias")
        )
    default_core = client.get("/api/v1/accounts/" + identifiers[0], headers=headers)
    default_extended = client.get(
        "/api/v1/accounts/" + identifiers[0] + "/details", headers=headers
    )
    assert default_core.status_code == default_extended.status_code == 200
    assert default_core.json()["balance"] == default_extended.json()["account"]["balance"]
    cases.append(CASES[8])

    owner_options = client.get("/api/v1/accounts/owner-options", headers=headers)
    owner_error = owner_options.json()
    assert owner_options.status_code == 200, (
        owner_options.status_code,
        {key: owner_error.get(key) for key in ("code", "message", "field_errors")}
        if isinstance(owner_error, dict)
        else "NON_OBJECT_RESPONSE",
    )
    assert any(row["id"] == owner_user_id for row in owner_options.json()["items"])
    assert all(
        set(row) == {"id", "name", "team_id", "team_name"} for row in owner_options.json()["items"]
    )
    cases.append(CASES[9])

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id,team_id FROM orbit_business_user WHERE tenant_id=%s AND id<>%s LIMIT 1",
            (tenant, owner_user_id),
        )
        other = cursor.fetchone()
        assert other, "严格归属夹具需同租户另一真实拥有者"
        cursor.execute(
            "UPDATE orbit_account_assignment SET ends_at=%s WHERE tenant_id=%s AND account_id=%s",
            (datetime(2026, 3, 7, 12), tenant, identifiers[3]),
        )
        cursor.execute(
            "INSERT INTO orbit_account_assignment(tenant_id,id,account_id,"
            "owner_user_id,owner_team_id,starts_at,reason) VALUES(%s,%s,%s,%s,"
            "%s,%s,'受控日内异常夹具，非真实分配')",
            (tenant, str(uuid4()), identifiers[3], other[0], other[1], datetime(2026, 3, 7, 12)),
        )
    asyncio.run(publish([fact(3, "2026-03-07", "50")]))
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT owner_user_id,owner_team_id,attribution_version,"
            "attribution_reason FROM orbit_account_spend_day WHERE "
            "tenant_id=%s AND account_id=%s",
            (tenant, identifiers[3]),
        )
        unknown = cursor.fetchone()
        assert unknown == (None, None, 1, "UNASSIGNED_AMBIGUOUS")
    cases.append(CASES[10])

    asyncio.run(publish([fact(4, "2026-03-07", "10")]))
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_assignment SET owner_user_id=%s,"
            "owner_team_id=%s WHERE tenant_id=%s AND account_id=%s",
            (*other, tenant, identifiers[4]),
        )
        cursor.execute(
            "DELETE FROM orbit_account_assignment WHERE tenant_id=%s AND account_id=%s",
            (tenant, identifiers[3]),
        )
        cursor.execute(
            "INSERT INTO orbit_account_assignment(tenant_id,id,account_id,"
            "owner_user_id,owner_team_id,starts_at,reason) VALUES(%s,%s,%s,%s,"
            "%s,%s,'受控区间修复，不能自动重写已冻结事实')",
            (
                tenant,
                str(uuid4()),
                identifiers[3],
                owner_user_id,
                owner_team_id,
                datetime(2026, 1, 1),
            ),
        )
    asyncio.run(
        publish(
            [
                fact(4, "2026-03-07", "20", observed_at="2026-03-10T12:00:00Z"),
                fact(3, "2026-03-07", "60", observed_at="2026-03-10T12:00:00Z"),
            ]
        )
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT owner_user_id,owner_team_id,attribution_version FROM "
            "orbit_account_spend_day_history WHERE tenant_id=%s AND "
            "account_id=%s ORDER BY revision",
            (tenant, identifiers[4]),
        )
        assert list(cursor.fetchall()) == [(owner_user_id, owner_team_id, 1)] * 2
        cursor.execute(
            "SELECT owner_user_id,owner_team_id,attribution_version,"
            "attribution_reason FROM orbit_account_spend_day WHERE "
            "tenant_id=%s AND account_id=%s",
            (tenant, identifiers[3]),
        )
        assert cursor.fetchone() == unknown
    cases.append(CASES[11])

    for index, day_value, start, end, observed in [
        (7, "2026-03-08", datetime(2026, 3, 8, 5), datetime(2026, 3, 9, 4), "2026-03-10T12:00:00Z"),
        (
            8,
            "2026-11-01",
            datetime(2026, 11, 1, 4),
            datetime(2026, 11, 2, 5),
            "2026-11-03T12:00:00Z",
        ),
    ]:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_ad_account SET timezone_id='America/New_York' WHERE "
                "tenant_id=%s AND id=%s",
                (tenant, identifiers[index]),
            )
            cursor.execute(
                "UPDATE orbit_account_assignment SET starts_at=%s,ends_at=%s "
                "WHERE tenant_id=%s AND account_id=%s",
                (start, end, tenant, identifiers[index]),
            )
        asyncio.run(publish([fact(index, day_value, "1", observed_at=observed)]))
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT owner_user_id,attribution_reason FROM "
                "orbit_account_spend_day WHERE tenant_id=%s AND account_id=%s",
                (tenant, identifiers[index]),
            )
            assert cursor.fetchone() == (owner_user_id, "COVERED")
    cases.append(CASES[12])
