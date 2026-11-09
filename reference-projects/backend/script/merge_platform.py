"""
合并多个平台的配置到目标平台

合并内容：
- agent_lines: 移动到目标平台
- material_category_ids: 移动到目标平台
- total_budget: 累加到目标平台
- target_region: 合并去重
- agent_line_kpi_config: game_platform 指向目标平台
- 源平台软删除到 trash（不级联删除已移动的数据）
"""

import asyncio
from datetime import datetime

from app.db.mongo import cols, trash

platform_col = cols.platform_config
kpi_col = cols.agent_line_kpi_config
platform_trash = trash.platform_config

TIME_FMT = "%Y-%m-%d %H:%M:%S"


async def main(
    source_platforms: list[str],
    target_platform: str,
    dry_run: bool = True,
):
    print(f"源平台: {source_platforms}")
    print(f"目标平台: {target_platform}")
    print(f"dry-run: {dry_run}\n")

    # 验证目标平台
    target_doc = await platform_col.find_one({"_id": target_platform})
    if not target_doc:
        print(f"[错误] 目标平台 [{target_platform}] 不存在")
        return

    # 验证源平台
    source_docs = await platform_col.find({"_id": {"$in": source_platforms}}).to_list()
    found_ids = {doc["_id"] for doc in source_docs}
    missing = set(source_platforms) - found_ids
    if missing:
        print(f"[错误] 源平台不存在: {missing}")
        return

    if target_platform in source_platforms:
        print("[错误] 目标平台不能在源平台列表中")
        return

    # 目标平台现有数据
    target_agent_lines = set(target_doc.get("agent_lines", []))
    target_material_ids = set(target_doc.get("material_category_ids", []))
    target_regions = set(target_doc.get("target_region") or [])
    target_budget = target_doc.get("total_budget") or 0

    print(f"--- 目标平台 [{target_platform}] 现有 ---")
    print(f"  agent_lines({len(target_agent_lines)}): {sorted(target_agent_lines)}")
    print(f"  material_categories={len(target_material_ids)}, "
          f"regions={len(target_regions)}, budget={target_budget}")

    # 收集源平台数据
    all_agent_lines = []
    all_material_category_ids = []
    all_target_regions = []
    total_budget_add = 0.0

    for doc in source_docs:
        agent_lines = doc.get("agent_lines", [])
        material_ids = doc.get("material_category_ids", [])
        regions = doc.get("target_region") or []
        budget = doc.get("total_budget") or 0

        all_agent_lines.extend(agent_lines)
        all_material_category_ids.extend(material_ids)
        all_target_regions.extend(regions)
        total_budget_add += budget

        print(f"\n--- 源平台 [{doc['_id']}] ---")
        print(f"  agent_lines({len(agent_lines)}): {sorted(agent_lines)}")
        print(f"  material_categories={len(material_ids)}, "
              f"regions={len(regions)}, budget={budget}")

    # 合并后统计
    merged_agent_lines = sorted(target_agent_lines | set(all_agent_lines))
    merged_material_ids = target_material_ids | set(all_material_category_ids)
    merged_regions = target_regions | set(all_target_regions)
    merged_budget = target_budget + total_budget_add

    kpi_count = await kpi_col.count_documents({"game_platform": {"$in": source_platforms}})

    print(f"\n====== 合并后 [{target_platform}] ======")
    print(f"  agent_lines({len(merged_agent_lines)}): {merged_agent_lines}")
    print(f"  material_categories={len(merged_material_ids)}, "
          f"regions={len(merged_regions)}, budget={merged_budget}")
    print(f"  KPI 配置待迁移: {kpi_count} 条")

    if dry_run:
        print("\n[dry-run] 以上为预览，未执行任何写入操作")
        return

    confirm_str = f"{','.join(source_platforms)}->{target_platform}"
    user_input = input(f"\n请输入 [{confirm_str}] 确认执行: ")
    if user_input != confirm_str:
        print("[取消] 输入不匹配，已取消操作")
        return

    # 1. 合并到目标平台
    update_ops: dict = {"$addToSet": {}}
    if all_agent_lines:
        update_ops["$addToSet"]["agent_lines"] = {"$each": all_agent_lines}
    if all_material_category_ids:
        update_ops["$addToSet"]["material_category_ids"] = {"$each": all_material_category_ids}
    if all_target_regions:
        update_ops["$addToSet"]["target_region"] = {"$each": all_target_regions}
    if total_budget_add > 0:
        update_ops["$inc"] = {"total_budget": total_budget_add}

    await platform_col.update_one({"_id": target_platform}, update_ops)
    print(f"\n[完成] 已合并到 [{target_platform}]")

    # 2. 迁移 KPI 配置
    if kpi_count:
        await kpi_col.update_many(
            {"game_platform": {"$in": source_platforms}},
            {"$set": {"game_platform": target_platform}},
        )
        print(f"[完成] KPI 配置已迁移 {kpi_count} 条")

    # 3. 软删除源平台（移到 trash）
    for doc in source_docs:
        doc["agent_lines"] = []
        doc["material_category_ids"] = []
        doc["delete_time"] = datetime.now().strftime(TIME_FMT)
        doc["deleted_by"] = "script"
        doc["_id"] = f"{doc['_id']}_del_{int(datetime.now().timestamp())}"
        await platform_trash.insert_one(doc)
    await platform_col.delete_many({"_id": {"$in": source_platforms}})
    print(f"[完成] 已软删除 {len(source_docs)} 个源平台到 trash")


if __name__ == "__main__":
    asyncio.run(main(
        source_platforms=["batwin-A8", "batwin-Rosen"],  # 源平台ID列表
        target_platform="batwin",  # 目标平台ID
        dry_run=False,  # 仅预览，不执行写入
    ))
