from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.core.security import auth_current_user, require_roles
from app.db.mongo import cols, trash
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.user_models import UserModel, Roles

router = APIRouter(prefix="/department", tags=["部门配置"])

# MongoDB 集合
collection = cols.department_config
collection_trash = trash.department_config


# Pydantic 模型
class DepartmentConfigCreate(BaseModel):
    name: str = Field(..., description="部门名称")
    parent_id: Optional[str] = Field(None, description="父部门名称，不传为顶级部门")


class DepartmentConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, description="部门名称")
    parent_id: Optional[str] = Field(None, description="父部门名称，传 null 设为顶级部门")


async def get_department_lineage(department: Optional[str]) -> list[str]:
    """部门名 + 所有祖先部门 + 所有后代部门"""
    depts = await collection.find({}, {"name": 1, "parent_id": 1}).to_list(length=None)
    parent_of = {d["name"]: d.get("parent_id") for d in depts}
    children_of: dict[str, list[str]] = {}
    for d in depts:
        if d.get("parent_id"):
            children_of.setdefault(d["parent_id"], []).append(d["name"])

    result = [department]
    current = department
    while parent_of.get(current):
        current = parent_of[current]
        result.append(current)

    frontier = [department]
    while frontier:
        frontier = [c for p in frontier for c in children_of.get(p, [])]
        result.extend(frontier)
    return result


async def get_department_subtree(department: Optional[str]) -> list[str]:
    """部门名 + 所有后代部门（不含父部门，与 get_department_lineage 的区别在这）"""
    depts = await collection.find({}, {"name": 1, "parent_id": 1}).to_list(length=None)
    children_of: dict[str, list[str]] = {}
    for d in depts:
        if d.get("parent_id"):
            children_of.setdefault(d["parent_id"], []).append(d["name"])

    result = [department]
    frontier = [department]
    while frontier:
        frontier = [c for p in frontier for c in children_of.get(p, [])]
        result.extend(frontier)
    return result


async def _is_descendant(ancestor_name: str, node_name: str) -> bool:
    """node_name 是否是 ancestor_name 的后代（沿 parent_id 向上回溯遇到 ancestor 即是）"""
    current = node_name
    while current:
        doc = await collection.find_one({"name": current}, {"parent_id": 1})
        if not doc:
            return False
        current = doc.get("parent_id")
        if current == ancestor_name:
            return True
    return False


def _build_tree(configs: list) -> list:
    """把扁平部门列表按 parent_id（父部门名称）组装成父子树（每个节点带 children）"""
    nodes = {}
    for config in configs:
        config["id"] = str(config.pop("_id"))
        config["children"] = []
        nodes[config["name"]] = config

    roots = []
    for config in nodes.values():
        parent_name = config.get("parent_id")
        if parent_name and parent_name in nodes:
            nodes[parent_name]["children"].append(config)
        else:
            roots.append(config)
    return roots


@router.get("/")
async def get_department_configs(
    page: int = 1,
    pageSize: int = 20,
):
    skip = (page - 1) * pageSize
    total = await collection.count_documents({})
    cursor = collection.find({}).sort("name", 1).skip(skip).limit(pageSize)
    configs = await cursor.to_list(length=pageSize)
    items = []
    for config in configs:
        config["id"] = str(config.pop("_id"))
        items.append(config)
    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }
    )


@router.get("/tree")
async def get_department_tree():
    """树形结构的部门列表：基于各部门的 parent_id（父部门名称）组装成父子树"""
    cursor = collection.find({}).sort("name", 1)
    configs = await cursor.to_list(length=None)
    tree = _build_tree(configs)
    return ApiResponse(data={"items": tree, "total": len(configs)})


@router.post("/", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def create_department_config(
    config_in: DepartmentConfigCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    # 检查部门名称是否已存在
    existing = await collection.find_one({"name": config_in.name})
    if existing:
        return ErrResponse(code=400, message="部门名称已存在")

    if config_in.parent_id and not await collection.find_one(
        {"name": config_in.parent_id}
    ):
        return ErrResponse(code=400, message="父部门不存在")

    config_data = {
        "name": config_in.name,
        "parent_id": config_in.parent_id or None,
        "create_time": datetime.now().strftime(SecondFormat),
        "created_by": current_user.username,
    }
    result = await collection.insert_one(config_data)
    created_config = await collection.find_one({"_id": result.inserted_id})
    created_config["id"] = str(created_config.pop("_id"))
    return ApiResponse(data=created_config, message="创建部门配置成功")


@router.put("/{config_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def update_department_config(
    config_id: str,
    config_update: DepartmentConfigUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    config = await collection.find_one({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到部门配置")

    update_fields = config_update.model_dump(exclude_unset=True)
    update_data = {}

    # 如果修改部门名称，检查新名称是否已存在
    if "name" in update_fields and update_fields["name"]:
        new_name = update_fields["name"]
        if new_name != config["name"]:
            existing = await collection.find_one(
                {"name": new_name, "_id": {"$ne": ObjectId(config_id)}}
            )
            if existing:
                return ErrResponse(code=400, message="部门名称已存在")
        update_data["name"] = new_name

    # 如果修改父部门（显式传入，可能为 null 表示设为顶级）
    if "parent_id" in update_fields:
        new_parent = update_fields["parent_id"]
        if not new_parent:
            update_data["parent_id"] = None
        elif new_parent == config["name"]:
            return ErrResponse(code=400, message="父部门不能是自己")
        elif not await collection.find_one({"name": new_parent}):
            return ErrResponse(code=400, message="父部门不存在")
        elif await _is_descendant(config["name"], new_parent):
            return ErrResponse(code=400, message="不能将子部门设为父部门")
        else:
            update_data["parent_id"] = new_parent

    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    update_data["updated_by"] = current_user.username

    await collection.update_one({"_id": ObjectId(config_id)}, {"$set": update_data})

    # 部门名称变更时，级联更新所有子部门的 parent_id
    if "name" in update_data and update_data["name"] != config["name"]:
        await collection.update_many(
            {"parent_id": config["name"]},
            {"$set": {"parent_id": update_data["name"]}},
        )

    updated_config = await collection.find_one({"_id": ObjectId(config_id)})
    updated_config["id"] = str(updated_config.pop("_id"))

    return ApiResponse(data=updated_config, message="更新部门配置成功")


@router.delete("/{config_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def delete_department_config(
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除部门配置"""
    config = await collection.find_one({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到部门配置")

    # 存在子部门时禁止删除
    if await collection.find_one({"parent_id": config["name"]}):
        return ErrResponse(code=400, message="存在子部门，无法删除")

    await collection.delete_one({"_id": ObjectId(config_id)})

    # 添加删除信息并移动到回收站
    config["delete_time"] = datetime.now().strftime(SecondFormat)
    config["deleted_by"] = current_user.username
    await collection_trash.insert_one(config)

    return ApiResponse(data=None, message="部门配置已删除")


@router.get("/options/")
async def get_department_options():
    """获取部门选项列表，用于下拉选择，只返回末级（叶子）部门名称"""
    parent_names = [p for p in await collection.distinct("parent_id") if p]
    cursor = collection.find(
        {"name": {"$nin": parent_names}}, {"name": 1, "_id": 0}
    ).sort("name", 1)
    departments = await cursor.to_list(length=None)
    options = [dept["name"] for dept in departments]
    return ApiResponse(data=options)
