"""真实Metrics默认未发行HTTP边界；不注册假来源或调用平台。"""

from uuid import uuid4

from metrics_query_read_checks import guard_target, query

METRIC_QUERY_HTTP_CASES = [
    "pythonMetricsPublicCapabilitiesExactCurrentMonitorContext",
    "pythonMetricsPublicHeadersBodyAndTargetTenantRejectBeforeBuild",
    "pythonMetricsPublicMissingSourceOriginal503NeverEmptyOr202",
    "pythonMetricsPublicMonitorContextDoesNotBorrowAccountsAction",
]


def run_metrics_http_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)

    def checked(response, status):
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert response.headers.get("x-request-id")
        return response.json()

    context = checked(client.get("/api/v1/metrics/capabilities", headers=headers), 200)
    assert set(context) == {"csrf_token"} and 16 <= len(context["csrf_token"]) <= 255
    body = query({"id": str(uuid4())})
    action = headers | {"X-CSRF-Token": context["csrf_token"], "Idempotency-Key": uuid4().hex}
    cases.append(METRIC_QUERY_HTTP_CASES[0])
    assert (
        client.get(
            "/api/v1/metrics/capabilities", headers=headers | {"X-Target-Tenant": str(uuid4())}
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/metrics/capabilities", headers=headers, params={"q": "x"}).status_code
        == 400
    )
    assert client.post("/api/v1/metrics/query", headers=headers, json=body).status_code == 400
    assert (
        client.post(
            "/api/v1/metrics/query", headers=action, json=body | {"unknown": True}
        ).status_code
        == 400
    )
    pairs = list(action.items())
    assert (
        client.post(
            "/api/v1/metrics/query", headers=pairs + [("Idempotency-Key", uuid4().hex)], json=body
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/metrics/query",
            headers=pairs + [("X-CSRF-Token", context["csrf_token"])],
            json=body,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/metrics/query", headers=action | {"If-Match": '"1"'}, json=body
        ).status_code
        == 400
    )
    cases.append(METRIC_QUERY_HTTP_CASES[1])

    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_metric_query_snapshot")
        before = cursor.fetchone()[0]
    admin.commit()
    response = client.post("/api/v1/metrics/query", headers=action, json=body)
    error = checked(response, 503)
    assert set(error) == {"code", "message", "request_id", "retryable", "field_errors"}
    assert error["retryable"] is True and error["request_id"] == response.headers["x-request-id"]
    assert "items" not in error and "totals" not in error
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_metric_query_snapshot")
        assert cursor.fetchone()[0] == before
    admin.commit()
    cases.append(METRIC_QUERY_HTTP_CASES[2])

    # 使用真正非bootstrap身份验证，root1是原框架显式超级管理员，不能伪作受限用户。
    from account_scope_visibility_plan_checks import prepare_plan_identities

    user = prepare_plan_identities(client, admin, headers, password, cache)["USER"]
    role_context = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_context["csrf_token"], "Idempotency-Key": uuid4().hex},
            json={
                "name": "指标公开只读-" + uuid4().hex[:12],
                "menu_codes": ["monitor"],
                "permission_codes": ["monitor.read"],
            },
        ),
        201,
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) SELECT %s,native_role_id "
            "FROM orbit_business_role WHERE id=%s",
            (user["actor_id"], role["id"]),
        )
        cursor.execute(
            "SELECT rm.role_id,rm.menu_id FROM sys_role_menu rm JOIN sys_user_role ur "
            "ON ur.role_id=rm.role_id WHERE ur.user_id=%s AND rm.menu_id=31011",
            (user["actor_id"],),
        )
        grants = cursor.fetchall()
    admin.commit()
    assert grants
    try:
        with admin.cursor() as cursor:
            cursor.executemany(
                "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                grants,
            )
        admin.commit()
        assert (
            client.get("/api/v1/scope-snapshots/capabilities", headers=user["headers"]).status_code
            == 403
        )
        user_context = checked(
            client.get("/api/v1/metrics/capabilities", headers=user["headers"]), 200
        )
        user_action = user["headers"] | {
            "X-CSRF-Token": user_context["csrf_token"],
            "Idempotency-Key": uuid4().hex,
        }
        assert (
            client.post("/api/v1/metrics/query", headers=user_action, json=body).status_code == 503
        )
        assert (
            client.post(
                "/api/v1/metrics/query",
                headers=user_action | {"X-CSRF-Token": context["csrf_token"]},
                json=body,
            ).status_code
            == 403
        )
    finally:
        admin.rollback()
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                grants,
            )
        admin.commit()
    cases.append(METRIC_QUERY_HTTP_CASES[3])
    return {"public_cases": 4, "production_source_present": False, "platform_writes": 0}
