import datetime

from conf.log_conf import init
from db.clients import mysql_client
from tasks.nouse.ad_sync.ad_sync import consumer_process, ProducerMethod
from utils.common import HourFormat


def t():
    account = {
        "_id": "68d520a3467f5415cc2a064d",
        "dev_id": "100092304260484",
        "app_id": "803924698951152",
        "app_secret": "REDACTED_REFERENCE_SECRET",
        "access_token": "REDACTED_REFERENCE_SECRET",
        "ad_platform": "facebook",
        "status": 1,
        "agent_lines": ["pkrk002", "pkrk005"],
        "placer_id": "alan01",
        "placement_team": "all",
        "app_name": "",
        "description": "",
        "proxy": "54.251.209.137",
        "update_time": "2025-10-17 16:44:15",
    }
    data = {
        **account,
        "review": False,
        "plat_map": {al: "aaa" for al in account["agent_lines"]},
        "department": "break",
        "date": "2025-10-17 18",
        "run_status": "SENDING",
        "create_time": "2025-04-22 10:01:00.007035",
    }
    # start_task(data)
    consumer_process(data)


def t_personnal():
    account = {
        "_id": "1957302861819964",
        "access_token": "REDACTED_REFERENCE_SECRET",
        "app_id": "1439113601068063",
        "app_secret": "REDACTED_REFERENCE_SECRET",
        "type": ProducerMethod.PERSONAL_PRODUCER.value,
    }

    data = {
        **account,
        "review": False,
        "plat_map": {al: "aaa" for al in ["pkrk002", "pkrk005"]},
        "department": "break",
        "date": "2026-04-01 12",
        "run_status": "SENDING",
        "create_time": "2025-04-22 10:01:00.007035",
    }
    # start_task(data)
    consumer_process(data)


def t1():
    account = {
        "_id": "6854fc015e777abb8e85fe0a",
        "access_token": "REDACTED_REFERENCE_SECRET",
        "ad_platform": "facebook",
        "agent_line": "ad1026",
        "agent_lines": ["vbbb"],
        "app_id": "1184384005874501",
        "app_name": "xxx",
        "app_secret": "REDACTED_REFERENCE_SECRET",
        "create_time": "2025-06-20 06:13:21.418707",
        "date": "2025-06-20 14",
        "dev_id": "61553969196597",
        "dev_mongo_id": "67f517a38f392449644fa3c8",
        "game_platform": "okjkt",
        "placer_id": "rtt",
        "plat_map": {"fb007": "sw", "fb07": "sw", "xcvx": "sw"},
        "review": False,
        "run_status": "SENDING",
        "status": 1,
    }
    account["dev_mongo_id"] = account["_id"]
    data = {
        **account,
        "date": "2025-06-20 20",
        "run_status": "SENDING",
        "create_time": "2025-06-04 10:01:00.007035",
        "review": True,
    }
    # start_task(data)
    consumer_process(data)


def t2():
    insights = (
        Ad("120222460412830122")
        .api_get(
            fields=self.ad_fields,
        )
        .get_insights(
            fields=self.insights_fields,
            params=construct_insights_params(level, self.message["day"]),
        )
    )


def t3():
    result = {
        "account_id": "act_1193412079167052",
        "account_name": "10ET011-0402-73",
        "ad_id": "120225094133610361",
        "ad_name": "Pb8627de5",
        "ad_platform": "facebook",
        "ad_set_id": "120224673108410361",
        "ad_set_name": "set-e567a8",
        "adset_budget": None,
        "agent_line": "ad1005",
        "amount_spent": 50.77,
        "app_installs": 0,
        "budget": 16000,
        "cam_budget": 16000,
        "campaign_id": "120224673108350361",
        "campaign_name": "LY_ad1005_ET1073_0509_apch",
        "china_date": "2025-05-12 21",
        "clicks_all": "99",
        "clicks_unique": "94",
        "complete_registration": "5",
        "cpc": "0.512828",
        "cpm": "9.810628",
        "create_time": datetime.datetime(
            2025, 5, 11, 11, 37, 43, tzinfo=datetime.timezone.utc
        ),
        "ctr": "1.913043",
        "date": "2025-05-12 00",
        "delivery": 1,
        "delivery_str": "ACTIVE",
        "dev_id": "100073048846494",
        "fetch_time": datetime.datetime(
            2025, 5, 12, 10, 48, 59, 111111, tzinfo=datetime.timezone.utc
        ),
        "frequency": "1.179084",
        "game_platform": "okjkt",
        "impressions": "5175",
        "inline_link_click_ctr": "1.410628",
        "inline_link_clicks": "73",
        "lead": "8",
        "level": "ad",
        "package_name": "",
        "placer_id": "ly",
        "purchases": "1",
        "purchases_value": "1.2",
        "reach": "4389",
        "subscribe_website": 0,
        "subscribe_website_values": 0,
        "timezone_name": "Asia/Bangkok",
        "unique_inline_link_click_ctr": "1.549328",
        "unique_inline_link_clicks": "68",
    }
    result["level"] = "account"
    write_data = construct_sql_data(result)
    hour_sql = f"INSERT INTO ad_hourly_detail ({', '.join(write_data.keys())}) VALUES ({', '.join(write_data.values())})"
    mysql_client.execute(hour_sql)
    if result["date"].endswith("00"):
        result["date"] = datetime.datetime.strptime(
            result["date"], HourFormat
        ) - datetime.timedelta(days=1)
        write_data = construct_sql_data(result)


if __name__ == "__main__":
    init()
    t_personnal()
