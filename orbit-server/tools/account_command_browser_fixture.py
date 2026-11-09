"""状态页专属隔离前置；受控来源只是入队条件，不是实际Meta验证证明。"""

import json
import re
from uuid import uuid4


def prepare_account_command_browser(admin, database, cipher):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("状态浏览器只允许本轮UUID隔离数据库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id FROM orbit_business_user WHERE user_id=1")
        tenant, owner = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_system_configuration WHERE tenant_id=%s "
            "AND section='META_BM' AND enabled=1 AND verification_status='READ_VERIFIED'",
            (tenant,),
        )
        assert cursor.fetchone()[0] == 0, "不得静默停用或替换其他受测来源"
        source = str(uuid4())
        cursor.execute(
            "INSERT INTO orbit_system_configuration "
            "(id,tenant_id,section,name,enabled,revision,settings_json,secrets_json,"
            "verification_status) VALUES(%s,%s,'META_BM',%s,1,1,%s,%s,'READ_VERIFIED')",
            (
                source,
                tenant,
                "仅本地命令入队前置-" + source,
                json.dumps({"businessId": "42", "graphVersion": "v25.0"}),
                json.dumps(
                    {
                        "accessToken": cipher.encrypt(
                            "fixture-not-a-platform-token", tenant, source, "accessToken"
                        )
                    }
                ),
            ),
        )
        cursor.execute(
            "SELECT id,synced_at FROM orbit_ad_account WHERE tenant_id=%s "
            "AND owner_user_id=%s AND name_prefix LIKE '详情受控-%%' "
            "AND unbound_at IS NULL ORDER BY id LIMIT 3",
            (tenant, owner),
        )
        accounts = cursor.fetchall()
        assert len(accounts) == 3
        for identifier, _synced in accounts:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_account_command WHERE tenant_id=%s "
                "AND account_id=%s AND active_kind IS NOT NULL",
                (tenant, identifier),
            )
            assert cursor.fetchone()[0] == 0
    admin.commit()
    return {"tenant": tenant, "source": source, "accounts": accounts}


def verify_account_command_browser(admin, prepared, project=None):
    """实际SQL核对只受理而未被执行；不把浏览器网络监听当后端平台计数。"""
    with admin.cursor() as cursor:
        for index, (identifier, synced) in enumerate(prepared["accounts"]):
            if project and ["desktop-1440", "wide-1920", "mobile-390"][index] != project:
                continue
            cursor.execute(
                "SELECT state,attempt_count,claimed_at,source_config_id,last_error_code "
                "FROM orbit_account_command WHERE tenant_id=%s AND account_id=%s AND kind='SYNC'",
                (prepared["tenant"], identifier),
            )
            assert cursor.fetchall() == (
                (
                    "WAITING_EXECUTOR",
                    0,
                    None,
                    prepared["source"],
                    "ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED",
                ),
            )
            cursor.execute(
                "SELECT synced_at FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                (prepared["tenant"], identifier),
            )
            assert cursor.fetchone()[0] == synced
    admin.commit()
