"""个人文件夹分享（只读）：owner 把单个文件夹分享给其他用户查看（不含子级）。
分享对象用 full_name（与 folder.owner 对称）。
整部门授权额外单存一条 department 记录，只为回显"整个部门"；能不能看仍只认 shared_to 记录，
所以调用方要把部门下的人展开成 targets 一起传进来。"""

from datetime import datetime, timezone
from typing import List, Dict

from bson import ObjectId

from app.db.mongo import cols

shares = cols.material_folder_shares
folders = cols.material_folders


async def add_shares(
    folder_id: str, owner: str, targets: List[str], departments: List[str]
) -> int:
    """增量新增分享：名单里已有的不动，重复调用幂等。返回本次写入的记录数。"""
    fid = ObjectId(folder_id)
    keys = [{"shared_to": t} for t in dict.fromkeys(targets) if t and t != owner]
    keys += [{"department": d} for d in dict.fromkeys(departments) if d]
    now = datetime.now(timezone.utc)
    for key in keys:
        await shares.update_one(
            {"folder_id": fid, **key},
            {
                "$set": {"updated_at": now},
                "$setOnInsert": {"owner": owner, "created_at": now},
            },
            upsert=True,
        )
    return len(keys)


async def list_shares(folder_id: str) -> Dict[str, List[str]]:
    """某文件夹分享给了谁：targets=人的 full_name，departments=整部门授权的部门标识。"""
    targets: List[str] = []
    departments: List[str] = []
    async for s in shares.find(
        {"folder_id": ObjectId(folder_id)}, {"shared_to": 1, "department": 1}
    ):
        if s.get("department"):
            departments.append(s["department"])
        elif s.get("shared_to"):
            targets.append(s["shared_to"])
    return {"targets": targets, "departments": departments}


async def delete_shares(
    folder_id: str, targets: List[str], departments: List[str]
) -> int:
    """取消对指定人/指定部门的分享。"""
    fid = ObjectId(folder_id)
    deleted = 0
    if targets:
        res = await shares.delete_many(
            {"folder_id": fid, "shared_to": {"$in": targets}}
        )
        deleted += res.deleted_count
    if departments:
        res = await shares.delete_many(
            {"folder_id": fid, "department": {"$in": departments}}
        )
        deleted += res.deleted_count
    return deleted


async def shared_root_ids(user: str) -> List[ObjectId]:
    """直接分享给 user 的文件夹 id（shared 树的根）。"""
    return [
        s["folder_id"]
        async for s in shares.find({"shared_to": user}, {"folder_id": 1})
    ]


async def shared_tree_nodes(user: str) -> List[Dict]:
    """分享给 user 的文件夹节点（仅被直接分享的那些，不含子级）。
    每个作为独立根平铺（parent_id 置 None），喂 build_tree_from_flat_data。"""
    roots = await shared_root_ids(user)
    if not roots:
        return []
    return [
        {
            "key": str(f["_id"]),
            "parent_id": None,
            "name": f["name"],
            "level": f["level"],
            "owner": f["owner"],
            "shared": True,
        }
        async for f in folders.find({"_id": {"$in": roots}})
    ]


async def can_access_folder(folder: Dict, user: str) -> bool:
    """user 是否可看该文件夹：owner 本人，或该文件夹被直接分享给 user（不含子级）。"""
    if folder.get("owner") == user:
        return True
    return folder["_id"] in set(await shared_root_ids(user))
