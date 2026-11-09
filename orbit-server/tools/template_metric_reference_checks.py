"""044模板指标原HTTP闭环；历史NULL保留未知，不把模板保存当新执行认证。"""

import json
import re
from copy import deepcopy
from uuid import uuid4

TEMPLATE_METRIC_REFERENCE_CASES = [
    "pythonTemplateMetricOriginalCreateGetFreezesHeadAndVersionDependencies",
    "pythonTemplateMetricSameBodyCurrentHeadChangeCreatesNewTemplateVersion",
    "pythonTemplateMetricClockNoiseDoesNotCreateTemplateVersion",
    "pythonTemplateMetricApplyNewKeyBindsCurrentProfileWithoutChangingTemplateSnapshot",
    "pythonTemplateMetricSuccessfulSaveApplyReplayBeforeDisabledSourceCasAndArchive",
    "pythonTemplateMetricNativeTemplateOnlyCreateEditNeedNoPlanWriteOrMonitor",
    "pythonTemplateMetricSuccessfulReplayReadPermissionAndNewWriteActionsAreDistinct",
    "pythonTemplateMetricApplyReplayRequiresTemplateReadPlanReadAndCurrentPlanVisibility",
    "pythonTemplateMetricHistoricalNullShareArchiveRemainUnknownNull",
    "pythonTemplateMetricActual044VersionUpdateDeleteGuardsRejectMutation",
    "pythonTemplateMetricActualOutbox1644RollsBackHeadVersionKeyAndClockThenRetry",
]
NATIVE_ACTOR = 940440001
NATIVE_ROLE = 940440001


def validate_template_metric_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("模板指标专项仅允许固定13306本轮UUID隔离库")


def template_metric_write_fixture(profile_id):
    from launch_draft_template_checks import tree

    campaigns = tree()
    campaigns[0]["adsets"][0]["metric_profile_id"] = profile_id
    return {
        "name": "指标模板SQL" + uuid4().hex,
        "description": "原模板指标闭环SQL夹具",
        "visibility": "PRIVATE",
        "recipient_user_ids": [],
        "campaigns": campaigns,
    }


def assert_historical_metric_dependencies_unknown(head, versions, expected_revisions):
    """NULL明确表示历史未记录；不得把空对象/缺版本解释为通过来源核验。"""
    assert head is None
    assert set(versions) == set(expected_revisions)
    assert all(type(revision) is int and value is None for revision, value in versions.items())


def run_template_metric_reference_checks(client, admin, headers, password, cache, database, cases):
    validate_template_metric_target(admin, database)
    from fixture_login import fixture_login
    from material_schema_checks import SPEC_PATH, validate_original_schema
    from metric_profile_reference_checks import (
        assert_metric_reference_permission_error,
        metric_reference_plan_fixture,
        seed_metric_reference_profile,
    )

    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest

    path, plan_path = "/api/v1/templates", "/api/v1/launch-plans"
    specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

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
    ownership = {"owner_user_id": subject, "owner_team_id": team}
    root_owner = {"id": subject, "team": team}

    def checked(response, expected, code=None, *, schema="Template"):
        body = response.json()
        diagnostic = {
            "status": response.status_code,
            "code": body.get("code") if isinstance(body, dict) else None,
        }
        assert response.status_code == expected and (code is None or diagnostic["code"] == code), (
            diagnostic
        )
        validate_original_schema(
            body,
            specification["components"]["schemas"][schema if expected in {200, 201} else "Error"],
            specification,
        )
        return body

    caps = client.get(path + "/capabilities", headers=headers)
    assert caps.status_code == 200
    root_csrf = caps.json()["csrf_token"]

    def write(key, revision=None, *, identity=None, csrf=None):
        value = (identity or headers) | {"X-CSRF-Token": csrf or root_csrf, "Idempotency-Key": key}
        if revision is not None:
            value["If-Match"] = f'"{revision}"'
        return value

    def snapshot():
        tables = [
            row[0]
            for row in sql(
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

    def decode(value):
        return json.loads(value) if isinstance(value, str) else value

    def frozen(identifier):
        head = sql(
            "SELECT dependency_json FROM orbit_launch_template WHERE tenant_id=%s AND id=%s",
            (tenant, identifier),
            rows=True,
        )[0][0]
        versions = sql(
            "SELECT revision,dependency_json FROM "
            "orbit_launch_template_version WHERE tenant_id=%s AND "
            "template_id=%s ORDER BY revision",
            (tenant, identifier),
            rows=True,
        )
        return decode(head), {revision: decode(value) for revision, value in versions}

    def plan_dependencies(identifier):
        return decode(
            sql(
                "SELECT dependency_json FROM orbit_launch_plan_version WHERE "
                "tenant_id=%s AND plan_id=%s ORDER BY revision DESC LIMIT 1",
                (tenant, identifier),
                rows=True,
            )[0][0]
        )

    def task_counts():
        return {
            table: len(rows) for table, rows in snapshot().items() if table.startswith("orbit_task")
        }

    original_tasks = task_counts()
    profile, dependency1 = seed_metric_reference_profile(admin, database, tenant, index=101)
    body, create_key = template_metric_write_fixture(profile["id"]), str(uuid4())
    created = checked(client.post(path, headers=write(create_key), json=body), 201)
    identifier = created["id"]
    assert created["revision"] == 1 and created["state"] == "ACTIVE"
    assert frozen(identifier)[0]["metric_profiles"] == {profile["id"]: dependency1}
    assert frozen(identifier)[1][1]["metric_profiles"] == {profile["id"]: dependency1}
    assert checked(client.get(path + "/" + identifier, headers=headers), 200) == created
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[0])

    _, dependency2 = seed_metric_reference_profile(
        admin, database, tenant, index=102, identifier=profile["id"]
    )
    update_key = str(uuid4())
    updated = checked(
        client.put(path + "/" + identifier, headers=write(update_key, 1), json=body), 200
    )
    assert updated["revision"] == 2
    head, versions = frozen(identifier)
    assert head["metric_profiles"] == versions[2]["metric_profiles"] == {profile["id"]: dependency2}
    assert versions[1]["metric_profiles"] == {profile["id"]: dependency1}
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[1])

    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    assert (
        checked(client.put(path + "/" + identifier, headers=write(str(uuid4()), 2), json=body), 200)
        == updated
    )
    assert len(frozen(identifier)[1]) == 2
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[2])

    apply_key = str(uuid4())
    apply_body = {"ownership": ownership, "reason": "指标模板原apply闭环SQL"}
    applied = checked(
        client.post(
            path + "/" + identifier + "/apply", headers=write(apply_key, 2), json=apply_body
        ),
        201,
        schema="Plan",
    )
    assert applied["state"] == "DRAFT" and applied["revision"] == 1
    assert applied["account_ids"] == applied["asset_ids"] == applied["identity_bindings"] == []
    assert plan_dependencies(applied["id"])["metric_profiles"] == {profile["id"]: dependency2}
    _, dependency3 = seed_metric_reference_profile(
        admin, database, tenant, index=103, identifier=profile["id"]
    )
    applied_new = checked(
        client.post(
            path + "/" + identifier + "/apply", headers=write(str(uuid4()), 2), json=apply_body
        ),
        201,
        schema="Plan",
    )
    assert applied_new["id"] != applied["id"]
    assert plan_dependencies(applied_new["id"])["metric_profiles"] == {profile["id"]: dependency3}
    assert frozen(identifier)[0]["metric_profiles"] == {profile["id"]: dependency2}
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[3])

    changed_body = deepcopy(body)
    changed_body["description"] += "已变更版本"
    changed = checked(
        client.put(path + "/" + identifier, headers=write(str(uuid4()), 2), json=changed_body), 200
    )
    assert changed["revision"] == 3
    sql(
        "UPDATE orbit_metric_profile_head SET "
        "state='DISABLED',revision=revision+1 WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    archived = checked(
        client.post(
            path + "/" + identifier + "/archive",
            headers=write(str(uuid4()), 3),
            json={"reason": "仅归档不重验来源"},
        ),
        200,
    )
    assert archived["state"] == "ARCHIVED" and archived["revision"] == 4
    before = snapshot()
    assert checked(client.post(path, headers=write(create_key), json=body), 201) == created
    assert (
        checked(client.put(path + "/" + identifier, headers=write(update_key, 1), json=body), 200)
        == updated
    )
    assert (
        checked(
            client.post(
                path + "/" + identifier + "/apply", headers=write(apply_key, 2), json=apply_body
            ),
            201,
            schema="Plan",
        )
        == applied
    )
    assert snapshot() == before
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[4])

    # 原native模板角色没有launch.create/edit/read和monitor。正式保存不隐含计划动作。
    native, role = NATIVE_ACTOR, NATIVE_ROLE
    actor_subject, name = str(uuid4()), "template_metric_" + uuid4().hex[:12]
    assert sql("SELECT user_id FROM sys_user WHERE user_id=%s", (native,), rows=True) == ()
    assert sql("SELECT role_id FROM sys_role WHERE role_id=%s", (role,), rows=True) == ()
    sql(
        "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,"
        "data_scope,status,del_flag) "
        "VALUES(%s,'模板指标原动作SQL角色',%s,1,'1','0','0')",
        (role, name),
    )
    for menu in (31000, 31020, 310201, 310202, 310203, 310204, 310205):
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, menu))
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,"
        "del_flag) SELECT %s,%s,'模板指标SQL身份',password,'0','0' FROM "
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
        "VALUES(%s,%s,%s,%s,'模板指标SQL身份',0,UTC_TIMESTAMP(3))",
        (tenant, actor_subject, native, team),
    )
    login = fixture_login(client, cache, {"username": name, "password": password})
    assert login.status_code == 200 and login.json().get("token")
    actor_headers = {"Authorization": "Bearer " + login.json()["token"]}
    actor_caps = client.get(path + "/capabilities", headers=actor_headers)
    assert actor_caps.status_code == 200
    csrf = actor_caps.json()["csrf_token"]
    actor_profile, _ = seed_metric_reference_profile(admin, database, tenant, index=104)
    actor_body, actor_key = template_metric_write_fixture(actor_profile["id"]), str(uuid4())
    actor_created = checked(
        client.post(
            path, headers=write(actor_key, identity=actor_headers, csrf=csrf), json=actor_body
        ),
        201,
    )
    seed_metric_reference_profile(
        admin, database, tenant, index=105, identifier=actor_profile["id"]
    )
    actor_updated = checked(
        client.put(
            path + "/" + actor_created["id"],
            headers=write(str(uuid4()), 1, identity=actor_headers, csrf=csrf),
            json=actor_body,
        ),
        200,
    )
    assert actor_updated["revision"] == 2
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[5])

    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=310201", (role,))
    before = snapshot()
    denied = checked(
        client.post(
            path, headers=write(actor_key, identity=actor_headers, csrf=csrf), json=actor_body
        ),
        403,
        "PERMISSION_DENIED",
    )
    assert_metric_reference_permission_error(denied, specification)
    assert snapshot() == before
    sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,310201)", (role,))
    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id IN (310202,310203)", (role,))
    before = snapshot()
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
            headers=write(str(uuid4()), 2, identity=actor_headers, csrf=csrf),
            json=actor_body,
        ),
        403,
        "PERMISSION_DENIED",
    )
    assert snapshot() == before
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[6])

    for menu in (31021, 31022):
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, menu))
    actor_apply_key = str(uuid4())
    actor_apply_body = {
        "ownership": {"owner_user_id": actor_subject, "owner_team_id": team},
        "reason": "原模板apply读取门禁",
    }
    actor_applied = checked(
        client.post(
            path + "/" + actor_created["id"] + "/apply",
            headers=write(actor_apply_key, 2, identity=actor_headers, csrf=csrf),
            json=actor_apply_body,
        ),
        201,
        schema="Plan",
    )
    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31022", (role,))
    before = snapshot()
    assert (
        checked(
            client.post(
                path + "/" + actor_created["id"] + "/apply",
                headers=write(actor_apply_key, 2, identity=actor_headers, csrf=csrf),
                json=actor_apply_body,
            ),
            201,
            schema="Plan",
        )
        == actor_applied
    )
    checked(
        client.post(
            path + "/" + actor_created["id"] + "/apply",
            headers=write(str(uuid4()), 2, identity=actor_headers, csrf=csrf),
            json=actor_apply_body,
        ),
        403,
        "PERMISSION_DENIED",
    )
    assert snapshot() == before
    for leaf in (31021, 310201):
        sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s", (role, leaf))
        try:
            before = snapshot()
            denied = checked(
                client.post(
                    path + "/" + actor_created["id"] + "/apply",
                    headers=write(actor_apply_key, 2, identity=actor_headers, csrf=csrf),
                    json=actor_apply_body,
                ),
                403,
                "PERMISSION_DENIED",
            )
            assert_metric_reference_permission_error(denied, specification)
            assert snapshot() == before
        finally:
            sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, leaf))
    # 真实Plan PUT将其归属改给root，验证旧apply结果也不能绕过当前对象读范围。
    reassigned = checked(
        client.put(
            plan_path + "/" + actor_applied["id"],
            headers=write(str(uuid4()), 1),
            json=metric_reference_plan_fixture(root_owner, actor_profile["id"]),
        ),
        200,
        schema="Plan",
    )
    assert reassigned["ownership"] == ownership
    before = snapshot()
    checked(
        client.post(
            path + "/" + actor_created["id"] + "/apply",
            headers=write(actor_apply_key, 2, identity=actor_headers, csrf=csrf),
            json=actor_apply_body,
        ),
        404,
        "NOT_FOUND",
    )
    assert snapshot() == before
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[7])

    # 显式旧版本SQL样本故意不填044新增列，保持历史未知，不假装已完成空来源核验。
    historical_id = str(uuid4())
    historical = template_metric_write_fixture(profile["id"])
    historical["name"] = "历史NULL模板" + uuid4().hex
    sql(
        "INSERT INTO orbit_launch_template(tenant_id,id,owner_user_id,"
        "owner_team_id,name,description,visibility,state,revision,"
        "config_json,config_hash,config_bytes,created_at,updated_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,'PRIVATE','ACTIVE',1,%s,%s,%s,"
        "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (
            tenant,
            historical_id,
            subject,
            team,
            historical["name"],
            historical["description"],
            canonical(historical["campaigns"]),
            digest(historical),
            len(canonical(historical).encode()),
        ),
    )
    sql(
        "INSERT INTO orbit_launch_template_version(tenant_id,template_id,"
        "revision,value_json,created_at,created_by) "
        "VALUES(%s,%s,1,%s,UTC_TIMESTAMP(3),1)",
        (
            tenant,
            historical_id,
            canonical(historical | {"ownership": ownership, "state": "ACTIVE"}),
        ),
    )
    assert_historical_metric_dependencies_unknown(*frozen(historical_id), (1,))
    shared = checked(
        client.post(
            path + "/" + historical_id + "/share",
            headers=write(str(uuid4()), 1),
            json={"recipient_user_ids": [actor_subject], "reason": "保留未知依赖"},
        ),
        200,
    )
    assert shared["revision"] == 2 and shared["visibility"] == "TEAM"
    old_archived = checked(
        client.post(
            path + "/" + historical_id + "/archive",
            headers=write(str(uuid4()), 2),
            json={"reason": "保留未知依赖归档"},
        ),
        200,
    )
    assert old_archived["revision"] == 3
    assert_historical_metric_dependencies_unknown(*frozen(historical_id), (1, 2, 3))
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[8])

    before = snapshot()
    for statement in (
        "UPDATE orbit_launch_template_version SET "
        "dependency_json=dependency_json WHERE tenant_id=%s AND "
        "template_id=%s AND revision=1",
        "DELETE FROM orbit_launch_template_version WHERE tenant_id=%s AND "
        "template_id=%s AND revision=1",
    ):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, (tenant, historical_id))
        except Exception as error:
            admin.rollback()
            assert error.args[0] == 1644, {"errno": error.args[0]}
        else:
            admin.rollback()
            raise AssertionError("044版本保护未阻止历史改写")
    assert snapshot() == before
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[9])

    active, _ = seed_metric_reference_profile(admin, database, tenant, index=106)
    failure_body, failure_key = template_metric_write_fixture(active["id"]), str(uuid4())
    trigger = "it_template_metric_outbox_" + uuid4().hex[:10]
    before = snapshot()
    sql(
        "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_launch_outbox FOR EACH ROW SIGNAL "
        "SQLSTATE '45000' SET "
        "MESSAGE_TEXT='ISOLATED_TEMPLATE_METRIC_OUTBOX_REJECT'"
    )
    try:
        failed = client.post(path, headers=write(failure_key), json=failure_body)
        checked(failed, 503)
        assert "ISOLATED_TEMPLATE_METRIC_OUTBOX_REJECT" not in failed.text
        assert snapshot() == before
    finally:
        sql("DROP TRIGGER IF EXISTS " + trigger)
    retried = checked(client.post(path, headers=write(failure_key), json=failure_body), 201)
    assert retried["revision"] == 1 and len(frozen(retried["id"])[1]) == 1
    assert task_counts() == original_tasks
    cases.append(TEMPLATE_METRIC_REFERENCE_CASES[10])
    return {
        "template_reference_cases": len(TEMPLATE_METRIC_REFERENCE_CASES),
        "authority": "ISOLATED_SQL_NOT_META",
        "task_writes": 0,
        "historical_null": "PRESERVED_UNKNOWN",
    }
