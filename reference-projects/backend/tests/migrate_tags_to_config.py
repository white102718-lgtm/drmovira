"""
迁移脚本：为现有 tags 生成 tag_config 并添加 config_id
按 game_platform 和 real_name 分组
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Dict

from bson import ObjectId

from app.db.mongo import cols

tree_tags_collection = cols.tree_tags
tag_configs_collection = cols.tag_configs


async def migrate_tags_to_config():
    """将现有的 tags 按 game_platform 和 real_name 分组，生成配置并添加 config_id"""

    print("开始迁移...")

    # 1. 使用聚合查询获取所有不同的 (game_platform, real_name) 组合
    pipeline = [
        {
            "$group": {
                "_id": {
                    "game_platform": "$game_platform",
                    "real_name": "$real_name"
                },
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id.real_name": 1, "_id.game_platform": 1}}
    ]

    cursor = tree_tags_collection.aggregate(pipeline)
    groups = await cursor.to_list(length=None)

    print(f"找到 {len(groups)} 个不同的 (game_platform, real_name) 组合")

    if not groups:
        print("没有找到任何标签，迁移终止")
        return

    # 显示分组信息
    for group in groups:
        game_platform = group["_id"].get("game_platform", "unknown")
        real_name = group["_id"].get("real_name", "unknown")
        count = group["count"]
        print(f"  {real_name} - {game_platform}: {count} 个标签")

    # 2. 为每个组合创建配置并批量更新标签
    current_time = datetime.now(timezone.utc)
    total_updated = 0
    config_created = 0

    for group in groups:
        game_platform = group["_id"].get("game_platform", "unknown")
        real_name = group["_id"].get("real_name", "unknown")
        tag_count = group["count"]

        # 生成配置名称
        config_name = f"{real_name}_{game_platform}"

        # 检查是否已存在该配置
        existing_config = await tag_configs_collection.find_one({
            "real_name": real_name,
            "name": config_name
        })

        if existing_config:
            config_id = str(existing_config["_id"])
            print(f"\n配置 '{config_name}' 已存在，使用现有配置 ID: {config_id}")
        else:
            # 创建新配置
            new_config = {
                "name": config_name,
                "real_name": real_name,
                "created_at": current_time,
                "updated_at": current_time,
            }
            result = await tag_configs_collection.insert_one(new_config)
            config_id = str(result.inserted_id)
            config_created += 1
            print(f"\n创建配置 '{config_name}'，ID: {config_id}")

        # 批量更新所有匹配该组合的标签（只更新没有 config_id 的标签）
        update_result = await tree_tags_collection.update_many(
            {
                "game_platform": game_platform,
                "real_name": real_name,
                "config_id": {"$exists": False}
            },
            {
                "$set": {
                    "config_id": config_id,
                    "updated_at": current_time
                }
            }
        )

        updated = update_result.modified_count
        total_updated += updated
        print(f"  更新了 {updated} 个标签（共 {tag_count} 个）")

    print(f"\n迁移完成！")
    print(f"- 创建配置数: {config_created}")
    print(f"- 更新标签数: {total_updated}")

    # 3. 验证结果
    print("\n验证结果：")

    for group in groups:
        game_platform = group["_id"].get("game_platform", "unknown")
        real_name = group["_id"].get("real_name", "unknown")
        config_name = f"{real_name}_{game_platform}"

        config = await tag_configs_collection.find_one({
            "real_name": real_name,
            "name": config_name
        })

        if config:
            config_id = str(config["_id"])
            count = await tree_tags_collection.count_documents({
                "config_id": config_id
            })
            print(f"  配置 '{config_name}' (ID: {config_id}): {count} 个标签")

    # 检查是否有标签没有 config_id
    no_config_count = await tree_tags_collection.count_documents({
        "config_id": {"$exists": False}
    })
    if no_config_count > 0:
        print(f"\n⚠️  警告：还有 {no_config_count} 个标签没有 config_id")

        # 显示这些标签
        no_config_tags = tree_tags_collection.find(
            {"config_id": {"$exists": False}}
        ).limit(10)
        print("  前 10 个没有 config_id 的标签：")
        async for tag in no_config_tags:
            print(f"    - {tag.get('_id')}: real_name={tag.get('real_name')}, game_platform={tag.get('game_platform')}, title={tag.get('title')}")


if __name__ == "__main__":
    asyncio.run(migrate_tags_to_config())
