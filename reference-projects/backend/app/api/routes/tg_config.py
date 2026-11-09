from datetime import datetime
from typing import Optional, List

from bson import ObjectId
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from app.core.security import auth_current_user, require_roles
from app.db.mongo import cols, trash
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.user_models import UserModel, Roles

router = APIRouter(prefix="/telegram-config", tags=["飞机消息配置"])

collection = cols.telegram_config
collection_trash = trash.telegram_config

# Token掩码标识
MASKED_TOKEN_PREFIX = "****"


def mask_token(token: str) -> str:
    """对token进行掩码处理，保留前3位和后3位"""
    if not token or len(token) <= 6:
        return "******"
    return f"{token[:3]}{MASKED_TOKEN_PREFIX}{token[-3:]}"


class PlaneMessageConfig(BaseModel):
    department: str = Field(..., description="部门")
    game_platforms: Optional[List[str]] = Field(None, description="游戏平台")
    message_type: str = Field(..., description="消息类型")
    token: str = Field(..., description="Token")
    chat_id: str = Field(..., description="Chat ID")

    @field_validator("department", "message_type", "token", "chat_id", mode="before")
    @classmethod
    def strip_str(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class PlaneMessageConfigUpdate(BaseModel):
    """用于更新的模型，所有字段都是可选的"""

    department: Optional[str] = Field(None, description="部门")
    game_platforms: Optional[List[str]] = Field(None, description="游戏平台")
    message_type: Optional[str] = Field(None, description="消息类型")
    token: Optional[str] = Field(None, description="Token")
    chat_id: Optional[str] = Field(None, description="Chat ID")


class PlaneMessageConfigResponse(PlaneMessageConfig):
    """用于返回的模型"""

    id: str = Field(..., description="ID")


@router.get("/")
async def get_plane_message_configs(page: int = 1, pageSize: int = 20):
    skip = (page - 1) * pageSize
    total = await collection.count_documents({})
    cursor = collection.find({}).sort("department", 1).skip(skip).limit(pageSize)
    configs = await cursor.to_list(length=pageSize)

    items = []
    for config in configs:
        # 对token进行掩码处理
        if "token" in config and config["token"]:
            config["token"] = mask_token(config["token"])

        # 使用 Response 模型自动过滤字段
        response = PlaneMessageConfigResponse(id=str(config["_id"]), **config)
        items.append(response.model_dump())

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }
    )


@router.post("/", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def create_plane_message_config(
    config_in: PlaneMessageConfig,
    current_user: UserModel = Depends(auth_current_user),
):
    config_data = config_in.model_dump()
    config_data["create_time"] = datetime.now().strftime(SecondFormat)
    config_data["created_by"] = current_user.username

    result = await collection.insert_one(config_data)
    created_config = await collection.find_one({"_id": result.inserted_id})
    created_config["id"] = str(created_config.pop("_id"))

    return ApiResponse(data=created_config, message="创建飞机消息配置成功")


@router.put("/{config_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def update_plane_message_config(
    config_id: str,
    config_update: PlaneMessageConfigUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    # 前端已经只传递修改的字段，直接使用
    update_data = config_update.model_dump(exclude_none=True)

    # 如果没有任何字段需要更新
    if not update_data:
        return ApiResponse(data=None, message="无需更新")

    config = await collection.find_one({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到配置")

    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    update_data["updated_by"] = current_user.username
    await collection.update_one({"_id": ObjectId(config_id)}, {"$set": update_data})

    updated_config = await collection.find_one({"_id": ObjectId(config_id)})
    # 对token进行掩码处理
    if "token" in updated_config and updated_config["token"]:
        updated_config["token"] = mask_token(updated_config["token"])

    # 使用 Response 模型自动过滤字段
    response = PlaneMessageConfigResponse(
        id=str(updated_config["_id"]), **updated_config
    )

    return ApiResponse(data=response.model_dump(), message="更新飞机消息配置成功")


@router.delete(
    "/{config_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def delete_plane_message_config(
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    config = await collection.find_one_and_delete({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到配置")

    config["delete_time"] = datetime.now().strftime(SecondFormat)
    config["deleted_by"] = current_user.username
    await collection_trash.insert_one(config)

    return ApiResponse(data=None, message="飞机消息配置已删除")
