import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, Depends, status, UploadFile, File, Form

from app.core.security import auth_current_user
from app.db.mongo import cols, trash
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.utils.file_util import convert_minio_url_to_https
from app.model_type_defs.file_type import FileExtensions
from app.model_type_defs.platform_models import (
    CategoryNodeCreate,
    CategoryNodeUpdate,
)
from app.model_type_defs.user_models import UserModel
from app.utils.file_util import calculate_hash

router = APIRouter(
    prefix="/material-category",
    tags=["素材分类"],
)

collection = cols.material_category
collection_trash = trash.material_category
platform_collection = cols.platform_config


# ==================== 辅助函数 ====================


async def unlink_category_from_platforms(category_id: str):
    """从所有 platform_config 中移除对该分类的引用"""
    await platform_collection.update_many(
        {"material_category_ids": category_id},
        {"$pull": {"material_category_ids": category_id}},
    )


async def soft_delete_category(category_id: str, current_user_name: str):
    """
    软删除素材分类:
    1. 移动到 trash 集合
    2. 从 material_category 删除
    3. 从所有 platform_config.material_category_ids 中移除引用
    """
    config = await collection.find_one_and_delete({"_id": ObjectId(category_id)})
    if config:
        config["delete_time"] = datetime.now().strftime(SecondFormat)
        config["deleted_by"] = current_user_name
        config["original_id"] = str(config["_id"])
        config["_id"] = ObjectId()
        await collection_trash.insert_one(config)

    await unlink_category_from_platforms(category_id)


async def soft_delete_sub_category(
    category_id: str, sub_category_id: str, current_user_name: str
):
    """
    软删除二级分类:
    1. 从一级分类中找到该二级分类
    2. 移动到 trash 集合
    3. 从一级分类的 sub_categories 中移除
    """
    doc = await collection.find_one(
        {"_id": ObjectId(category_id), "sub_categories.id": sub_category_id},
        {"sub_categories.$": 1, "name": 1},
    )
    if doc and doc.get("sub_categories"):
        sub_category = doc["sub_categories"][0]
        trash_record = {
            "_id": ObjectId(),
            "type": "sub_category",
            "parent_category_id": category_id,
            "parent_category_name": doc.get("name", ""),
            "sub_category": sub_category,
            "delete_time": datetime.now().strftime(SecondFormat),
            "deleted_by": current_user_name,
        }
        await collection_trash.insert_one(trash_record)

    await collection.update_one(
        {"_id": ObjectId(category_id)},
        {"$pull": {"sub_categories": {"id": sub_category_id}}},
    )


# ==================== 查询接口 ====================


@router.get(
    "/tree/{game_platform}",
    summary="获取分类树",
    description="根据平台获取分类树结构，返回该平台下所有一级分类的 id、name、description 及其二级分类"
)
async def get_category_tree_by_platform(game_platform: str):
    platform = await platform_collection.find_one(
        {"_id": game_platform}, {"material_category_ids": 1}
    )
    if not platform or not platform.get("material_category_ids"):
        return ApiResponse(data=[])

    category_ids = [ObjectId(cid) for cid in platform["material_category_ids"]]
    cursor = collection.find(
        {"_id": {"$in": category_ids}}, {"_id": 1, "name": 1, "description": 1, "sub_categories": 1}
    )
    configs = await cursor.to_list(length=None)

    tree = []
    for config in configs:
        tree.append(
            {
                "id": str(config["_id"]),
                "name": config.get("name", ""),
                "description": config.get("description", ""),
                "children": [
                    {
                        "id": sub.get("id", ""),
                        "name": sub.get("name", ""),
                        "description": sub.get("description", "")
                    }
                    for sub in config.get("sub_categories", [])
                ],
            }
        )

    return ApiResponse(data=tree)


@router.get("/sub-category/{sub_category_id}/contents")
async def get_sub_category_contents(sub_category_id: str):
    """
    根据二级分类ID获取其下的内容列表
    """
    doc = await collection.find_one(
        {"sub_categories.id": sub_category_id}, {"sub_categories.$": 1}
    )
    if not doc or not doc.get("sub_categories"):
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    sub_category = doc["sub_categories"][0]
    contents = []
    for c in sub_category.get("contents", []):
        content = {
            "id": c.get("id", ""),
            "type": c.get("type", ""),
            "text": c.get("text", ""),
            "name": c.get("name", ""),
            "remark": c.get("remark"),
            "url": get_minio_url(c["text"]) if c.get("text") else None,
        }
        contents.append(content)
    return ApiResponse(
        data={
            "id": sub_category.get("id", ""),
            "name": sub_category.get("name", ""),
            "contents": contents,
        }
    )


# ==================== 一级分类操作接口 ====================


@router.post("/{game_platform}/category")
async def create_category(
    game_platform: str,
    data: CategoryNodeCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    """新增一级分类并关联到平台"""
    platform = await platform_collection.find_one({"_id": game_platform})
    if not platform:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="游戏平台不存在")

    now = datetime.now().strftime(SecondFormat)
    category_data = {
        "name": data.name,
        "sub_categories": [],
        "create_time": now,
        "update_time": now,
        "created_by": current_user.username,
    }

    # 如果提供了 description，则保存
    if data.description is not None:
        category_data["description"] = data.description

    result = await collection.insert_one(category_data)
    category_id = str(result.inserted_id)

    await platform_collection.update_one(
        {"_id": game_platform},
        {"$addToSet": {"material_category_ids": category_id}},
    )

    response_data = {"id": category_id, "name": data.name, "children": []}
    if data.description is not None:
        response_data["description"] = data.description

    return ApiResponse(
        data=response_data,
        message="创建成功",
    )


@router.put("/category/{category_id}")
async def update_category(
    category_id: str,
    data: CategoryNodeUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    """修改一级分类名称和描述"""
    if not ObjectId.is_valid(category_id):
        return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="无效的分类ID格式")

    category = await collection.find_one({"_id": ObjectId(category_id)})
    if not category:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该分类")

    # 构建更新字段
    update_fields = {
        "update_time": datetime.now().strftime(SecondFormat),
        "updated_by": current_user.username,
    }

    # 只更新提供的字段
    if data.name is not None:
        update_fields["name"] = data.name
    if data.description is not None:
        update_fields["description"] = data.description

    await collection.update_one(
        {"_id": ObjectId(category_id)},
        {"$set": update_fields},
    )

    # 获取更新后的完整数据
    updated_category = await collection.find_one({"_id": ObjectId(category_id)})
    response_data = {
        "id": category_id,
        "name": updated_category.get("name"),
        "description": updated_category.get("description"),
    }

    return ApiResponse(data=response_data, message="更新成功")


@router.delete("/{game_platform}/category/{category_id}")
async def delete_category(
    game_platform: str,
    category_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除一级分类（软删除）"""
    if not ObjectId.is_valid(category_id):
        return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="无效的分类ID格式")

    category = await collection.find_one({"_id": ObjectId(category_id)})
    if not category:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该分类")

    await soft_delete_category(category_id, current_user.username)
    return ApiResponse(data=None, message="删除成功")


# ==================== 二级分类操作接口 ====================


@router.post("/category/{category_id}/sub-category")
async def create_sub_category(
    category_id: str,
    data: CategoryNodeCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    """新增二级分类"""
    if not ObjectId.is_valid(category_id):
        return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="无效的分类ID格式")

    category = await collection.find_one({"_id": ObjectId(category_id)})
    if not category:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该一级分类")

    sub_category_id = str(uuid4())
    sub_category = {
        "id": sub_category_id,
        "name": data.name,
        "contents": [],
    }

    # 如果提供了 description，则保存
    if data.description is not None:
        sub_category["description"] = data.description

    await collection.update_one(
        {"_id": ObjectId(category_id)},
        {
            "$push": {"sub_categories": sub_category},
            "$set": {
                "update_time": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    response_data = {"id": sub_category_id, "name": data.name}
    if data.description is not None:
        response_data["description"] = data.description

    return ApiResponse(
        data=response_data,
        message="创建成功",
    )


@router.put("/category/{category_id}/sub-category/{sub_category_id}")
async def update_sub_category(
    category_id: str,
    sub_category_id: str,
    data: CategoryNodeUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    """修改二级分类名称和描述"""
    if not ObjectId.is_valid(category_id):
        return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="无效的分类ID格式")

    # 构建更新字段
    update_fields = {
        "update_time": datetime.now().strftime(SecondFormat),
        "updated_by": current_user.username,
    }

    # 只更新提供的字段
    if data.name is not None:
        update_fields["sub_categories.$.name"] = data.name
    if data.description is not None:
        update_fields["sub_categories.$.description"] = data.description

    result = await collection.update_one(
        {"_id": ObjectId(category_id), "sub_categories.id": sub_category_id},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    # 获取更新后的完整数据
    doc = await collection.find_one(
        {"_id": ObjectId(category_id), "sub_categories.id": sub_category_id},
        {"sub_categories.$": 1}
    )
    sub_category = doc["sub_categories"][0] if doc and doc.get("sub_categories") else {}
    response_data = {
        "id": sub_category_id,
        "name": sub_category.get("name"),
        "description": sub_category.get("description"),
    }

    return ApiResponse(
        data=response_data,
        message="更新成功",
    )


@router.delete("/category/{category_id}/sub-category/{sub_category_id}")
async def delete_sub_category(
    category_id: str,
    sub_category_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除二级分类（软删除）"""
    if not ObjectId.is_valid(category_id):
        return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="无效的分类ID格式")

    doc = await collection.find_one(
        {"_id": ObjectId(category_id), "sub_categories.id": sub_category_id}
    )
    if not doc:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    await soft_delete_sub_category(category_id, sub_category_id, current_user.username)

    await collection.update_one(
        {"_id": ObjectId(category_id)},
        {
            "$set": {
                "update_time": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            }
        },
    )

    return ApiResponse(data=None, message="删除成功")


# ==================== 内容操作接口 ====================

CONTENT_BUCKET = buckets.content


def get_content_type(filename: str) -> str:
    """根据文件扩展名获取 content_type"""
    ext = Path(filename).suffix.lower()
    content_type_map = {
        # 图片
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".avif": "image/avif",
        ".heic": "image/heic",
        ".tiff": "image/tiff",
        # 视频
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv",
        ".webm": "video/webm",
    }
    return content_type_map.get(ext, "application/octet-stream")


async def upload_to_minio(
    file_content: bytes,
    original_filename: str,
    product_id: str = "",
    category_id: str = "",
) -> str:
    """
    上传文件到 MinIO
    返回存储路径: {md5_hash[:8]}.{ext}（存储在根目录）
    """
    file_md5 = calculate_hash(file_content)
    ext = Path(original_filename).suffix.lower()
    filename = f"{file_md5[:8]}{ext}"
    # 直接使用文件名，不添加子目录
    object_name = filename
    content_type = get_content_type(original_filename)

    await asyncio.to_thread(
        minio_client.put_object,
        CONTENT_BUCKET,
        object_name,
        BytesIO(file_content),
        length=len(file_content),
        content_type=content_type,
    )

    return object_name


async def delete_from_minio(object_name: str):
    """从 MinIO 删除文件"""
    try:
        await asyncio.to_thread(
            minio_client.remove_object,
            CONTENT_BUCKET,
            object_name,
        )
    except Exception:
        pass  # 忽略删除错误


def get_minio_url(object_name: str) -> Optional[str]:
    """生成 MinIO 文件的完整访问 URL"""
    if not object_name:
        return None
    url = minio_client.presigned_get_object(
        CONTENT_BUCKET,
        object_name,
        expires=timedelta(days=7),
    )
    return convert_minio_url_to_https(url)


async def soft_delete_content(
    sub_category_id: str,
    content_id: str,
    current_user_name: str,
) -> Optional[str]:
    """
    软删除内容:
    1. 从二级分类中找到该内容
    2. 移动到 trash 集合
    3. 返回 MinIO 文件路径用于删除
    """
    doc = await collection.find_one(
        {"sub_categories.id": sub_category_id},
        {"sub_categories.$": 1, "name": 1, "_id": 1},
    )
    if not doc or not doc.get("sub_categories"):
        return None

    sub_category = doc["sub_categories"][0]
    content = None
    for c in sub_category.get("contents", []):
        if c.get("id") == content_id:
            content = c
            break

    if not content:
        return None

    # 记录到 trash
    trash_record = {
        "_id": ObjectId(),
        "type": "content",
        "parent_category_id": str(doc["_id"]),
        "parent_category_name": doc.get("name", ""),
        "sub_category_id": sub_category_id,
        "sub_category_name": sub_category.get("name", ""),
        "content": content,
        "delete_time": datetime.now().strftime(SecondFormat),
        "deleted_by": current_user_name,
    }
    await collection_trash.insert_one(trash_record)

    return content.get("text")  # 返回 MinIO 路径


@router.post("/sub-category/{sub_category_id}/content")
async def create_content(
    sub_category_id: str,
    file: Optional[UploadFile] = File(None),
    name: str = Form(...),
    remark: Optional[str] = Form(None),
    current_user: UserModel = Depends(auth_current_user),
):
    """新增内容（上传文件到 MinIO）"""
    # 查找包含该二级分类的一级分类
    doc = await collection.find_one(
        {"sub_categories.id": sub_category_id},
        {"_id": 1},
    )
    if not doc:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    object_name = None
    file_type_value = None

    if file:
        # 读取文件内容
        file_content = await file.read()

        # 获取文件类型
        try:
            file_type = FileExtensions.classify_by_extension(file.filename)
        except ValueError:
            return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="不支持的文件格式")

        # 上传到 MinIO（存储在根目录）
        object_name = await upload_to_minio(file_content, file.filename)
        file_type_value = file_type.value

    # 创建内容记录
    content_id = str(uuid4())
    content = {
        "id": content_id,
        "type": file_type_value,
        "text": object_name,
        "name": name,
        "remark": remark,
    }

    # 添加到二级分类的 contents 数组
    await collection.update_one(
        {"_id": doc["_id"], "sub_categories.id": sub_category_id},
        {
            "$push": {"sub_categories.$.contents": content},
            "$set": {
                "update_time": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    return ApiResponse(
        data={**content, "url": get_minio_url(object_name) if object_name else None},
        message="创建成功",
    )


@router.put("/sub-category/{sub_category_id}/content/{content_id}")
async def update_content(
    sub_category_id: str,
    content_id: str,
    file: Optional[UploadFile] = File(None),
    name: Optional[str] = Form(None),
    remark: Optional[str] = Form(None),
    current_user: UserModel = Depends(auth_current_user),
):
    """修改内容（可选重新上传文件）"""
    # 查找包含该内容的文档
    doc = await collection.find_one(
        {"sub_categories.id": sub_category_id},
        {"_id": 1, "sub_categories.$": 1},
    )
    if not doc or not doc.get("sub_categories"):
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    sub_category = doc["sub_categories"][0]
    old_content = None
    content_index = -1
    for i, c in enumerate(sub_category.get("contents", [])):
        if c.get("id") == content_id:
            old_content = c
            content_index = i
            break

    if old_content is None:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该内容")

    new_object_name = old_content.get("text")
    new_type = old_content.get("type")

    # 如果上传了新文件
    if file:
        file_content = await file.read()
        try:
            file_type = FileExtensions.classify_by_extension(file.filename)
        except ValueError:
            return ErrResponse(code=status.HTTP_400_BAD_REQUEST, message="不支持的文件格式")

        # 删除旧文件
        if old_content.get("text"):
            await delete_from_minio(old_content["text"])

        # 上传新文件（存储在根目录）
        new_object_name = await upload_to_minio(file_content, file.filename)
        new_type = file_type.value

    # 构建更新后的内容
    updated_content = {
        "id": content_id,
        "type": new_type,
        "text": new_object_name,
        "name": name if name is not None else old_content.get("name"),
        "remark": remark if remark is not None else old_content.get("remark"),
    }

    # 更新数据库
    await collection.update_one(
        {"_id": doc["_id"], "sub_categories.id": sub_category_id},
        {
            "$set": {
                f"sub_categories.$.contents.{content_index}": updated_content,
                "update_time": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    return ApiResponse(
        data={**updated_content, "url": get_minio_url(new_object_name)},
        message="更新成功",
    )


@router.delete("/sub-category/{sub_category_id}/content/{content_id}")
async def delete_content(
    sub_category_id: str,
    content_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除内容（从 MinIO 删除文件）"""
    # 查找包含该内容的文档
    doc = await collection.find_one(
        {"sub_categories.id": sub_category_id},
        {"_id": 1, "sub_categories.$": 1},
    )
    if not doc or not doc.get("sub_categories"):
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该二级分类")

    sub_category = doc["sub_categories"][0]
    content_exists = any(
        c.get("id") == content_id for c in sub_category.get("contents", [])
    )
    if not content_exists:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到该内容")

    # 软删除并获取 MinIO 路径
    minio_path = await soft_delete_content(
        sub_category_id, content_id, current_user.username
    )

    # 从数据库中移除内容
    await collection.update_one(
        {"_id": doc["_id"], "sub_categories.id": sub_category_id},
        {
            "$pull": {"sub_categories.$.contents": {"id": content_id}},
            "$set": {
                "update_time": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    # 从 MinIO 删除文件
    if minio_path:
        await delete_from_minio(minio_path)

    return ApiResponse(data=None, message="删除成功")


# ==================== URL 获取接口 ====================


@router.get("/url/{object_name:path}")
async def get_content_url(object_name: str):
    """
    根据 MinIO 对象路径获取访问 URL
    object_name 格式如: default/default/7ca646fa.jpg
    """
    url = minio_client.presigned_get_object(
        CONTENT_BUCKET,
        object_name,
        expires=timedelta(minutes=10),
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data={"url": url, "object_name": object_name})