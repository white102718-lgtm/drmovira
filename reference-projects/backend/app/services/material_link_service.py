"""素材↔个人文件夹关联（多对多）：文件夹归属从 materials 文档剥离到 material_folder_links，
一条素材文档可被多个文件夹引用。folder_id 永远是具体文件夹（无根目录）。"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bson import ObjectId

from app.db.mongo import cols

links = cols.material_folder_links


async def link_material(
    material_id: ObjectId,
    folder_id: str,
    source: str,
    order_id: Optional[str] = None,
) -> None:
    """素材入个人文件夹：按 (material_id, folder_id) 幂等 upsert，已存在则不动。"""
    await links.update_one(
        {"material_id": material_id, "folder_id": ObjectId(folder_id)},
        {
            "$setOnInsert": {
                "source": source,
                "order_id": order_id,
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def unlink_folder_materials(
    folder_id: str, material_ids: List[ObjectId]
) -> List[ObjectId]:
    """删除文件夹下这些素材的归属关系，返回删后再无任何 link 的孤儿 material_id。"""
    fid = ObjectId(folder_id)
    present = [
        link["material_id"]
        async for link in links.find(
            {"folder_id": fid, "material_id": {"$in": material_ids}},
            {"material_id": 1},
        )
    ]
    if not present:
        return []
    await links.delete_many({"folder_id": fid, "material_id": {"$in": present}})
    return [m for m in present if not await links.find_one({"material_id": m})]


async def paginate_folder(
    folder_id: str,
    skip: int,
    limit: int,
    material_ids: Optional[List[ObjectId]] = None,
) -> Tuple[List[ObjectId], int]:
    """文件夹内素材分页（最新在前）：返回有序 material_id 列表与总数。
    material_ids 非 None 时只在这批素材内分页（basename 等按素材字段过滤后传入）。"""
    q = {"folder_id": ObjectId(folder_id)}
    if material_ids is not None:
        q["material_id"] = {"$in": material_ids}
    total = await links.count_documents(q)
    ordered = [
        link["material_id"]
        async for link in links.find(q, {"material_id": 1})
        .sort("_id", -1)
        .skip(skip)
        .limit(limit)
    ]
    return ordered, total


async def folder_material_ids(folder_id: str) -> List[ObjectId]:
    """文件夹内全部 material_id（发布/删除等批量操作用）。"""
    return [
        link["material_id"]
        async for link in links.find({"folder_id": ObjectId(folder_id)}, {"material_id": 1})
    ]


async def folder_has_links(folder_id: str) -> bool:
    """文件夹是否还挂着素材（删文件夹空判用）。"""
    return await links.find_one({"folder_id": ObjectId(folder_id)}) is not None
