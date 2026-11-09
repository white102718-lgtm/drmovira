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

# set_local_proxy()  # 注释掉，避免设置本地代理
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
  "update_time": "2025-12-18 07:30:25"
}
message = {
    **account,
    "date": "2025-10-21 10",
    "run_status": "SENDING",
    "create_time": "2025-05-06 10:01:00.007035",
    "review": False,
}


def _set_api():
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
    return me
ad_fields = [
    Ad.Field.id,
    Ad.Field.name,
    Ad.Field.adset_id,
    Ad.Field.adset,
    Ad.Field.campaign_id,
    Ad.Field.campaign,
    Ad.Field.created_time,
    Ad.Field.status,
    Ad.Field.effective_status,
    # 重点：添加嵌套查询，拉取素材的图片或视频缩略图链接
    "creative{id,image_url,thumbnail_url,name}",
]
me = _set_api()  # 注释掉，避免导入时执行
# xx=AdAccount('act_1262681728720213').api_get([
#     AdAccount.Field.id,
#     AdAccount.Field.name,
#     AdAccount.Field.account_status,
#     AdAccount.Field.created_time,
#     AdAccount.Field.timezone_name,
#     AdAccount.Field.spend_cap,  # 账户消耗限额,
#     AdAccount.Field.balance,  # 账户余额/欠款,
#     AdAccount.Field.timezone_name,
# ])
# get = Ad(120239004070600443).api_get(ad_fields)
# print(list(get))

def _get_ad_accounts():
    return me.get_ad_accounts(
        fields=["id", "name", "account_status", AdAccount.Field.timezone_name]
    )


account_fields = [
    AdAccount.Field.id,
    AdAccount.Field.name,
    AdAccount.Field.account_status,
    AdAccount.Field.created_time,
    AdAccount.Field.timezone_name,
]
campaign_fields = [
    Campaign.Field.name,
    Campaign.Field.status,
    Campaign.Field.effective_status,
    Campaign.Field.daily_budget,
    Campaign.Field.created_time,
]
# accounts = _get_ad_accounts()  # 注释掉，避免导入时执行

insights_params = {
    "level": "campaign",
    "time_range": {"since": "2025-10-21", "until": "2025-10-21"},
    "fields": [
        AdsInsights.Field.actions,
        AdsInsights.Field.action_values,
        AdsInsights.Field.conversions,
        AdsInsights.Field.conversion_values,
    ],
    "action_report_time": "conversion",  # 关键参数：按转化时间报告
    "filtering": [
        {
            "field": "campaign.effective_status",
            "operator": "IN",
            "value": ["ACTIVE", "PAUSED", "DELETED", "ARCHIVED"],
        }
    ],
}
campaign_insights_params = {
    "level": "campaign",
    "time_range": {"since": "2025-10-21", "until": "2025-10-21"},
    "fields": [
        AdsInsights.Field.campaign_id,
        AdsInsights.Field.campaign_name,
        AdsInsights.Field.actions,
    ],
}
# sets = Campaign(fbid="120233949035440390").get_ad_sets(fields={"name", "id"})
# xxx = list(Campaign(fbid="120235046690690524").get_insights(params=insights_params))
# AdSet(fbid='120226873880990635')

# # 使用迭代器方式，捕获单个账户的异常并跳过（已注释）
# accounts_iterator = iter(accounts)
# account_count = 0
# blocked_count = 0
#
# print("开始处理账户...\n")
#
# while True:
#     try:
#         accountA = next(accounts_iterator)
#         a = accountA[AdAccount.Field.id]
#         print(f"✓ {a}")
#         account_count += 1

#         # if accountA["name"] != "QQ006-RX16-0905+7-018":
#         #     continue
#         # account.api_get(fields=account_fields)
#         # campaigns = accountA.get_campaigns(campaign_insights_params)
#         # ad_sets = account.get_ad_sets(fields={"name", "id"})
#         # print(accountA[AdAccount.Field.name], accountA[AdAccount.Field.timezone_name])
#         # campaigns = accountA.get_insights(params=campaign_insights_params)
#         # l = list(campaigns)
#         # for c_info in l:
#         #     id_, name = (
#         #         c_info[AdsInsights.Field.campaign_id],
#         #         c_info[AdsInsights.Field.campaign_name],
#         #     )
#
#     except StopIteration:
#         # 迭代结束
#         print(f"\n✅ 总共成功处理 {account_count} 个账户")
#         if blocked_count > 0:
#             print(f"⚠️ 跳过 {blocked_count} 个有问题的账户")
#         break
#     except Exception as e:
#         # 某个账户报错，记录并跳过
#         blocked_count += 1
#         error_msg = str(e)
#         if "too many calls" in error_msg.lower():
#             print(f"⚠️ 账户达到速率限制，跳过: {error_msg[:100]}")
#         else:
#             print(f"⚠️ 账户错误，跳过: {error_msg[:100]}")
#         continue  # 跳过这个账户，继续下一个
#     print(account_count,blocked_count)
#         #     if name != "yyl_ktrkoo1_ET88_091601_apch":
#         #         continue
#         # campaign = Campaign(fbid=id_).api_get(fields=campaign_fields)
#         # print(campaign)
#     #     insights_params["level"] = AdsInsights.Level.adset
#     #     campaign.get_insights(params=insights_params)

def test(account_id="act_827825373560889", dev_config=None): # 100025262451548  act_643830688447951
    """
    测试获取账户信息 - 只调用 fb_account_consumer 中的账户获取部分

    :param account_id: 广告账户ID，格式为 "act_xxxxx"
    :param dev_config: 开发者配置，包含 app_id, app_secret, access_token, proxy(可选)
    """
    # 1. 初始化 API（使用自定义配置或默认配置）
    if dev_config:
        proxy = dev_config["proxy"]
        proxy_url = f"socks5://SilverDragon91:REDACTED_REFERENCE_SECRET@{proxy}:3129" if proxy else None
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        session = FacebookSession(
            dev_config["app_id"],
            dev_config["app_secret"],
            dev_config["access_token"],
            proxies=proxies
        )
        api = FacebookAdsApi(session)
        FacebookAdsApi.set_default_api(api)
    else:
        _set_api()


    # 2. 定义账户字段（所有可用字段 - 共70个）
    account_fields = [
        # === 基本信息 ===
        AdAccount.Field.id,                              # 账户ID（含act_前缀）
        AdAccount.Field.account_id,                      # 账户ID（无前缀）
        AdAccount.Field.name,                            # 账户名称
        AdAccount.Field.account_status,                  # 账户状态: 1=活跃, 2=禁用, 3=未结算, 7=待审核, 8=临时不可用, 9=待审批, 101=关闭
        AdAccount.Field.disable_reason,                  # 禁用原因
        AdAccount.Field.created_time,                    # 创建时间
        AdAccount.Field.age,                             # 账户年龄（天）

        # === 时区与货币 ===
        AdAccount.Field.timezone_name,                   # 时区名称
        AdAccount.Field.timezone_id,                     # 时区ID
        AdAccount.Field.timezone_offset_hours_utc,       # UTC偏移小时数
        AdAccount.Field.currency,                        # 货币

        # === 预算与消耗 ===
        AdAccount.Field.spend_cap,                       # 账户消耗限额
        AdAccount.Field.amount_spent,                    # 已消耗金额
        AdAccount.Field.balance,                         # 账户余额/欠款
        AdAccount.Field.min_campaign_group_spend_cap,    # 最小系列消耗上限
        AdAccount.Field.min_daily_budget,                # 最小日预算

    ]

    # 3. 获取账户信息
    account_info = AdAccount(account_id).api_get(fields=account_fields)

    # 4. 打印所有字段
    print("=" * 80)
    print("AdAccount 信息")
    print("=" * 80)
    for key, value in account_info.items():
        print(f"  {key}: {value}")
    print("=" * 80)

    return account_info


if __name__ == "__main__":

    # 示例2: 使用自定义开发者配置
    custom_dev = {
        "app_id": "818855530763411",
        "app_secret": "REDACTED_REFERENCE_SECRET",
        "access_token": "REDACTED_REFERENCE_SECRET",
        # "proxy": "13.250.117.58",  # 可选
    }
    test(account_id="act_827825373560889", dev_config=custom_dev)

