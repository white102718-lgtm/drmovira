"""原指标字段UI独立夹具；真实UUID资料与无monitor读取的最小原计划角色。"""

import re
from uuid import uuid4

from metric_profile_query_checks import seed_metric_profile_browser_fixture

WRITER_ID = 940450001
WRITER_MENUS = (31000, 31020, 31021, 31022, 31023)


def prepare_launch_metric_browser_fixture(admin, database):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("指标字段浏览器只允许本轮13306独立UUID数据库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("指标字段浏览器实际数据库不符")
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (WRITER_ID,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM sys_role WHERE role_id=%s", (WRITER_ID,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT tenant_id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, team = cursor.fetchone()
        username = "metric_writer_" + uuid4().hex[:12]
        cursor.execute(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
            "VALUES(%s,'指标字段原计划浏览器夹具',%s,1,'1','0','0')",
            (WRITER_ID, username),
        )
        cursor.executemany(
            "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
            [(WRITER_ID, menu) for menu in WRITER_MENUS],
        )
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag) "
            "SELECT %s,%s,'指标字段浏览器人员',password,'0','0' FROM sys_user WHERE user_id=1",
            (WRITER_ID, username),
        )
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (WRITER_ID, str(uuid4())),
        )
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (WRITER_ID, WRITER_ID)
        )
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (WRITER_ID, tenant),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
            "display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,'指标字段浏览器人员',0,UTC_TIMESTAMP(3))",
            (tenant, str(uuid4()), WRITER_ID, team),
        )
    admin.commit()
    seeded = seed_metric_profile_browser_fixture(admin, database)
    assert len(seeded["ids"]) == 21
    return {"writer_username": username, "profile_id": seeded["ids"][0], "profile_count": 21}
