from datetime import datetime, timedelta
import re
import secrets
from typing import Literal, List, Optional
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Response, status as Status
from pydantic import BaseModel, field_validator

from app.core.security import (
    require_roles,
    oauth2_scheme,
    auth_current_user,
    make_forward_token,
    public,
)
from app.db.mongo import user_cols, trash
from app.model_type_defs.common_models import ErrResponse, ApiResponse, SecondFormat
from app.model_type_defs.user_models import (
    Roles,
    RoleCreate,
    RoleUpdate,
    UserModel,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["user"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
role_router = APIRouter(prefix="/roles", tags=["role"])

collection = user_cols.user
collection_role = user_cols.role


@router.get("/department_scope", summary="获取部门范围内的用户ID以及用户name")
async def get_department_scope(current_user: UserModel = Depends(auth_current_user)):
    cursor = await collection.find(
        {"department": current_user.department},
        {"_id": 1, "full_name": 1, "real_name": 1},
    ).to_list(length=None)
    return ApiResponse(
        data=[
            {
                "user_id": str(user["_id"]),
                "username": user["full_name"],
                "real_name": user["real_name"],
            }
            for user in cursor
        ]
    )


@auth_router.get("/codes")
def auth_codes():
    return ApiResponse(data=[])


@auth_router.get(
    "/service-token",
    summary="签发转发 token,供同源兄弟服务(automationApi/aiReport)按 Bearer 识别用户",
)
async def service_token(current_user: UserModel = Depends(auth_current_user)):
    return ApiResponse(data=make_forward_token(current_user.id, current_user.roles))


@auth_router.post("/logout")
@public
async def logout():
    return ApiResponse(data=None)


@auth_router.get(
    "/introspect",
    summary="供 nginx auth_request 使用，校验 token 并以 header 返回用户信息",
)
async def introspect(current_user: UserModel = Depends(auth_current_user)):
    return Response(
        status_code=204,
        headers={
            "X-User-Id": str(current_user.id),
            "X-User-Name": quote(current_user.username),
            "X-User-Roles": ",".join(current_user.roles),
            "X-User-Dept": quote(current_user.department or ""),
        },
    )


@router.get("/names")
async def list_real_names(
    roles: List[Literal["operator", "operator_leader", "creator"]] = Query(...),
    scoped: bool = Query(False),
    current_user: UserModel = Depends(auth_current_user),
):
    # 数据权限（scoped=True 时生效）：admin 全部，operator_leader 本部门，operator/creator 仅本人
    query = {"roles": {"$in": roles}}
    if scoped and Roles.ADMIN not in current_user.roles:
        if Roles.OPERATOR_LEADER in current_user.roles:
            query["department"] = current_user.department
        else:
            query["real_name"] = current_user.real_name
    cursor = collection.find(
        query,
        projection={"_id": 0, "real_name": 1},
    )

    users = await cursor.to_list(length=None)  # length=None 表示取所有结果
    real_names = [u["real_name"] for u in users]
    return ApiResponse(data=real_names)


@router.get("/full_names")
async def list_full_names(
    roles: List[Literal["operator", "operator_leader", "creator"]] = Query([]),
    department: Optional[str] = Query(None),
):
    """启用状态用户的 full_name：roles 和 department 都可选，同传取交集，都不传返回全部"""
    # status 缺失按启用算（与 security.py 的 get("status", 1) 对齐），故用 $ne 0 而非 == 1
    query = {"status": {"$ne": 0}}
    if roles:
        query["roles"] = {"$in": roles}
    if department:
        query["department"] = department
    cursor = collection.find(query, projection={"_id": 0, "full_name": 1})

    users = await cursor.to_list(length=None)  # length=None 表示取所有结果
    full_names = [u["full_name"] for u in users if u.get("full_name")]
    return ApiResponse(data=full_names)


@router.get("/roles_user", summary="查询全部素材师用户")
async def search_users(current_user: UserModel = Depends(auth_current_user)):
    cursor = collection.find(
        {"roles": "creator",},
        projection={"_id": 1, "real_name": 1, "full_name": 1, "roles": 1},
    )
    users = await cursor.to_list(length=None)
    return ApiResponse(
        data=[
            {
                "user_id": str(u["_id"]),
                "real_name": u.get("real_name"),
                "full_name": u.get("full_name"),
                "roles": u.get("roles", []),
            }
            for u in users
        ]
    )


@router.get("/department_options")
async def list_user_department_options():
    departments = await collection.distinct("department")
    options = sorted({department for department in departments if department})
    return ApiResponse(data=options)


@router.get(
    "/", dependencies=[Depends(require_roles([Roles.ADMIN]))], summary="获取所有用户"
)
async def list_users(
    full_name: Optional[str] = None,
    real_name: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[int] = None,
    startTime: Optional[str] = None,
    endTime: Optional[str] = None,
    page: Optional[int] = 1,
    pageSize: Optional[int] = 20,
):
    query = {}
    if full_name:
        query["full_name"] = {"$regex": re.escape(full_name), "$options": "i"}
    if real_name:
        query["real_name"] = {"$regex": re.escape(real_name), "$options": "i"}
    if department:
        query["department"] = department
    if status is not None:
        query["status"] = status
    if startTime and endTime:
        query["create_time"] = {"$gte": startTime, "$lte": endTime}

    skip = (page - 1) * pageSize
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("_id", -1).skip(skip).limit(pageSize)
    users = await cursor.to_list(length=pageSize)

    items = []
    for user in users:
        user_dict = UserModel(**user).model_dump()
        user_dict["_id"] = str(user["_id"])
        user_dict["createTime"] = user["create_time"]
        user_dict["api_keys"] = [
            {**k, "key": k["key"][:5] + "..." + k["key"][-4:]}
            for k in user.get("api_keys", [])
        ]
        items.append(user_dict)

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }
    )


@router.get("/info")
async def get_user(
    token: str = Depends(oauth2_scheme),
    current_user: UserModel = Depends(auth_current_user),
):
    return ApiResponse(
        data={
            "token": token,
            "userId": current_user.id,
            "username": current_user.username,
            "phone": current_user.phone or "",
            "realName": current_user.real_name,
            "roles": current_user.roles,
            "full_name": current_user.full_name or "",
            "department": current_user.department or "",
            "departments": current_user.departments or [],
        }
    )


@router.get(
    "/me", summary="基于会话 cookie(app_session)获取当前用户信息,不依赖 header token"
)
async def get_user_by_session(
    current_user: UserModel = Depends(auth_current_user),
):
    return ApiResponse(
        data={
            "userId": current_user.id,
            "username": current_user.username,
            "phone": current_user.phone or "",
            "realName": current_user.real_name,
            "roles": current_user.roles,
            "full_name": current_user.full_name or "",
            "department": current_user.department or "",
            "departments": current_user.departments or [],
        }
    )


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v):
        if v is None:
            return v
        v = v.strip() if isinstance(v, str) else v
        if not v:
            raise ValueError("用户姓名不能为空")
        return v


@router.put("/me", summary="修改个人信息")
async def update_my_profile(
    body: ProfileUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    update_data = {}

    if body.full_name is not None:
        update_data["full_name"] = body.full_name

    if not update_data:
        return ErrResponse(
            code=Status.HTTP_400_BAD_REQUEST, message="没有需要更新的字段"
        )

    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    await collection.update_one(
        {"username": current_user.username},
        {"$set": update_data},
    )
    return ApiResponse(data={"message": "更新成功"})


@router.put("/{user_id}", dependencies=[Depends(require_roles([Roles.ADMIN]))])
async def update_user(user_id: str, user_update: UserUpdate):
    user = await collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        return ErrResponse(code=Status.HTTP_404_NOT_FOUND, message="未找到用户")

    update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}

    update_data.pop("password", None)
    update_data.pop("username", None)
    update_data.pop("phone", None)

    if "real_name" in update_data and update_data["real_name"] != user["real_name"]:
        if await collection.find_one(
            {"real_name": update_data["real_name"], "_id": {"$ne": ObjectId(user_id)}}
        ):
            return ErrResponse(
                code=Status.HTTP_400_BAD_REQUEST, message="英文昵称已存在"
            )

    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    await collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

    updated_user = await collection.find_one({"_id": ObjectId(user_id)})
    updated_user_dict = UserModel(**updated_user).model_dump()
    updated_user_dict["id"] = str(updated_user["_id"])

    return ApiResponse(data=updated_user_dict)


@router.delete("/{user_id}", dependencies=[Depends(require_roles([Roles.ADMIN]))])
async def delete_user(user_id: str):
    result = await collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        return ErrResponse(code=Status.HTTP_404_NOT_FOUND, message="未找到用户")
    return ApiResponse(data=None, message="User deleted")


class ApiKeyCreate(BaseModel):
    name: str
    remark: Optional[str] = None
    expires_days: int  # 必填，1~90 天


@router.get(
    "/{user_id}/apikeys",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
    summary="查询用户所有 API Key",
)
async def list_apikeys(user_id: str):
    user = await collection.find_one({"_id": ObjectId(user_id)}, {"api_keys": 1})
    if not user:
        return ErrResponse(code=Status.HTTP_404_NOT_FOUND, message="未找到用户")
    keys = [
        {**k, "key": k["key"][:5] + "..." + k["key"][-4:]}
        for k in user.get("api_keys", [])
    ]
    return ApiResponse(data=keys)


@router.post(
    "/{user_id}/apikey",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
    summary="生成新 API Key",
)
async def generate_apikey(user_id: str, body: ApiKeyCreate):
    if not body.name.strip():
        return ErrResponse(code=400, message="名称不能为空")
    if body.expires_days != -1 and not (1 <= body.expires_days <= 90):
        return ErrResponse(code=400, message="过期天数必须为 -1（永不过期）或 1~90 天")
    user = await collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        return ErrResponse(code=Status.HTTP_404_NOT_FOUND, message="未找到用户")
    now = datetime.now()
    api_key = "sk-" + secrets.token_urlsafe(32)
    key_id = secrets.token_hex(8)
    expires_at = (
        None
        if body.expires_days == -1
        else (now + timedelta(days=body.expires_days)).strftime(SecondFormat)
    )
    entry = {
        "id": key_id,
        "name": body.name.strip(),
        "remark": body.remark,
        "key": api_key,
        "expires_at": expires_at,
        "created_at": now.strftime(SecondFormat),
    }
    await collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$push": {"api_keys": entry},
            "$set": {"update_time": now.strftime(SecondFormat)},
        },
    )
    return ApiResponse(
        data={
            "id": key_id,
            "name": entry["name"],
            "remark": entry["remark"],
            "key": api_key,
            "expires_at": expires_at,
        }
    )


@router.delete(
    "/{user_id}/apikey/{key_id}",
    summary="撤销指定 API Key",
)
async def revoke_apikey(
    user_id: str,
    key_id: str,
    operator: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    user = await collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        return ErrResponse(code=Status.HTTP_404_NOT_FOUND, message="未找到用户")
    keys = user.get("api_keys", [])
    target_key = next((k for k in keys if k["id"] == key_id), None)
    if not target_key:
        return ErrResponse(code=404, message="API Key 不存在")

    now = datetime.now().strftime(SecondFormat)
    await trash.api_keys.insert_one(
        {
            **target_key,
            "owner_user_id": user_id,
            "owner_username": user.get("username"),
            "owner_real_name": user.get("real_name"),
            "deleted_by_username": operator.username,
            "deleted_by_real_name": operator.real_name,
            "deleted_at": now,
        }
    )

    await collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$pull": {"api_keys": {"id": key_id}},
            "$set": {"update_time": now},
        },
    )
    return ApiResponse(data={"message": "API Key 已撤销"})


@role_router.post(
    "/", summary="创建角色", dependencies=[Depends(require_roles([Roles.ADMIN]))]
)
async def create_role(role: RoleCreate):
    existing = await collection_role.find_one({"name": role.name})
    if existing:
        return ErrResponse(code=400, message="角色名已存在")
    role_data = role.model_dump()
    role_data["create_time"] = datetime.now().strftime(SecondFormat)
    role_data["update_time"] = role_data["create_time"]

    result = await collection_role.insert_one(role_data)
    created_role = await collection_role.find_one({"_id": result.inserted_id})
    created_role["id"] = str(created_role.pop("_id"))
    return ApiResponse(data=created_role)


@role_router.get(
    "/",
    summary="获取所有角色",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
    response_model=ApiResponse,
)
async def get_all_roles(
    name: str = None,
    status: int = None,
    startTime: str = None,
    endTime: str = None,
    page: int = 1,
    pageSize: int = 20,
):
    query = {}
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    if status is not None:
        query["status"] = status
    if startTime and endTime:
        query["create_time"] = {"$gte": startTime, "$lte": endTime}
    skip = (page - 1) * pageSize
    total = await collection_role.count_documents(query)
    cursor = collection_role.find(query).sort("_id", -1).skip(skip).limit(pageSize)
    items = await cursor.to_list(length=pageSize)

    for item in items:
        item["_id"] = str(item.pop("_id"))
        item["createTime"] = item["create_time"]
    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }
    )


@role_router.get(
    "/{role_id}",
    summary="根据ID获取角色",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def get_role(role_id: str):
    role = await collection_role.find_one({"_id": ObjectId(role_id)})
    if not role:
        return ErrResponse(code=404, message="角色不存在")

    role["id"] = str(role.pop("_id"))
    return ApiResponse(data=role)


@role_router.put(
    "/{role_id}",
    summary="更新角色",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def update_role(role_id: str, role_update: RoleUpdate):
    role = await collection_role.find_one({"_id": ObjectId(role_id)})
    if not role:
        return ErrResponse(code=404, message="角色不存在")
    update_data = {k: v for k, v in role_update.model_dump().items() if v is not None}
    update_data["permissions"] = [
        x for x in update_data["permissions"] if x is not None
    ]
    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    await collection_role.update_one({"_id": ObjectId(role_id)}, {"$set": update_data})
    updated_role = await collection_role.find_one({"_id": ObjectId(role_id)})
    updated_role["id"] = str(updated_role.pop("_id"))
    return ApiResponse(data=updated_role)


@role_router.delete(
    "/{role_id}",
    summary="删除角色",
    dependencies=[Depends(require_roles([Roles.ADMIN]))],
)
async def delete_role(role_id: str):
    role = await collection_role.find_one({"_id": ObjectId(role_id)})
    if not role:
        return ErrResponse(code=404, message="角色不存在")
    users_with_role = await collection.find_one({"roles": role["name"]})
    if users_with_role:
        return ErrResponse(code=400, message="无法删除：有用户正在使用此角色")
    await collection_role.delete_one({"_id": ObjectId(role_id)})
    return ApiResponse(data={"message": "角色删除成功"})
