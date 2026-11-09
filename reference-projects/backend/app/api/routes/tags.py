import base64
import io
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Query, Depends
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field

from app.core.security import require_roles, auth_current_user
from app.db.clients import get_db
from app.db.mongo import cols, trash
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.sql_constants import get_ad_stat_columns
from app.model_type_defs.tag_operations import (
    build_ad_where_conditions,
    build_select_fields,
    remove_tags_from_doris,
)
from app.model_type_defs.user_models import Roles
from app.model_type_defs.user_models import UserModel

router = APIRouter(prefix="/tags", tags=["tags"])

fact_collection = cols.fact_tags
inference_collection = cols.inference_tags


class TagBase(BaseModel):
    name: str
    title: str
    tags: List[str]


class TreeDataStatsRequest(BaseModel):
    config_id: Optional[str] = None
    real_name: Optional[str] = None
    origin: Optional[bool] = False
    right_game_platform: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_field: Literal["create_time", "date"] = Field(
        default="create_time", description="时间筛选字段: create_time 或 date"
    )
    tags: List[str] = Field(default_factory=list, description="标签列表")
    tag_filter_condition: str = Field(
        default="contains", description="标签筛选条件: contains 或 excludes"
    )
    min_spent: Optional[int] = Field(default=None, description="最小花费")


async def get_all_tags(
    collection: AsyncIOMotorCollection, name: Optional[str] = None
) -> List[Dict]:
    query = {}
    if name:
        query["name"] = name

    cursor = collection.find(query)
    tags = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        tags.append(doc)

    return tags


@router.get("/fact")
async def get_all_fact_tags(name: Optional[str] = Query(None)):
    tags = await get_all_tags(fact_collection, name)
    return ApiResponse(data=tags)


@router.get("/inference")
async def get_all_inference_tags(name: Optional[str] = Query(None)):
    tags = await get_all_tags(inference_collection, name)
    return ApiResponse(data=tags)


# TODO 修改删除标签要把素材中的标签也删除
async def update_or_create_tag(
    collection: AsyncIOMotorCollection, name: str, data: dict
) -> Dict:
    current_time = datetime.now(timezone.utc)

    await collection.update_one(
        {"name": name},
        {
            "$set": {**data, "updated_at": current_time},
            "$setOnInsert": {"created_at": current_time},
        },
        upsert=True,
    )

    updated = await collection.find_one({"name": name})
    updated["id"] = str(updated.pop("_id"))

    return updated


@router.post("/fact", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def update_fact_tag(tag: TagBase):
    updated = await update_or_create_tag(
        fact_collection, tag.name, {"tags": tag.tags, "title": tag.title}
    )
    return ApiResponse(data=updated)


@router.post("/inference", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def update_inference_tag(tag: TagBase):
    updated = await update_or_create_tag(
        inference_collection, tag.name, {"tags": tag.tags, "title": tag.title}
    )
    return ApiResponse(data=updated)


async def delete_tag_type(collection: AsyncIOMotorCollection, name: str) -> bool:
    await collection.delete_one({"name": name})
    return True


@router.delete(
    "/fact/{name}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def delete_fact_tag_type(name: str):
    result = await delete_tag_type(fact_collection, name)
    return ApiResponse(data=result)


@router.delete(
    "/inference/{name}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def delete_inference_tag_type(name: str):
    result = await delete_tag_type(inference_collection, name)
    return ApiResponse(data=result)


async def init_tags():
    # name 对应着前端表格, 不能用中文
    fact_tags_data = (
        [
            {
                "_id": "67dd466ccb88b87164476365",
                "name": "country",
                "title": "国家",
                "tags": ["印尼"],
                "created_at": "2025-03-21T10:58:52.089Z",
                "updated_at": "2025-03-21T10:58:52.089Z",
            },
            {
                "_id": "67dd466ccb88b87164476366",
                "name": "category",
                "title": "品类",
                "tags": ["游戏"],
                "created_at": "2025-03-21T10:58:52.089Z",
                "updated_at": "2025-03-21T10:58:52.089Z",
            },
        ],
    )

    inference_tags_data = [
        {
            "name": "成效",
            "title": "成效",
            "tags": ["1", "2", "3", "test", "ban"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "name": "类别",
            "title": "类别",
            "tags": [
                "cheat",
                "game",
                "girl",
                "give",
                "induce",
                "mahjong",
                "slots",
                "withdraw",
            ],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "name": "备用",
            "title": "备用",
            "tags": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    ]

    await fact_collection.delete_many({})
    await inference_collection.delete_many({})

    if fact_tags_data:
        await fact_collection.insert_many(fact_tags_data)
    if inference_tags_data:
        await inference_collection.insert_many(inference_tags_data)

    return {"message": "标签数据初始化成功"}


router_edit = APIRouter(prefix="/tags-edit", tags=["tags-edit"])
tree_tags_collection = cols.tree_tags
materials_collection = cols.materials
commons_collection = cols.material_commons
tag_configs_collection = cols.tag_configs
tag_configs_trash_collection = trash.tag_configs


class TreeTagCreate(BaseModel):
    title: str
    parent_id: Optional[str] = None
    level: int = 1
    config_id: Optional[str] = None
    real_name: str


class TagConfigCreate(BaseModel):
    name: str
    real_name: str


class TagConfigUpdate(BaseModel):
    name: str


class TagConfigResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TreeTagResponse(BaseModel):
    title: str
    key: str
    level: int
    children: List["TreeTagResponse"] = Field(default_factory=list)
    parent_id: Optional[str]
    config_id: Optional[str] = None
    real_name: Optional[str] = None


# 重要：为了支持递归定义，需要更新forward references
TreeTagResponse.model_rebuild()

# ================== 配置管理接口 ==================


@router_edit.get("/config/")
async def get_tag_configs(
    real_name: Optional[str] = Query(None),
):
    """获取配置列表，支持按用户筛选"""
    query: Dict[str, Any] = {}
    if real_name:
        query["real_name"] = real_name

    cursor = tag_configs_collection.find(query).sort("created_at", 1)
    configs = []

    async for doc in cursor:
        configs.append(
            {
                "id": str(doc["_id"]),
                "name": doc.get("name", ""),
                "real_name": doc.get("real_name", ""),
                "created_at": (
                    doc.get("created_at").isoformat() if doc.get("created_at") else None
                ),
                "updated_at": (
                    doc.get("updated_at").isoformat() if doc.get("updated_at") else None
                ),
            }
        )

    return ApiResponse(data=configs)


@router_edit.post("/config/")
async def create_tag_config(config_data: TagConfigCreate):
    current_time = datetime.now(timezone.utc)
    # 检查同一用户下是否已存在同名配置
    existing = await tag_configs_collection.find_one(
        {"name": config_data.name, "real_name": config_data.real_name}
    )
    if existing:
        return ErrResponse(code=400, message="配置名称已存在")

    new_config = {
        "name": config_data.name,
        "real_name": config_data.real_name,
        "created_at": current_time,
        "updated_at": current_time,
    }

    await tag_configs_collection.insert_one(new_config)

    return ApiResponse(
        data={
            "id": str(new_config["_id"]),
            "name": new_config["name"],
            "real_name": new_config["real_name"],
            "created_at": new_config["created_at"].isoformat(),
            "updated_at": new_config["updated_at"].isoformat(),
        }
    )


@router_edit.put("/config/{config_id}")
async def update_tag_config(config_id: str, config_data: TagConfigUpdate):
    """更新配置"""
    current_time = datetime.now(timezone.utc)

    # 检查配置是否存在
    existing = await tag_configs_collection.find_one({"_id": ObjectId(config_id)})
    if not existing:
        return ErrResponse(code=404, message="配置不存在")

    # 检查同一用户下新名称是否与其他配置冲突
    name_conflict = await tag_configs_collection.find_one(
        {
            "_id": ObjectId(config_id),
            "name": config_data.name,
            "real_name": existing.get("real_name"),
        }
    )
    if name_conflict:
        return ErrResponse(code=400, message="配置名称已存在")

    # 更新配置
    await tag_configs_collection.update_one(
        {"_id": ObjectId(config_id)},
        {"$set": {"name": config_data.name, "updated_at": current_time}},
    )

    return ApiResponse(
        data={
            "id": config_id,
            "name": config_data.name,
            "real_name": existing.get("real_name", ""),
            "created_at": (
                existing.get("created_at").isoformat()
                if existing.get("created_at")
                else None
            ),
            "updated_at": current_time.isoformat(),
        }
    )


@router_edit.delete("/config/{config_id}")
async def delete_tag_config(
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    # TODO 删除配置后, 也要删除配置对应的tags
    config = await tag_configs_collection.find_one_and_delete(
        {"_id": ObjectId(config_id)}
    )
    if not config:
        return ErrResponse(code=404, message="配置不存在")

    config["delete_time"] = datetime.now(timezone.utc)
    config["deleted_by"] = current_user.username
    await tag_configs_trash_collection.insert_one(config)

    return ApiResponse(data=None, message="配置已删除")


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


@router_edit.get("/")
async def get_tree_tags(
    config_id: Optional[str] = Query(None),
    real_name: Optional[str] = Query(None),
):
    """获取所有树形标签数据，组装成树形结构"""
    query: Dict[str, Any] = {}
    if config_id:
        query["config_id"] = config_id
    if real_name:
        query["real_name"] = real_name
    cursor = tree_tags_collection.find(query).sort("_id", 1)
    nodes = []

    async for doc in cursor:
        doc["key"] = str(doc["_id"])
        nodes.append(doc)

    tree_data = await build_tree_from_flat_data(nodes)
    return ApiResponse(data=tree_data)


@router_edit.post("/tree_data")
async def get_tree_data_with_stats(
    request: TreeDataStatsRequest,
    db=Depends(get_db),
):
    """获取带统计数据的树形标签数据（支持标签筛选）"""
    # 使用公共的统计字段定义（使用ad作为别名）
    stat_columns = get_ad_stat_columns("ad")

    # 添加 AppsFlyer 相关字段
    af_columns = {
        "注册用户数": "COALESCE(SUM(ad.register_users), 0)",
        "首充用户数": "COALESCE(SUM(ad.first_recharge_users), 0)",
        "当日注册首充用户数": "COALESCE(SUM(ad.same_day_register_first_recharge_users), 0)",
        "D1复购人数": "COALESCE(SUM(ad.d1_purchase_users), 0)",
        "D1复购留存": "ROUND(COALESCE(SUM(ad.d1_purchase_users), 0) * 100.0 / NULLIF(SUM(ad.first_recharge_users), 0), 2)",
    }

    # 合并所有统计字段
    all_stat_columns = {**stat_columns, **af_columns}

    # 步骤1: 确定需要查询的标签范围
    query: Dict[str, Any] = {}
    if request.config_id:
        query["config_id"] = request.config_id
    if request.real_name:
        query["real_name"] = request.real_name

    tags_filter = []
    if request.tags:
        # 有tags参数：查询指定标签及其父标签
        tags_filter = request.tags
        # 获取所有父级标签
        all_tag_ids = set()
        for tag_id in tags_filter:
            parts = tag_id.split("-")
            for i in range(1, len(parts) + 1):
                all_tag_ids.add("-".join(parts[:i]))
        needed_tag_ids = list(all_tag_ids)
        query["_id"] = {"$in": needed_tag_ids}
    # else: 无tags参数，query保持原样，查询所有匹配的标签

    # 步骤2: 统一查询MongoDB标签
    cursor = tree_tags_collection.find(query).sort("_id", 1)
    nodes_dict = {}
    all_tags = set()

    async for doc in cursor:
        tag_id = str(doc["_id"])
        node = {
            "key": tag_id,
            "title": doc.get("title", tag_id),
            "level": doc.get("level", 1),
            "parent_id": doc.get("parent_id"),
            "config_id": doc.get("config_id"),
            "real_name": doc.get("real_name"),
            "is_tag": True,
        }
        nodes_dict[tag_id] = node
        all_tags.add(tag_id)

    # 步骤3: 统一构建并执行SQL查询
    if all_tags:
        # 构建标签筛选条件
        if request.tags:
            # 有tags参数：使用tag_filter_condition
            tags_literal = ", ".join(f"'{tag}'" for tag in tags_filter)
            if request.tag_filter_condition == "excludes":
                arrays_overlap_condition = (
                    f"NOT arrays_overlap(m.tags, [{tags_literal}])"
                )
            else:
                arrays_overlap_condition = f"arrays_overlap(m.tags, [{tags_literal}])"
        else:
            # 无tags参数：使用所有标签进行过滤
            tags_literal = ", ".join(f"'{tag}'" for tag in all_tags)
            arrays_overlap_condition = f"arrays_overlap(m.tags, [{tags_literal}])"
        # 使用公共函数构建 WHERE 条件和 SELECT 字段
        where_clause = build_ad_where_conditions(
            base_conditions=[arrays_overlap_condition],
            game_platform=request.right_game_platform,
            start_date=request.start_date,
            end_date=request.end_date,
            date_field=request.date_field,
        )
        # 使用合并后的所有字段
        select_fields = build_select_fields(all_stat_columns)
        table_name='ad_daily_detail' if request.origin else "ad_daily_cleaned"
        # 构建统一的SQL
        sql = f"""
        SELECT
            t.tag,
            {', '.join(select_fields)}
        FROM (
            SELECT
                m.unique_name,
                m.tags,
                ad.ad_id,
                ad.date,
                ad.amount_spent, ad.impressions, ad.clicks_all, ad.reach,
                ad.app_installs, ad.purchases, ad.purchases_value, ad.complete_registration,
                ad.subscribe_website, ad.subscribe_website_values,
                ad.inline_link_clicks,
                af.register_users,
                af.first_recharge_users,
                af.same_day_register_first_recharge_users,
                af.d1_purchase_users
            FROM ad_materials m
            JOIN {table_name} ad ON m.unique_name = ad.unique_name
            LEFT JOIN af_day af ON ad.ad_id = af.ad_id
                AND ad.date = af.date
            WHERE {where_clause}
        ) ad
        LATERAL VIEW EXPLODE(ad.tags) t AS tag
        WHERE t.tag IN ({tags_literal})
        GROUP BY t.tag
        """

        # 添加min_spent过滤（仅分支2需要）
        if request.tags and request.min_spent is not None:
            sql += f" HAVING ROUND(SUM(ad.amount_spent), 2) > {request.min_spent}"

        # 执行查询
        doris_data = await db.fetchall(sql, as_dict=True)

        # 步骤4: 统一合并统计数据
        for stats in doris_data:
            tag = stats.get("tag")
            if tag and tag in nodes_dict:
                stats.pop("tag", None)
                nodes_dict[tag].update(stats)

    # 步骤5: 统一构建树并返回
    nodes_list = list(nodes_dict.values())
    tree_data = await build_tree_from_flat_data(nodes_list)

    # 所有列名直接从 all_stat_columns 的 keys 获取
    all_columns = list(all_stat_columns.keys())

    return ApiResponse(
        data={
            "tree_data": tree_data,
            "columns": all_columns,
        }
    )


def flatten_tree_data(
    nodes: List[Dict], columns: List[str], parent_title: str = ""
) -> List[Dict]:
    """将树形数据展平为列表，用于导出Excel"""
    rows = []
    for node in nodes:
        # 构建层级路径
        current_title = node.get("title", "")
        full_path = f"{parent_title}/{current_title}" if parent_title else current_title

        row = {
            "层级路径": full_path,
            "标签名称": current_title,
            "层级": node.get("level", 1),
        }

        # 添加统计列
        for col in columns:
            row[col] = node.get(col, 0)

        rows.append(row)

        # 递归处理子节点
        children = node.get("children", [])
        if children:
            rows.extend(flatten_tree_data(children, columns, full_path))

    return rows


@router_edit.post("/tree_data/export")
async def export_tree_data_to_excel(
    request: TreeDataStatsRequest,
    db=Depends(get_db),
):
    """导出树形标签统计数据为Excel文件"""
    response = await get_tree_data_with_stats(request, db)
    data = response.data

    tree_data = data["tree_data"]
    columns = data["columns"]

    flat_data = flatten_tree_data(tree_data, columns)
    df = pd.DataFrame(flat_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="标签统计数据")

    output.seek(0)

    filename = f"标签统计数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_content = base64.b64encode(output.read()).decode("utf-8")

    return ApiResponse(
        data={
            "filename": filename,
            "content": file_content,
        }
    )


@router_edit.post("/")
async def add_tree_tag(tag_data: TreeTagCreate):
    """添加新的树形标签节点（子节点）"""
    current_time = datetime.now(timezone.utc)

    # 生成key
    doc = await tree_tags_collection.find_one(
        {"parent_id": tag_data.parent_id}, sort=[("created_at", -1)]
    )
    num = doc["_id"].split("-")[-1] if doc else 0
    parent_id = f"{tag_data.parent_id}-" if tag_data.parent_id else ""
    new_key = f"{parent_id}{int(num) + 1}"

    new_node = {
        "title": tag_data.title,
        "_id": new_key,
        "level": tag_data.level,
        "parent_id": tag_data.parent_id,
        "config_id": tag_data.config_id,
        "real_name": tag_data.real_name,
        "created_at": current_time,
        "updated_at": current_time,
    }
    await tree_tags_collection.insert_one(new_node)
    return ApiResponse(data=None, message="success")


@router_edit.delete("/{key}")
async def delete_tree_tag(key: str, db=Depends(get_db)):
    """删除树形标签节点及其所有子节点"""
    node = await tree_tags_collection.find_one({"_id": key})
    if not node:
        return ErrResponse(code=404, message="节点不存在")

    # 基于分层 key 的前缀快速匹配（如 1-2 会匹配 1-2 及其子 1-2-3）
    pattern = f"^{re.escape(key)}($|-)"

    # 先查出要删除的具体标签列表
    tags_to_delete = []
    cursor = tree_tags_collection.find(
        {"_id": {"$regex": pattern}}, projection={"_id": 1}
    )
    async for doc in cursor:
        tags_to_delete.append(doc["_id"])

    if not tags_to_delete:
        return ErrResponse(code=404, message="节点不存在")

    # 先查询包含这些标签的materials的basename（在删除之前）
    affected_basenames_cursor = materials_collection.find(
        {"tags_new": {"$in": tags_to_delete}}, {"basename": 1}
    )
    affected_basenames = [doc["basename"] async for doc in affected_basenames_cursor]

    # 从 materials.tags_new 中移除标签
    await materials_collection.update_many(
        {"tags_new": {"$in": tags_to_delete}},
        {"$pull": {"tags_new": {"$in": tags_to_delete}}},
    )

    # 从material_commons 公共素材中删除标签
    await commons_collection.update_many(
        {"tags_new": {"$in": tags_to_delete}},
        {"$pull": {"tags_new": {"$in": tags_to_delete}}},
    )

    # 从Doris中删除标签
    if affected_basenames:
        await remove_tags_from_doris(db, affected_basenames, tags_to_delete)

    # 删除树节点（自身及子节点）
    result = await tree_tags_collection.delete_many({"_id": {"$in": tags_to_delete}})
    if result.deleted_count > 0:
        return ApiResponse(
            data={
                "message": "节点删除成功",
                "deleted_count": result.deleted_count,
                "deleted_key": key,
            }
        )
    else:
        return ErrResponse(code=404, message="节点不存在")


class TreeTagUpdate(BaseModel):
    title: Optional[str] = None


@router_edit.put("/{key}")
async def update_tree_tag(key: str, payload: TreeTagUpdate):
    """更新树形标签节点标题"""
    current_time = datetime.now(timezone.utc)

    update_fields = {"updated_at": current_time}
    if payload.title is not None:
        update_fields["title"] = payload.title

    if len(update_fields) == 1:  # 仅包含 updated_at，未提供可更新字段
        return ErrResponse(code=400, message="未提供需要更新的字段")

    result = await tree_tags_collection.update_one(
        {"_id": key}, {"$set": update_fields}
    )

    if result.modified_count > 0:
        return ApiResponse(data=None, message="success")
    else:
        return ErrResponse(code=404, message="节点不存在")


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_tags())
    print("标签初始化完成！")
