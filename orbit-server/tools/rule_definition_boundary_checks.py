"""原规则字段边界的真实HTTP补充；仅在主线13306本轮UUID隔离库运行。"""

import copy
import hashlib
import json
from uuid import uuid4

RULE_DEFINITION_BOUNDARY_CASES = (
    "pythonRuleDefinitionUnicodeNameOneEightyAndOverflowNoPartialWrites",
    "pythonRuleDefinitionAllThreeTargetsFourWindowsAndInvalidEnums",
    "pythonRuleDefinitionFiveGroupsTwentyLeavesAndBothOverflowBoundaries",
    "pythonRuleDefinitionInclusive366DaysAnd367DayRejection",
    "pythonRuleDefinitionCooldownZero10080AndOutsideBoundaries",
    "pythonRuleDefinitionMaxDailyOne1000AndOutsideBoundaries",
    "pythonRuleDefinitionStrictIntegersAndReadonlyFieldsHaveNoPartialWrites",
)


def run_rule_definition_boundary_checks(client, admin, headers, password, cache, database, cases):
    # 先核目标，禁止在原项目或正式库创建边界数据。
    if __package__:
        from .metric_fact_schema_checks import MetricFactSqlFixture
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import TABLES, checked, definition_body, guard_rule_target
    else:
        from metric_fact_schema_checks import MetricFactSqlFixture
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import TABLES, checked, definition_body, guard_rule_target

    guard_rule_target(admin, database)
    from orbit_api.rule_contract import Rule, parse_rule_response

    fixture = MetricFactSqlFixture(admin, database)
    account = fixture.account()
    fixture.sql(
        "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (fixture.tenant,)
    )
    profile, _ = seed_metric_reference_profile(admin, database, fixture.tenant, index=964)
    scope_cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200)
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers
            | {"X-CSRF-Token": scope_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": [account], "filter": None},
        ),
        201,
    )
    cap = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"}), 200
    )
    base = definition_body(
        "边界-" + uuid4().hex, fixture.owner, fixture.team, scope["id"], profile["id"]
    )
    created = 0
    rejected = 0

    def snapshot():
        # 数据量由本专项有限fixture约束；比较八张规则表的完整原行，不只比COUNT。
        result = []
        with admin.cursor() as cursor:
            for table in TABLES:
                cursor.execute("SELECT * FROM " + table)
                rows = sorted(cursor.fetchall(), key=repr)
                result.append(
                    hashlib.sha256(
                        json.dumps(rows, ensure_ascii=False, default=str).encode()
                    ).hexdigest()
                )
        admin.commit()
        return result

    def submit(body):
        return client.post(
            "/api/v1/rules",
            headers=headers
            | {
                "X-CSRF-Token": cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            },
            json=body,
        )

    def valid(update):
        nonlocal created
        body = copy.deepcopy(base)
        body["name"] = "边界-" + uuid4().hex
        body.update(copy.deepcopy(update))
        value = checked(submit(body), 201)
        parsed = parse_rule_response(Rule, value)
        assert parsed.state == "DRAFT" and parsed.revision == 1 and parsed.next_run_at is None
        assert {key: value[key] for key in body} == body
        stored = checked(client.get("/api/v1/rules/" + value["id"], headers=headers), 200)
        assert stored == value
        created += 1

    def invalid(update, pointer, *, code="FIELD_VALIDATION_FAILED"):
        nonlocal rejected
        body = copy.deepcopy(base)
        body.update(copy.deepcopy(update))
        before = snapshot()
        value = checked(submit(body), 422 if code == "FIELD_VALIDATION_FAILED" else 400, code=code)
        assert len(value["field_errors"]) == 1
        assert value["field_errors"][0]["path"] == pointer
        assert value["field_errors"][0]["code"] == code
        assert snapshot() == before
        rejected += 1

    valid({"name": "界"})
    valid({"name": "界" * 80})
    for name in ("", "   ", "界" * 81):
        invalid({"name": name}, "/name")
    cases.append(RULE_DEFINITION_BOUNDARY_CASES[0])

    for target in ("CAMPAIGN", "ADSET", "AD"):
        valid({"target_level": target})
    for window in ("TODAY", "YESTERDAY", "LAST_3D", "LAST_7D"):
        valid({"window": window})
    invalid({"target_level": "ACCOUNT"}, "/target_level")
    invalid({"window": "LAST_30D"}, "/window")
    cases.append(RULE_DEFINITION_BOUNDARY_CASES[1])

    condition = base["groups"][0]["conditions"][0]

    def groups(count, leaves):
        return [
            {"logic": "AND", "conditions": [copy.deepcopy(condition) for _ in range(leaves)]}
            for _ in range(count)
        ]

    valid({"groups": groups(5, 4)})
    invalid({"groups": groups(6, 1)}, "/groups")
    invalid({"groups": groups(1, 11)}, "/groups/0/conditions")
    invalid({"groups": groups(3, 7)}, "/groups")
    cases.append(RULE_DEFINITION_BOUNDARY_CASES[2])

    schedule = base["schedule"] | {"start_date": "2026-01-01", "end_date": "2027-01-01"}
    valid({"schedule": schedule})
    invalid({"schedule": schedule | {"end_date": "2027-01-02"}}, "/schedule/end_date")
    cases.append(RULE_DEFINITION_BOUNDARY_CASES[3])

    for field, good, bad, index in (
        ("cooldown_minutes", (0, 10080), (-1, 10081), 4),
        ("max_daily", (1, 1000), (0, 1001), 5),
    ):
        for number in good:
            valid({field: number})
        for number in bad:
            invalid({field: number}, "/" + field)
        cases.append(RULE_DEFINITION_BOUNDARY_CASES[index])
    for field in ("cooldown_minutes", "max_daily"):
        invalid({field: True}, "/" + field, code="INVALID_STRUCTURE")
    for field, value in (
        ("id", str(uuid4())),
        ("revision", 1),
        ("state", "ENABLED"),
        ("next_run_at", None),
    ):
        invalid({field: value}, "/" + field, code="UNKNOWN_FIELD")
    cases.append(RULE_DEFINITION_BOUNDARY_CASES[6])
    return {
        "created_drafts": created,
        "strict_rejections": rejected,
        "technical_profile_only": True,
        "simulation_or_enable_called": False,
        "capacity_tested": False,
    }
