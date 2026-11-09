"""主动只读探测真实HTTP/mTLS/事务检查；仅由有隔离库护栏的父运行器调用。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

PROBE_CASES = [
    "environmentProbeQueuesOriginalAckAndIdempotentReplay",
    "environmentProbeStrictScopeCsrfRevisionAndSinglePending",
    "environmentProbeRejectsOldObservationAndMissingDiagnostics",
    "environmentProbeFreshObservationCompletesWithoutIdentityGrant",
    "environmentProbeCompletionReplayAndConflictingPayload",
    "environmentProbeFailureIsNotSuccess",
    "environmentProbeExpiryAndCertificateRevocation",
    "environmentProbeAuditFailureRollsBackQueue",
    "environmentProbeConcurrentQueueOnlyOneRequest",
    "environmentProbeInitiatorRevocationCancelsDispatch",
]


def run_probe_checks(
    client, device, headers, write, sql, checked, tenant, agent, cases, read_headers
):
    root = f"/api/v1/execution-agents/{agent}"
    queue = "/api/v1/agent-api/probe-requests"

    def state_path(identifier):
        return root + "/probe-requests/" + identifier

    def stamp():
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    old_observed = stamp()
    wh = write(1, "PROBE")
    ack = checked(client.post(root + "/probe", headers=wh), 202)
    assert set(ack) == {"id", "revision", "state", "request_id"}
    assert ack["state"] == "QUEUED" and ack["revision"] == 1
    assert checked(client.post(root + "/probe", headers=wh), 202) == ack
    request = checked(client.get(state_path(ack["id"]), headers=headers))
    assert set(request) == {
        "id",
        "agent_id",
        "state",
        "created_at",
        "expires_at",
        "completed_at",
        "error_code",
    }
    assert request["state"] == "QUEUED" and request["completed_at"] is None
    assert checked(device.get(queue))["request"]["id"] == ack["id"]
    assert checked(client.get(root, headers=headers))["revision"] == 1
    cases.append(PROBE_CASES[0])
    checked(client.post(root + "/probe", headers=write(1, "PROBE")), 409)
    checked(client.post(root + "/probe", headers=wh | {"If-Match": '"2"'}), 409)
    checked(client.post(root + "/probe", headers=wh | {"X-CSRF-Token": "x" * 32}), 400)
    checked(
        client.post(root + "/probe", headers={k: v for k, v in wh.items() if k != "X-CSRF-Token"}),
        403,
    )
    checked(client.post(root + "/probe", headers=wh, json={}), 413)
    checked(client.get(state_path(ack["id"]), headers=read_headers), 403)
    checked(
        client.get(
            f"/api/v1/execution-agents/{uuid4()}/probe-requests/{ack['id']}", headers=headers
        ),
        404,
    )
    checked(device.get(queue + "?other=1"), 400)
    cases.append(PROBE_CASES[1])
    boot = str(uuid4())

    def report(seq, api="READY", observed=None):
        value = {"agent_id": agent, "boot_id": boot, "seq": seq, "observed_at": observed or stamp()}
        checked(device.post("/api/v1/agent-api/heartbeats", json=value | {"profiles": []}))
        checked(
            device.post(
                "/api/v1/agent-api/diagnostics",
                json=value
                | {
                    "api_status": api,
                    "inventory_coverage": "FULL" if api == "READY" else "UNAVAILABLE",
                    "error_code": None if api == "READY" else "PROFILE_DISCOVERY_FAILED",
                },
            )
        )
        return value

    value = {"agent_id": agent, "boot_id": boot, "seq": 1, "observed_at": stamp()}
    checked(device.post("/api/v1/agent-api/heartbeats", json=value | {"profiles": []}))
    complete = queue + "/" + ack["id"] + "/complete"
    checked(device.post(complete, json=value), 409)
    fresh = report(2)
    checked(device.post(complete, json=fresh | {"observed_at": old_observed}), 409)
    assert checked(client.get(state_path(ack["id"]), headers=headers))["state"] == "QUEUED"
    cases.append(PROBE_CASES[2])
    result = checked(device.post(complete, json=fresh))
    assert result["state"] == "COMPLETED" and result["id"] == ack["id"]
    state = checked(client.get(state_path(ack["id"]), headers=headers))
    assert state["state"] == "COMPLETED" and state["completed_at"] and state["error_code"] is None
    assert checked(device.get(queue))["request"] is None
    assert checked(client.get(root, headers=headers))["revision"] == 1
    cases.append(PROBE_CASES[3])
    assert checked(device.post(complete, json=fresh)) == result
    checked(device.post(complete, json=fresh | {"seq": 3}), 409)
    cases.append(PROBE_CASES[4])
    failed = checked(client.post(root + "/probe", headers=write(1, "PROBE")), 202)
    value = report(3, "UNKNOWN")
    result = checked(device.post(queue + "/" + failed["id"] + "/complete", json=value))
    assert result["state"] == "FAILED"
    state = checked(client.get(state_path(failed["id"]), headers=headers))
    assert state["error_code"] == "LOCAL_API_UNAVAILABLE"
    cases.append(PROBE_CASES[5])
    expired = checked(client.post(root + "/probe", headers=write(1, "PROBE")), 202)
    sql(
        "UPDATE orbit_agent_probe_request SET "
        "created_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 121 SECOND),"
        "expires_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE tenant_id=%s AND id=%s",
        (tenant, expired["id"]),
    )
    assert checked(client.get(state_path(expired["id"]), headers=headers))["state"] == "EXPIRED"
    assert checked(device.get(queue))["request"] is None
    checked(device.post(queue + "/" + expired["id"] + "/complete", json=value), 410)
    sql(
        "UPDATE orbit_agent_certificate SET revoked_at=UTC_TIMESTAMP(6) "
        "WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
    )
    checked(device.get(queue), 403)
    checked(device.post(complete, json=fresh), 403)
    sql(
        "UPDATE orbit_agent_certificate SET revoked_at=NULL WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
    )
    cases.append(PROBE_CASES[6])
    before = sql(
        "SELECT COUNT(*) FROM orbit_agent_probe_request WHERE tenant_id=%s AND agent_id=%s",
        (tenant, agent),
        True,
    )[0][0]
    sql(
        "CREATE TRIGGER orbit_probe_test_audit_failure BEFORE INSERT ON "
        "orbit_execution_agent_outbox FOR EACH ROW SIGNAL SQLSTATE '45000' "
        "SET MESSAGE_TEXT='isolated probe rollback'"
    )
    try:
        checked(client.post(root + "/probe", headers=write(1, "PROBE")), 503)
    finally:
        sql("DROP TRIGGER orbit_probe_test_audit_failure")
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_agent_probe_request WHERE tenant_id=%s AND agent_id=%s",
            (tenant, agent),
            True,
        )[0][0]
        == before
    )
    cases.append(PROBE_CASES[7])

    # 两个真实并发HTTP写只能产生一个有效待办，禁止用串行假装验证互斥。
    concurrent_headers = [write(1, "PROBE"), write(1, "PROBE")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda h: client.post(root + "/probe", headers=h), concurrent_headers)
        )
    assert sorted(r.status_code for r in responses) == [202, 409]
    queued = next(r.json() for r in responses if r.status_code == 202)
    count = sql(
        "SELECT COUNT(*) FROM orbit_agent_probe_request WHERE tenant_id=%s AND agent_id=%s "
        "AND state='QUEUED' AND expires_at>UTC_TIMESTAMP(6)",
        (tenant, agent),
        True,
    )[0][0]
    assert count == 1
    value = report(4)
    checked(device.post(queue + "/" + queued["id"] + "/complete", json=value))
    cases.append(PROBE_CASES[8])
    revoked_headers = write(1, "PROBE")
    revoked = checked(client.post(root + "/probe", headers=revoked_headers), 202)
    menu = sql("SELECT menu_id,status FROM sys_menu WHERE perms='environments.probe'", fetch=True)
    assert len(menu) == 1
    try:
        sql("UPDATE sys_menu SET status='1' WHERE menu_id=%s", (menu[0][0],))
        checked(client.post(root + "/probe", headers=revoked_headers), 403)
        assert checked(device.get(queue))["request"] is None
        state = checked(client.get(state_path(revoked["id"]), headers=headers))
        assert state["state"] == "FAILED" and state["error_code"] == "PROBE_AUTHORIZATION_REVOKED"
        checked(device.post(queue + "/" + revoked["id"] + "/complete", json=value), 403)
    finally:
        sql("UPDATE sys_menu SET status=%s WHERE menu_id=%s", (menu[0][1], menu[0][0]))
    checked(
        device.post(
            queue + "/" + revoked["id"] + "/complete", json=value | {"agent_id": str(uuid4())}
        ),
        403,
    )
    cases.append(PROBE_CASES[9])
