import asyncio
import base64
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Optional, List, TypedDict, BinaryIO
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import UploadFile, File, Form, Query, APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import require_roles, auth_current_user
from app.db.clients import redis_cli
from app.db.mongo import cols
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.ad_sync_models import RunStatus
from app.model_type_defs.common_models import ApiResponse, SecondFormat, ErrResponse
from app.model_type_defs.file_type import FileExtensions
from app.model_type_defs.user_models import Roles, UserModel
from app.utils.file_util import extract_first_frame_from_memory, calculate_sha3_256, convert_minio_url_to_https

router = APIRouter(prefix="/creative", tags=["creative"])


class AIModel(str, Enum):
    QWEN = "qwen"
    GOOGLE = "google"


creative_collection = cols.creative_materials
creative_collection_img = cols.creative_materials_img
tasks_collection = cols.creative_tasks
tasks_collection_img = cols.creative_tasks_img
tasks_collection_run_img = cols.creative_run_tasks_img
UPLOAD_BUCKET = buckets.creative_origin
UPLOAD_BUCKET_IMG = buckets.creative_origin_img
GENERATED_BUCKET = buckets.creative_generated
GENERATED_BUCKET_IMG = buckets.creative_generated_img
REDIS_KEY = "materials:creative:tasks"
REDIS_KEY_IMG = "materials:creative:tasks_img"
MAX_FILE_SIZE = 100 * 1024 * 1024


class FileInfo(TypedDict):
    _id: str
    basename: str


class BulkTaskItem(BaseModel):
    prompt: str
    video_num: int = 1
    file_id: Optional[str] = None
    unique_filename: Optional[str] = None


async def validate_video_file(file: UploadFile):
    if not file.content_type or not file.content_type.startswith("video/"):
        return ErrResponse(code=400, message="只支持视频文件上传")
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in FileExtensions.VIDEO_EXTENSIONS:
        return ErrResponse(
            code=400,
            message=f"不支持的视频格式: {file_ext}，支持的格式: {FileExtensions.VIDEO_EXTENSIONS}",
        )


async def upload_file(file) -> ErrResponse | FileInfo:
    res = await validate_video_file(file)
    if res:
        return res
    file_content = await file.read()
    sha3_256 = calculate_sha3_256(file_content)
    file_metadata = await creative_collection.find_one(
        {"sha3_256": sha3_256}, projection={"_id": 1, "basename": 1}
    )
    if file_metadata:
        file_metadata["_id"] = str(file_metadata["_id"])
        return file_metadata
    if len(file_content) > MAX_FILE_SIZE:
        return ErrResponse(
            code=400,
            message=f"文件大小超过限制 ({MAX_FILE_SIZE // (1024 * 1024)}MB)",
        )
    try:
        filetype = FileExtensions.classify_by_extension(file.filename)
        thumbnail_bytes = await asyncio.to_thread(
            extract_first_frame_from_memory,
            file_content,
            filetype,
        )
        thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode("utf-8")
    except Exception as e:
        thumbnail_b64 = None
    name = str(uuid.uuid1()).replace("-", "")[:16]
    await asyncio.to_thread(
        minio_client.put_object,
        UPLOAD_BUCKET,
        name,
        BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type,
    )
    file_metadata = {
        "upload_filename": file.filename,
        "sha3_256": sha3_256,
        "basename": Path(file.filename).stem,
        "unique_filename": name,
        "file_size": len(file_content),
        "content_type": file.content_type,
        "thumbnail": thumbnail_b64,
        "upload_time": datetime.now(timezone.utc),
    }
    result = await creative_collection.update_one(
        {"sha3_256": file_metadata["sha3_256"]},
        {"$setOnInsert": file_metadata},  # 只在插入时写入
        upsert=True,  # 不存在就插
    )
    return {"_id": str(result.upserted_id), "basename": file_metadata["basename"]}


class CustomUploadFile(UploadFile):
    """Custom UploadFile that can be created from bytes with content_type support"""

    def __init__(self, filename: str, file: BinaryIO, content_type: str = None):
        super().__init__(filename=filename, file=file)
        self._content_type = content_type

    @property
    def content_type(self) -> str:
        return self._content_type


async def create_video_task(
    file: Optional[UploadFile] = None,
    file_id: Optional[str] = None,
    unique_filename: Optional[str] = None,
    prompt: str = "",
    video_num: int = 1,
    current_user: UserModel = None,
):
    if video_num < 1 or video_num > 10:
        raise HTTPException(status_code=400, detail="视频数量必须在1-10之间")
    if unique_filename is not None:
        # 微调情况下, 直接读取生成的文件, 重新走正常上传文件步骤
        file_bytes = await asyncio.to_thread(
            lambda: minio_client.get_object(GENERATED_BUCKET, unique_filename).read()
        )
        content_type, encoding = mimetypes.guess_type(unique_filename)
        file = CustomUploadFile(
            filename=unique_filename,
            file=BytesIO(file_bytes),
            content_type=content_type or "video/mp4",
        )
    if file is not None:
        # 正常上传文件步骤
        file_metadata = await upload_file(file)
        if isinstance(file_metadata, ErrResponse):
            return file_metadata
    else:
        # 已经上传过文件, 重新基于此文件处理
        one = await creative_collection.find_one(
            {"_id": ObjectId(file_id)}, {"_id": 0, "basename": 1}
        )
        file_metadata = {"_id": file_id, "basename": one["basename"]}
    response = await tasks_collection.insert_many(
        [
            {
                "file_id": str(file_metadata["_id"]),
                "basename": file_metadata["basename"],
                "prompt": prompt,
                "video_num": video_num,
                "status": RunStatus.SENDING.value,
                "created_at": datetime.now(timezone.utc).strftime(SecondFormat),
                "real_name": current_user.real_name,
            }
            for i in range(video_num)
        ]
    )
    ids_ = [str(_id) for _id in response.inserted_ids]
    await redis_cli.rpush(REDIS_KEY, *ids_)

    return {
        "task_id": file_metadata["_id"],
        "basename": file_metadata["basename"],
        "video_num": video_num,
        "prompt": prompt,
    }


@router.post(
    "/", dependencies=[Depends(require_roles([*Roles.OPERATOR_ALL, Roles.CREATOR]))]
)
async def upload_creative_material(
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = File(None),
    unique_filename: Optional[str] = Form(None),
    prompt: str = Form(...),
    video_num: int = Form(1),
    current_user: UserModel = Depends(auth_current_user),
):
    result = await create_video_task(
        file=file,
        file_id=file_id,
        unique_filename=unique_filename,
        prompt=prompt,
        video_num=video_num,
        current_user=current_user,
    )
    return ApiResponse(
        code=0,
        data={
            "task_id": result["task_id"],
            "message": f"文件上传成功，创作任务已创建，将生成{result['video_num']}个视频",
        },
    )


@router.post(
    "/bulk", dependencies=[Depends(require_roles([*Roles.OPERATOR_ALL, Roles.CREATOR]))]
)
async def bulk_upload_creative_material(
    bulk_tasks: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: UserModel = Depends(auth_current_user),
):
    # 解析JSON字符串为字典列表，然后转换为Pydantic模型
    try:
        bulk_tasks_data = json.loads(bulk_tasks)
        parsed_bulk_tasks = [BulkTaskItem(**task) for task in bulk_tasks_data]
    except json.JSONDecodeError as e:
        return ErrResponse(code=400, message=f"JSON格式错误: {str(e)}")
    except Exception as e:
        return ErrResponse(code=400, message=f"解析批量任务配置失败: {str(e)}")

    if len(files) != len(parsed_bulk_tasks):
        return ErrResponse(code=400, message="文件数量与任务数量不匹配")

    successful_tasks = []
    failed_tasks = []
    total_videos = 0

    # 逐个处理文件
    for i, (file, task) in enumerate(zip(files, parsed_bulk_tasks)):
        try:
            # 调用抽取的核心方法
            result = await create_video_task(
                file=file,
                file_id=task.file_id,
                unique_filename=task.unique_filename,
                prompt=task.prompt,
                video_num=task.video_num,
                current_user=current_user,
            )

            # 如果是错误响应，记录失败
            if isinstance(result, ErrResponse):
                failed_tasks.append(
                    {"index": i + 1, "filename": file.filename, "error": result.message}
                )
                continue

            # 记录成功
            successful_tasks.append(
                {
                    "index": i + 1,
                    "filename": file.filename,
                    "task_id": result["task_id"],
                    "video_num": result["video_num"],
                    "prompt": result["prompt"],
                }
            )
            total_videos += result["video_num"]

        except Exception as e:
            failed_tasks.append(
                {"index": i + 1, "filename": file.filename, "error": str(e)}
            )

    # 返回处理结果
    result_data = {
        "total_files": len(files),
        "successful_count": len(successful_tasks),
        "failed_count": len(failed_tasks),
        "total_videos": total_videos,
        "successful_tasks": successful_tasks,
    }

    if failed_tasks:
        result_data["failed_tasks"] = failed_tasks
    message = f"批量上传完成: 成功{len(successful_tasks)}个文件，失败文件:{failed_tasks}，总计将生成{total_videos}个视频"
    result_data["message"] = message
    return ApiResponse(data=result_data)


@router.get("/")
async def list_creative_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    skip: int = Query(0, ge=0),
    basename: Optional[str] = Query(None, description="文件名(无后缀)"),
    real_name: Optional[str] = Query(None),
):
    query = {"status": {"$in": [RunStatus.COMPLETED.value, RunStatus.FAILED.value]}}
    if basename:
        query["basename"] = basename
    if real_name:
        query["real_name"] = real_name
    skip = (page - 1) * page_size + skip
    cursor = (
        tasks_collection.find(
            query,
            projection={
                "file_id": 1,
                "basename": 1,
                "prompt": 1,
                "video_num": 1,
                "created_at": 1,
                "real_name": 1,
                "thumbnail": 1,
                "unique_filename": 1,
                "status": 1,
            },
        )
        .sort("_id", -1)
        .skip(skip)
        .limit(page_size)
    )
    materials = []
    async for material in cursor:
        material["created_at"] = (
            datetime.strptime(material["created_at"], SecondFormat)
            .replace(tzinfo=timezone.utc)
            .astimezone(timezone(timedelta(hours=8)))
            .strftime(SecondFormat)
        )
        material["_id"] = str(material.pop("_id"))
        materials.append(material)
    has_more = len(materials) == page_size
    return ApiResponse(
        data={
            "materials": materials,
            "has_more": has_more,
        }
    )


@router.get("/running/")
async def list_creative_tasks_running(
    basename: Optional[str] = Query(None, description="文件名(无后缀)"),
    real_name: Optional[str] = Query(None),
):
    # 构建基础查询条件（不包含real_name）
    base_conditions = {
        "status": {"$in": [RunStatus.SENDING.value, RunStatus.STARTED.value]}
    }
    if basename:
        base_conditions["basename"] = basename

    # 构建完整查询条件（包含real_name）
    match_conditions = base_conditions.copy()
    if real_name:
        match_conditions["real_name"] = real_name

    # 统计等待数量（不受real_name过滤影响）
    wait_num = await tasks_collection.count_documents(base_conditions)

    # 使用聚合管道优化查询，一次性获取所有需要的数据
    pipeline = [
        {"$match": match_conditions},
        {"$sort": {"_id": 1}},
        {"$addFields": {"file_id_obj": {"$toObjectId": "$file_id"}}},
        {
            "$lookup": {
                "from": "creative_materials",
                "localField": "file_id_obj",
                "foreignField": "_id",
                "as": "material_info",
                "pipeline": [{"$project": {"thumbnail": 1}}],
            }
        },
        {
            "$addFields": {
                "thumbnail": {"$arrayElemAt": ["$material_info.thumbnail", 0]}
            }
        },
        {"$project": {"thumbnail": 1, "status": 1, "processed_at": 1, "file_id": 1}},
    ]

    # 执行聚合查询
    cursor = tasks_collection.aggregate(pipeline)
    materials = await cursor.to_list()

    remaining_time = 180
    current_time = datetime.now(ZoneInfo("Asia/Shanghai"))

    # 计算STARTED状态任务的剩余时间
    for material in materials:
        if material["status"] == RunStatus.STARTED.value and material.get(
            "processed_at"
        ):
            elapsed = (current_time - material["processed_at"]).total_seconds()
            remaining_time = max(0, int(180 - elapsed))

    # 转换结果格式（倒序排列并转为字典）
    result = {
        str(material["_id"]): {
            "_id": str(material["_id"]),
            "thumbnail": material.get("thumbnail"),
            "status": material["status"],
            "processed_at": material.get("processed_at"),
            "file_id": material["file_id"],
        }
        for material in reversed(materials)
    }

    return ApiResponse(
        data={"data": result, "wait_num": wait_num, "remaining_time": remaining_time}
    )


@router.get(
    "/running/{_id}",
    description="任务完成后, 单独查询任务添加到列表, 小红点展示未读",
)
async def get_creative_tasks_running(_id: str):
    material = await tasks_collection.find_one(
        {
            "_id": ObjectId(_id),
            "status": {"$in": [RunStatus.COMPLETED.value, RunStatus.FAILED.value]},
        }
    )
    if material is not None:
        material["_id"] = str(material.pop("_id"))
    return ApiResponse(data=material)


@router.get("/url/{unique_filename}")
async def get_file_url(unique_filename: str):
    url = minio_client.presigned_get_object(
        GENERATED_BUCKET,
        unique_filename,
        expires=timedelta(minutes=10),
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data=url)


@router.get("/murl/{_id}")
async def get_material_file_url(_id: str):
    one = await creative_collection.find_one(
        {"_id": ObjectId(_id)}, {"_id": 0, "unique_filename": 1}
    )
    url = minio_client.presigned_get_object(
        UPLOAD_BUCKET,
        one["unique_filename"],
        expires=timedelta(minutes=10),
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data=url)


@router.get("/thumbnail/{file_id}")
async def get_thumbnail_by_file_id(file_id: str):
    result = await creative_collection.find_one(
        {"_id": ObjectId(file_id)}, {"thumbnail": 1, "_id": 0}
    )
    if not result or not result.get("thumbnail"):
        return ErrResponse(code=404, message="缩略图不存在")
    return ApiResponse(data=result["thumbnail"])


async def validate_image_file(file: UploadFile):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片格式文件上传")
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in FileExtensions.IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {file_ext}，支持的格式: {FileExtensions.IMAGE_EXTENSIONS}",
        )


async def upload_images(files: List[UploadFile]) -> List[FileInfo]:
    uploaded_files_info = []
    for idx, file in enumerate(files):
        await validate_image_file(file)  # 直接调用，异常会自动传播
        file_content = await file.read()
        if len(file_content) > 20 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"文件 {file.filename} 大小超过限制 (20MB)",
            )
        sha3_256 = calculate_sha3_256(file_content)
        existing_file = await creative_collection_img.find_one(
            {"sha3_256": sha3_256}, projection={"_id": 1, "basename": 1}
        )
        if existing_file:
            file_info = {
                "_id": str(existing_file["_id"]),
                "basename": existing_file["basename"],
            }
            uploaded_files_info.append(file_info)
            continue
        name = str(uuid.uuid1()).replace("-", "")[:16]
        # 上传到MinIO
        await asyncio.to_thread(
            minio_client.put_object,
            UPLOAD_BUCKET_IMG,
            name,
            BytesIO(file_content),
            length=len(file_content),
            content_type=file.content_type,
        )
        try:
            filetype = FileExtensions.classify_by_extension(file.filename)
            thumbnail_bytes = await asyncio.to_thread(
                extract_first_frame_from_memory,
                file_content,
                filetype,
            )
            thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode("utf-8")
        except Exception as e:
            thumbnail_b64 = None
        # 文件元数据
        file_metadata = {
            "upload_filename": file.filename,
            "sha3_256": sha3_256,
            "basename": Path(file.filename).stem,
            "thumbnail": thumbnail_b64,
            "unique_filename": name,
            "file_size": len(file_content),
            "content_type": file.content_type,
            "upload_time": datetime.now(timezone.utc),
        }
        # 保存到数据库
        result = await creative_collection_img.update_one(
            {"sha3_256": file_metadata["sha3_256"]},
            {"$setOnInsert": file_metadata},
            upsert=True,
        )
        file_id = (
            str(result.upserted_id)
            if result.upserted_id
            else str(
                (
                    await creative_collection_img.find_one(
                        {"sha3_256": sha3_256}, {"_id": 1}
                    )
                )["_id"]
            )
        )
        file_info = {
            "_id": file_id,
            "basename": file_metadata["basename"],
        }
        uploaded_files_info.append(file_info)
    return uploaded_files_info


async def create_image_task(
    files: List[UploadFile] = None,
    file_ids: List[str] = None,
    unique_filenames: List[str] = None,
    prompt: str = None,
    image_num: int = 1,
    task_type: int = 1,
    model: AIModel = AIModel.QWEN,
    current_user: UserModel = None,
):
    if files is None:
        files = []
    if file_ids is None:
        file_ids = []
    if unique_filenames is None:
        unique_filenames = []
    if task_type != 2 and (
        not prompt
        or len(prompt.strip()) < 5
        or prompt.isdigit()
        or bool(re.fullmatch(r"[0-9\W]+", prompt))
    ):
        raise HTTPException(status_code=400, detail="提示词至少输入5个有效字符")
    if image_num < 1 or image_num > 10:
        raise HTTPException(status_code=400, detail="图片数量必须在1-10之间")

    file_info = []
    for _id in file_ids:
        one = await creative_collection_img.find_one(
            {"_id": ObjectId(_id)}, {"_id": 0, "basename": 1}
        )
        file_info.append({"_id": str(_id), "basename": one["basename"]})
    tmp_files = []
    for unique_filename in unique_filenames:
        # 微调情况下, 直接读取生成的文件, 重新走正常上传文件步骤
        file_bytes = await asyncio.to_thread(
            lambda: minio_client.get_object(
                GENERATED_BUCKET_IMG, unique_filename
            ).read()
        )
        content_type, encoding = mimetypes.guess_type(unique_filename)
        file = CustomUploadFile(
            filename=unique_filename,
            file=BytesIO(file_bytes),
            content_type=content_type or "application/octet-stream",
        )
        tmp_files.append(file)
    files = tmp_files + files
    len_files = len(files) + len(file_info)
    if len_files == 0:
        return ErrResponse(code=400, message="至少需要上传一张图片")
    if len_files > 3:
        return ErrResponse(code=400, message="最多只能上传10张图片")
    if task_type == 2 and len_files != 1:
        return ErrResponse(code=400, message="图片复刻只能上传一张图片")
    if files:
        upload_results = await upload_images(files)
        file_info.extend(upload_results)
    tasks = {
        "file_ids": [f["_id"] for f in file_info],
        "basenames": [f["basename"] for f in file_info],
        "prompt": prompt,
        "task_type": task_type,
        "image_num": image_num,
        "model": model.value,
        "status": RunStatus.SENDING.value,
        "created_at": datetime.now(timezone.utc).strftime(SecondFormat),
        "real_name": current_user.real_name,
    }
    response = await tasks_collection_run_img.insert_one(tasks)
    await redis_cli.rpush(REDIS_KEY_IMG, str(response.inserted_id))

    return {
        "task_id": str(response.inserted_id),
        "file_ids": [f["_id"] for f in file_info],
        "basenames": [f["basename"] for f in file_info],
        "image_num": image_num,
        "task_type": task_type,
        "prompt": prompt,
    }


@router.post(
    "/img/", dependencies=[Depends(require_roles([*Roles.OPERATOR_ALL, Roles.CREATOR]))]
)
async def upload_creative_img(
    files: List[UploadFile] = File([]),
    prompt: str = Form(...),
    image_num: int = Form(1),
    task_type: int = Form(1),
    model: AIModel = Form(AIModel.QWEN),
    current_user: UserModel = Depends(auth_current_user),
    file_ids: List[str] = File([]),
    unique_filenames: List[str] = File([]),
):
    result = await create_image_task(
        files=files,
        file_ids=file_ids,
        unique_filenames=unique_filenames,
        prompt=prompt,
        image_num=image_num,
        task_type=task_type,
        model=model,
        current_user=current_user,
    )

    return ApiResponse(data=f"创作任务已创建，将生成{result['image_num']}张新图片")


class BulkImageTaskItem(BaseModel):
    prompt: str
    image_num: int = 1
    task_type: int = 1  # 1: 多图修改, 2: 单图复刻
    model: AIModel = AIModel.QWEN
    file_ids: List[str] = []
    unique_filenames: List[str] = []


@router.post(
    "/img/bulk", dependencies=[Depends(require_roles([*Roles.OPERATOR_ALL, Roles.CREATOR]))]
)
async def bulk_upload_creative_img(
    bulk_tasks: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: UserModel = Depends(auth_current_user),
):
    # 解析JSON字符串为字典列表，然后转换为Pydantic模型
    try:
        bulk_tasks_data = json.loads(bulk_tasks)
        parsed_bulk_tasks = [BulkImageTaskItem(**task) for task in bulk_tasks_data]
    except json.JSONDecodeError as e:
        return ErrResponse(code=400, message=f"JSON格式错误: {str(e)}")
    except Exception as e:
        return ErrResponse(code=400, message=f"解析批量任务配置失败: {str(e)}")

    if len(files) != len(parsed_bulk_tasks):
        return ErrResponse(code=400, message="文件数量与任务数量不匹配")
    successful_tasks = []
    failed_tasks = []
    total_images = 0
    for i, (file, task) in enumerate(zip(files, parsed_bulk_tasks)):
        try:
            result = await create_image_task(
                files=[file],
                file_ids=task.file_ids,
                unique_filenames=task.unique_filenames,
                prompt=task.prompt,
                image_num=task.image_num,
                task_type=task.task_type,
                model=task.model,
                current_user=current_user,
            )
            successful_tasks.append(
                {
                    "index": i + 1,
                    "filename": file.filename,
                    "task_id": result["task_id"],
                    "image_num": result["image_num"],
                    "task_type": result["task_type"],
                    "prompt": result["prompt"],
                    "basenames": result["basenames"],
                }
            )
            total_images += result["image_num"]

        except HTTPException as e:
            failed_tasks.append(
                {"index": i + 1, "filename": file.filename, "error": e.detail}
            )
        except Exception as e:
            failed_tasks.append(
                {"index": i + 1, "filename": file.filename, "error": str(e)}
            )
    result_data = {
        "total_files": len(files),
        "successful_count": len(successful_tasks),
        "failed_count": len(failed_tasks),
        "total_images": total_images,
        "successful_tasks": successful_tasks,
    }
    if failed_tasks:
        result_data["failed_tasks"] = failed_tasks
    message = f"批量上传完成: 成功{len(successful_tasks)}个文件，失败:{failed_tasks}，总计将生成{total_images}张新图片"
    result_data["message"] = message
    return ApiResponse(data=result_data)


@router.get("/img-running/")
async def list_creative_img_tasks_running(
    basename: Optional[str] = Query(None, description="文件名(无后缀)"),
):
    base_conditions = {
        "status": {"$in": [RunStatus.SENDING.value, RunStatus.STARTED.value]}
    }
    if basename:
        base_conditions["basename"] = basename
    materials = await tasks_collection_run_img.find(
        base_conditions,
        {"status": 1, "processed_at": 1, "real_name": 1, "image_num": 1},
    ).to_list()
    remaining_time = 50
    current_time = datetime.now(ZoneInfo("Asia/Shanghai"))
    for material in materials:
        if material["status"] == RunStatus.STARTED.value and material.get(
            "processed_at"
        ):
            elapsed = (current_time - material["processed_at"]).total_seconds()
            remaining_time = max(0, int(50 - elapsed))
    result = {
        str(material["_id"]): {
            "_id": str(material["_id"]),
            "status": material["status"],
            "processed_at": material.get("processed_at"),
            "image_num": material["image_num"],
            "real_name": material["real_name"],
        }
        for material in reversed(materials)
    }
    return ApiResponse(data={"data": result, "remaining_time": remaining_time})


@router.get(
    "/img-running/{_id}",
    description="任务完成后, 单独查询任务添加到列表, 小红点展示未读",
)
async def get_img_creative_tasks_running(_id: str):
    material = await tasks_collection_img.find_one(
        {"_id": ObjectId(_id)},
        projection={
            "file_ids": 1,
            "basenames": 1,
            "prompt": 1,
            "image_num": 1,
            "created_at": 1,
            "real_name": 1,
            "results": 1,
            "task_type": 1,
            "status": 1,
            "error_message": 1,
        },
    )
    if material is not None:
        material["_id"] = str(material.pop("_id"))
    return ApiResponse(data=material)


@router.get("/img/")
async def list_creative_img_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    skip: int = Query(0, ge=0),
    basename: Optional[str] = Query(None, description="文件名(无后缀)"),
    real_name: Optional[str] = Query(None),
):
    query = {}
    if basename:
        query["basenames"] = basename
    if real_name:
        query["real_name"] = real_name
    skip = (page - 1) * page_size + skip
    cursor = (
        tasks_collection_img.find(
            query,
            projection={
                "file_ids": 1,
                "basenames": 1,
                "prompt": 1,
                "image_num": 1,
                "created_at": 1,
                "real_name": 1,
                "results": 1,
                "task_type": 1,
                "status": 1,
                "error_message": 1,
            },
        )
        .sort("_id", -1)
        .skip(skip)
        .limit(page_size)
    )
    materials = []
    async for material in cursor:
        material["created_at"] = (
            datetime.strptime(material["created_at"], SecondFormat)
            .replace(tzinfo=timezone.utc)
            .astimezone(timezone(timedelta(hours=8)))
            .strftime(SecondFormat)
        )
        material["_id"] = str(material.pop("_id"))
        materials.append(material)
    has_more = len(materials) == page_size
    return ApiResponse(
        data={
            "materials": materials,
            "has_more": has_more,
        }
    )


@router.get("/url-img/{unique_filename}")
async def get_img_file_url(unique_filename: str):
    url = minio_client.presigned_get_object(
        GENERATED_BUCKET_IMG,
        unique_filename,
        expires=timedelta(minutes=10),
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data=url)


@router.get("/murl-img/{_id}")
async def get_material_file_url(_id: str):
    one = await creative_collection_img.find_one(
        {"_id": ObjectId(_id)}, {"_id": 0, "unique_filename": 1, "basename": 1}
    )
    url = minio_client.presigned_get_object(
        UPLOAD_BUCKET_IMG,
        one["unique_filename"],
        expires=timedelta(minutes=10),
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data=(url, one["basename"]))


@router.get("/thumbnail_img/{file_ids}")
async def get_thumbnail_img_by_file_id(file_ids: str):
    cursor = creative_collection_img.find(
        {"_id": {"$in": [ObjectId(fid) for fid in file_ids.split(",")]}},
        {"thumbnail": 1, "_id": 1},
    )
    data = {}
    async for doc in cursor:
        data[str(doc["_id"])] = doc.get("thumbnail")
    return ApiResponse(data=data)
