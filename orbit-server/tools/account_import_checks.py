"""主任务串行接入的真实HTTP/MySQL账户受理专项；不伪造平台元数据或执行平台写入。"""

from uuid import uuid4

CASES = [
    "pythonAccountImportRawTokensAndExactQueuedResult",
    "pythonAccountImportIdempotencyAndOriginalLimitBeforeDeduplication",
    "pythonAccountImportFiveHundredRowsUseBoundCursorPages",
    "pythonAccountImportAuditFailureRollsBackBatchRowsAndIdempotency",
]


def run_account_import_checks(
    client, admin, headers, owner_user_id, owner_team_id, vendor_id, cases
):
    """调用方预置可读AVAILABLE户商并已分配给目标owner；对象root必须为当前隔离临时目录。"""
    caps = client.get("/api/v1/account-imports/capabilities", headers=headers)
    assert caps.status_code == 200

    def request(raw, key=None):
        return client.post(
            "/api/v1/account-imports",
            headers=headers
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": key or "account-import-" + uuid4().hex,
            },
            json={
                "vendor_id": vendor_id,
                "owner_user_id": owner_user_id,
                "owner_team_id": owner_team_id,
                "account_ids_text": raw,
            },
        )

    def count(table):
        # 表名只能来自下面固定调用点，不能由网络请求传入。
        with admin.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM " + table)
            return cursor.fetchone()[0]

    before_accounts = count("orbit_ad_account")
    first = request("act_000123，000123\ninvalid 44")
    assert first.status_code == 202
    value = first.json()
    assert set(value) == {
        "id",
        "revision",
        "vendor_id",
        "state",
        "total",
        "success_count",
        "failed_count",
        "duplicate_count",
        "rows",
        "next_cursor",
    }
    assert value["state"] == "QUEUED" and value["total"] == 4
    assert (
        value["success_count"] == 0 and value["failed_count"] == 1 and value["duplicate_count"] == 1
    )
    assert [row["state"] for row in value["rows"]] == ["WAITING", "DUPLICATE", "INVALID", "WAITING"]
    assert value["rows"][0]["normalized_id"] == "000123"
    assert value["rows"][1]["duplicate_of"] == 0
    assert all(row["spend"]["amount"] is None for row in value["rows"])
    actual = client.get("/api/v1/account-imports/" + value["id"], headers=headers)
    assert actual.status_code == 200 and actual.json() == value
    for path, params in (
        ("/api/v1/account-imports/not-a-uuid", None),
        ("/api/v1/accounts/not-a-uuid", None),
        ("/api/v1/accounts", {"operator_user_id": "not-a-uuid"}),
        ("/api/v1/accounts", {"vendor_id": "not-a-uuid"}),
    ):
        invalid = client.get(path, params=params, headers=headers)
        assert invalid.status_code == 422
    assert count("orbit_ad_account") == before_accounts  # 排队不能创建假账户。
    cases.append(CASES[0])

    key = "account-replay-" + uuid4().hex
    initial = request("00001", key)
    assert initial.status_code == 202
    before = count("orbit_account_import")
    assert request("00001", key).json() == initial.json()
    assert request("00002", key).status_code == 409
    assert request("1 " * 501).status_code == 422
    assert count("orbit_account_import") == before
    cases.append(CASES[1])

    page = request(" ".join(str(number) for number in range(500)))
    assert page.status_code == 202 and len(page.json()["rows"]) == 200
    result, seen = page.json(), []
    while True:
        seen.extend(row["token_index"] for row in result["rows"])
        if not result["next_cursor"]:
            break
        response = client.get(
            "/api/v1/account-imports/" + result["id"],
            params={"cursor": result["next_cursor"]},
            headers=headers,
        )
        assert response.status_code == 200
        result = response.json()
    assert seen == list(range(500))
    cases.append(CASES[2])

    tables = [
        "orbit_account_import",
        "orbit_account_import_row",
        "orbit_account_idempotency",
        "orbit_account_event",
        "orbit_account_outbox",
    ]
    before = {table: count(table) for table in tables}
    key = "account-rollback-" + uuid4().hex
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER account_accept_audit_fail BEFORE INSERT ON orbit_account_event "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'"
        )
    try:
        assert request("000888", key).status_code == 503
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_accept_audit_fail")
    assert {table: count(table) for table in tables} == before
    assert request("000888", key).status_code == 202
    assert count("orbit_account_import") == before["orbit_account_import"] + 1
    cases.append(CASES[3])
