"""指标候选真实HTTP/041水位专项；所有数据明确SQL夹具，不证明外部Meta来源。"""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

METRIC_PROFILE_QUERY_CASES = [
    "pythonMetricQueryOriginalPageAndTwentyOneStrictSqlProfilesKeyset",
    "pythonMetricQueryExactUuidAndIntersectingFilterNeverNameSearch",
    "pythonMetricQueryFourPageSizesAndStableDatabaseUtcWatermark",
    "pythonMetricQuerySignedCursorRejectsTamperFilterSizeActorAndNewSession",
    "pythonMetricQueryCurrentMonitorActionRevocationRejectsSameToken",
    "pythonMetricQueryActualForeignTenantCannotReadRootSharedProfiles",
    "pythonMetricQueryRegistryChangeInvalidatesPreviouslySignedCursor",
    "pythonMetricQueryActual041MetaInsertUpdateDeleteAndNonMetaNoop",
    "pythonMetricQueryActual041MaxClockRejectsAndRollsBackConfiguration",
    "pythonMetricQueryActual041MissingClockRejectsAndRollsBackConfiguration",
    "pythonMetricQueryActual041CrossTenantMoveUpdatesBothClockWatermarks",
    "pythonMetricQueryCorruptHashOrProofFailsWholeHttpPage",
    "pythonMetricQueryFreshTransactionRejectsExistingRepeatableReadSnapshot",
    "pythonMetricQueryActualTechnicalMetaJoinDoesNotReverseLockConfiguration",
    "pythonMetricQueryUndefinedGenericFiltersExplicit400RemainContractGap",
]


def validate_metric_query_target(admin, database):
    if (
        not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("指标候选专项仅允许127.0.0.1:13306本轮UUID隔离库")


def query_profile_sql_sample(index, *, identifier=None):
    """可复用严格原DTO/规范摘要样本；不构造权威Provider或假扫描成功。"""
    from orbit_api.directory_tokens import canonical
    from orbit_api.metric_profile_contract import MetricSourceProof, publication

    profile = {
        "id": identifier or str(uuid4()),
        "version": "observed-v" + f"{index:03d}",
        "source": "FIXTURE",
        "register_action_type": None,
        "purchase_action_type": "observed-purchase-" + f"{index:03d}",
        "value_action_type": None,
        "attribution_windows": ["opaque-original-window-" + f"{index:03d}"],
        "action_report_time": "observed-report-time",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 28,
        "verified": True,
    }
    observed = datetime.now(UTC) - timedelta(seconds=1)
    observed = observed.replace(microsecond=observed.microsecond // 1000 * 1000)
    proof = MetricSourceProof(
        "a" * 64,
        observed,
        "isolated-query:SQL_ONLY_NOT_META",
        None,
        None,
    )
    prepared = publication(
        profile, "ISOLATED-NOT-PLATFORM", [{"event_type": "SQL_SAMPLE", "window_days": 7}], proof
    )
    proof_doc = {
        "source_sha256": proof.source_sha256,
        "observed_at": proof.observed_at.isoformat(),
        "evidence_ref": proof.evidence_ref,
        "source_config_id": None,
        "source_config_revision": None,
    }
    return profile, prepared.profile_hash, canonical(proof_doc)


def seed_metric_profile_browser_fixture(admin, database):
    validate_metric_query_target(admin, database)
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            assert cursor.fetchone()[0] == database
            cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
            tenant = cursor.fetchone()[0]
            cursor.execute(
                "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=%s FOR UPDATE",
                (tenant,),
            )
            revision = cursor.fetchone()[0]
            assert 1 <= revision < 9007199254740991
            profiles = []
            for index in range(1, 22):
                profile, digest, proof = query_profile_sql_sample(index)
                cursor.execute(
                    "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,version,"
                    "payload_json,payload_hash,source,authority_kind,observed_at,evidence_ref,"
                    "source_sha256,source_proof_json,created_by) "
                    "VALUES(%s,%s,%s,%s,%s,'FIXTURE','ISOLATED_TEST',%s,"
                    "'isolated-query:SQL_ONLY_NOT_META',%s,%s,1)",
                    (
                        tenant,
                        profile["id"],
                        profile["version"],
                        json.dumps(profile, ensure_ascii=False),
                        digest,
                        datetime.fromisoformat(json.loads(proof)["observed_at"]).replace(
                            tzinfo=None
                        ),
                        "a" * 64,
                        proof,
                    ),
                )
                cursor.execute(
                    "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,"
                    "revision,state) "
                    "VALUES(%s,%s,%s,1,'ENABLED')",
                    (tenant, profile["id"], profile["version"]),
                )
                profiles.append(profile)
            cursor.execute(
                "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
                (tenant,),
            )
        admin.commit()
        return {
            "tenant_id": tenant,
            "ids": [profile["id"] for profile in profiles],
            "profiles": profiles,
        }
    except BaseException:
        admin.rollback()
        raise


def run_metric_profile_query_checks(client, admin, headers, password, cache, database, cases):
    validate_metric_query_target(admin, database)
    from fixture_login import fixture_login
    from material_schema_checks import SPEC_PATH, validate_original_schema

    fixture = seed_metric_profile_browser_fixture(admin, database)
    tenant = fixture["tenant_id"]
    path = "/api/v1/metric-profiles"
    specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    page_schema = specification["components"]["schemas"]["MetricProfilePage"]

    def sql(statement, values=(), *, rows=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if rows else None
        admin.commit()
        return result

    def checked(response, status=200, code=None):
        body = response.json()
        diagnostic = {
            "status": response.status_code,
            "code": body.get("code") if isinstance(body, dict) else None,
        }
        assert response.status_code == status and (code is None or diagnostic["code"] == code), (
            diagnostic
        )
        if status == 200:
            validate_original_schema(body, page_schema, specification)
        return body

    def get(parameters=None, identity=None, status=200, code=None):
        return checked(
            client.get(path, headers=identity or headers, params=parameters or {}), status, code
        )

    def clock(target=tenant):
        return sql(
            "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=%s",
            (target,),
            rows=True,
        )[0][0]

    baseline = [
        value[0]
        for value in sql(
            "SELECT id FROM orbit_metric_profile_head WHERE tenant_id=%s AND "
            "state='ENABLED' ORDER BY id",
            (tenant,),
            rows=True,
        )
    ]
    first = get({"page_size": "20"})
    assert len(first["items"]) == 20 and first["next_cursor"]
    all_items, current = first["items"][:], first
    seen_cursors = set()
    while current["next_cursor"]:
        token = current["next_cursor"]
        assert token not in seen_cursors and len(seen_cursors) < 20
        seen_cursors.add(token)
        current = get({"page_size": "20", "cursor": token})
        assert current["data_as_of"] == first["data_as_of"]
        all_items.extend(current["items"])
    assert [item["id"] for item in all_items] == baseline
    by_id = {item["id"]: item for item in all_items}
    assert all(by_id[profile["id"]] == profile for profile in fixture["profiles"])
    cases.append(METRIC_PROFILE_QUERY_CASES[0])

    left, right = fixture["ids"][:2]
    assert get({"q": left})["items"] == [by_id[left]]
    assert get({"metric_profile_id": left})["items"] == [by_id[left]]
    assert get({"q": left, "metric_profile_id": right})["items"] == []
    get({"q": "observed"}, status=422)
    cases.append(METRIC_PROFILE_QUERY_CASES[1])

    for size in (20, 50, 100, 200):
        result = get({"page_size": str(size)})
        assert len(result["items"]) == min(size, len(baseline))
        assert result["data_as_of"].endswith("Z") and result["scope_version"] >= 1
    cases.append(METRIC_PROFILE_QUERY_CASES[2])

    suffix = uuid4().hex[:14]
    foreign_tenant, foreign_team = str(uuid4()), str(uuid4())
    role = int(sql("SELECT COALESCE(MAX(role_id),0)+1 FROM sys_role", rows=True)[0][0])
    actor = int(sql("SELECT COALESCE(MAX(user_id),0)+1 FROM sys_user", rows=True)[0][0])
    local_team = sql("SELECT team_id FROM orbit_business_user WHERE user_id=1", rows=True)[0][0]
    sql("INSERT INTO orbit_tenant(id,name) VALUES(%s,'指标查询异租户SQL夹具')", (foreign_tenant,))
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'指标查询异租户团队')",
        (foreign_tenant, foreign_team),
    )
    for table in ("orbit_directory_clock", "orbit_metric_profile_clock"):
        sql("INSERT INTO " + table + "(tenant_id) VALUES(%s)", (foreign_tenant,))
    sql(
        "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,"
        "status,del_flag) VALUES(%s,'指标查询只读SQL角色',%s,1,'1','0','0')",
        (role, "metric_query_" + suffix),
    )
    for menu in (31000, 31030, 31031, 310301):
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, menu))
    actor_names = []
    for offset, target, team in ((0, tenant, local_team), (1, foreign_tenant, foreign_team)):
        native, name = actor + offset, "metric_query_" + suffix + "_" + str(offset)
        actor_names.append(name)
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,"
            "del_flag) SELECT %s,%s,'指标只读SQL身份',password,'0','0' FROM sys_user "
            "WHERE user_id=1",
            (native, name),
        )
        sql(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,"
            "create_time) VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, role))
        sql(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, target),
        )
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
            "display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,'指标只读SQL身份',0,UTC_TIMESTAMP(3))",
            (target, str(uuid4()), native, team),
        )

    def login(name):
        response = fixture_login(client, cache, {"username": name, "password": password})
        assert response.status_code == 200 and response.json().get("token")
        return {"Authorization": "Bearer " + response.json()["token"]}

    local_headers, foreign_headers = login(actor_names[0]), login(actor_names[1])
    local_first = get({"page_size": "20"}, local_headers)
    token = local_first["next_cursor"]
    get({"page_size": "50", "cursor": token}, local_headers, status=409, code="SCOPE_CHANGED")
    get(
        {"page_size": "20", "q": left, "cursor": token},
        local_headers,
        status=409,
        code="SCOPE_CHANGED",
    )
    get({"page_size": "20", "cursor": token}, headers, status=409, code="SCOPE_CHANGED")
    new_session_headers = login(actor_names[0])
    assert new_session_headers != local_headers
    get({"page_size": "20", "cursor": token}, new_session_headers, status=409, code="SCOPE_CHANGED")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    get({"page_size": "20", "cursor": tampered}, local_headers, status=400, code="TOKEN_INVALID")
    cases.append(METRIC_PROFILE_QUERY_CASES[3])

    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31031", (role,))
    try:
        get(identity=local_headers, status=403, code="PERMISSION_DENIED")
    finally:
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31031)", (role,))
    cases.append(METRIC_PROFILE_QUERY_CASES[4])
    foreign = get(identity=foreign_headers)
    assert foreign["items"] == [] and foreign["next_cursor"] is None
    assert get({"q": left}, foreign_headers)["items"] == []
    cases.append(METRIC_PROFILE_QUERY_CASES[5])

    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    get(
        {"page_size": "20", "cursor": token},
        local_headers,
        status=409,
        code="METRIC_PROFILE_CHANGED",
    )
    cases.append(METRIC_PROFILE_QUERY_CASES[6])

    def configuration(identifier, target=tenant, section="META_BM"):
        sql(
            "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,"
            "enabled,settings_json,secrets_json) VALUES(%s,%s,%s,%s,0,'{}','{}')",
            (identifier, target, section, "指标041SQL样本" + identifier[:8]),
        )

    config = str(uuid4())
    initial = clock()
    configuration(config)
    assert clock() == initial + 1
    sql(
        "UPDATE orbit_system_configuration SET enabled=1,revision=revision+1 WHERE id=%s", (config,)
    )
    assert clock() == initial + 2
    sql("DELETE FROM orbit_system_configuration WHERE id=%s", (config,))
    assert clock() == initial + 3
    non_meta = str(uuid4())
    configuration(non_meta, section="METRICS")
    sql("UPDATE orbit_system_configuration SET revision=revision+1 WHERE id=%s", (non_meta,))
    sql("DELETE FROM orbit_system_configuration WHERE id=%s", (non_meta,))
    assert clock() == initial + 3
    cases.append(METRIC_PROFILE_QUERY_CASES[7])

    def must_fail_config(identifier, target):
        try:
            configuration(identifier, target)
        except Exception as error:
            admin.rollback()
            assert error.args[0] == 1644, {"errno": error.args[0]}
        else:
            raise AssertionError("缺失或耗尽clock不得提交META配置")
        assert (
            sql("SELECT id FROM orbit_system_configuration WHERE id=%s", (identifier,), rows=True)
            == ()
        )

    before_max = clock()
    sql(
        "UPDATE orbit_metric_profile_clock SET revision=9007199254740991 WHERE tenant_id=%s",
        (tenant,),
    )
    try:
        must_fail_config(str(uuid4()), tenant)
        assert clock() == 9007199254740991
    finally:
        # 仅本轮SQL夹具恢复水位；非生产回拨/自动续签机制。
        sql(
            "UPDATE orbit_metric_profile_clock SET revision=%s WHERE tenant_id=%s",
            (before_max + 1, tenant),
        )
    cases.append(METRIC_PROFILE_QUERY_CASES[8])

    foreign_revision = clock(foreign_tenant)
    sql("DELETE FROM orbit_metric_profile_clock WHERE tenant_id=%s", (foreign_tenant,))
    try:
        must_fail_config(str(uuid4()), foreign_tenant)
    finally:
        sql(
            "INSERT INTO orbit_metric_profile_clock(tenant_id,revision) VALUES(%s,%s)",
            (foreign_tenant, foreign_revision),
        )
    cases.append(METRIC_PROFILE_QUERY_CASES[9])

    moving = str(uuid4())
    configuration(moving)
    old_water, foreign_water = clock(), clock(foreign_tenant)
    sql(
        "UPDATE orbit_system_configuration SET tenant_id=%s,revision=revision+1 WHERE id=%s",
        (foreign_tenant, moving),
    )
    assert clock() == old_water + 1 and clock(foreign_tenant) == foreign_water + 1
    sql("DELETE FROM orbit_system_configuration WHERE id=%s", (moving,))
    cases.append(METRIC_PROFILE_QUERY_CASES[10])

    for kind in ("hash", "proof", "observation", "future_observation"):
        profile, digest, proof = query_profile_sql_sample(77)
        observed = datetime.fromisoformat(json.loads(proof)["observed_at"]).replace(tzinfo=None)
        if kind == "hash":
            digest = "b" * 64
        elif kind == "proof":
            proof = '{"bad":true}'
        elif kind == "observation":
            observed += timedelta(milliseconds=1)
        else:
            observed = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0, tzinfo=None)
            proof = json.dumps(
                json.loads(proof)
                | {
                    "observed_at": observed.replace(tzinfo=UTC).isoformat(),
                }
            )
        sql(
            "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,version,"
            "payload_json,payload_hash,source,authority_kind,observed_at,"
            "evidence_ref,source_sha256,source_proof_json,created_by) "
            "VALUES(%s,%s,%s,%s,%s,'FIXTURE','ISOLATED_TEST',%s,"
            "'isolated-query:SQL_ONLY_NOT_META',%s,%s,1)",
            (
                tenant,
                profile["id"],
                profile["version"],
                json.dumps(profile),
                digest,
                observed,
                "a" * 64,
                proof,
            ),
        )
        sql(
            "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,"
            "revision,state) VALUES(%s,%s,%s,1,'ENABLED')",
            (tenant, profile["id"], profile["version"]),
        )
        sql(
            "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
            (tenant,),
        )
        try:
            get({"q": profile["id"]}, status=503, code="METRIC_PROFILE_AUTHORITY_UNAVAILABLE")
        finally:
            sql(
                "UPDATE orbit_metric_profile_head SET "
                "state='DISABLED',revision=revision+1 WHERE tenant_id=%s AND id=%s",
                (tenant, profile["id"]),
            )
            sql(
                "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
                (tenant,),
            )
    cases.append(METRIC_PROFILE_QUERY_CASES[11])

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def old_snapshot():
        from orbit_api.metric_profile_query import MetricProfileQuery

        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                await session.execute(text("SELECT id FROM orbit_tenant ORDER BY id LIMIT 1"))
                try:
                    await MetricProfileQuery(None, isolated_fixture=True).page(session, 1, "", {})
                except ValueError:
                    pass
                else:
                    raise AssertionError("旧RR事务不得复用为新分页快照")
        finally:
            await engine.dispose()

    asyncio.run(old_snapshot())
    cases.append(METRIC_PROFILE_QUERY_CASES[12])
    # 只用于锁协议的META技术形状，非真实Meta Authority/外部认证证据。
    # 先证明HTTP确实读取所关联行，再持该config锁重读，不能用不相关行冒充。
    import hashlib

    from orbit_api.directory_tokens import canonical

    technical_config = str(uuid4())
    configuration(technical_config)
    sql("UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (technical_config,))
    technical_profile, _, technical_proof = query_profile_sql_sample(88)
    technical_profile["source"] = "META"
    technical_proof = json.loads(technical_proof) | {
        "source_config_id": technical_config,
        "source_config_revision": 1,
        "evidence_ref": "isolated-query:NOT_META_AUTHORITY",
    }
    sql(
        "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,version,payload_json,"
        "payload_hash,source,authority_kind,source_config_id,source_config_revision,observed_at,"
        "evidence_ref,source_sha256,source_proof_json,created_by) "
        "VALUES(%s,%s,%s,%s,%s,'META','TRUSTED',%s,1,%s,"
        "'isolated-query:NOT_META_AUTHORITY',%s,%s,1)",
        (
            tenant,
            technical_profile["id"],
            technical_profile["version"],
            canonical(technical_profile),
            hashlib.sha256(canonical(technical_profile).encode()).hexdigest(),
            technical_config,
            datetime.fromisoformat(technical_proof["observed_at"]).replace(tzinfo=None),
            "a" * 64,
            canonical(technical_proof),
        ),
    )
    sql(
        "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,revision,state) "
        "VALUES(%s,%s,%s,1,'ENABLED')",
        (tenant, technical_profile["id"], technical_profile["version"]),
    )
    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))

    async def no_reverse_configuration_lock():
        import base64
        import os

        from orbit_api.credentials import CredentialCipher
        from orbit_api.directory_tokens import DirectoryTokens
        from orbit_api.metric_profile_query import MetricProfileQuery

        # 仅该内部调用的临时游标签名密钥，无环境读取、不输出、不持久化。
        cipher = CredentialCipher("it", {"it": base64.b64encode(os.urandom(32)).decode()})
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        try:
            async with async_sessionmaker(engine)() as session:
                result = await asyncio.wait_for(
                    MetricProfileQuery(DirectoryTokens(cipher), isolated_fixture=True).page(
                        session,
                        1,
                        "ISOLATED_INTERNAL_QUERY_NOT_HTTP_SESSION",
                        {"q": technical_profile["id"]},
                    ),
                    timeout=5,
                )
                assert result["items"] == [technical_profile]
        finally:
            await engine.dispose()

    try:
        assert get({"q": technical_profile["id"]})["items"] == [technical_profile]
        admin.begin()
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM orbit_system_configuration WHERE id=%s FOR UPDATE",
                (technical_config,),
            )
            assert cursor.fetchone()[0] == technical_config
        asyncio.run(no_reverse_configuration_lock())
    finally:
        admin.rollback()
        sql(
            "UPDATE orbit_metric_profile_head SET state='DISABLED',revision=revision+1 "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, technical_profile["id"]),
        )
        sql(
            "UPDATE orbit_system_configuration SET enabled=0,revision=revision+1 WHERE id=%s",
            (technical_config,),
        )
        sql(
            "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
            (tenant,),
        )
    cases.append(METRIC_PROFILE_QUERY_CASES[13])
    for field in (
        "status",
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "entity_type",
    ):
        get({field: "undefined"}, status=400, code="UNKNOWN_FIELD")
    cases.append(METRIC_PROFILE_QUERY_CASES[14])
    return {
        "query_cases": len(METRIC_PROFILE_QUERY_CASES),
        "seed_profiles": 21,
        "authority": "ISOLATED_SQL_NOT_META",
        "undefined_filters": "EXPLICIT_400_CONTRACT_GAP",
    }
