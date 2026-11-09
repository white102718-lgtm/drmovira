from datetime import timezone, timedelta

from bson.codec_options import CodecOptions
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.conf import MongodbConf

client = AsyncIOMotorClient(MongodbConf.CONNECTION)

tz_cst = timezone(timedelta(hours=8))
codec_options = CodecOptions(tz_aware=True, tzinfo=tz_cst)

_db = client.get_database("plat", codec_options=codec_options)
_db_trash = client.get_database("trash", codec_options=codec_options)
_db_user = client.get_database("user", codec_options=codec_options)


class Collections:
    # 素材
    materials: AsyncIOMotorCollection = _db["materials"]
    ad_creatives: AsyncIOMotorCollection = _db["ad_creatives"]
    tree_tags: AsyncIOMotorCollection = _db["tree_tags"]
    material_category: AsyncIOMotorCollection = _db["material_category"]
    creative_histories: AsyncIOMotorCollection = _db["creative_histories"]
    material_groups: AsyncIOMotorCollection = _db["material_groups"]
    material_group_histories: AsyncIOMotorCollection = _db["material_group_histories"]
    # 标签
    fact_tags: AsyncIOMotorCollection = _db["fact_tags"]
    inference_tags: AsyncIOMotorCollection = _db["inference_tags"]
    tag_configs: AsyncIOMotorCollection = _db["tag_configs"]

    # 创意生成
    creative_materials: AsyncIOMotorCollection = _db["creative_materials"]
    creative_materials_img: AsyncIOMotorCollection = _db["creative_materials_img"]
    creative_tasks: AsyncIOMotorCollection = _db["creative_tasks"]
    creative_tasks_img: AsyncIOMotorCollection = _db["creative_tasks_img"]
    creative_run_tasks_img: AsyncIOMotorCollection = _db["creative_run_tasks_img"]

    # FB 资源
    fb_system_users: AsyncIOMotorCollection = _db["fb_system_users"]
    personal_accounts: AsyncIOMotorCollection = _db["personal_accounts"]
    fb_ad_accounts: AsyncIOMotorCollection = _db["fb_ad_accounts"]
    fb_businesses: AsyncIOMotorCollection = _db["fb_businesses"]
    fb_pages: AsyncIOMotorCollection = _db["fb_pages"]
    fb_pixels: AsyncIOMotorCollection = _db["fb_pixels"]
    fb_asset_assignments: AsyncIOMotorCollection = _db["fb_asset_assignments"]
    fb_material_uploads: AsyncIOMotorCollection = _db["fb_material_uploads"]

    # 广告运营
    accounts: AsyncIOMotorCollection = _db["accounts"]
    ad_operations: AsyncIOMotorCollection = _db["ad_operations"]
    # 广告实体配置最新态:一对象一条,_id=FB 对象 id,worker 拉取后 upsert
    ad_config_campaigns: AsyncIOMotorCollection = _db["ad_config_campaigns"]
    ad_config_adsets: AsyncIOMotorCollection = _db["ad_config_adsets"]
    ad_config_ads: AsyncIOMotorCollection = _db["ad_config_ads"]
    ad_config_activities: AsyncIOMotorCollection = _db["ad_config_activities"]
    # 广告原始素材名：_id=广告 ID，assets[].name=平台返回的原始素材文件名
    ad_asset_names: AsyncIOMotorCollection = _db["ad_asset_names"]
    # 查看记录:按(账户+日期)缓存整天操作记录,sealed=该天已过不再变更
    ad_config_activity_days: AsyncIOMotorCollection = _db["ad_config_activity_days"]
    ad_sync_history: AsyncIOMotorCollection = _db["ad_sync_history"]
    tasks: AsyncIOMotorCollection = _db["tasks"]

    # 素材工单
    material_orders: AsyncIOMotorCollection = _db["material_orders"]
    material_order_outputs: AsyncIOMotorCollection = _db["material_order_outputs"]
    material_order_comments: AsyncIOMotorCollection = _db["material_order_comments"]
    material_order_histories: AsyncIOMotorCollection = _db["material_order_histories"]
    material_folders: AsyncIOMotorCollection = _db["material_folders"]
    material_folder_links: AsyncIOMotorCollection = _db["material_folder_links"]
    material_folder_shares: AsyncIOMotorCollection = _db["material_folder_shares"]
    material_commons: AsyncIOMotorCollection = _db["material_commons"]

    # 配置
    platform_config: AsyncIOMotorCollection = _db["platform_config"]
    platform_field_map: AsyncIOMotorCollection = _db["platform_field_map"]
    agent_line_config: AsyncIOMotorCollection = _db["agent_line_config"]
    agent_line_kpi_config: AsyncIOMotorCollection = _db["agent_line_kpi_config"]
    ad_create_templates: AsyncIOMotorCollection = _db["ad_create_templates"]
    material_templates: AsyncIOMotorCollection = _db["material_templates"]
    department_config: AsyncIOMotorCollection = _db["department_config"]
    # 飞书「MP媒介资料表」账户登记:account_id 唯一,user_name=当前使用人
    feishu_account_used_record: AsyncIOMotorCollection = _db["feishu_account_used_record"]
    telegram_config: AsyncIOMotorCollection = _db["telegram_config"]
    dashboard_filter_templates: AsyncIOMotorCollection = _db["dashboard_filter_templates"]
    dashboard_column_settings: AsyncIOMotorCollection = _db["dashboard_column_settings"]


class UserCollections:
    user: AsyncIOMotorCollection = _db_user["user"]
    role: AsyncIOMotorCollection = _db_user["role"]
    menu: AsyncIOMotorCollection = _db_user["menu"]


class TrashCollections:
    accounts: AsyncIOMotorCollection = _db_trash["accounts"]
    materials: AsyncIOMotorCollection = _db_trash["materials"]  # 删除留痕，不可还原
    ad_create_templates: AsyncIOMotorCollection = _db_trash["ad_create_templates"]
    material_templates: AsyncIOMotorCollection = _db_trash["material_templates"]
    department_config: AsyncIOMotorCollection = _db_trash["department_config"]
    platform_config: AsyncIOMotorCollection = _db_trash["platform_config"]
    material_category: AsyncIOMotorCollection = _db_trash["material_category"]
    agent_line_config: AsyncIOMotorCollection = _db_trash["agent_line_config"]
    agent_line_kpi_config: AsyncIOMotorCollection = _db_trash["agent_line_kpi_config"]
    tag_configs: AsyncIOMotorCollection = _db_trash["tag_configs"]
    telegram_config: AsyncIOMotorCollection = _db_trash["telegram_config"]
    api_keys: AsyncIOMotorCollection = _db_trash["api_keys"]


cols = Collections()
trash = TrashCollections()
user_cols = UserCollections()


