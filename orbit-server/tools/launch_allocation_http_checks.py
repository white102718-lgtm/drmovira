"""原分配HTTP默认关闭专项；仅独立UUID库，不把SQL队列夹具当POST受理成功。"""

import re
from uuid import uuid4

from launch_draft_template_checks import draft

LAUNCH_ALLOCATION_HTTP_CASES = [
    "pythonLaunchAllocationOriginalRequestHeadersAndStrictBody",
    "pythonLaunchAllocationDefaultMissingProvider503AndZeroBusinessWrites",
    "pythonLaunchAllocationCurrentCsrfAndActionBeforeProviderAvailability",
    "pythonLaunchAllocationOriginalPersistedQueuedReadWithoutProviderOrFakeTask",
    "pythonLaunchAllocationParentBindingAndUnknownQueryRejectWithoutMutation",
]


def run_launch_allocation_http_checks(client, admin, headers, database, cases):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("分配HTTP只允许主线本轮13306/UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
        }
        return response.json()

    def write(revision=1):
        capability = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return headers | {
            "X-CSRF-Token": capability["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": str(uuid4()),
        }

    create_headers = write()
    create_headers.pop("If-Match")
    item = checked(
        client.post(
            "/api/v1/launch-plans",
            headers=create_headers,
            json=draft({"id": owner, "team": team}),
        ),
        201,
    )
    path = f"/api/v1/launch-plans/{item['id']}/allocations"
    request = {
        "asset_ids": [str(uuid4())],
        "allow_repeat": False,
        "seed": 0,
        "algorithm_version": "allocation-v1",
    }

    def snapshot():
        with admin.cursor() as cursor:
            result = []
            for name in (
                "orbit_launch_plan",
                "orbit_launch_plan_version",
                "orbit_launch_allocation",
                "orbit_launch_allocation_item",
                "orbit_launch_allocation_runtime",
                "orbit_launch_allocation_chunk",
                "orbit_launch_allocation_guard",
                "orbit_launch_clock",
                "orbit_launch_event",
                "orbit_launch_outbox",
                "orbit_launch_idempotency",
                "orbit_task",
            ):
                cursor.execute("SELECT * FROM " + name)
                result.append(tuple(sorted(cursor.fetchall(), key=repr)))
            return tuple(result)

    before = snapshot()
    for missing, expected in (("Idempotency-Key", 400), ("If-Match", 400), ("X-CSRF-Token", 403)):
        incomplete = write()
        incomplete.pop(missing)
        checked(client.post(path, headers=incomplete, json=request), expected)
    for body in ({}, request | {"seed": True}, request | {"extra": "not-allowed"}):
        checked(client.post(path, headers=write(), json=body), 400)
    checked(client.post(path, headers=write(), json=request | {"seed": -1}), 422)
    assert snapshot() == before
    cases.append(LAUNCH_ALLOCATION_HTTP_CASES[0])

    rejected = checked(client.post(path, headers=write(), json=request), 503)
    assert rejected["code"] == "ALLOCATION_PROVIDER_UNAVAILABLE"
    assert snapshot() == before
    cases.append(LAUNCH_ALLOCATION_HTTP_CASES[1])

    checked(client.post(path, headers=write() | {"X-CSRF-Token": "invalid" * 8}, json=request), 403)
    revoked_header = write()
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31023")
        status = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31023")
    try:
        checked(client.post(path, headers=revoked_header, json=request), 403)
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status=%s WHERE menu_id=31023", (status,))
    assert snapshot() == before
    cases.append(LAUNCH_ALLOCATION_HTTP_CASES[2])

    # 仅用于原GET序列化/授权验证，不伪称缺生产Provider的POST已接受或Worker已求解。
    allocation = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_launch_allocation "
            "(tenant_id,id,plan_id,plan_revision,state,task_id,algorithm_version,seed,input_hash,"
            "warnings_json,active,created_at,updated_at) "
            "VALUES(%s,%s,%s,1,'QUEUED',NULL,'allocation-v1',0,%s,'[]',0,UTC_TIMESTAMP(3),"
            "UTC_TIMESTAMP(3))",
            (tenant, allocation, item["id"], "b" * 64),
        )
    stored = checked(client.get(path + "/" + allocation, headers=headers), 200)
    assert stored == {
        "id": allocation,
        "plan_id": item["id"],
        "plan_revision": 1,
        "state": "QUEUED",
        "task_id": None,
        "algorithm_version": "allocation-v1",
        "seed": 0,
        "input_hash": "b" * 64,
        "items": [],
        "warnings": [],
    }
    cases.append(LAUNCH_ALLOCATION_HTTP_CASES[3])
    before = snapshot()
    checked(client.get(path + "/" + str(uuid4()), headers=headers), 404)
    checked(
        client.get(f"/api/v1/launch-plans/{uuid4()}/allocations/{allocation}", headers=headers),
        404,
    )
    checked(client.get(path + "/" + allocation + "?actor=1", headers=headers), 400)
    assert snapshot() == before
    cases.append(LAUNCH_ALLOCATION_HTTP_CASES[4])
    return {"case_count": len(LAUNCH_ALLOCATION_HTTP_CASES), "production_provider": "MISSING"}
