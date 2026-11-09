"""素材个人文件夹管理：文件夹增删改移、文件夹内素材列表/删除/打标签，
以及个人文件夹素材发布到公共库。"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from minio.deleteobjects import DeleteObject
from pymongo import UpdateOne
from pydantic import BaseModel

from app.api.routes.department import get_department_subtree
from app.core.security import auth_current_user
from app.db.clients import get_db
from app.db.mongo import cols, user_cols
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.file_type import FileType
from app.model_type_defs.material_order_models import (
    MATERIAL_LIST_PROJECTION,
    MaterialScope,
    FolderCreate,
    FolderRename,
    FolderMove,
)
from app.model_type_defs.user_models import Roles, UserModel
from app.services import material_folder_share_service as share_svc
from app.services import material_link_service as link_svc
from app.services import material_trash_service as trash_svc
from app.services.material_order_service import blocked_material_basenames
from app.services.material_tag_service import resolve_tag_titles

router = APIRouter(prefix="/material-folders", tags=["素材个人文件夹"])

collection = cols.materials
material_folders_collection = cols.material_folders
bucket_name = buckets.materials


async def build_tree_from_flat_data(nodes: List[Dict]) -> List[Dict]:
    """将扁平化的节点数据构建成树形结构，支持统计数据"""
    # 创建节点映射
    node_map = {}
    for node in nodes:
        # 直接使用字典，解包所有数据
        tree_node = {**node}
        node_map[node["key"]] = tree_node

    # 构建树形结构
    root_nodes = []
    for node in nodes:
        tree_node = node_map[node["key"]]
        parent_key = node.get("parent_id")

        if parent_key and parent_key in node_map:
            # 确保父节点有children字段
            if "children" not in node_map[parent_key]:
                node_map[parent_key]["children"] = []
            # 添加到父节点的children中
            node_map[parent_key]["children"].append(tree_node)
        else:
            # 根节点
            root_nodes.append(tree_node)

    return sorted(root_nodes, key=lambda x: x["key"])


async def visible_folder_owners(current_user: UserModel) -> List[str]:
    """可浏览其文件夹的其他用户 full_name：admin 看投放/素材三角色全量，其余看本部门及子部门"""
    if Roles.ADMIN in current_user.roles:
        query: Dict[str, Any] = {
            "roles": {"$in": [*Roles.OPERATOR_ALL, Roles.CREATOR]}
        }
    elif current_user.department:
        query = {
            "department": {"$in": await get_department_subtree(current_user.department)}
        }
    else:
        return []
    # query["status"] = {"$ne": 0}  # status 缺失按启用算
    return [
        u["full_name"]
        async for u in user_cols.user.find(query, {"_id": 0, "full_name": 1})
        if u.get("full_name") and u["full_name"] != current_user.full_name
    ]


# =============== 个人文件夹 → 公共素材库 ===============


class PublishRequest(BaseModel):
    folder_id: str
    materials: List[str]


@router.post("/publish")
async def publish_to_public(
    data: PublishRequest, current_user: UserModel = Depends(auth_current_user)
):
    """投放师把自己个人文件夹的素材手动投放到公共素材库（素材仍留在文件夹）"""
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(data.folder_id), "owner": current_user.full_name}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    folder_material_ids = await link_svc.folder_material_ids(data.folder_id)
    result = await collection.update_many(
        {
            "_id": {"$in": folder_material_ids},
            "basename": {"$in": data.materials},
            "scope": MaterialScope.PERSONAL,
        },
        {
            "$set": {
                "scope": MaterialScope.PUBLIC,
                "published_at": datetime.now(timezone.utc),
            }
        },
    )
    return ApiResponse(data={"published": result.modified_count})


# =============== 个人素材文件夹（两级层级管理）===============


@router.post("")
async def create_folder(
    body: FolderCreate, current_user: UserModel = Depends(auth_current_user)
):
    """创建个人素材文件夹：一级(挂个人根) 或 子级(挂上级，最多三级)"""
    owner = current_user.full_name
    now = datetime.now(timezone.utc)
    if body.parent_id is None:
        level = 1
    else:
        parent = await material_folders_collection.find_one(
            {"_id": ObjectId(body.parent_id), "owner": owner}
        )
        if not parent:
            return ErrResponse(message="父文件夹不存在或非本人")
        if parent["level"] >= 3:
            return ErrResponse(message="最多支持三级文件夹")
        level = parent["level"] + 1
    result = await material_folders_collection.insert_one(
        {
            "owner": owner,
            "name": body.name,
            "parent_id": body.parent_id,
            "level": level,
            "created_at": now,
            "updated_at": now,
        }
    )
    return ApiResponse(data={"id": str(result.inserted_id), "level": level})


@router.get("")
async def list_folders(
    full_name: Optional[str] = Query(None),
    current_user: UserModel = Depends(auth_current_user),
):
    """文件夹树：mine=自己的，shared=别人分享给自己的（仅被分享的那些文件夹，不含子级）。
    full_name 查看他人的树：admin 不限，其余仅限本部门及子部门的用户。"""
    owner = full_name if full_name else current_user.full_name
    if owner != current_user.full_name and Roles.ADMIN not in current_user.roles:
        if owner not in await visible_folder_owners(current_user):
            return ErrResponse(message="无权查看该用户的文件夹")
    nodes = []
    async for f in material_folders_collection.find({"owner": owner}):
        nodes.append(
            {
                "key": str(f["_id"]),
                "parent_id": f.get("parent_id"),
                "name": f["name"],
                "level": f["level"],
            }
        )
    mine = await build_tree_from_flat_data(nodes)
    # 看他人的树时不带 shared：别人收到的分享来自任意部门,不该顺带暴露
    shared = (
        await build_tree_from_flat_data(await share_svc.shared_tree_nodes(owner))
        if owner == current_user.full_name
        else []
    )
    return ApiResponse(data={"mine": mine, "shared": shared})


@router.get("/department/owners")
async def list_department_owners(current_user: UserModel = Depends(auth_current_user)):
    """有个人文件夹的其他用户（admin=投放/素材三角色全量，其余=本部门及子部门），
    前端据此渲染部门文件夹的一级节点，展开时再按 full_name 拉该用户的树"""
    names = await visible_folder_owners(current_user)
    if not names:
        return ApiResponse(data=[])
    owners = await material_folders_collection.distinct(
        "owner", {"owner": {"$in": names}}
    )
    return ApiResponse(data=sorted(owners))


@router.put("/{fid}")
async def rename_folder(
    fid: str, body: FolderRename, current_user: UserModel = Depends(auth_current_user)
):
    """重命名个人文件夹"""
    res = await material_folders_collection.update_one(
        {"_id": ObjectId(fid), "owner": current_user.full_name},
        {"$set": {"name": body.name, "updated_at": datetime.now(timezone.utc)}},
    )
    if res.matched_count == 0:
        return ErrResponse(message="文件夹不存在或非本人")
    return ApiResponse(data={"id": fid})


@router.put("/{fid}/move")
async def move_folder(
    fid: str, body: FolderMove, current_user: UserModel = Depends(auth_current_user)
):
    """移动个人文件夹（含整个子树）：parent_id 为空移到一级，否则挂到目标文件夹下"""
    owner = current_user.full_name
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": owner}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    if body.parent_id == fid:
        return ErrResponse(message="不能移动到自身")
    if body.parent_id is None:
        new_level = 1
    else:
        parent = await material_folders_collection.find_one(
            {"_id": ObjectId(body.parent_id), "owner": owner}
        )
        if not parent:
            return ErrResponse(message="目标文件夹不存在或非本人")
        new_level = parent["level"] + 1

    subtree = {fid: folder}
    frontier = [fid]
    while frontier:
        cursor = material_folders_collection.find(
            {"owner": owner, "parent_id": {"$in": frontier}}
        )
        frontier = []
        async for child in cursor:
            cid = str(child["_id"])
            subtree[cid] = child
            frontier.append(cid)
    if body.parent_id in subtree:
        return ErrResponse(message="不能移动到自己的子文件夹下")

    level_shift = new_level - folder["level"]
    if max(f["level"] for f in subtree.values()) + level_shift > 3:
        return ErrResponse(message="移动后将超过三级层级")

    now = datetime.now(timezone.utc)
    ops = [
        UpdateOne(
            {"_id": folder["_id"]},
            {
                "$set": {
                    "parent_id": body.parent_id,
                    "level": new_level,
                    "updated_at": now,
                }
            },
        )
    ]
    ops.extend(
        UpdateOne({"_id": f["_id"]}, {"$set": {"level": f["level"] + level_shift}})
        for cid, f in subtree.items()
        if cid != fid
    )
    await material_folders_collection.bulk_write(ops)
    return ApiResponse(data={"id": fid, "level": new_level})


@router.delete("/{fid}")
async def delete_folder(fid: str, current_user: UserModel = Depends(auth_current_user)):
    """删除个人文件夹：含子文件夹或素材时禁止删除"""
    owner = current_user.full_name
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": owner}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    if await material_folders_collection.find_one({"parent_id": fid}):
        return ErrResponse(message="文件夹非空（含子文件夹），不可删除")
    if await link_svc.folder_has_links(fid):
        return ErrResponse(message="文件夹非空（含素材），不可删除")
    await material_folders_collection.delete_one({"_id": ObjectId(fid)})
    return ApiResponse(data={"id": fid})


# =============== 文件夹分享（权限设置，只读）===============


class FolderShareBody(BaseModel):
    targets: List[str] = []  # 被分享人 full_name 列表
    departments: List[str] = []  # 整部门授权，部门 id 或部门名


async def expand_share_targets(body: FolderShareBody) -> List[str]:
    """targets 加上 departments（含子部门）下所有人的 full_name，去重"""
    names = list(body.targets)
    depts: List[str] = []
    for entry in body.departments:
        doc = (
            await cols.department_config.find_one({"_id": ObjectId(entry)}, {"name": 1})
            if ObjectId.is_valid(entry)
            else None
        )
        depts.extend(await get_department_subtree(doc["name"] if doc else entry))
    if depts:
        async for u in user_cols.user.find(
            {"department": {"$in": depts}}, {"_id": 0, "full_name": 1}
        ):
            if u.get("full_name"):
                names.append(u["full_name"])
    return list(dict.fromkeys(names))


@router.get("/{fid}/shares")
async def list_folder_shares(
    fid: str, current_user: UserModel = Depends(auth_current_user)
):
    """查看该文件夹分享给了谁（仅 owner）"""
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": current_user.full_name}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    return ApiResponse(data=await share_svc.list_shares(fid))


@router.put("/{fid}/shares")
async def set_folder_shares(
    fid: str,
    body: FolderShareBody,
    current_user: UserModel = Depends(auth_current_user),
):
    """新增该文件夹的分享（增量，仅 owner）：departments 展开到该部门及子部门下所有人"""
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": current_user.full_name}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    count = await share_svc.add_shares(
        fid,
        current_user.full_name,
        await expand_share_targets(body),
        body.departments,
    )
    return ApiResponse(data={"shared_count": count})


@router.delete("/{fid}/shares")
async def delete_folder_shares(
    fid: str,
    body: FolderShareBody,
    current_user: UserModel = Depends(auth_current_user),
):
    """取消分享（仅 owner）：departments 展开到该部门及子部门下所有人一并取消"""
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": current_user.full_name}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    deleted = await share_svc.delete_shares(
        fid, await expand_share_targets(body), body.departments
    )
    return ApiResponse(data={"deleted_count": deleted})


class FolderMaterialsDeleteRequest(BaseModel):
    ids: List[str]


@router.post("/{fid}/materials/batch_delete")
async def delete_folder_materials(
    fid: str,
    body: FolderMaterialsDeleteRequest,
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    """删除个人文件夹下的素材（仅本人）：解除归属；变成孤儿且未发布(personal)的彻底删除，已发布公共库的留存为纯公共素材；
    有消耗或在投的素材不删（blocked 返回）"""
    folder = await material_folders_collection.find_one(
        {"_id": ObjectId(fid), "owner": current_user.full_name}
    )
    if not folder:
        return ErrResponse(message="文件夹不存在或非本人")
    basename_by_id = {
        doc["_id"]: doc["basename"]
        async for doc in collection.find(
            {"_id": {"$in": [ObjectId(i) for i in body.ids]}},
            projection={"basename": 1},
        )
    }
    blocked = await blocked_material_basenames(
        db, list(set(basename_by_id.values()))
    )
    orphans = await link_svc.unlink_folder_materials(
        fid, [mid for mid, b in basename_by_id.items() if b not in blocked]
    )
    detached_count = len(orphans)
    docs = await collection.find(
        {"_id": {"$in": orphans}, "scope": MaterialScope.PERSONAL},
        projection={"img": 0},
    ).to_list(length=None)
    filenames = [doc["filename"] for doc in docs]
    await trash_svc.record_deleted(docs, current_user, "folder")
    if filenames:
        await asyncio.to_thread(
            lambda: list(
                minio_client.remove_objects(
                    bucket_name, [DeleteObject(f) for f in filenames]
                )
            )
        )
    result = await collection.delete_many({"filename": {"$in": filenames}})
    return ApiResponse(
        data={
            "deleted_count": result.deleted_count,
            "detached_count": detached_count - result.deleted_count,
            "blocked": sorted(blocked),
        }
    )


@router.get("/{fid}/materials")
async def list_folder_materials(
    fid: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=400),
    basename: Optional[str] = Query(None),
    filetype: Optional[FileType] = Query(None),
    current_user: UserModel = Depends(auth_current_user),
):
    """获取指定个人文件夹下的素材（本人、被分享者、本部门及子部门可看，超管不限）"""
    folder = await material_folders_collection.find_one({"_id": ObjectId(fid)})
    if not folder:
        return ErrResponse(message="文件夹不存在")
    if (
        Roles.ADMIN not in current_user.roles
        and not await share_svc.can_access_folder(folder, current_user.full_name)
        and folder.get("owner") not in await visible_folder_owners(current_user)
    ):
        return ErrResponse(message="无权访问该文件夹")

    material_ids = None
    mat_filter: Dict[str, Any] = {}
    if basename:
        mat_filter["basename"] = basename
    if filetype:
        mat_filter["filetype"] = filetype
    if mat_filter:
        material_ids = [
            doc["_id"] async for doc in collection.find(mat_filter, {"_id": 1})
        ]

    skip = (page - 1) * page_size
    ordered_ids, total = await link_svc.paginate_folder(
        fid, skip, page_size, material_ids
    )
    docs = {
        doc["_id"]: doc
        async for doc in collection.find(
            {"_id": {"$in": ordered_ids}}, projection=MATERIAL_LIST_PROJECTION
        )
    }
    items = []
    tags_key_name: Dict[str, str] = {}
    for mid in ordered_ids:  # 按 link 顺序（最新在前）拼装
        doc = docs.get(mid)
        if not doc:
            continue
        doc["id"] = str(doc.pop("_id"))
        await resolve_tag_titles(doc, tags_key_name)
        items.append(doc)
    return ApiResponse(
        data={"total": total, "items": items, "page": page, "page_size": page_size}
    )


class FolderMaterialsTagRequest(BaseModel):
    ids: List[str]
    tags_new: List[str]


@router.put("/materials/tags")
async def tag_folder_materials(
    body: FolderMaterialsTagRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    """给文件夹下的素材打标签：直接覆盖 tags_new（标签打在素材上，共享），不写 Doris"""
    result = await collection.update_many(
        {"_id": {"$in": [ObjectId(i) for i in body.ids]}},
        {"$set": {"tags_new": body.tags_new, "updated_at": datetime.now(timezone.utc)}},
    )
    return ApiResponse(data={"modified_count": result.modified_count})
