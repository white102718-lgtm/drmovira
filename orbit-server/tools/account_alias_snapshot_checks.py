"""020代称业务时点快照真实专项草案；由主线接线后串行执行，不访问真实平台。"""

import re
from uuid import uuid4

CASES = [
    "pythonAccountAliasUnsetIsCapturedAsNullWithExplicitSource",
    "pythonAccountAliasCurrentRefreshDoesNotRewriteAcceptedHistory",
    "pythonAccountAliasReplayKeepsFirstBusinessSnapshot",
    "pythonAccountAliasImportOnlyDoesNotRequireReadPermission",
    "pythonAccountAliasSnapshotFailureRollsBackOriginalBusinessTransaction",
    "pythonAccountAliasCurrentAndExtendedStayConsistentAndOldCursorsInvalidate",
]


def run_account_alias_snapshot_checks(
    client,
    admin,
    headers,
    import_identity,
    vendor_id,
    database,
    cases,
):
    """专属VENDOR需未设alias且分配root与import-only同团队拥有者；headers只留内存。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("代称快照专项只允许本轮独立MySQL夹具")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("活动连接不是本轮声明的独立MySQL库")
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_owner, root_team = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_vendor_alias WHERE tenant_id=%s AND vendor_id=%s",
            (tenant, vendor_id),
        )
        assert cursor.fetchone()[0] == 0, "须使用本轮独占且从未设置alias的VENDOR"
    caps = client.get("/api/v1/vendor-aliases/capabilities", headers=headers)
    assert caps.status_code == 200

    def change(alias):
        current = client.get("/api/v1/vendor-aliases/" + vendor_id, headers=headers)
        assert current.status_code == 200
        result = client.put(
            "/api/v1/vendor-aliases/" + vendor_id,
            headers=headers
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": '"' + str(current.json()["revision"]) + '"',
            },
            json={"alias": alias, "reason": "受控业务快照验收，非生产资料维护"},
        )
        assert result.status_code == 200
        return result.json()

    def create(identity, owner, team, key=None):
        capability = client.get("/api/v1/account-imports/capabilities", headers=identity)
        assert capability.status_code == 200
        return client.post(
            "/api/v1/account-imports",
            headers=identity
            | {
                "X-CSRF-Token": capability.json()["csrf_token"],
                "Idempotency-Key": key or "alias-snapshot-" + uuid4().hex,
            },
            json={
                "vendor_id": vendor_id,
                "owner_user_id": owner,
                "owner_team_id": team,
                "account_ids_text": "invalid-snapshot-token",
            },
        )

    def snapshot(identifier):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT alias,alias_revision,alias_source,vendor_name_snapshot "
                "FROM orbit_account_vendor_alias_snapshot WHERE tenant_id=%s "
                "AND resource_type='IMPORT' AND resource_id=%s ORDER BY resource_revision",
                (tenant, identifier),
            )
            return list(cursor.fetchall())

    first = create(headers, root_owner, root_team)
    assert first.status_code == 202
    initial = snapshot(first.json()["id"])
    assert len(initial) == 1 and initial[0][0:3] == (None, 1, "UNSET")
    cases.append(CASES[0])
    changed = False
    try:
        alias_a = change("快照代称甲")
        changed = True
        key = "alias-snapshot-replay-" + uuid4().hex
        accepted = create(headers, root_owner, root_team, key)
        assert accepted.status_code == 202
        frozen = snapshot(accepted.json()["id"])
        assert len(frozen) == 1 and frozen[0][:3] == (
            "快照代称甲",
            alias_a["revision"],
            "VENDOR_ALIAS",
        )
        query = {"vendor_id": vendor_id, "page_size": "20"}
        heads = {
            endpoint: client.get(endpoint, headers=headers, params=query)
            for endpoint in ("/api/v1/accounts", "/api/v1/accounts/extended")
        }
        assert all(
            result.status_code == 200 and result.json()["next_cursor"] for result in heads.values()
        ), "游标专项需该独占户商至少21个可见账户"
        alias_b = change("当前代称乙")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM orbit_ad_account WHERE tenant_id=%s AND vendor_id=%s LIMIT 1",
                (tenant, vendor_id),
            )
            account = cursor.fetchone()
        assert account, "当前显示验收需本轮已有真实本机绑定账户引用专属VENDOR"
        current = client.get("/api/v1/accounts/" + account[0], headers=headers)
        assert current.status_code == 200 and current.json()["vendor_alias"] == alias_b["alias"]
        extended = client.get("/api/v1/accounts/" + account[0] + "/details", headers=headers)
        assert (
            extended.status_code == 200
            and extended.json()["account"]["vendor_alias"] == current.json()["vendor_alias"]
        )
        for endpoint, result in heads.items():
            old_page = client.get(
                endpoint, headers=headers, params=query | {"cursor": result.json()["next_cursor"]}
            )
            assert old_page.status_code == 409
        assert snapshot(accepted.json()["id"]) == frozen and snapshot(first.json()["id"]) == initial
        cases.append(CASES[1])
        cases.append(CASES[5])
        replay = create(headers, root_owner, root_team, key)
        assert replay.status_code == 202 and replay.json()["id"] == accepted.json()["id"]
        assert snapshot(replay.json()["id"]) == frozen
        cases.append(CASES[2])
        only_headers = import_identity["headers"]
        assert client.get("/api/v1/accounts/extended", headers=only_headers).status_code == 403
        imported = create(
            only_headers, import_identity["owner_user_id"], import_identity["owner_team_id"]
        )
        assert imported.status_code == 202
        assert snapshot(imported.json()["id"])[0][:3] == (
            "当前代称乙",
            alias_b["revision"],
            "VENDOR_ALIAS",
        )
        cases.append(CASES[3])

        def state():
            values = []
            with admin.cursor() as cursor:
                for table in (
                    "orbit_account_import",
                    "orbit_account_import_row",
                    "orbit_account_idempotency",
                    "orbit_account_vendor_alias_snapshot",
                    "orbit_account_event",
                    "orbit_account_outbox",
                ):
                    cursor.execute("SELECT COUNT(*) FROM " + table)
                    values.append(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,)
                )
                values.append(cursor.fetchone()[0])
            return values

        for target in ("SNAPSHOT", "AUDIT"):
            before = state()
            with admin.cursor() as cursor:
                if target == "SNAPSHOT":
                    cursor.execute(
                        "CREATE TRIGGER account_alias_snapshot_fail BEFORE INSERT ON "
                        "orbit_account_vendor_alias_snapshot FOR EACH ROW "
                        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'"
                    )
                else:
                    cursor.execute(
                        "CREATE TRIGGER account_alias_snapshot_fail BEFORE INSERT ON "
                        "orbit_account_event FOR EACH ROW BEGIN "
                        "IF NEW.action='IMPORT_ACCEPTED' THEN "
                        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
                    )
            key = "alias-snapshot-rollback-" + uuid4().hex
            try:
                failed = create(headers, root_owner, root_team, key)
                assert failed.status_code == 503 and state() == before
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS account_alias_snapshot_fail")
            retried = create(headers, root_owner, root_team, key)
            assert retried.status_code == 202 and len(snapshot(retried.json()["id"])) == 1
        cases.append(CASES[4])
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_alias_snapshot_fail")
        if changed:
            change(None)
