"""动作专属候选真实HTTP/MySQL协议；仅主线隔离库串行调用，不扩大生产权限。"""

import re
from uuid import uuid4

CASES = [
    "pythonAccountAssignmentOptionsActionsOnlyCurrentAccountScope",
    "pythonAccountAssignmentOptionsEnabledManagedOwnersActualKeysetPages",
    "pythonAccountAssignmentOptionsTargetVendorIntersectionAndRealAlias",
    "pythonAccountAssignmentOptionsForeignScopeAndStrictParametersDenied",
    "pythonAccountAssignmentOptionsCursorBindsSourceRevisionAndQuery",
]


def run_account_assignment_options_checks(
    client,
    admin,
    headers,
    owner_user_id,
    owner_team_id,
    vendor_id,
    target_identity,
    action_identity,
    database,
    cases,
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("分配候选专项只允许本轮独立MySQL夹具")
    native_ids = tuple(range(990200, 990222))
    marker = "分配候选-" + uuid4().hex[:12]
    foreign_team, foreign_owner = str(uuid4()), str(uuid4())
    members = [str(uuid4()) for _ in range(21)]
    account, foreign_account = str(uuid4()), str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id BETWEEN 990200 AND 990221")
        assert cursor.fetchone()[0] == 0, "候选夹具技术ID已占用，拒绝覆盖"
        cursor.execute(
            "INSERT INTO orbit_business_team"
            "(tenant_id,id,name,enabled,revision,created_at,updated_at) "
            "VALUES(%s,%s,%s,1,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, foreign_team, marker + "外团队"),
        )
        for index, native in enumerate(native_ids):
            owner = members[index] if index < 21 else foreign_owner
            team = owner_team_id if index < 21 else foreign_team
            name = marker + f"-{index:02}"
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (
                    native,
                    "options_" + uuid4().hex[:12],
                    name,
                    uuid4().hex[:16] + "@fixture.example.org",
                ),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (native, tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user"
                "(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
                "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team, name),
            )
        for identifier, owner, team in (
            (account, owner_user_id, owner_team_id),
            (foreign_account, foreign_owner, foreign_team),
        ):
            cursor.execute(
                "INSERT INTO orbit_ad_account "
                "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,"
                "timezone_id,auth_status,account_status,value_json,"
                "details_json,bound_at,created_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','Asia/Shanghai','AUTHORIZED','ACTIVE',"
                "'{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                (
                    tenant,
                    identifier,
                    str(10**23 + uuid4().int % 10**23),
                    marker,
                    marker,
                    owner,
                    team,
                ),
            )
    path = f"/api/v1/accounts/{account}/assignment-options"
    action_headers = action_identity["headers"]
    first = client.get(
        path, headers=action_headers, params={"kind": "OWNER", "q": marker, "page_size": "20"}
    )
    assert first.status_code == 200
    assert set(first.json()) == {"items", "next_cursor"}
    assert client.get("/api/v1/accounts/extended", headers=action_headers).status_code == 403
    assert (
        client.get("/api/v1/account-imports/capabilities", headers=action_headers).status_code
        == 403
    )
    cases.append(CASES[0])
    page = first.json()
    assert len(page["items"]) == 20 and page["next_cursor"]
    assert all(set(row) == {"id", "name", "team_id", "team_name"} for row in page["items"])
    second = client.get(
        path,
        headers=action_headers,
        params={"kind": "OWNER", "q": marker, "page_size": "20", "cursor": page["next_cursor"]},
    )
    assert (
        second.status_code == 200
        and len(second.json()["items"]) == 1
        and second.json()["next_cursor"] is None
    )
    identifiers = [row["id"] for row in page["items"] + second.json()["items"]]
    assert len(set(identifiers)) == 21 and set(identifiers) == set(members)
    # 当前停用人员立即消失，不能因候选游标把旧启用状态当作执行承诺。
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_user SET status='1' WHERE user_id=%s", (native_ids[0],))
    filtered = client.get(
        path, headers=action_headers, params={"kind": "OWNER", "q": marker, "page_size": "50"}
    )
    assert filtered.status_code == 200 and len(filtered.json()["items"]) == 20
    assert members[0] not in {item["id"] for item in filtered.json()["items"]}
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_user SET status='0' WHERE user_id=%s", (native_ids[0],))
    cases.append(CASES[1])
    vendors = client.get(
        path,
        headers=action_headers,
        params={"kind": "VENDOR", "owner_user_id": target_identity["owner_user_id"]},
    )
    assert vendors.status_code == 200
    selected = next(row for row in vendors.json()["items"] if row["id"] == vendor_id)
    actual = client.get("/api/v1/vendor-aliases/" + vendor_id, headers=headers)
    assert actual.status_code == 200 and selected["alias"] == actual.json()["alias"]
    assert set(selected) == {"id", "name", "alias"}
    # 新同团队人员没被分配此户商，应为空交集；不能仅凭同团队返回资料。
    no_link = client.get(
        path, headers=action_headers, params={"kind": "VENDOR", "owner_user_id": members[0]}
    )
    assert no_link.status_code == 200 and vendor_id not in {
        row["id"] for row in no_link.json()["items"]
    }
    cases.append(CASES[2])
    assert (
        client.get(
            f"/api/v1/accounts/{foreign_account}/assignment-options",
            headers=action_headers,
            params={"kind": "OWNER"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            path, headers=action_headers, params={"kind": "VENDOR", "owner_user_id": foreign_owner}
        ).status_code
        == 404
    )
    for params in (
        {"kind": "bad"},
        {"kind": "OWNER", "owner_user_id": owner_user_id},
        {"kind": "VENDOR"},
        {"kind": "OWNER", "page_size": "201"},
    ):
        assert client.get(path, headers=action_headers, params=params).status_code == 422
    assert client.get(path + "?kind=OWNER&kind=VENDOR", headers=action_headers).status_code == 400
    assert (
        client.get(
            path, headers=action_headers, params={"kind": "OWNER", "ignored": "1"}
        ).status_code
        == 400
    )
    cases.append(CASES[3])
    assert (
        client.get(
            path,
            headers=action_headers,
            params={
                "kind": "OWNER",
                "q": "different",
                "page_size": "20",
                "cursor": page["next_cursor"],
            },
        ).status_code
        == 409
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET revision=revision+1 WHERE tenant_id=%s AND id=%s",
            (tenant, account),
        )
    stale = client.get(
        path,
        headers=action_headers,
        params={"kind": "OWNER", "q": marker, "page_size": "20", "cursor": page["next_cursor"]},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "SCOPE_CHANGED"
    cases.append(CASES[4])
