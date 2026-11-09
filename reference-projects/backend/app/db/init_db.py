#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT, HASHED


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_collections(
    client: AsyncIOMotorClient, db_name: str, collections: List[str]
) -> None:
    """创建MongoDB集合"""
    db = client[db_name]
    existing_collections = await db.list_collection_names()

    for collection in collections:
        if collection not in existing_collections:
            await db.create_collection(collection)
            logger.info(f"创建集合 {collection} 成功")
        else:
            logger.info(f"集合 {collection} 已存在")


async def insert_data(
    client: AsyncIOMotorClient,
    db_name: str,
    collections_data: Dict[str, List[Dict[str, Any]]],
) -> None:
    """向MongoDB集合中插入数据

    Args:
        client: MongoDB客户端
        db_name: 数据库名称
        collections_data: 集合数据，键为集合名称，值为要插入的文档列表
    """
    db = client[db_name]

    for collection_name, documents in collections_data.items():
        if not documents:
            continue

        collection = db[collection_name]

        try:
            result = await collection.insert_many(documents)
            logger.info(
                f"向集合 {collection_name} 插入{len(result.inserted_ids)}条数据成功"
            )
        except Exception as e:
            logger.error(f"向集合 {collection_name} 插入数据失败: {e}")


async def create_indexes(
    client: AsyncIOMotorClient,
    db_name: str,
    collection_indexes: Dict[str, List[Dict[str, Any]]],
    force: bool = False,
) -> None:
    """创建MongoDB索引

    Args:
        client: MongoDB客户端
        db_name: 数据库名称
        collection_indexes: 索引配置
        force: 是否强制重新创建索引，True则先删除已有索引
    """
    db = client[db_name]

    for collection_name, indexes in collection_indexes.items():
        collection = db[collection_name]

        # 查询已有索引
        existing_indexes = await collection.index_information()

        # 如果强制重建索引，先删除已有索引（保留_id_默认索引）
        if force:
            for index_name in existing_indexes:
                if index_name != "_id_":
                    logger.info(f"删除集合 {collection_name} 的索引 {index_name}")
                    await collection.drop_index(index_name)
            # 重查，确保后续判断基于最新状态
            existing_indexes = await collection.index_information()

        for index_config in indexes:
            fields = index_config["fields"]
            options = index_config.get("options", {})

            index_models = []
            for field, direction in fields.items():
                if direction == "text":
                    index_models.append((field, TEXT))
                elif direction == 1:
                    index_models.append((field, ASCENDING))
                elif direction == -1:
                    index_models.append((field, DESCENDING))
                elif isinstance(direction, str) and direction.lower() == "hashed":
                    index_models.append((field, HASHED))

            # 若配置中指定了索引名且数据库中已存在同名索引，则跳过创建
            configured_name = options.get("name")
            if configured_name and configured_name in existing_indexes:
                logger.error(
                    f"集合 {collection_name} 索引 {configured_name} 已存在，跳过创建"
                )
                continue

            try:
                index_name = await collection.create_index(index_models, **options)
                logger.error(f"为集合 {collection_name} 创建索引 {index_name} 成功")
            except Exception as e:
                logger.error(f"为集合 {collection_name} 创建索引失败: {e}")


async def init_db(force: bool = False) -> None:
    """初始化数据库，创建集合和索引
    Args:
        force: 是否强制重新创建索引
    """
    client = AsyncIOMotorClient(MongodbConf.CONNECTION)

    # { db_name: { collection_name: [index_config, ...] } }
    all_indexes = {
        "plat": {
            "ad_sync_history": [
                {
                    "fields": {"date": -1, "agent_lines": 1},
                    "options": {"name": "day_al"},
                },
            ],
            "agent_line_config": [
                {
                    "fields": {"package_url": 1},
                    "options": {"name": "package_url_1"},
                },
                {
                    "fields": {"history_package_urls": 1},
                    "options": {"name": "history_package_urls_1"},
                },
            ],
            # 树形标签集合：为 add_tree_tag 的同父节点下按 _id 倒序查找提供支持
            "tree_tags": [
                {
                    "fields": {"parent_id": 1, "_id": -1},
                    "options": {"name": "pid_1__id_-1"},
                }
            ],
            "creative_materials": [
                {
                    "fields": {"sha3_256": 1},
                    "options": {"name": "sha3_256_1"},
                }
            ],
            "creative_tasks": [
                {
                    "fields": {"basename": 1},
                    "options": {"name": "basename_1"},
                },
                {
                    "fields": {"real_name": 1, "status": 1},
                    "options": {"name": "real_name_1_status_1"},
                },
                {
                    "fields": {"status": 1},
                    "options": {"name": "status_1"},
                },
            ],
            "materials": [
                {
                    "fields": {"filename": 1},
                    "options": {"name": "filename_1", "unique": True},
                },
                # created_at 并入使 basename 查询可覆盖投影上传时间（素材看板排序次级 key）
                {
                    "fields": {"basename": 1, "created_at": 1},
                    "options": {"name": "basename_1_created_at_1"},
                },
                {
                    "fields": {"sha3_256": 1},
                    "options": {"name": "sha3_256_1"},
                },
                {
                    "fields": {"tags_new": 1},
                    "options": {"name": "tags_new_1"},
                },
                {
                    "fields": {
                        "created_at": -1,
                        "country": 1,
                        "operator": 1,
                        "game_platform": 1,
                    },
                    "options": {
                        "name": "created_at_-1_country_1_operator_1_game_platform_1"
                    },
                },
                # 素材看板覆盖索引：列表/导出所需小字段全部入索引，避免读带大缩略图的文档
                {
                    "fields": {
                        "created_at": -1,
                        "basename": 1,
                        "filename": 1,
                        "origin_filename": 1,
                        "filetype": 1,
                        "creative_editor": 1,
                        "country": 1,
                        "department": 1,
                        "order_id": 1,
                        "user": 1,
                        "operator": 1,
                    },
                    "options": {"name": "dashboard_covered_v3"},
                },
                # 看板部门筛选(operator=需求方 full_name)按 basename 集合解析用
                {
                    "fields": {"operator": 1, "basename": 1},
                    "options": {"name": "operator_1_basename_1"},
                },
                # 绿通筛选：等值前缀 + created_at 兼作区间和排序 + _id 稳定翻页次级键
                {
                    "fields": {"is_green_material": 1, "created_at": -1, "_id": -1},
                    "options": {"name": "green_1_created_at_-1__id_-1"},
                },
            ],
            "ad_creatives": [
                {
                    "fields": {"sha3_256": 1},
                    "options": {"name": "sha3_256_1", "unique": True},
                },
                {
                    "fields": {"basename": 1},
                    "options": {"name": "basename_1"},
                },
                {
                    "fields": {"updated_at": -1},
                    "options": {"name": "updated_at_-1"},
                },
                {
                    "fields": {"user": 1},
                    "options": {"name": "user_1"},
                },
            ],
            "personal_accounts": [
                {
                    "fields": {"accounts.id": 1},
                    "options": {"name": "accounts.id_1"},
                },
                {
                    "fields": {"pages.id": 1},
                    "options": {"name": "pages.id_1"},
                },
                {
                    # 个号锚点查询：{user_name, status:True}
                    "fields": {"user_name": 1, "status": 1},
                    "options": {"name": "user_name_1_status_1"},
                },
                {
                    # 给 _get_personal_accounts 的 $lookup foreignField=app_id 用
                    "fields": {"app_id": 1},
                    "options": {"name": "app_id_1"},
                },
            ],
            "fb_system_users": [
                {
                    "fields": {"accounts.id": 1},
                    "options": {"name": "accounts.id_1"},
                },
                {
                    "fields": {"pages.id": 1},
                    "options": {"name": "pages.id_1"},
                },
            ],
            # 开发者配置集合：按 app_id 单查（多处 find_one）/ 按 department+status 列表查
            "accounts": [
                {
                    "fields": {"app_id": 1},
                    "options": {"name": "app_id_1"},
                },
                {
                    "fields": {"department": 1, "status": 1},
                    "options": {"name": "department_1_status_1"},
                },
            ],
            # 部门资产分配：按用户 / 按部门兜底
            "fb_asset_assignments": [
                {
                    "fields": {"user_id": 1},
                    "options": {"name": "user_id_1"},
                },
                {
                    "fields": {"department": 1},
                    "options": {"name": "department_1"},
                },
            ],
            # 素材工单集合
            "material_orders": [
                {
                    "fields": {"order_no": 1},
                    "options": {"name": "order_no_1", "unique": True},
                },
                {
                    "fields": {"status": 1, "expected_delivery_at": 1},
                    "options": {"name": "status_1_exp_1"},
                },
                {
                    "fields": {"creator": 1, "created_at": -1},
                    "options": {"name": "creator_1_created_at_-1"},
                },
                {
                    "fields": {"designers": 1, "status": 1},
                    "options": {"name": "designers_1_status_1"},
                },
                # list_orders 默认按 created_at 倒序，基础条件 status:$ne 收窄不了，
                # 无此索引则全表扫+阻塞排序；也供按时间单查
                {
                    "fields": {"created_at": -1},
                    "options": {"name": "created_at_-1"},
                },
            ],
            "material_order_outputs": [
                {
                    "fields": {"order_id": 1, "version_no": -1},
                    "options": {"name": "order_1_ver_-1"},
                },
                # 覆盖索引：统计实际产出数只走索引键，不落文档（文档内嵌 base64 缩略图）
                {
                    "fields": {"order_id": 1, "basename": 1},
                    "options": {"name": "order_1_basename_1"},
                },
                # 素材库按 basename 兜底查未入库素材，无此索引会全表扫过带缩略图的文档
                {
                    "fields": {"basename": 1},
                    "options": {"name": "basename_1"},
                },
                # 素材看板两条基础表路径各一个覆盖索引：谓词和投影都在索引键里，
                # 不回表读内嵌 base64 缩略图的文档。前缀按各自的收窄字段排：
                # 投放窗口为基础表时按 basename 收窄，提交日期为基础表时按 created_at
                {
                    "fields": {
                        "basename": 1,
                        "created_at": -1,
                        "designer": 1,
                        "filetype": 1,
                        "order_id": 1,
                    },
                    "options": {"name": "dashboard_outputs_by_basename"},
                },
                {
                    "fields": {
                        "created_at": -1,
                        "basename": 1,
                        "designer": 1,
                        "filetype": 1,
                        "order_id": 1,
                    },
                    "options": {"name": "dashboard_outputs_by_created"},
                },
            ],
            "material_order_comments": [
                {
                    "fields": {"order_id": 1, "created_at": 1},
                    "options": {"name": "order_1_created_1"},
                },
            ],
            "material_folders": [
                {
                    "fields": {"owner": 1, "parent_id": 1},
                    "options": {"name": "owner_1_parent_1"},
                },
            ],
            # 素材↔个人文件夹关联（多对多）：一条素材可归属多个文件夹
            "material_folder_links": [
                {
                    "fields": {"material_id": 1, "folder_id": 1},
                    "options": {"name": "mat_folder_uniq", "unique": True},
                },
                {
                    "fields": {"folder_id": 1, "_id": -1},
                    "options": {"name": "folder_1__id_-1"},
                },
            ],
            # 个人文件夹分享（只读）：owner 分享给 shared_to 查看
            "material_folder_shares": [
                {
                    "fields": {"folder_id": 1, "shared_to": 1},
                    "options": {"name": "folder_shared_to_uniq", "unique": True},
                },
                {
                    "fields": {"shared_to": 1},
                    "options": {"name": "shared_to_1"},
                },
            ],
            # 公共素材（共享模版库）：库内去重 + 按时间列表
            "material_commons": [
                {
                    "fields": {"filename": 1},
                    "options": {"name": "filename_1", "unique": True},
                },
                {
                    "fields": {"sha3_256": 1},
                    "options": {"name": "sha3_256_1"},
                },
                {
                    "fields": {"created_at": -1},
                    "options": {"name": "created_at_-1"},
                },
            ],
            # 广告配置模板集合
            "ad_create_templates": [
                {
                    # 复合唯一索引：同一用户下模板名唯一
                    "fields": {"real_name": 1, "name": 1},
                    "options": {"name": "real_name_1_name_1", "unique": True},
                },
                {
                    # 用户查询索引
                    "fields": {"real_name": 1},
                    "options": {"name": "real_name_1"},
                },
                {
                    # 时间排序索引
                    "fields": {"create_time": -1},
                    "options": {"name": "create_time_-1"},
                },
            ],
        },
        "trash": {
            # 素材删除留痕：按时间列表 / 反查某素材是被谁删的
            "materials": [
                {
                    "fields": {"deleted_at": -1},
                    "options": {"name": "deleted_at_-1"},
                },
                {
                    "fields": {"basename": 1},
                    "options": {"name": "basename_1"},
                },
            ],
        },
        "user": {
            "user": [
                {
                    "fields": {"username": 1},
                    "options": {"name": "username_1", "unique": True},
                },
                {
                    "fields": {"real_name": 1},
                    "options": {"name": "real_name_1", "unique": True},
                },
                {
                    "fields": {"roles": 1},
                    "options": {"name": "roles_1"},
                },
                {
                    # fb_asset_assignment.assigned_asset_ids 用部门反查用户
                    "fields": {"department": 1},
                    "options": {"name": "department_1"},
                },
                {
                    "fields": {"full_name": 1},
                    "options": {"name": "full_name_1"},
                },
                {
                    "fields": {"phone": 1},
                    "options": {"name": "phone_1"},
                },
            ],
            "role": [
                {
                    "fields": {"name": 1},
                    "options": {"name": "name_1", "unique": True},
                },
            ],
        },
    }

    try:
        for db_name, collection_indexes in all_indexes.items():
            await create_indexes(client, db_name, collection_indexes, force=force)
        logger.info("索引初始化完成")
    except Exception as e:
        logger.error(f"索引初始化失败: {e}")
        raise
    finally:
        client.close()


def dat():

    # 集合数据字典，键为集合名称，值为要插入的文档列表
    collections_data = {
        "user": [
            {
                "username": "adminer",
                "real_name": "admin",
                "roles": ["admin"],
                "status": 1,
                "hashed_password": "REDACTED_REFERENCE_SECRET",
                "create_time": "2025-05-23 10:54:13",
                "update_time": "2025-05-23 13:45:51",
                "ips": [],
            }
        ],
        "role": [
            {
                "_id": "682ed07cad4559436a4ec614",
                "remark": "最高权限",
                "permissions": [],
                "status": 1,
                "name": "admin",
                "create_time": "2025-05-22 15:21:32",
                "update_time": "2025-05-22 16:28:07",
            },
            {
                "_id": "6830128fccd124c245d3cffd",
                "remark": "同事看的",
                "permissions": [
                    "682da13d715bc7951663d0dc",
                    "682da162715bc7951663d0de",
                    "682da14d715bc7951663d0dd",
                    "682d9e70715bc7951663d0d6",
                    "682d9e9d715bc7951663d0d8",
                    "682d9e93715bc7951663d0d7",
                ],
                "status": 1,
                "name": "viewer",
                "create_time": "2025-05-23 06:15:43",
                "update_time": "2025-05-29 09:52:58",
            },
            {
                "_id": "683013deccd124c245d3cffe",
                "remark": "投手",
                "permissions": [
                    "682da13d715bc7951663d0dc",
                    "682da162715bc7951663d0de",
                    "682da14d715bc7951663d0dd",
                    "682d9e70715bc7951663d0d6",
                    "682d9e9d715bc7951663d0d8",
                    "682d9e93715bc7951663d0d7",
                    "682da084715bc7951663d0db",
                    "68551e697545551429f76ef0",
                    "682da084715bc7951663d0db",
                    "68551ee27545551429f76ef1",
                ],
                "status": 1,
                "name": "operator",
                "create_time": "2025-05-23 06:21:18",
                "update_time": "2025-06-20 08:43:12",
            },
            {
                "_id": "683034f7712a4ea401c5bb21",
                "remark": "开发者",
                "permissions": [
                    "682d9e70715bc7951663d0d6",
                    "682d9e93715bc7951663d0d7",
                    "682d9e9d715bc7951663d0d8",
                    "682da13d715bc7951663d0dc",
                    "682e99b19a67603683a5dd8d",
                    "682da14d715bc7951663d0dd",
                    "682da084715bc7951663d0db",
                    "682da162715bc7951663d0de",
                    "68551e697545551429f76ef0",
                    "682da084715bc7951663d0db",
                    "68551ee27545551429f76ef1",
                ],
                "status": 1,
                "name": "developer",
                "create_time": "2025-05-23 08:42:31",
                "update_time": "2025-06-20 08:43:21",
            },
        ],
        "menu": [
            {
                "_id": "682edffe9a3772ee0bd8d9ee",
                "name": "User",
                "status": 1,
                "type": "menu",
                "path": "/system/user",
                "component": "/system/user/list",
                "meta": {
                    "icon": "carbon:user-avatar",
                    "title": "用户管理",
                    "order": 11,
                },
                "pid": "682da02c715bc7951663d0d9",
            },
            {
                "_id": "682e99b19a67603683a5dd8d",
                "name": "Test",
                "status": 1,
                "type": "menu",
                "path": "/test",
                "component": "/materials/test",
                "meta": {"title": "测试"},
                "pid": "682da13d715bc7951663d0dc",
            },
            {
                "_id": "682da464b2d69f484613de06",
                "name": "SystemMenu",
                "status": 1,
                "type": "menu",
                "path": "/system/menu",
                "component": "/system/menu/list",
                "meta": {"icon": "mdi:menu", "title": "system.menu.title", "order": 13},
                "pid": "682da02c715bc7951663d0d9",
            },
            {
                "_id": "682da162715bc7951663d0de",
                "name": "Tags",
                "status": 1,
                "type": "menu",
                "path": "/materials/tags",
                "component": "/materials/tags",
                "meta": {
                    "icon": "mdi:tag-multiple-outline",
                    "title": "标签和属性配置",
                    "order": 11,
                },
                "pid": "682da13d715bc7951663d0dc",
            },
            {
                "_id": "682da14d715bc7951663d0dd",
                "name": "Manage",
                "status": 1,
                "type": "menu",
                "path": "/materials/manage",
                "component": "/materials/upload",
                "meta": {
                    "icon": "mdi:folder-table-outline",
                    "title": "素材管理",
                    "order": 10,
                },
                "pid": "682da13d715bc7951663d0dc",
            },
            {
                "_id": "682da13d715bc7951663d0dc",
                "name": "Materials",
                "status": 1,
                "type": "catalog",
                "path": "/materials",
                "meta": {
                    "icon": "ion:layers-outline",
                    "title": "materials.title",
                    "order": 11,
                },
            },
            {
                "_id": "682da084715bc7951663d0db",
                "name": "SystemDev",
                "status": 1,
                "type": "menu",
                "path": "/system/dev",
                "component": "/system/developers/index",
                "meta": {"icon": "mdi:account-cog", "title": "开发者配置", "order": 10},
                "pid": "68551e697545551429f76ef0",
            },
            {
                "_id": "682da067715bc7951663d0da",
                "name": "SystemRole",
                "status": 1,
                "type": "menu",
                "path": "/system/role",
                "component": "/system/role/list",
                "meta": {
                    "icon": "mdi:account-group",
                    "title": "system.role.title",
                    "order": 12,
                },
                "pid": "682da02c715bc7951663d0d9",
            },
            {
                "_id": "682da02c715bc7951663d0d9",
                "name": "System",
                "status": 1,
                "type": "catalog",
                "path": "/system",
                "meta": {
                    "icon": "ion:settings-outline",
                    "title": "system.title",
                    "order": 999,
                },
            },
            {
                "_id": "682d9e9d715bc7951663d0d8",
                "name": "MaterialStatistics",
                "status": 1,
                "type": "menu",
                "path": "/dashboard/material-statistics",
                "component": "/dashboard/material-statistics",
                "meta": {"icon": "mdi:view-grid", "title": "素材统计", "order": 11},
                "pid": "682d9e70715bc7951663d0d6",
            },
            {
                "_id": "682d9e93715bc7951663d0d7",
                "name": "DashboardAdManager",
                "status": 1,
                "type": "menu",
                "path": "/dashboard/ad-manager",
                "component": "/dashboard/ad-manager",
                "meta": {"icon": "mdi:table-large", "title": "广告面板", "order": 10},
                "pid": "682d9e70715bc7951663d0d6",
            },
            {
                "_id": "682d9e70715bc7951663d0d6",
                "name": "Dashboard",
                "status": 1,
                "type": "catalog",
                "path": "/dashboard",
                "meta": {
                    "icon": "mdi:view-dashboard-variant",
                    "title": "广告详情",
                    "order": 10,
                },
            },
            {
                "_id": "68551e697545551429f76ef0",
                "name": "Project",
                "status": 1,
                "type": "catalog",
                "path": "/project",
                "meta": {"icon": "carbon:apps", "title": "项目配置", "order": 12},
            },
            {
                "_id": "68551ee27545551429f76ef1",
                "name": "platform-config",
                "status": 1,
                "type": "menu",
                "path": "/config/plat-agent",
                "component": "/system/platform-config/index.vue",
                "meta": {
                    "icon": "carbon:expand-all",
                    "title": "平台代理线",
                    "order": 10,
                },
                "pid": "68551e697545551429f76ef0",
            },
        ],
    }
    # 创建集合
    # await create_collections(client, db_name, list(collections_data.keys()))
    # 创建集合
    # await create_collections(client, db_name, list(collections_data.keys()))

    # 插入数据
    # await insert_data(client, db_name, collections_data)


if __name__ == "__main__":
    from app.conf import MongodbConf

    # from app.db.my_minio import minio_init
    asyncio.run(init_db())
    # minio_init()
