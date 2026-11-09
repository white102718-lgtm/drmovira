"""规则定义整页验收的最小真实HTTP图；不重跑故障注入/容量专项。"""

import json
from uuid import uuid4

RULE_DEFINITION_BROWSER_CASE = "pythonRuleDefinitionBrowserFixtureUsesOriginalCreateAndRead"


def prepare_rule_definition_browser(client, admin, headers, database, cases):
    from metric_fact_schema_checks import MetricFactSqlFixture
    from metric_profile_reference_checks import seed_metric_reference_profile
    from rule_definition_checks import checked, definition_body, guard_rule_target

    guard_rule_target(admin, database)
    fixture = MetricFactSqlFixture(admin, database)
    marker = "业务闭环" + uuid4().hex[:8]
    accounts = [fixture.account() for _ in range(3)]
    for index, account in enumerate(accounts):
        name = marker + "账户" + str(index + 1)
        fixture.sql(
            "UPDATE orbit_ad_account SET name=%s,name_prefix=%s WHERE tenant_id=%s AND id=%s",
            (name, name, fixture.tenant, account),
        )
    fixture.sql(
        "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (fixture.tenant,)
    )
    profile, _ = seed_metric_reference_profile(admin, database, fixture.tenant, index=970)
    cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200)
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": accounts[:1], "filter": None},
        ),
        201,
    )
    cap = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"}), 200
    )
    body = definition_body(
        marker + "现有草稿", fixture.owner, fixture.team, scope["id"], profile["id"]
    )
    rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=body,
        ),
        201,
    )
    assert checked(client.get("/api/v1/rules/" + rule["id"], headers=headers), 200) == rule
    pause_body = body | {"name": marker + "暂停验收技术状态"}
    pause_rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=pause_body,
        ),
        201,
    )
    # 仅隔离SQL技术状态，用来实测暂停；绝不伪称原enable接口或Simulation成功。
    # 不修改已封存版本/成员，不停trigger或外键，不启动调度，也不填假next_run_at。
    event = str(uuid4())
    try:
        admin.begin()
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_rule_event(tenant_id,id,rule_id,revision,actor_id,request_id,"
                "action,reason,details_json) VALUES(%s,%s,%s,2,1,%s,'ENABLE',NULL,%s)",
                (
                    fixture.tenant,
                    event,
                    pause_rule["id"],
                    str(uuid4()),
                    json.dumps({"fixture_only": "PAUSE_INPUT_NOT_ENABLE_SUCCESS"}),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_rule_version(tenant_id,rule_id,revision,"
                "payload_json,payload_hash,"
                "name,owner_user_id,owner_team_id,target_level,state,manifest_id,metric_profile_id,"
                "metric_profile_version,metric_profile_hash,profile_proof_hash,event_id) "
                "SELECT tenant_id,rule_id,2,payload_json,payload_hash,name,"
                "owner_user_id,owner_team_id,"
                "target_level,'ENABLED',manifest_id,metric_profile_id,metric_profile_version,"
                "metric_profile_hash,profile_proof_hash,%s FROM orbit_rule_version "
                "WHERE tenant_id=%s AND rule_id=%s AND revision=1",
                (event, fixture.tenant, pause_rule["id"]),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                "UPDATE orbit_rule_head SET revision=2,state='ENABLED',updated_at=UTC_TIMESTAMP(3) "
                "WHERE tenant_id=%s AND id=%s AND revision=1 AND state='DRAFT'",
                (fixture.tenant, pause_rule["id"]),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                "INSERT INTO orbit_rule_outbox(tenant_id,event_id) VALUES(%s,%s)",
                (fixture.tenant, event),
            )
            cursor.execute(
                "UPDATE orbit_rule_clock SET revision=revision+1 WHERE tenant_id=%s",
                (fixture.tenant,),
            )
        admin.commit()
    except BaseException:
        admin.rollback()
        raise
    pause_value = checked(client.get("/api/v1/rules/" + pause_rule["id"], headers=headers), 200)
    assert pause_value["state"] == "ENABLED" and pause_value["revision"] == 2
    assert pause_value["next_run_at"] is None
    cases.append(RULE_DEFINITION_BROWSER_CASE)
    return {
        "scope": "ISOLATED_SQL_PROFILE_NOT_META_OR_ENABLE",
        "marker": marker,
        "account_ids": accounts,
        "profile_id": profile["id"],
        "existing_draft_id": rule["id"],
        "pause_fixture_id": pause_rule["id"],
        "pause_fixture_authority": "ISOLATED_SQL_STATE_NOT_ENABLE_OR_SIMULATION_SUCCESS",
        "browser_checks_executed": False,
    }
