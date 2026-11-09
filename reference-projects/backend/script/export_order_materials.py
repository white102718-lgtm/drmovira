"""导出所有关联工单的素材（名称 / 素材师 / 创意策划 / 上传时间）到 Excel。

用法：DEPLOY_ENV=prod PYTHONPATH=. python -u script/export_order_materials.py <输出xlsx路径>

两个来源合并：materials 中关联工单的素材（有 order_id，或无 order_id 但能按 basename
反查 material_order_outputs），以及无 order_id 但已填写 creative_editor 的剪辑素材；再加上
material_order_outputs 里尚未入库的产出物。产出物入库后会在 materials 留一条同名记录，故按
basename 全局去重：materials 优先，同源多条取最早一次上传。素材师取 creative_editor，为空
回退产出物 designer；创意策划从素材关联工单的 creative_planners 读取。
"""

import asyncio
import sys
from datetime import datetime, timezone

import pandas as pd
from bson import ObjectId

from app.db.mongo import cols

COLS = {
    "basename": "素材名称",
    "designer": "素材师",
    "creative_planners": "创意策划",
    "created_at": "上传时间",
}
# 无上传时间的排最后，可被有时间的同名记录顶掉
_FAR = datetime(9999, 1, 1, tzinfo=timezone.utc)


def _keep_earliest(
    store: dict, bn: str, designer: str, order_id: str | None, created_at
) -> None:
    cur = store.get(bn)
    if cur is None or (created_at or _FAR) < (cur["created_at"] or _FAR):
        store[bn] = {
            "designer": designer,
            "order_id": order_id,
            "created_at": created_at,
        }


def _format_names(names) -> str:
    if isinstance(names, list):
        return "、".join(str(name) for name in names if name)
    return str(names or "")


async def collect() -> list[dict]:
    outputs: dict[str, dict] = {}
    async for o in cols.material_order_outputs.find(
        {"basename": {"$nin": [None, ""]}},
        projection={"basename": 1, "designer": 1, "order_id": 1, "created_at": 1, "_id": 0},
    ):
        _keep_earliest(
            outputs,
            o["basename"],
            o.get("designer") or "",
            o.get("order_id"),
            o.get("created_at"),
        )

    merged: dict[str, dict] = {}
    async for m in cols.materials.find(
        {}, projection={"basename": 1, "creative_editor": 1, "created_at": 1,
                        "order_id": 1, "_id": 0}
    ):
        bn = m.get("basename")
        if not bn:
            continue
        out = outputs.get(bn)
        editor = m.get("creative_editor") or ""
        # 直传素材没有工单关联时，仍导出已分配剪辑的素材。
        if not m.get("order_id") and out is None and not editor:
            continue
        designer = editor or (out["designer"] if out else "")
        _keep_earliest(
            merged,
            bn,
            designer,
            m.get("order_id") or (out.get("order_id") if out else None),
            m.get("created_at"),
        )

    for bn, out in outputs.items():
        if bn not in merged:
            merged[bn] = out

    order_ids = {str(v["order_id"]) for v in merged.values() if v.get("order_id")}
    valid_order_ids = [ObjectId(order_id) for order_id in order_ids if ObjectId.is_valid(order_id)]
    planners_by_order = {
        str(order["_id"]): _format_names(order.get("creative_planners"))
        async for order in cols.material_orders.find(
            {"_id": {"$in": valid_order_ids}},
            projection={"creative_planners": 1},
        )
    }

    rows = [
        {
            "basename": bn,
            "designer": v["designer"],
            "creative_planners": planners_by_order.get(str(v.get("order_id")), ""),
            "created_at": v["created_at"].strftime("%Y-%m-%d %H:%M:%S") if v["created_at"] else "",
        }
        for bn, v in merged.items()
    ]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows


def main(out_path: str) -> None:
    rows = asyncio.run(collect())
    df = pd.DataFrame(rows, columns=list(COLS)).rename(columns=COLS)
    df.to_excel(out_path, index=False, sheet_name="素材数据", engine="openpyxl")
    print(f"导出 {len(rows)} 条 -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
