"""
回填 materials.is_green_material（冗余自 material_orders）

只处理带该字段的工单：老工单没标过绿通，回填后仍无该字段，筛选两个方向都不命中。
扫描 materials 时只投影 order_id/is_green_material —— 文档内嵌 base64 缩略图，
整文档拉取在生产库要 80s+。
"""

import asyncio

from app.db.mongo import cols

CHUNK = 1000


async def _update_chunked(ids: list, value: bool) -> None:
    for i in range(0, len(ids), CHUNK):
        await cols.materials.update_many(
            {"_id": {"$in": ids[i : i + CHUNK]}},
            {"$set": {"is_green_material": value}},
        )


async def main(dry_run: bool = True):
    print(f"dry-run: {dry_run}\n")

    green_by_order = {
        str(o["_id"]): o["is_green_material"]
        async for o in cols.material_orders.find(
            {"is_green_material": {"$exists": True}},
            projection={"is_green_material": 1},
        )
    }
    print(f"带绿通标签的工单: {len(green_by_order)}")
    if not green_by_order:
        print("[跳过] 没有可回填的工单")
        return

    to_true, to_false, matched, already = [], [], 0, 0
    async for m in cols.materials.find(
        {"order_id": {"$ne": None}},
        projection={"order_id": 1, "is_green_material": 1},
    ):
        flag = green_by_order.get(m["order_id"])
        if flag is None:
            continue
        matched += 1
        if m.get("is_green_material") == flag:
            already += 1
        elif flag:
            to_true.append(m["_id"])
        else:
            to_false.append(m["_id"])

    print(f"关联到这些工单的素材: {matched}（其中 {already} 条已是正确值）")
    print(f"待置 true: {len(to_true)}")
    print(f"待置 false: {len(to_false)}")

    if dry_run:
        print("\n[dry-run] 以上为预览，未执行任何写入操作")
        return
    if not to_true and not to_false:
        print("\n[完成] 无需更新")
        return

    await _update_chunked(to_true, True)
    await _update_chunked(to_false, False)
    print(f"\n[完成] 已回填 {len(to_true) + len(to_false)} 条")


if __name__ == "__main__":
    asyncio.run(main(dry_run=True))
