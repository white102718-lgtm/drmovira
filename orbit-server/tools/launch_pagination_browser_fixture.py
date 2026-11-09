"""原列表真实分页浏览器数据；仅专属UUID库内部21条，不代表业务创建验收。"""

import re
from uuid import uuid4

from launch_draft_template_checks import draft


def prepare_launch_pagination_browser_fixture(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("分页浏览器夹具只允许当前13306/UUID库")
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_contract import parse_plan

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        for ordinal in range(21):
            identifier = str(uuid4())
            value = parse_plan(
                canonical(
                    draft({"id": owner, "team": team}) | {"name": f"UI_PAGE_PLAN_{ordinal:02d}"}
                ).encode()
            )
            payload = canonical(value)
            cursor.execute(
                "INSERT INTO orbit_launch_plan "
                "(tenant_id,id,owner_user_id,owner_team_id,channel_id,name,state,revision,"
                "payload_json,payload_hash,payload_bytes,account_count,asset_count,created_at,"
                "updated_at) VALUES(%s,%s,%s,%s,NULL,%s,'DRAFT',1,%s,%s,%s,0,0,"
                "'2026-01-02 12:00:00.000','2026-01-02 12:00:00.000')",
                (
                    tenant,
                    identifier,
                    owner,
                    team,
                    value["name"],
                    payload,
                    digest(value),
                    len(payload.encode()),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_launch_plan_version "
                "(tenant_id,plan_id,revision,payload_json,payload_hash,dependency_json,created_at,"
                "created_by) VALUES(%s,%s,1,%s,%s,'{}','2026-01-02 12:00:00.000',1)",
                (tenant, identifier, payload, digest(value)),
            )
            template_id = str(uuid4())
            template = {
                "name": f"UI_PAGE_TEMPLATE_{ordinal:02d}",
                "description": "内部分页夹具，非模板创建验收",
                "visibility": "PRIVATE",
                "recipient_user_ids": [],
                "campaigns": [],
                "ownership": {"owner_user_id": owner, "owner_team_id": team},
            }
            cursor.execute(
                "INSERT INTO orbit_launch_template "
                "(tenant_id,id,owner_user_id,owner_team_id,name,description,visibility,state,"
                "revision,config_json,config_hash,config_bytes,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,'PRIVATE','ACTIVE',1,'[]',%s,2,"
                "'2026-01-02 12:00:00.000','2026-01-02 12:00:00.000')",
                (
                    tenant,
                    template_id,
                    owner,
                    team,
                    template["name"],
                    template["description"],
                    digest([]),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_launch_template_version "
                "(tenant_id,template_id,revision,value_json,created_at,created_by) "
                "VALUES(%s,%s,1,%s,'2026-01-02 12:00:00.000',1)",
                (tenant, template_id, canonical(template)),
            )
    admin.commit()
    return {"plan_count": 21, "template_count": 21, "created_day_utc": "2026-01-02"}
