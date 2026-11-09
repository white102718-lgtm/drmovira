import logging
from datetime import datetime, timezone

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)


def get_google_ads_client(dev):
    from utils.common import set_local_proxy
    set_local_proxy()

    # 完整的service account信息
    service_account_info = {
        "type": "service_account",
        "project_id": "amiable-dragon-465510-j9",
        "private_key_id": "ac58e773ab7718c1789c5876b8e259e54706260f",
        "private_key": "REDACTED_REFERENCE_SECRET\n",
        "client_email": "rtt-795@amiable-dragon-465510-j9.iam.gserviceaccount.com",
        "client_id": "107477834312479123925",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/rtt-795%40amiable-dragon-465510-j9.iam.gserviceaccount.com",
        "universe_domain": "googleapis.com",
    }
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=["https://www.googleapis.com/auth/adwords"]
    )
    client = GoogleAdsClient(
        credentials=credentials,
        developer_token=dev["developer_token"],
        use_proto_plus=True,
        login_customer_id=dev["login_customer_id"],
    )
    return client


def fetch_asset_conversion_breakdown(client, customer_id, date):
    """
    获取素材级别的转化数据
    尝试通过 conversion_action 资源查询
    """
    ga_service = client.get_service("GoogleAdsService")

    # 尝试方案1: 直接从 ad_group_ad_asset_view 查询转化动作
    query = f"""
        SELECT
            asset.id,
            segments.conversion_action,
            segments.conversion_action_name,
            metrics.conversions,
            metrics.conversions_value,
            segments.date
        FROM ad_group_ad_asset_view
        WHERE segments.date = '{date}'
        AND metrics.conversions > 0
    """

    conversion_data = {}
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in response:
            for row in batch.results:
                asset_id = str(row.asset.id)
                action_name = row.segments.conversion_action_name

                if asset_id not in conversion_data:
                    conversion_data[asset_id] = {
                        "APP_INSTALLS": {"count": 0, "value": 0.0},
                        "PURCHASE": {"count": 0, "value": 0.0},
                        "SUBMIT_LEAD_FORM": {"count": 0, "value": 0.0},
                        "SIGNUP": {"count": 0, "value": 0.0},
                        "ADD_TO_CART": {"count": 0, "value": 0.0},
                        "OTHER": {"count": 0, "value": 0.0},
                    }

                # 根据转化动作名称判断类型
                action_name_lower = action_name.lower()
                if 'install' in action_name_lower or 'app' in action_name_lower:
                    conversion_data[asset_id]["APP_INSTALLS"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["APP_INSTALLS"]["value"] += row.metrics.conversions_value
                elif 'purchase' in action_name_lower or 'buy' in action_name_lower:
                    conversion_data[asset_id]["PURCHASE"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["PURCHASE"]["value"] += row.metrics.conversions_value
                elif 'signup' in action_name_lower or 'register' in action_name_lower:
                    conversion_data[asset_id]["SIGNUP"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["SIGNUP"]["value"] += row.metrics.conversions_value
                elif 'lead' in action_name_lower:
                    conversion_data[asset_id]["SUBMIT_LEAD_FORM"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["SUBMIT_LEAD_FORM"]["value"] += row.metrics.conversions_value
                elif 'cart' in action_name_lower:
                    conversion_data[asset_id]["ADD_TO_CART"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["ADD_TO_CART"]["value"] += row.metrics.conversions_value
                else:
                    conversion_data[asset_id]["OTHER"]["count"] += int(row.metrics.conversions)
                    conversion_data[asset_id]["OTHER"]["value"] += row.metrics.conversions_value

        logging.info(f"获取到 {len(conversion_data)} 个素材的转化细分数据")
        return conversion_data

    except GoogleAdsException as e:
        logging.warning(f"获取素材转化细分数据失败: {e}")
        logging.warning("将使用总转化数代替")
        return {}


def fetch_conversion_breakdown(client, customer_id, date, resource_name="customer"):
    """
    获取按转化动作类型细分的转化数据
    返回字典: {resource_id: {category: conversions_count}}
    """
    ga_service = client.get_service("GoogleAdsService")

    # 根据不同资源构建查询
    if resource_name == "customer":
        query = f"""
            SELECT
                customer.id,
                segments.conversion_action_category,
                segments.conversion_action_name,
                metrics.conversions,
                metrics.conversions_value,
                segments.date
            FROM customer
            WHERE segments.date = '{date}'
        """
        id_field = "customer.id"
    elif resource_name == "campaign":
        query = f"""
            SELECT
                campaign.id,
                segments.conversion_action_category,
                segments.conversion_action_name,
                metrics.conversions,
                metrics.conversions_value,
                segments.date
            FROM campaign
            WHERE segments.date = '{date}'
        """
        id_field = "campaign.id"
    elif resource_name == "ad_group":
        query = f"""
            SELECT
                ad_group.id,
                segments.conversion_action_category,
                segments.conversion_action_name,
                metrics.conversions,
                metrics.conversions_value,
                segments.date
            FROM ad_group
            WHERE segments.date = '{date}'
        """
        id_field = "ad_group.id"

    conversion_data = {}
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in response:
            for row in batch.results:
                # 获取资源ID
                if resource_name == "customer":
                    resource_id = str(row.customer.id)
                elif resource_name == "campaign":
                    resource_id = str(row.campaign.id)
                elif resource_name == "ad_group":
                    resource_id = str(row.ad_group.id)

                category = row.segments.conversion_action_category.name

                if resource_id not in conversion_data:
                    conversion_data[resource_id] = {
                        "ADD_TO_CART": {"count": 0, "value": 0.0},
                        "PURCHASE": {"count": 0, "value": 0.0},
                        "SUBMIT_LEAD_FORM": {"count": 0, "value": 0.0},
                        "SIGNUP": {"count": 0, "value": 0.0},
                        "APP_INSTALLS": {"count": 0, "value": 0.0},
                        "OTHER": {"count": 0, "value": 0.0},
                    }

                # 累加转化数据
                if category in conversion_data[resource_id]:
                    conversion_data[resource_id][category]["count"] += int(row.metrics.conversions)
                    conversion_data[resource_id][category]["value"] += row.metrics.conversions_value
                else:
                    conversion_data[resource_id]["OTHER"]["count"] += int(row.metrics.conversions)
                    conversion_data[resource_id]["OTHER"]["value"] += row.metrics.conversions_value

    except GoogleAdsException as e:
        logging.warning(f"获取{resource_name}转化细分数据失败: {e}")
        return {}

    return conversion_data


def fetch_account_level_data(client, customer_id, date):
    """获取账户级别数据"""
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            customer.id,
            customer.descriptive_name,
            customer.currency_code,
            customer.time_zone,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.conversions_by_conversion_date,
            metrics.conversions_value_by_conversion_date,
            metrics.ctr,
            metrics.average_cpc,
            metrics.interactions,
            metrics.interaction_rate,
            metrics.all_conversions,
            metrics.all_conversions_value,
            metrics.view_through_conversions,
            metrics.conversions_from_interactions_rate,
            metrics.cost_per_conversion,
            metrics.value_per_conversion,
            metrics.value_per_all_conversions,
            segments.date
        FROM customer
        WHERE segments.date = '{date}'
    """

    # 获取转化细分数据
    conversion_breakdown = fetch_conversion_breakdown(client, customer_id, date, "customer")

    results = []
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            account_id = str(row.customer.id)
            conv_data = conversion_breakdown.get(account_id, {})

            results.append({
                "level": "account",
                "account_id": account_id,
                "account_name": row.customer.descriptive_name,
                "campaign_id": None,
                "campaign_name": None,
                "ad_set_id": None,
                "ad_set_name": None,
                "ad_id": None,
                "ad_name": None,
                "delivery": 1,
                "delivery_str": "ENABLED",
                "cam_budget": 0,
                "adset_budget": 0,
                "budget": 0,
                "amount_spent": round(row.metrics.cost_micros / 1000000, 2),
                "impressions": row.metrics.impressions,
                "clicks_all": row.metrics.clicks,
                "clicks_unique": None,  # Google Ads无去重点击指标
                "reach": 0,
                "frequency": 0,
                "ctr": row.metrics.ctr,
                "cpc": round(row.metrics.average_cpc / 1000000, 4),
                "cpm": round((row.metrics.cost_micros / 1000) / max(row.metrics.impressions, 1), 2),
                # 使用clicks而非interactions (interactions包含视频观看等)
                "inline_link_clicks": row.metrics.clicks,
                "inline_link_click_ctr": row.metrics.ctr,
                "unique_inline_link_clicks": None,  # Google Ads无此指标
                "unique_inline_link_click_ctr": None,
                # 使用转化细分数据
                "app_installs": conv_data.get("APP_INSTALLS", {}).get("count", 0),
                "purchases": conv_data.get("PURCHASE", {}).get("count", 0),
                "purchases_value": conv_data.get("PURCHASE", {}).get("value", 0.0),
                "complete_registration": conv_data.get("SIGNUP", {}).get("count", 0),
                "subscribe_website": conv_data.get("ADD_TO_CART", {}).get("count", 0),
                "subscribe_website_values": conv_data.get("ADD_TO_CART", {}).get("value", 0.0),
                "lead": conv_data.get("SUBMIT_LEAD_FORM", {}).get("count", 0),
                # Google Ads无原生1日点击归因窗口，设置为None
                "purchases_1dclick": None,
                "purchase_values_1dclick": None,
                "subscriptions_1dclick": None,
                "subscriptions_value_1dclick": None,
                "app_installs_1dclick": None,
                "register_1dclick": None,
                "lead_1dclick": None,
                "date": str(row.segments.date),
            })
    logging.info(f"获取到 {len(results)} 条账户级别数据")
    return results


def fetch_campaign_level_data(client, customer_id, date):
    """获取广告系列级别数据"""
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            customer.id,
            customer.descriptive_name,
            campaign.id,
            campaign.name,
            campaign.status,
            campaign_budget.amount_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.conversions_by_conversion_date,
            metrics.conversions_value_by_conversion_date,
            metrics.view_through_conversions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.interactions,
            metrics.interaction_rate,
            metrics.unique_users,
            metrics.average_impression_frequency_per_user,
            metrics.all_conversions,
            metrics.all_conversions_value,
            metrics.conversions_from_interactions_rate,
            metrics.cost_per_conversion,
            metrics.value_per_conversion,
            metrics.value_per_all_conversions,
            segments.date
        FROM campaign
        WHERE segments.date = '{date}'
        LIMIT 1000
    """

    # 获取转化细分数据
    conversion_breakdown = fetch_conversion_breakdown(client, customer_id, date, "campaign")

    results = []
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            campaign_id = str(row.campaign.id)
            conv_data = conversion_breakdown.get(campaign_id, {})

            results.append({
                "level": "campaign",
                "account_id": str(row.customer.id),
                "account_name": row.customer.descriptive_name,
                "campaign_id": campaign_id,
                "campaign_name": row.campaign.name,
                "ad_set_id": None,
                "ad_set_name": None,
                "ad_id": None,
                "ad_name": None,
                "delivery": 1 if row.campaign.status.name == "ENABLED" else 0,
                "delivery_str": row.campaign.status.name,
                "cam_budget": round(row.campaign_budget.amount_micros / 1000000, 2) if row.campaign_budget else 0,
                "adset_budget": 0,
                "budget": round(row.campaign_budget.amount_micros / 1000000, 2) if row.campaign_budget else 0,
                "amount_spent": round(row.metrics.cost_micros / 1000000, 2),
                "impressions": row.metrics.impressions,
                "clicks_all": row.metrics.clicks,
                "clicks_unique": None,  # Google Ads无去重点击指标
                "reach": row.metrics.unique_users,
                "frequency": round(row.metrics.average_impression_frequency_per_user, 2) if row.metrics.average_impression_frequency_per_user else 0,
                "ctr": row.metrics.ctr,
                "cpc": round(row.metrics.average_cpc / 1000000, 4),
                "cpm": round((row.metrics.cost_micros / 1000) / max(row.metrics.impressions, 1), 2),
                # 使用clicks而非interactions
                "inline_link_clicks": row.metrics.clicks,
                "inline_link_click_ctr": row.metrics.ctr,
                "unique_inline_link_clicks": None,  # Google Ads无此指标
                "unique_inline_link_click_ctr": None,
                # 使用转化细分数据
                "app_installs": conv_data.get("APP_INSTALLS", {}).get("count", 0),
                "purchases": conv_data.get("PURCHASE", {}).get("count", 0),
                "purchases_value": conv_data.get("PURCHASE", {}).get("value", 0.0),
                "complete_registration": conv_data.get("SIGNUP", {}).get("count", 0),
                "subscribe_website": conv_data.get("ADD_TO_CART", {}).get("count", 0),
                "subscribe_website_values": conv_data.get("ADD_TO_CART", {}).get("value", 0.0),
                "lead": conv_data.get("SUBMIT_LEAD_FORM", {}).get("count", 0),
                # Google Ads无原生1日点击归因窗口，设置为None
                "purchases_1dclick": None,
                "purchase_values_1dclick": None,
                "subscriptions_1dclick": None,
                "subscriptions_value_1dclick": None,
                "app_installs_1dclick": None,
                "register_1dclick": None,
                "lead_1dclick": None,
                "date": str(row.segments.date),
            })
    logging.info(f"获取到 {len(results)} 条广告系列级别数据")
    return results


def fetch_adset_level_data(client, customer_id, date):
    """获取广告组级别数据"""
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            customer.id,
            customer.descriptive_name,
            campaign.id,
            campaign.name,
            campaign.status,
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.cpc_bid_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.conversions_by_conversion_date,
            metrics.conversions_value_by_conversion_date,
            metrics.view_through_conversions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.interactions,
            metrics.interaction_rate,
            metrics.all_conversions,
            metrics.all_conversions_value,
            metrics.conversions_from_interactions_rate,
            metrics.cost_per_conversion,
            metrics.value_per_conversion,
            metrics.value_per_all_conversions,
            segments.date
        FROM ad_group
        WHERE segments.date = '{date}'
        LIMIT 1000
    """

    # 获取转化细分数据
    conversion_breakdown = fetch_conversion_breakdown(client, customer_id, date, "ad_group")

    results = []
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            ad_group_id = str(row.ad_group.id)
            conv_data = conversion_breakdown.get(ad_group_id, {})

            results.append({
                "level": "adset",
                "account_id": str(row.customer.id),
                "account_name": row.customer.descriptive_name,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "ad_set_id": ad_group_id,
                "ad_set_name": row.ad_group.name,
                "ad_id": None,
                "ad_name": None,
                "delivery": 1 if row.ad_group.status.name == "ENABLED" else 0,
                "delivery_str": row.ad_group.status.name,
                "cam_budget": 0,
                "adset_budget": round(row.ad_group.cpc_bid_micros / 1000000, 2) if row.ad_group.cpc_bid_micros else 0,
                "budget": 0,
                "amount_spent": round(row.metrics.cost_micros / 1000000, 2),
                "impressions": row.metrics.impressions,
                "clicks_all": row.metrics.clicks,
                "clicks_unique": None,  # Google Ads无去重点击指标
                "reach": 0,
                "frequency": 0,
                "ctr": row.metrics.ctr,
                "cpc": round(row.metrics.average_cpc / 1000000, 4),
                "cpm": round((row.metrics.cost_micros / 1000) / max(row.metrics.impressions, 1), 2),
                # 使用clicks而非interactions
                "inline_link_clicks": row.metrics.clicks,
                "inline_link_click_ctr": row.metrics.ctr,
                "unique_inline_link_clicks": None,  # Google Ads无此指标
                "unique_inline_link_click_ctr": None,
                # 使用转化细分数据
                "app_installs": conv_data.get("APP_INSTALLS", {}).get("count", 0),
                "purchases": conv_data.get("PURCHASE", {}).get("count", 0),
                "purchases_value": conv_data.get("PURCHASE", {}).get("value", 0.0),
                "complete_registration": conv_data.get("SIGNUP", {}).get("count", 0),
                "subscribe_website": conv_data.get("ADD_TO_CART", {}).get("count", 0),
                "subscribe_website_values": conv_data.get("ADD_TO_CART", {}).get("value", 0.0),
                "lead": conv_data.get("SUBMIT_LEAD_FORM", {}).get("count", 0),
                # Google Ads无原生1日点击归因窗口，设置为None
                "purchases_1dclick": None,
                "purchase_values_1dclick": None,
                "subscriptions_1dclick": None,
                "subscriptions_value_1dclick": None,
                "app_installs_1dclick": None,
                "register_1dclick": None,
                "lead_1dclick": None,
                "date": str(row.segments.date),
            })
    logging.info(f"获取到 {len(results)} 条广告组级别数据")
    return results


def fetch_asset_level_data(client, customer_id, date):
    """获取广告素材资源级别数据"""
    ga_service = client.get_service("GoogleAdsService")

    # 先获取素材级别的转化细分数据
    conversion_breakdown = fetch_asset_conversion_breakdown(client, customer_id, date)

    # 查询广告素材资源数据（包含素材详细信息）
    query = f"""
        SELECT
            customer.id,
            customer.descriptive_name,
            campaign.id,
            campaign.name,
            campaign.status,
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.cpc_bid_micros,
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.status,
            asset.id,
            asset.name,
            asset.type,
            asset.image_asset.full_size.url,
            asset.image_asset.full_size.width_pixels,
            asset.image_asset.full_size.height_pixels,
            asset.youtube_video_asset.youtube_video_id,
            asset.youtube_video_asset.youtube_video_title,
            ad_group_ad_asset_view.enabled,
            ad_group_ad_asset_view.field_type,
            ad_group_ad_asset_view.performance_label,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.ctr,
            metrics.average_cpc,
            segments.date
        FROM ad_group_ad_asset_view
        WHERE segments.date = '{date}'
        AND metrics.impressions > 0
        LIMIT 10000
    """

    results = []
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in response:
            for row in batch.results:
                asset_id = str(row.asset.id)
                asset_type = row.asset.type.name if row.asset.type else "UNKNOWN"

                # 获取素材URL和尺寸信息
                asset_url = None
                asset_width = None
                asset_height = None
                video_id = None
                video_title = None

                if asset_type == "IMAGE":
                    try:
                        if row.asset.image_asset and row.asset.image_asset.full_size:
                            asset_url = row.asset.image_asset.full_size.url
                            asset_width = row.asset.image_asset.full_size.width_pixels
                            asset_height = row.asset.image_asset.full_size.height_pixels
                    except:
                        pass
                elif asset_type == "YOUTUBE_VIDEO":
                    try:
                        if row.asset.youtube_video_asset:
                            video_id = row.asset.youtube_video_asset.youtube_video_id
                            video_title = row.asset.youtube_video_asset.youtube_video_title
                            if video_id:
                                asset_url = f"https://www.youtube.com/watch?v={video_id}"
                    except:
                        pass

                # 获取该素材的转化细分数据
                conv_data = conversion_breakdown.get(asset_id, {})

                # 打印调试信息
                logging.info(f"Asset ID: {asset_id}, Type: {asset_type}, Name: {row.asset.name if row.asset.name else 'None'}")
                logging.info(f"Impressions: {row.metrics.impressions}, Clicks: {row.metrics.clicks}, Spent: ${row.metrics.cost_micros / 1000000:.2f}")
                logging.info(f"App Installs: {conv_data.get('APP_INSTALLS', {}).get('count', 0)}")

                results.append({
                    "level": "ad",  # level 设为 ad（与 gg_ad_sync.py 保持一致）
                    "account_id": str(row.customer.id),
                    "account_name": row.customer.descriptive_name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "ad_set_id": str(row.ad_group.id),
                    "ad_set_name": row.ad_group.name,
                    "ad_id": asset_id,  # ad_id 设为 asset_id
                    "ad_name": row.asset.name if row.asset.name else None,  # ad_name 设为 asset_name
                    "delivery": 1 if row.ad_group_ad_asset_view.enabled else 0,
                    "delivery_str": "ENABLED" if row.ad_group_ad_asset_view.enabled else "PAUSED",
                    "cam_budget": 0,
                    "adset_budget": round(row.ad_group.cpc_bid_micros / 1000000, 2) if row.ad_group.cpc_bid_micros else 0,
                    "budget": 0,
                    "amount_spent": round(row.metrics.cost_micros / 1000000, 2),
                    "impressions": row.metrics.impressions,
                    "clicks_all": row.metrics.clicks,
                    "clicks_unique": None,
                    "reach": 0,
                    "frequency": 0,
                    "ctr": row.metrics.ctr,
                    "cpc": round(row.metrics.average_cpc / 1000000, 4) if row.metrics.average_cpc else 0,
                    "cpm": round((row.metrics.cost_micros / 1000) / max(row.metrics.impressions, 1), 2) if row.metrics.impressions > 0 else 0,
                    "inline_link_clicks": row.metrics.clicks,
                    "inline_link_click_ctr": row.metrics.ctr,
                    "unique_inline_link_clicks": None,
                    "unique_inline_link_click_ctr": None,
                    # 使用转化细分数据
                    "app_installs": conv_data.get("APP_INSTALLS", {}).get("count", 0),
                    "purchases": conv_data.get("PURCHASE", {}).get("count", 0),
                    "purchases_value": conv_data.get("PURCHASE", {}).get("value", 0.0),
                    "complete_registration": conv_data.get("SIGNUP", {}).get("count", 0),
                    "subscribe_website": conv_data.get("ADD_TO_CART", {}).get("count", 0),
                    "subscribe_website_values": conv_data.get("ADD_TO_CART", {}).get("value", 0.0),
                    "lead": conv_data.get("SUBMIT_LEAD_FORM", {}).get("count", 0),
                    "purchases_1dclick": None,
                    "purchase_values_1dclick": None,
                    "subscriptions_1dclick": None,
                    "subscriptions_value_1dclick": None,
                    "app_installs_1dclick": None,
                    "register_1dclick": None,
                    "lead_1dclick": None,
                    "date": str(row.segments.date),
                })
    except GoogleAdsException as e:
        logging.error(f"获取广告素材资源级别数据失败: {e}")
        return []

    logging.info(f"获取到 {len(results)} 条广告素材资源级别数据")
    return results


def fetch_google_ads_reports(dev):
    client = get_google_ads_client(dev)
    if not client:
        return []

    customer_id = dev["customer_id"]
    date = dev["date"]
    all_results = []

    # 获取各层级数据
    account_data = fetch_account_level_data(client, customer_id, date)
    campaign_data = fetch_campaign_level_data(client, customer_id, date)
    adset_data = fetch_adset_level_data(client, customer_id, date)
    asset_data = fetch_asset_level_data(client, customer_id, date)

    # 合并所有数据
    all_results.extend(account_data)
    all_results.extend(campaign_data)
    all_results.extend(adset_data)
    all_results.extend(asset_data)
    return all_results


def convert(google_data, dev):
    results = []
    for item in google_data:
        business_fields = {
            "date": f"{item.get('date')} 00:00:00",
            "game_platform": dev.get("game_platform"),
            "ad_platform": "google_ads",
            "agent_line": dev.get("agent_line"),
            "timezone_name": "Asia/Shanghai",
            "dev_id": dev.get("dev_id"),
            "china_date": f"{dev.get('date')} 00:00:00",
            "create_time": datetime.now(timezone.utc),
            "fetch_time": datetime.now(timezone.utc),
            "placer_id": dev.get("placer_id", ""),
            "package_name": dev.get("app_name", ""),
        }
        standard_data = {**item, **business_fields}
        results.append(standard_data)

    return results


def sync_google_ads_data(dev):
    logging.info(f"开始Google Ads数据同步，日期: {dev['date']}")
    google_data = fetch_google_ads_reports(dev)
    logging.info(f'{google_data}')
    if not google_data:
        logging.warning("未获取到Google Ads数据")
        return []
    # 转换为标准格式
    results = convert(google_data, dev)
    # for result in results:
    #     logging.info(result)
    return results


if __name__ == "__main__":
    dev = {
        "ad_platform": "google",
        "game_platform": "",
        "agent_line": "",
        "placer_id": "rtt",
        "app_name": "",
        "date": "2025-07-23",
        "customer_id": "8776198849",
        "login_customer_id": "3101283750",
        "developer_token": "REDACTED_REFERENCE_SECRET",
    }
    results = sync_google_ads_data(dev)
    print(f"获取到 {len(results)} 条数据")
