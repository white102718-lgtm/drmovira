import os
import sys
import json
import time
from datetime import datetime
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.ad import Ad

from utils.common import set_local_proxy
from model_type_defs.fb_type import FacebookAdConfig


DEV_CONFIG = {
    "app_id": "1156297120038785",
    "app_secret": "REDACTED_REFERENCE_SECRET",
    "access_token": "REDACTED_REFERENCE_SECRET",
}



class AdPublisher:
    def __init__(self, config, data):
        self.app_id = config["app_id"]
        self.app_secret = config["app_secret"]
        self.access_token = config["access_token"]
        self.proxy = config["proxy"]
        self._init_api()
        self.data = data

    def _init_api(self):
        FacebookAdsApi.init(self.app_id, self.app_secret, self.access_token)

    def publish_from_config(self):
        account_ids = self.data.get("account_ids", [])
        for account_id in account_ids:
            print(f"--- Processing Account: {account_id} ---")
            account = AdAccount(account_id)
            campaigns_data = self.data.get("campaigns", [])

            for camp_cfg in campaigns_data:
                self._process_campaign(account, camp_cfg)

    def upload_image(self, account, image_path):
        if not os.path.exists(image_path):
            print(f"Error: Image not found at {image_path}")
            return None

        image = account.create_ad_image(params={"filename": image_path})
        return image[AdImage.Field.hash]

    def _process_campaign(self, account, camp_cfg):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        camp_params = camp_cfg.copy()
        adsets_data = camp_params.pop("adsets", [])

        if "name" in camp_params:
            camp_params["name"] = f"{camp_params['name']}_{timestamp}"

        campaign = account.create_campaign(params=camp_params)
        print(f"Created Campaign: {camp_params['name']} (ID: {campaign['id']})")

        for adset_cfg in adsets_data:
            self._process_adset(account, campaign, adset_cfg)

    def _process_adset(self, account, campaign, adset_cfg):
        timestamp = datetime.now().strftime("%H%M%S")
        as_params = adset_cfg.copy()
        ads_data = as_params.pop("ads", [])

        as_params["name"] = f"{as_params['name']}_{timestamp}"
        as_params["campaign_id"] = campaign["id"]

        ad_set = account.create_ad_set(params=as_params)
        print(f"  Created Ad Set: {as_params['name']} (ID: {ad_set['id']})")

        for ad_cfg in ads_data:
            self._process_ad(account, ad_set, ad_cfg)

    def _process_ad(self, account, ad_set, ad_cfg):
        ad_params = ad_cfg.copy()
        creative_cfg = ad_params.pop("creative", {})
        page_id = ad_params.pop("page_id", None)
        link_url = ad_params.pop("link_url", None)

        image_hash = None
        creative_type = creative_cfg.pop("type", None)
        if creative_type == "image":
            image_path = creative_cfg.pop("path", None)
            if image_path:
                image_hash = self.upload_image(account, image_path)
                if not image_hash:
                    print("    Skipping ad due to missing image hash")
                    return

        creative_params = {
            "name": f"Creative_{datetime.now().timestamp()}",
            "object_story_spec": {
                "page_id": page_id,
                "link_data": {
                    "link": link_url,
                    "message": creative_cfg.get("body"),
                    "name": creative_cfg.get("title"),
                    "call_to_action": {"type": "LEARN_MORE"},
                },
            },
        }

        if image_hash:
            creative_params["object_story_spec"]["link_data"]["image_hash"] = image_hash

        creative = account.create_ad_creative(params=creative_params)

        ad_params["adset_id"] = ad_set["id"]
        ad_params["creative"] = {"creative_id": creative["id"]}

        ad = account.create_ad(params=ad_params)
        print(f"    Created Ad: {ad_params['name']} (ID: {ad['id']})")


if __name__ == "__main__":
    set_local_proxy()
    data: FacebookAdConfig = {
        "account_ids": ["act_1690699338271283"],
        "campaigns": [
            {
                "name": "Series_A_Sales",
                "objective": "OUTCOME_SALES",
                "status": "PAUSED",
                "special_ad_categories": [],
                "buying_type": "AUCTION",
                "is_adset_budget_sharing_enabled": False,
                "adsets": [
                    {
                        "name": "Group_1_Conversions",
                        "daily_budget": 100,
                        "optimization_goal": "OFFSITE_CONVERSIONS",
                        "billing_event": "IMPRESSIONS",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "targeting": {
                            "geo_locations": {"countries": ["US"]},
                            "age_min": 18,
                            "age_max": 65,
                            "publisher_platforms": ["facebook", "instagram"],
                        },
                        "status": "PAUSED",
                        "promoted_object": {
                            "pixel_id": "3776295676006945",
                            "custom_event_type": "PURCHASE",
                        },
                        "ads": [
                            {
                                "name": "Ad_1_Product",
                                "page_id": "920300004492299",
                                "link_url": "https://example.com/product1",
                                "status": "PAUSED",
                                "creative": {
                                    "type": "image",
                                    "path": "D:\\code\\python\\pvstore\\schedulers\\test\\Snipaste_2025-12-23_15-07-44.png",
                                    "title": "Great Product",
                                    "body": "Check this out!",
                                },
                                "contextual_multi_ads": {"enroll_status": "OPT_OUT"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    publisher = AdPublisher(DEV_CONFIG, data)
    publisher.publish_from_config()
