"""原execute默认关闭的真实HTTP门禁；不以503测试冒充原202成功受理。"""

import re
from uuid import uuid4

from launch_draft_template_checks import draft

EXECUTION_HTTP_CASES = [
    "pythonLaunchExecutionOriginalHeadersStrictBodyAndNoUnquotedCas",
    "pythonLaunchExecutionDefaultAuthorityMissing503HasZeroTaskCommandPreparationWrites",
    "pythonLaunchExecutionCurrentCsrfAndExecutePermissionBeforeAuthorityGate",
    "pythonLaunchExecutionMissingObjectNotHiddenByGlobal503",
    "pythonLaunchExecutionUnknownQueryRejectedAndTargetTenantCurrently403",
]


def run_launch_execution_http_checks(client, admin, headers, database, cases):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("执行HTTP门禁仅允许本轮13306 UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        _tenant, owner, team = cursor.fetchone()

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
        }
        return response.json()

    def write():
        caps = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return headers | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"1"',
        }

    create_headers = write()
    create_headers.pop("If-Match")
    plan = checked(
        client.post(
            "/api/v1/launch-plans",
            headers=create_headers,
            json=draft({"id": owner, "team": team}),
        ),
        201,
    )
    path = f"/api/v1/launch-plans/{plan['id']}/execute"
    body = {"hash": "a" * 64, "activate_ack": False}

    def snapshot():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s "
                "AND (table_name LIKE 'orbit_launch%%' OR table_name LIKE 'orbit_task%%' "
                "OR table_name='orbit_material_reference') ORDER BY table_name",
                (database,),
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert tables and all(re.fullmatch(r"[a-z_]+", name) for name in tables)
            rows = []
            for name in tables:
                cursor.execute("SELECT * FROM " + name)
                rows.append((name, tuple(sorted(cursor.fetchall(), key=repr))))
            return rows

    original = snapshot()
    for name, status in (("Idempotency-Key", 400), ("If-Match", 400), ("X-CSRF-Token", 403)):
        incomplete = write()
        incomplete.pop(name)
        checked(client.post(path, headers=incomplete, json=body), status)
    for invalid in ({}, body | {"activate_ack": 1}, body | {"unregistered": True}):
        checked(client.post(path, headers=write(), json=invalid), 400)
    checked(client.post(path, headers=write() | {"If-Match": "1"}, json=body), 400)
    assert snapshot() == original
    cases.append(EXECUTION_HTTP_CASES[0])

    for _ in range(2):
        result = checked(client.post(path, headers=write(), json=body), 503)
        assert result["code"] == "LAUNCH_EXECUTION_AUTHORITY_UNAVAILABLE"
    assert snapshot() == original
    cases.append(EXECUTION_HTTP_CASES[1])

    checked(
        client.post(path, headers=write() | {"X-CSRF-Token": "invalid-fixture"}, json=body), 403
    )
    permission_headers = write()
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_menu WHERE perms='launch.execute'")
        status = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_menu SET status='1' WHERE perms='launch.execute'")
    try:
        checked(client.post(path, headers=permission_headers, json=body), 403)
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status=%s WHERE perms='launch.execute'", (status,))
    assert snapshot() == original
    cases.append(EXECUTION_HTTP_CASES[2])

    checked(client.post(f"/api/v1/launch-plans/{uuid4()}/execute", headers=write(), json=body), 404)
    assert snapshot() == original
    cases.append(EXECUTION_HTTP_CASES[3])
    checked(client.post(path + "?unknown=1", headers=write(), json=body), 400)
    checked(client.post(path, headers=write() | {"X-Target-Tenant": str(uuid4())}, json=body), 403)
    assert snapshot() == original
    cases.append(EXECUTION_HTTP_CASES[4])
    return {
        "default_authority": "UNAVAILABLE",
        "business_mutation": False,
        "known_gap": "受控SUPER跨租户写尚未实现，当前统一403；本档不结清完整原execute合同",
    }
