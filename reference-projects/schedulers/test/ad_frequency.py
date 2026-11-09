import logging

from facebook_business import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights

account = {
    "_id": "680dfbae4cdedb21b7c48437",
    "dev_id": "100073048846494",
    "app_id": "1593241295170213",
    "app_secret": "REDACTED_REFERENCE_SECRET",
    "access_token": "REDACTED_REFERENCE_SECRET",
    "ad_platform": "facebook",
    "status": 1,
    "agent_line": "ad1005",
    "game_platform": "okjkt",
    "placer_id": "ly",
    "app_name": None,
    "description": None,
    "proxy": "18.142.239.219",
}
# Enable HTTP debug logging to inspect raw responses
logging.basicConfig(level=logging.DEBUG)

# Initialize the API
api = FacebookAdsApi.init(
    app_id="1593241295170213",
    app_secret="REDACTED_REFERENCE_SECRET",
    access_token="REDACTED_REFERENCE_SECRET",
)
# Optionally enforce account's attribution setting
api.api_default_params = {"use_account_attribution_setting": True}

# Define the fields you want, using the AdsInsights.Field enum
fields = [
    AdsInsights.Field.campaign_name,
    AdsInsights.Field.adset_name,
    AdsInsights.Field.ad_name,
    AdsInsights.Field.impressions,
    AdsInsights.Field.reach,
    AdsInsights.Field.frequency,
    AdsInsights.Field.spend,
]

# Set up parameters: explicit time_range is more reliable than presest
params = {
    "time_range": {"since": "2025-04-22", "until": "2025-04-22"},
    "level": "ad",  # 'campaign', 'adset', or 'ad'
    "date_preset": None,  # unset if time_range is provided
    "time_increment": "all_days",
    "fields": ["date_start", "date_stop", "spend"],
    "time_zone": "Asia/Shanghai",  # 'breakdowns': ['age', 'gender'],  # remove if you get None metrics
}

# Fetch insights synchronously (is_async=False)
insights = AdAccount("act_679268331330516").get_insights(
    fields=fields, params=params, is_async=False
)

# Check if data was returned
if not insights:
    print("No insights data returned. Check date range, permissions, and ad delivery.")
else:
    for entry in insights:
        # Use .get() to safely retrieve each metric
        ad_name = entry.get(AdsInsights.Field.ad_name)
        impressions = entry.get(AdsInsights.Field.impressions)
        reach = entry.get(AdsInsights.Field.reach)
        frequency = entry.get(AdsInsights.Field.frequency)
        spend = entry.get(AdsInsights.Field.spend)

        print(
            f"Ad: {ad_name}\n"
            f"  Impressions: {impressions}\n"
            f"  Reach:       {reach}\n"
            f"  Frequency:   {frequency}\n"
            f"  Spend:       {spend}\n"
            "---------------------------"
        )
        break
