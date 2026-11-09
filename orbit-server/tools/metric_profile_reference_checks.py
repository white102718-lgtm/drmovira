"""原计划指标引用真实HTTP闭环；仅13306 UUID技术SQL资料，不证明Meta来源或执行。"""

import json
import re
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

METRIC_PROFILE_REFERENCE_CASES = [
    "pythonMetricReferenceOriginalPostGetFreezesExactVersionHashAndSource",
    "pythonMetricReferenceSamePlanBodyNewKeyAfterHeadChangeCreatesNewPlanVersion",
    "pythonMetricReferenceUnrelatedMetricClockNoiseDoesNotCreatePlanVersion",
    "pythonMetricReferenceSuccessfulCreateUpdateKeysReplayBeforeChangedHeadDisabledAndCas",
    "pythonMetricReferenceNewCreateEditNeedNoMonitorOrLaunchRead",
    "pythonMetricReferenceSuccessfulReplayRechecksReadAndNewWritesRecheckOriginalActions",
    "pythonMetricReferenceInvalidOwnerAndMissingProfileHaveNoPlanOrTaskWrites",
    "pythonMetricReferenceDisabledOrChangedTechnicalMetaConfigurationRejectsAtomically",
    "pythonMetricReferenceSameSuccessfulKeyDifferentBodyConflictsWithoutRebinding",
    "pythonMetricReferenceActualOutbox1644RollsBackAllWritesAndSameKeyRetrySucceeds",
]
NATIVE_ACTOR = 940430001
NATIVE_ROLE = 940430001


def validate_metric_reference_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("计划指标引用专项仅允许本机13306 UUID隔离库")


def metric_reference_plan_fixture(owner, profile_id):
    from launch_draft_template_checks import draft, tree

    value = draft(owner)
    value["campaigns"] = tree()
    value["campaigns"][0]["adsets"][0]["metric_profile_id"] = profile_id
    return value


def seed_metric_reference_profile(
    admin, database, tenant, *, index=1, identifier=None, config=None
):
    """严格原资料SQL样本；config仅用来检验来源拒绝，不是外部Meta权威发布。"""
    validate_metric_reference_target(admin, database)
    from metric_profile_query_checks import query_profile_sql_sample

    from orbit_api.directory_tokens import canonical

    profile, digest, proof_json = query_profile_sql_sample(index, identifier=identifier)
    proof = json.loads(proof_json)
    kind = "ISOLATED_TEST"
    if config is not None:
        import hashlib

        profile["source"] = "META"
        kind = "TRUSTED"
        proof.update(
            source_config_id=config[0],
            source_config_revision=config[1],
            evidence_ref="isolated-plan-reference:NOT_META_AUTHORITY",
        )
        digest = hashlib.sha256(canonical(profile).encode()).hexdigest()
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            assert cursor.fetchone()[0] == database
            cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
            assert cursor.fetchone()[0] == tenant
            cursor.execute(
                "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=%s FOR UPDATE",
                (tenant,),
            )
            assert 1 <= cursor.fetchone()[0] < 9007199254740991
            cursor.execute(
                "SELECT revision FROM orbit_metric_profile_head WHERE "
                "tenant_id=%s AND id=%s FOR UPDATE",
                (tenant, profile["id"]),
            )
            old = cursor.fetchone()
            revision = old[0] + 1 if old else 1
            cursor.execute(
                "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,"
                "version,payload_json,"
                "payload_hash,source,authority_kind,source_config_id,source_config_revision,observed_at,"
                "evidence_ref,source_sha256,source_proof_json,created_by) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (
                    tenant,
                    profile["id"],
                    profile["version"],
                    canonical(profile),
                    digest,
                    profile["source"],
                    kind,
                    proof["source_config_id"],
                    proof["source_config_revision"],
                    datetime.fromisoformat(proof["observed_at"]).replace(tzinfo=None),
                    proof["evidence_ref"],
                    proof["source_sha256"],
                    canonical(proof),
                ),
            )
            if old:
                cursor.execute(
                    "UPDATE orbit_metric_profile_head SET "
                    "current_version=%s,revision=%s,state='ENABLED',"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND id=%s",
                    (profile["version"], revision, tenant, profile["id"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO orbit_metric_profile_head(tenant_id,id,"
                    "current_version,revision,state) VALUES(%s,%s,%s,1,'ENABLED')",
                    (tenant, profile["id"], profile["version"]),
                )
            cursor.execute(
                "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
                (tenant,),
            )
        admin.commit()
        return profile, {
            "version": profile["version"],
            "head_revision": revision,
            "profile_hash": digest,
            "source_sha256": proof["source_sha256"],
            "source_config_id": proof["source_config_id"],
            "source_config_revision": proof["source_config_revision"],
        }
    except BaseException:
        admin.rollback()
        raise


def assert_metric_reference_permission_error(body, specification):
    """原业务Error固定五字段；配置扩展三字段不能套到Plan权限错误。"""
    from material_schema_checks import validate_original_schema

    validate_original_schema(body, specification["components"]["schemas"]["Error"], specification)
    assert set(body) == {"code", "message", "field_errors", "retryable", "request_id"}
    assert body["code"] == "PERMISSION_DENIED"
    assert body["field_errors"] == [] and body["retryable"] is False


def run_metric_profile_reference_checks(client, admin, headers, password, cache, database, cases):
    validate_metric_reference_target(admin, database)
    from fixture_login import fixture_login
    from material_schema_checks import SPEC_PATH, validate_original_schema

    def sql(statement, values=(), *, rows=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if rows else None
        admin.commit()
        return result

    assert sql("SELECT DATABASE()", rows=True)[0][0] == database
    tenant, subject, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", rows=True
    )[0]
    root_owner = {"id": subject, "team": team}
    path = "/api/v1/launch-plans"
    specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    schema = specification["components"]["schemas"]["Plan"]

    def checked(response, expected, code=None):
        body = response.json()
        diagnostic = {
            "status": response.status_code,
            "code": body.get("code") if isinstance(body, dict) else None,
        }
        assert response.status_code == expected and (code is None or diagnostic["code"] == code), (
            diagnostic
        )
        if expected in {200, 201}:
            validate_original_schema(body, schema, specification)
        else:
            validate_original_schema(
                body,
                specification["components"]["schemas"]["Error"],
                specification,
            )
        return body

    root_caps = client.get(path + "/capabilities", headers=headers)
    assert root_caps.status_code == 200
    root_csrf = root_caps.json()["csrf_token"]

    def write(key, *, revision=None, identity=None, csrf=None):
        result = (identity or headers) | {"X-CSRF-Token": csrf or root_csrf, "Idempotency-Key": key}
        if revision is not None:
            result["If-Match"] = f'"{revision}"'
        return result

    def snapshot():
        tables = [
            value[0]
            for value in sql(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND "
                "(TABLE_NAME LIKE 'orbit_launch_%%' OR TABLE_NAME LIKE 'orbit_task%%' "
                "OR TABLE_NAME LIKE 'orbit_metric_profile_%%') ORDER BY TABLE_NAME",
                (database,),
                rows=True,
            )
        ]
        return {
            table: tuple(sorted(sql("SELECT * FROM " + table, rows=True), key=repr))
            for table in tables
        }

    def versions(identifier):
        values = sql(
            "SELECT revision,dependency_json FROM orbit_launch_plan_version "
            "WHERE tenant_id=%s AND plan_id=%s ORDER BY revision",
            (tenant, identifier),
            rows=True,
        )
        return {
            revision: json.loads(value) if isinstance(value, str) else value
            for revision, value in values
        }

    def task_count():
        return {
            table: len(values)
            for table, values in snapshot().items()
            if table.startswith("orbit_task")
        }

    original_tasks = task_count()
    profile, dependency1 = seed_metric_reference_profile(admin, database, tenant)
    body = metric_reference_plan_fixture(root_owner, profile["id"])
    create_key = str(uuid4())
    created = checked(client.post(path, headers=write(create_key), json=body), 201)
    identifier = created["id"]
    assert created["state"] == "DRAFT" and created["revision"] == 1
    assert versions(identifier)[1]["metric_profiles"] == {profile["id"]: dependency1}
    assert checked(client.get(path + "/" + identifier, headers=headers), 200) == created
    assert task_count() == original_tasks
    cases.append(METRIC_PROFILE_REFERENCE_CASES[0])

    _, dependency2 = seed_metric_reference_profile(
        admin, database, tenant, index=2, identifier=profile["id"]
    )
    update_key = str(uuid4())
    updated = checked(
        client.put(path + "/" + identifier, headers=write(update_key, revision=1), json=body), 200
    )
    assert updated["revision"] == 2 and updated["id"] == identifier
    frozen = versions(identifier)
    assert frozen[1]["metric_profiles"] == {profile["id"]: dependency1}
    assert frozen[2]["metric_profiles"] == {profile["id"]: dependency2}
    cases.append(METRIC_PROFILE_REFERENCE_CASES[1])

    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    noop = checked(
        client.put(path + "/" + identifier, headers=write(str(uuid4()), revision=2), json=body), 200
    )
    assert noop == updated and len(versions(identifier)) == 2
    cases.append(METRIC_PROFILE_REFERENCE_CASES[2])

    seed_metric_reference_profile(admin, database, tenant, index=3, identifier=profile["id"])
    before_replay = snapshot()
    assert checked(client.post(path, headers=write(create_key), json=body), 201) == created
    assert (
        checked(
            client.put(path + "/" + identifier, headers=write(update_key, revision=1), json=body),
            200,
        )
        == updated
    )
    assert snapshot() == before_replay
    changed_body = deepcopy(body)
    changed_body["name"] += "新版本"
    changed = checked(
        client.put(
            path + "/" + identifier, headers=write(str(uuid4()), revision=2), json=changed_body
        ),
        200,
    )
    assert changed["revision"] == 3
    sql(
        "UPDATE orbit_metric_profile_head SET "
        "state='DISABLED',revision=revision+1 WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    before_replay = snapshot()
    assert checked(client.post(path, headers=write(create_key), json=body), 201) == created
    assert (
        checked(
            client.put(path + "/" + identifier, headers=write(update_key, revision=1), json=body),
            200,
        )
        == updated
    )
    assert snapshot() == before_replay
    assert checked(client.get(path + "/" + identifier, headers=headers), 200) == changed
    cases.append(METRIC_PROFILE_REFERENCE_CASES[3])

    # 原native角色只授launch原动作，没有monitor和额外系统菜单。
    suffix = uuid4().hex[:12]
    native, role = NATIVE_ACTOR, NATIVE_ROLE
    native_subject = str(uuid4())
    name = "metric_ref_" + suffix
    assert sql("SELECT user_id FROM sys_user WHERE user_id=%s", (native,), rows=True) == ()
    assert sql("SELECT role_id FROM sys_role WHERE role_id=%s", (role,), rows=True) == ()
    sql(
        "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,"
        "data_scope,status,del_flag) "
        "VALUES(%s,'指标计划引用原动作SQL角色',%s,1,'1','0','0')",
        (role, name),
    )
    for menu in (31000, 31020, 31021, 31022, 31023):
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, menu))
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,"
        "del_flag) SELECT %s,%s,'指标引用SQL用户',password,'0','0' FROM "
        "sys_user WHERE user_id=1",
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
        (native, tenant),
    )
    sql(
        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
        "display_name,invited,created_at) "
        "VALUES(%s,%s,%s,%s,'指标引用SQL用户',0,UTC_TIMESTAMP(3))",
        (tenant, native_subject, native, team),
    )
    logged = fixture_login(client, cache, {"username": name, "password": password})
    assert logged.status_code == 200 and logged.json().get("token")
    actor_headers = {"Authorization": "Bearer " + logged.json()["token"]}
    caps = client.get(path + "/capabilities", headers=actor_headers)
    assert caps.status_code == 200
    csrf = caps.json()["csrf_token"]
    actor_profile, _ = seed_metric_reference_profile(admin, database, tenant, index=4)
    actor_body = metric_reference_plan_fixture(
        {"id": native_subject, "team": team}, actor_profile["id"]
    )
    actor_key = str(uuid4())
    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31021", (role,))
    actor_created = checked(
        client.post(
            path, headers=write(actor_key, identity=actor_headers, csrf=csrf), json=actor_body
        ),
        201,
    )
    seed_metric_reference_profile(admin, database, tenant, index=5, identifier=actor_profile["id"])
    actor_updated = checked(
        client.put(
            path + "/" + actor_created["id"],
            headers=write(str(uuid4()), revision=1, identity=actor_headers, csrf=csrf),
            json=actor_body,
        ),
        200,
    )
    assert actor_updated["revision"] == 2
    cases.append(METRIC_PROFILE_REFERENCE_CASES[4])

    before_denied = snapshot()
    denied = client.post(
        path, headers=write(actor_key, identity=actor_headers, csrf=csrf), json=actor_body
    )
    error = checked(denied, 403, "PERMISSION_DENIED")
    assert_metric_reference_permission_error(error, specification)
    assert snapshot() == before_denied
    sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31021)", (role,))
    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id IN (31022,31023)", (role,))
    before_denied = snapshot()
    assert (
        checked(
            client.post(
                path, headers=write(actor_key, identity=actor_headers, csrf=csrf), json=actor_body
            ),
            201,
        )
        == actor_created
    )
    checked(
        client.post(
            path, headers=write(str(uuid4()), identity=actor_headers, csrf=csrf), json=actor_body
        ),
        403,
        "PERMISSION_DENIED",
    )
    checked(
        client.put(
            path + "/" + actor_created["id"],
            headers=write(str(uuid4()), revision=2, identity=actor_headers, csrf=csrf),
            json=actor_body,
        ),
        403,
        "PERMISSION_DENIED",
    )
    assert snapshot() == before_denied
    cases.append(METRIC_PROFILE_REFERENCE_CASES[5])

    active, _ = seed_metric_reference_profile(admin, database, tenant, index=6)
    for bad_owner, metric_id, status, code in (
        ({"id": str(uuid4()), "team": team}, active["id"], 422, "OWNER_UNAVAILABLE"),
        (root_owner, str(uuid4()), 404, "METRIC_PROFILE_UNAVAILABLE"),
    ):
        invalid_body = metric_reference_plan_fixture(bad_owner, metric_id)
        before_invalid = snapshot()
        checked(client.post(path, headers=write(str(uuid4())), json=invalid_body), status, code)
        assert snapshot() == before_invalid
    cases.append(METRIC_PROFILE_REFERENCE_CASES[6])

    # 仅来源失效分支使用META技术形状；绝非真实Meta连接/Authority发布。
    config_id = str(uuid4())
    sql(
        "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,"
        "enabled,settings_json,secrets_json) "
        "VALUES(%s,%s,'META_BM',%s,0,'{}','{}')",
        (config_id, tenant, "指标引用失效SQL" + suffix),
    )
    technical, _ = seed_metric_reference_profile(
        admin, database, tenant, index=7, config=(config_id, 1)
    )
    technical_body = metric_reference_plan_fixture(root_owner, technical["id"])
    before_invalid = snapshot()
    checked(
        client.post(path, headers=write(str(uuid4())), json=technical_body),
        409,
        "METRIC_PROFILE_SOURCE_CHANGED",
    )
    assert snapshot() == before_invalid
    sql(
        "UPDATE orbit_system_configuration SET enabled=1,revision=revision+1 WHERE id=%s",
        (config_id,),
    )
    before_invalid = snapshot()
    checked(
        client.post(path, headers=write(str(uuid4())), json=technical_body),
        409,
        "METRIC_PROFILE_SOURCE_CHANGED",
    )
    assert snapshot() == before_invalid
    cases.append(METRIC_PROFILE_REFERENCE_CASES[7])

    conflict = deepcopy(body)
    conflict["name"] += "异正文"
    before_conflict = snapshot()
    checked(
        client.post(path, headers=write(create_key), json=conflict), 409, "IDEMPOTENCY_CONFLICT"
    )
    assert snapshot() == before_conflict
    cases.append(METRIC_PROFILE_REFERENCE_CASES[8])

    failure_body = metric_reference_plan_fixture(root_owner, active["id"])
    failure_key, trigger = str(uuid4()), "it_metric_plan_outbox_" + uuid4().hex[:12]
    before_failure = snapshot()
    sql(
        "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_launch_outbox FOR EACH ROW SIGNAL "
        "SQLSTATE '45000' SET "
        "MESSAGE_TEXT='ISOLATED_METRIC_PLAN_OUTBOX_REJECT'"
    )
    try:
        failed = client.post(path, headers=write(failure_key), json=failure_body)
        checked(failed, 503)
        assert "ISOLATED_METRIC_PLAN_OUTBOX_REJECT" not in failed.text
        assert snapshot() == before_failure
    finally:
        sql("DROP TRIGGER IF EXISTS " + trigger)
    retried = checked(client.post(path, headers=write(failure_key), json=failure_body), 201)
    assert retried["revision"] == 1 and len(versions(retried["id"])) == 1
    assert task_count() == original_tasks
    cases.append(METRIC_PROFILE_REFERENCE_CASES[9])
    return {
        "reference_cases": len(METRIC_PROFILE_REFERENCE_CASES),
        "authority": "ISOLATED_SQL_NOT_META",
        "task_writes": 0,
    }
