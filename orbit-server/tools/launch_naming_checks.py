"""命名真实HTTP/MySQL独立专项；仅主线隔离UUID数据库串行执行。"""

import re
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from launch_draft_template_checks import assert_status, draft, tree

LAUNCH_NAMING_CASES = [
    "pythonLaunchNamingOriginalEmptyBodyContractAndRealExpandedSlots",
    "pythonLaunchNamingSameIntentDifferentKeysReuseImmutableReservation",
    "pythonLaunchNamingConcurrentPlansOccupyDisjointSequenceRanges",
    "pythonLaunchNamingCurrentNicknameFallbackInvalidatesOldKeyWithoutRewritingHistory",
    "pythonLaunchNamingPersistedPriorShanghaiDateCannotReplayAsCurrentPreview",
    "pythonLaunchNamingAuditFailureRollsBackCounterNamesClockAndKey",
    "pythonLaunchNamingDisabledChannelAndRevokedActionBlockSuccessfulReplay",
    "pythonLaunchNamingForeignTenantAndMissingSourcesNeverConsumeSequence",
    "pythonLaunchNamingStatusCASHeadReusesActualSourceReservationWithoutNewSequence",
]


def run_launch_naming_checks(client, admin, headers, fixture, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute("SELECT nick_name FROM sys_user WHERE user_id=1")
        previous_nickname = cursor.fetchone()[0]
        cursor.execute(
            "SELECT display_name FROM orbit_business_user WHERE tenant_id=%s AND id=%s",
            (tenant, owner),
        )
        previous_name = cursor.fetchone()[0]

    def head(revision=None, key=None):
        caps = assert_status(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return (
            headers
            | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": key or str(uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision is not None else {})
        )

    def reference(kind, **extra):
        caps = assert_status(
            client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers), 200
        )
        value = {
            "kind": kind,
            "id": str(uuid4()),
            "name": "命名专项来源",
            "availability": "AVAILABLE",
            "owner_team_id": team,
            "data_owner_user_ids": [owner],
            "source_key": "naming-" + uuid4().hex,
        } | extra
        preview = assert_status(
            client.post(
                "/api/v1/reference-catalog-imports",
                headers=head(),
                json={
                    "kind": kind,
                    "source": "命名专项隔离fixture",
                    "reason": "真实来源预检",
                    "base_catalog_revision": caps["catalog_revision"],
                    "items": [value],
                },
            ),
            201,
        )
        assert preview["state"] == "VALIDATED"
        assert_status(
            client.post(
                f"/api/v1/reference-catalog-imports/{preview['id']}/commit",
                headers=head(preview["revision"]),
            ),
            200,
        )
        return value

    agent = reference("BUSINESS_AGENT")
    product = reference("PRODUCT", allowed_agent_ids=[agent["id"]])
    channel_body = {
        "ownership": {"owner_team_id": team, "data_owner_user_ids": [owner]},
        "code": "NAMING_" + uuid4().hex,
        "name": "真实命名渠道",
        "product_id": product["id"],
        "agent_id": agent["id"],
        "type": "WEBSITE",
        "media": "META",
        "url": "https://example.com/naming",
        "status": "ENABLED",
    }
    channel = assert_status(client.post("/api/v1/channels", headers=head(), json=channel_body), 201)
    accounts = [str(uuid4()), str(uuid4())]
    with admin.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO orbit_ad_account
        (tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,
        timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at)
        VALUES(%s,%s,%s,'命名账户','命名账户',%s,%s,'USD','Asia/Shanghai','AUTHORIZED','ACTIVE',
        '{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
            [
                (tenant, identifier, str(10**25 + uuid4().int % 10**25), owner, team)
                for identifier in accounts
            ],
        )
        cursor.execute("UPDATE sys_user SET nick_name='命名昵称' WHERE user_id=1")
        cursor.execute(
            "UPDATE orbit_business_user SET display_name='真实姓名' WHERE tenant_id=%s AND id=%s",
            (tenant, owner),
        )

    def create(**changes):
        body = (
            draft({"id": owner, "team": team})
            | {"account_ids": accounts, "channel_id": channel["id"], "campaigns": tree()}
            | changes
        )
        return assert_status(client.post("/api/v1/launch-plans", headers=head(), json=body), 201)

    def reserve(plan, write=None):
        return client.post(
            f"/api/v1/launch-plans/{plan['id']}/campaign-names",
            headers=write or head(plan["revision"]),
        )

    def naming_snapshot():
        with admin.cursor() as cursor:
            result = []
            for table in (
                "orbit_launch_name_sequence",
                "orbit_launch_name_reservation",
                "orbit_launch_name_item",
                "orbit_launch_clock",
                "orbit_launch_idempotency",
                "orbit_launch_event",
                "orbit_launch_outbox",
            ):
                cursor.execute("SELECT * FROM " + table)
                result.append(tuple(sorted(cursor.fetchall(), key=repr)))
            return tuple(result)

    try:
        first = create()
        path = f"/api/v1/launch-plans/{first['id']}/campaign-names"
        invalid = client.post(path, headers=head(first["revision"]), json={})
        assert invalid.status_code == 400
        assert client.post(path, headers=head()).status_code == 400
        key = head(first["revision"])
        original = assert_status(reserve(first, key), 200)
        assert set(original) == {"id", "plan_revision", "naming_date", "items"}
        assert (
            len(original["items"]) == 4 and len({row["slot_key"] for row in original["items"]}) == 4
        )
        assert all(set(row) == {"slot_key", "name", "sequence"} for row in original["items"])
        assert [row["sequence"] for row in original["items"]] == ["1", "2", "3", "4"]
        assert all(row["name"].startswith("真实命名渠道_命名昵称_") for row in original["items"])
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,revision FROM orbit_launch_plan WHERE tenant_id=%s AND id=%s",
                (tenant, first["id"]),
            )
            assert cursor.fetchone() == ("DRAFT", first["revision"])
        cases.append(LAUNCH_NAMING_CASES[0])

        assert assert_status(reserve(first, key), 200) == original
        assert assert_status(reserve(first), 200) == original
        uppercase_path = f"/api/v1/launch-plans/{first['id'].upper()}/campaign-names"
        assert assert_status(client.post(uppercase_path, headers=key), 200) == original
        assert (
            assert_status(client.post(uppercase_path, headers=head(first["revision"])), 200)
            == original
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_launch_name_reservation "
                "WHERE tenant_id=%s AND plan_id=%s",
                (tenant, first["id"]),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT last_sequence FROM orbit_launch_name_sequence "
                "WHERE tenant_id=%s AND channel_id=%s",
                (tenant, channel["id"]),
            )
            assert int(cursor.fetchone()[0]) == 4
        cases.append(LAUNCH_NAMING_CASES[1])

        concurrent = [create(), create()]
        writes = [head(plan["revision"]) for plan in concurrent]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(reserve, plan, write)
                for plan, write in zip(concurrent, writes, strict=True)
            ]
            results = [assert_status(future.result(), 200) for future in futures]
        assert len({row["sequence"] for result in results for row in result["items"]}) == 8
        assert {int(row["sequence"]) for result in results for row in result["items"]} == set(
            range(5, 13)
        )
        cases.append(LAUNCH_NAMING_CASES[2])

        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_user SET nick_name='' WHERE user_id=1")
        assert reserve(first, key).status_code == 409
        fallback_key = head(first["revision"])
        fallback = assert_status(reserve(first, fallback_key), 200)
        assert fallback["id"] != original["id"]
        assert all(row["name"].startswith("真实命名渠道_真实姓名_") for row in fallback["items"])
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM orbit_launch_name_item "
                "WHERE tenant_id=%s AND reservation_id=%s ORDER BY ordinal",
                (tenant, original["id"]),
            )
            assert [row[0] for row in cursor.fetchall()] == [
                row["name"] for row in original["items"]
            ]
        cases.append(LAUNCH_NAMING_CASES[3])

        # 构造隔离历史记录日期，验证真实HTTP不把上一项目日旧键当成当前预览。
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_name_reservation "
                "SET naming_date=DATE_SUB(naming_date,INTERVAL 1 DAY) WHERE tenant_id=%s AND id=%s",
                (tenant, fallback["id"]),
            )
        stale = reserve(first, fallback_key)
        assert stale.status_code == 409 and stale.json()["code"] == "NAMING_PREVIEW_STALE"
        current_day = assert_status(reserve(first), 200)
        assert (
            current_day["id"] != fallback["id"]
            and current_day["naming_date"] == original["naming_date"]
        )
        cases.append(LAUNCH_NAMING_CASES[4])

        atomic = create()
        failed_key = head(atomic["revision"])
        before = naming_snapshot()
        with admin.cursor() as cursor:
            cursor.execute("""CREATE TRIGGER fixture_launch_naming_failure
            BEFORE INSERT ON orbit_launch_event
            FOR EACH ROW BEGIN IF NEW.action='plan.naming' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated naming audit fixture';
            END IF; END""")
        try:
            assert reserve(atomic, failed_key).status_code == 503
            assert naming_snapshot() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER fixture_launch_naming_failure")
        assert_status(reserve(atomic, failed_key), 200)
        cases.append(LAUNCH_NAMING_CASES[5])

        disabled = assert_status(
            client.put(
                f"/api/v1/channels/{channel['id']}",
                headers=head(channel["revision"]),
                json=channel_body | {"status": "DISABLED"},
            ),
            200,
        )
        assert reserve(first, key).status_code == 422
        assert_status(
            client.put(
                f"/api/v1/channels/{channel['id']}",
                headers=head(disabled["revision"]),
                json=channel_body,
            ),
            200,
        )
        valid = assert_status(reserve(first), 200)
        valid_key = head(first["revision"])
        assert assert_status(reserve(first, valid_key), 200) == valid
        with admin.cursor() as cursor:
            cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31023")
            action_status = cursor.fetchone()[0]
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31023")
        try:
            assert reserve(first, valid_key).status_code == 403
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_menu SET status=%s WHERE menu_id=31023", (action_status,)
                )
        cases.append(LAUNCH_NAMING_CASES[6])

        missing = create(account_ids=[], channel_id=None)
        before = naming_snapshot()
        assert reserve(missing).status_code == 422
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
                (tenant,),
            )
            foreign_tenant, foreign_owner, foreign_team = cursor.fetchone()
            foreign_id = str(uuid4())
            cursor.execute(
                """INSERT INTO orbit_launch_plan
            (tenant_id,id,owner_user_id,owner_team_id,channel_id,name,state,revision,payload_json,payload_hash,
            payload_bytes,account_count,asset_count,created_at,updated_at)
            SELECT %s,%s,%s,%s,NULL,name,state,revision,payload_json,payload_hash,
            payload_bytes,account_count,asset_count,created_at,updated_at
            FROM orbit_launch_plan WHERE tenant_id=%s AND id=%s""",
                (foreign_tenant, foreign_id, foreign_owner, foreign_team, tenant, missing["id"]),
            )
        assert (
            client.post(
                f"/api/v1/launch-plans/{foreign_id}/campaign-names", headers=head(1)
            ).status_code
            == 404
        )
        assert naming_snapshot() == before
        cases.append(LAUNCH_NAMING_CASES[7])
        # 这里只用SQL模拟已发生的纯状态CAS，不把它当validate接口验收。
        # 真正被测的是同一配置源在head变化后的原命名HTTP及零新增占号。
        anchored = create()
        anchor_key = head(anchored["revision"])
        anchor_names = assert_status(reserve(anchored, anchor_key), 200)
        before = naming_snapshot()
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_plan SET state='VALIDATED',revision=revision+1 "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, anchored["id"]),
            )
        try:
            assert assert_status(reserve(anchored, anchor_key), 200) == anchor_names
            assert reserve(anchored).status_code == 409  # 新键旧CAS不能消耗序号。
            state_head = anchored | {"revision": anchored["revision"] + 1}
            refreshed = assert_status(reserve(state_head), 200)
            assert refreshed == anchor_names
            assert refreshed["plan_revision"] == anchored["revision"]
            after = naming_snapshot()
            assert after[:4] == before[:4] and after[5:] == before[5:]
            assert len(after[4]) == len(before[4]) + 1  # 新键仅登记原结果，不占新序号。
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(revision) FROM orbit_launch_plan_version "
                    "WHERE tenant_id=%s AND plan_id=%s",
                    (tenant, anchored["id"]),
                )
                assert cursor.fetchone()[0] == anchored["revision"]
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_launch_plan SET state='DRAFT',revision=%s "
                    "WHERE tenant_id=%s AND id=%s",
                    (anchored["revision"], tenant, anchored["id"]),
                )
        cases.append(LAUNCH_NAMING_CASES[8])
        return {
            "plan_id": first["id"],
            "reservation_id": original["id"],
            "case_count": len(LAUNCH_NAMING_CASES),
        }
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_user SET nick_name=%s WHERE user_id=1", (previous_nickname,))
            cursor.execute(
                "UPDATE orbit_business_user SET display_name=%s WHERE tenant_id=%s AND id=%s",
                (previous_name, tenant, owner),
            )
