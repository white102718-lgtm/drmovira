import json
import time

import requests
from facebook_business import FacebookSession
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.user import User
from facebook_business.api import FacebookAdsApi

from utils.common import set_local_proxy

set_local_proxy()
account = {
    "_id": "694385c1dd4159f9be218043",
    "dev_id": "61577630318771",
    "app_id": "1156297120038785",
    "app_secret": "REDACTED_REFERENCE_SECRET",
    "access_token": "REDACTED_REFERENCE_SECRET",
    "ad_platform": "facebook",
    "status": 1,
    "agent_lines": [],
    "placer_id": "ly",
    "proxy": "13.250.117.58",
    "update_time": "2025-12-18 07:30:25",
}
message = {
    **account,
    "date": "2025-10-21 10",
    "run_status": "SENDING",
    "create_time": "2025-05-06 10:01:00.007035",
    "review": False,
}


proxy = message["proxy"]
proxy = f"socks5://SilverDragon91:REDACTED_REFERENCE_SECRET@{proxy}:3129"
proxies = {"http": proxy, "https": proxy} if proxy else None
session = FacebookSession(
    message["app_id"],
    message["app_secret"],
    message["access_token"],
    proxies=proxies,
)
api = FacebookAdsApi(session)
FacebookAdsApi.set_default_api(api)
me = User(fbid="me", api=api)

# 用于存储所有账户数据
all_accounts = []
page_count = 0
after_cursor = None

# 循环获取所有分页数据
while True:
    page_count += 1

    # 创建新的 batch 对象（每一页都需要新的 batch）
    batch = api.new_batch()

    # 用于存储当前页结果的容器
    result_container = {"data": None, "paging": None, "error": None}

    # 定义成功回调
    def success_callback(response):
        # response 是 FacebookResponse 对象，使用 json() 方法获取数据
        data = response.json()
        # 提取 data 字段中的账户列表
        result_container["data"] = data.get("data", [])
        result_container["paging"] = data.get("paging", {})
        print(
            f"Batch 成功获取第 {page_count} 页: {len(result_container['data'])} 个账户"
        )

    # 定义失败回调
    def failure_callback(response):
        result_container["error"] = response.json()["error"]
        print(f"Batch 获取账户失败: {result_container['error']}")
        usage = next(
            (
                item["value"]
                for item in response.headers()
                if item.get("name") == "X-Business-Use-Case-Usage"
            ),
            None,
        )
        if usage:
            loads = json.loads(usage)
            _, v = next(iter(loads.items()))
            time.sleep(v[0]["estimated_time_to_regain_access"] * 60)

    # 构建请求参数
    params = {"limit": 25}
    if after_cursor:
        params["after"] = after_cursor
        print(f"获取第 {page_count} 页，cursor: {after_cursor[:25]}...")

    me.get_ad_accounts(
        fields=[AdAccount.Field.id],
        params=params,
        batch=batch,
        success=success_callback,
        failure=failure_callback,
    )

    # 执行 batch
    batch.execute()

    # 检查错误
    if result_container["error"]:
        page_count-=1
        continue

    if result_container["data"] is None:
        print("Batch 执行完成但未获取到账户数据")
        continue

    # 累加本页数据
    all_accounts.extend([x["id"] for x in result_container["data"]])

    # 检查是否有下一页
    paging = result_container["paging"]
    if paging and "cursors" in paging and "after" in paging["cursors"]:
        after_cursor = paging["cursors"]["after"]
    else:
        # 没有下一页，退出循环
        break
print(all_accounts)
print(len(all_accounts))
pass
