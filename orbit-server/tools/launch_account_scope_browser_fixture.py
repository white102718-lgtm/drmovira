"""账户范围浏览器样本：仅本轮UUID库，不作为账户导入或平台授权验收。"""

import re
from uuid import uuid4


def prepare_launch_account_scope_browser_fixture(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("账户范围浏览器样本只允许本轮13306 UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("账户范围样本数据库不一致")
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM orbit_ad_account WHERE tenant_id=%s", (tenant,))
        # 此函数只在全新launch浏览器库执行，拒绝给已有账户环境追加样本。
        if cursor.fetchone()[0] != 0:
            raise ValueError("范围样本要求全新隔离账户目录")
        groups = []
        for prefix, count in (("UI_SCOPE_OK_", 21), ("UI_SCOPE_OVER_", 501)):
            values = []
            for ordinal in range(count):
                identifier = str(uuid4())
                # 固定前缀只用于隔离列表筛选；长外部ID保留原字符串语义。
                name = f"{prefix}{ordinal:03d}"
                external = str(10**25 + len(groups) * 10000 + ordinal)
                values.append((tenant, identifier, external, name, name, owner, team))
            cursor.executemany(
                """INSERT INTO orbit_ad_account
                (tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,
                 timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','Asia/Shanghai','AUTHORIZED','ACTIVE',
                       '{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
                values,
            )
            groups.append({"prefix": prefix, "count": count})
    admin.commit()
    return {
        "scope": "内部账户只读样本，不证明账户导入、平台观察或写授权",
        "groups": [{"prefix": group["prefix"], "count": group["count"]} for group in groups],
    }
