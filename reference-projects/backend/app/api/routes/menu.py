from typing import List, Optional, Set

from bson import ObjectId
from fastapi import APIRouter, Depends

from app.core.security import auth_current_user, require_roles
from app.db.mongo import user_cols
from app.model_type_defs.common_models import ErrResponse, ApiResponse
from app.model_type_defs.menu_models import MenuItem
from app.model_type_defs.user_models import UserModel, Roles

router = APIRouter(prefix="/menus", tags=["user"])

collection = user_cols.menu
collection_role = user_cols.role


def _is_accessible(menu: dict, user_roles: Set[str]) -> bool:
    restricted = menu.get("restricted_roles")
    if not restricted:
        return True
    return bool(user_roles & set(restricted))


# 辅助函数：构建菜单树并排序
def build_menu_tree(menus: List[dict]) -> List[dict]:
    # 创建菜单ID到菜单的映射，并为菜单添加children属性
    menu_map = {str(menu["_id"]): menu for menu in menus}
    root_menus = []

    # 构建菜单树
    for menu in menus:
        # 只在有子菜单时才添加children属性
        if menu.get("pid") and str(menu["pid"]) in menu_map:
            parent = menu_map[str(menu["pid"])]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(menu)
        else:
            root_menus.append(menu)

    # 递归排序
    def sort_menus(menu_list):
        menu_list.sort(key=lambda x: x.get("meta", {}).get("order", 0))
        for menu in menu_list:
            if "children" in menu:
                sort_menus(menu["children"])

    sort_menus(root_menus)
    return root_menus


@router.post(
    "/",
    summary="创建菜单",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def create_menu(menu: MenuItem):
    if menu.pid:
        one = await collection.find_one({"_id": ObjectId(menu.pid)}, {"_id": 1})
        if not one:
            return ErrResponse(code=404, message="Parent menu not found")
    menu_dict = menu.model_dump(exclude_none=True)
    result = collection.insert_one(menu_dict)
    return ApiResponse(data=menu)


@router.get(
    "/all",
    summary="查询全部菜单(管理员)",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def get_all_menus():
    all_menus = []
    async for menu in collection.find():
        menu["_id"] = str(menu["_id"])
        all_menus.append(menu)
    # 构建菜单树并排序
    root_menus = build_menu_tree(all_menus)
    return ApiResponse(data=root_menus)


@router.get("/", summary="查询当前用户可访问的菜单")
async def get_current_user_menus(current_user: UserModel = Depends(auth_current_user)):
    user_roles: Set[str] = set(current_user.roles or [])
    is_admin = Roles.ADMIN in user_roles

    all_menus = []
    if is_admin:
        async for menu in collection.find():
            menu["_id"] = str(menu["_id"])
            if _is_accessible(menu, user_roles):
                all_menus.append(menu)
    else:
        # 一次查询拿所有角色的 permissions
        visible_menu_ids: Set[str] = set()
        async for role_doc in collection_role.find({"name": {"$in": list(user_roles)}}):
            visible_menu_ids.update(p for p in (role_doc.get("permissions") or []) if p)

        if visible_menu_ids:
            async for menu in collection.find(
                {"_id": {"$in": [ObjectId(mid) for mid in visible_menu_ids]}, "status": 1}
            ):
                menu["_id"] = str(menu["_id"])
                if _is_accessible(menu, user_roles):
                    all_menus.append(menu)

    return ApiResponse(data=build_menu_tree(all_menus))


@router.get("/path")
async def get_path(_id: Optional[str] = None, path: Optional[str] = None):
    query_filter = {}
    if _id:
        query_filter["_id"] = {"$ne": ObjectId(_id)}
    if path:
        query_filter["path"] = path
    menu = await collection.find_one(query_filter, projection={"_id": 1})
    if menu:
        return ApiResponse(data=True)
    return ApiResponse(data=False)


@router.get("/name")
async def get_name(_id: Optional[str] = None, name: Optional[str] = None):
    query_filter = {}
    if _id:
        query_filter["_id"] = {"$ne": ObjectId(_id)}
    if name:
        query_filter["name"] = name
    menu = await collection.find_one(query_filter, projection={"_id": 1})
    if menu:
        return ApiResponse(data=True)
    return ApiResponse(data=False)


@router.get("/{_id}", summary="根据 ID 查询菜单")
async def get_menu(_id: str):
    menu = await collection.find_one({"_id": ObjectId(_id)})
    if menu:
        menu["_id"] = str(menu["_id"])
        return ApiResponse(data=menu)
    return ErrResponse(code=404, message="Menu not found")


@router.put(
    "/{menu_id}",
    summary="更新菜单",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def update_menu(menu_id: str, updated_menu: MenuItem):
    result = await collection.update_one(
        {"_id": ObjectId(menu_id)}, {"$set": updated_menu.model_dump(exclude_none=True)}
    )
    if result.modified_count:
        menu = await collection.find_one({"_id": ObjectId(menu_id)})
        menu["_id"] = str(menu["_id"])
        return ApiResponse(data=menu)
    return ErrResponse(code=404, message="Menu not found or update failed")


@router.delete(
    "/{menu_id}",
    summary="删除菜单",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def delete_menu(menu_id: str):
    result = await collection.delete_one({"_id": ObjectId(menu_id)})
    if result.deleted_count:
        return ApiResponse(data={"message": "Menu deleted successfully"})
    return ErrResponse(code=404, message="Menu not found")
