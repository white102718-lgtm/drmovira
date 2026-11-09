"""公共素材（素材师/投放师共享模版库）业务逻辑层。

与广告素材库 `materials` 隔离：独立集合 `material_commons` + 独立桶 `material-commons`，
仅图片/视频，不写 Doris、不参与广告消耗分析。
"""

import asyncio
import base64
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from bson import ObjectId
from fastapi import UploadFile
from minio.deleteobjects import DeleteObject

from app.db.mongo import cols
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.file_type import FileExtensions, FileType
from app.model_type_defs.user_models import UserModel
from app.utils.file_util import (
    convert_minio_url_to_https,
    extract_thumb_and_meta,
    calculate_hash,
    calculate_sha3_256,
    iter_archive_media,
    ARCHIVE_EXTS,
)
from app.services import task_service
from app.services.material_tag_service import attach_tags_tree, resolve_tag_titles

commons = cols.material_commons
BUCKET = buckets.material_commons
TMP_BUCKET = buckets.tmp

ALLOWED_EXTS = FileExtensions.IMAGE_EXTENSIONS | FileExtensions.VIDEO_EXTENSIONS
MAX_SIZE = 500 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _presign(filename: str) -> str:
    return convert_minio_url_to_https(
        minio_client.presigned_get_object(BUCKET, filename, expires=timedelta(hours=1))
    )


async def _process_one(
    filename: str, content: bytes, uploader: str, tags_new: Optional[List[str]]
) -> dict:
    """单个图片/视频入公共素材库：md5 规范命名、库内去重、缩略图+宽高时长。
    返回素材文档 + message（新建为空 / 重复为「该素材已存在」）。"""
    ext = Path(filename).suffix.lower()
    file_md5 = await asyncio.to_thread(calculate_hash, content)
    sha3 = await asyncio.to_thread(calculate_sha3_256, content)
    filetype = FileExtensions.classify_by_extension(filename)
    frame, width, height, duration = await asyncio.to_thread(
        extract_thumb_and_meta, content, filetype == FileType.VIDEO
    )

    fname = f"{filetype.get_prefix()}{file_md5[:8]}{ext}"
    existing = await commons.find_one({"filename": fname})
    if existing:
        if existing.get("sha3_256") == sha3:
            # 同内容已在库 → 复用既有，不重复入桶/入库
            existing["id"] = str(existing.pop("_id"))
            existing.pop("file_md5", None)
            existing.pop("sha3_256", None)
            return {**existing, "message": "文件重复"}
        # 同名不同内容（md5[:8] 撞）→ 追加时间戳后缀避让
        fname = (
            f"{filetype.get_prefix()}{file_md5[:8]}"
            f"_{str(int(_now().timestamp()))[-4:]}{ext}"
        )

    await asyncio.to_thread(
        minio_client.put_object,
        BUCKET,
        fname,
        BytesIO(content),
        length=len(content),
        content_type=f"{filetype.value}/{ext[1:]}",
    )
    n = _now()
    doc = {
        "filename": fname,
        "origin_filename": filename,
        "basename": Path(fname).stem,
        "filetype": filetype.value,
        "img": base64.b64encode(frame).decode("utf-8") if frame else None,
        "width": width,
        "height": height,
        "duration": duration,
        "file_md5": file_md5,
        "sha3_256": sha3,
        "user": uploader,
        "tags_new": tags_new,
        "created_at": n,
        "updated_at": n,
    }
    result = await commons.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc.pop("file_md5", None)
    doc.pop("sha3_256", None)
    return {**doc, "message": ""}


async def _run_upload_job(
    task_id: str,
    filename: str,
    content: bytes,
    uploader: str,
    tags_new: Optional[List[str]],
) -> None:
    """后台跑公共素材入库：压缩包(zip/7z)解压后内部图片/视频逐个入库，单文件直接入库；
    结果 {items, skipped, errors} 落 Redis 任务。单文件失败记进 errors，解压失败/致命错才 failed。"""
    try:
        await task_service.set_processing(task_id)
        ext = Path(filename).suffix.lower()
        skipped: List[str] = []
        if ext in ARCHIVE_EXTS:
            entries, skipped = await asyncio.to_thread(
                iter_archive_media, content, ext, ALLOWED_EXTS
            )
            if not entries:
                await task_service.fail(task_id, "压缩包内未找到支持的图片/视频")
                return
            sources = entries
        else:
            sources = [(filename, content)]
        items, errors = [], []
        for name, data in sources:
            try:
                items.append(await _process_one(name, data, uploader, tags_new))
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        await task_service.done(
            task_id, {"items": items, "skipped": skipped, "errors": errors}
        )
    except Exception as e:
        await task_service.fail(task_id, str(e))


async def upload(
    file: UploadFile, current_user: UserModel, tags_new: Optional[List[str]] = None,
):
    """上传公共素材（图片/视频/压缩包）：压缩包(zip/7z)解压后内部逐个入库。
    立即返回 {task_id}，处理在后台跑，前端轮询 GET /upload-tasks/{task_id} 取
    {items, skipped, errors}（每个 item 带 message：新建为空 / 重复为「该素材已存在」）。"""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS and ext not in ARCHIVE_EXTS:
        return ErrResponse(message=f"不支持的文件类型: {ext}")
    content = await file.read()
    if len(content) > MAX_SIZE:
        return ErrResponse(message="文件超过 500MB 限制")
    task_id = await task_service.create()
    task_service.spawn(
        _run_upload_job(
            task_id, file.filename, content, current_user.full_name, tags_new
        )
    )
    return ApiResponse(data={"task_id": task_id})


# ==================== 打包下载（后台任务）====================

_ZIP_DOWNLOAD_WORKERS = 16


def _fetch_object(item: Tuple[str, str]) -> Tuple[str, bytes]:
    filename, entry_name = item
    resp = minio_client.get_object(BUCKET, filename)
    try:
        return entry_name, resp.read()
    finally:
        resp.close()
        resp.release_conn()


def _zip_to_minio(items: List[Tuple[str, str]]) -> str:
    """同步拉取 MinIO 文件打包并上传临时桶，返回对象名。阻塞操作，须在线程里跑。
    ZIP_STORED 不压缩：视频/图片已是压缩格式，DEFLATE 只烧 CPU 无收益；下载分批并发。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        zip_path = Path(tmp.name)
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zipf:
        with ThreadPoolExecutor(max_workers=_ZIP_DOWNLOAD_WORKERS) as ex:
            # 分批并发下载：每批至多 workers 个驻留内存，写盘有界；STORED 写盘很快
            for i in range(0, len(items), _ZIP_DOWNLOAD_WORKERS):
                batch = items[i : i + _ZIP_DOWNLOAD_WORKERS]
                for entry_name, data in ex.map(_fetch_object, batch):
                    zipf.writestr(entry_name, data)
    obj_name = zip_path.name
    minio_client.fput_object(TMP_BUCKET, obj_name, str(zip_path))
    zip_path.unlink()
    return obj_name


async def _build_and_upload_zip(items: List[Tuple[str, str]]) -> Dict[str, str]:
    """打包 MinIO 多个公共素材为 ZIP 上传临时桶，返回 {url, filename}。"""
    obj_name = await asyncio.to_thread(_zip_to_minio, items)
    url = convert_minio_url_to_https(
        minio_client.presigned_get_object(
            TMP_BUCKET, obj_name, expires=timedelta(days=1)
        )
    )
    return {"url": url, "filename": obj_name}


async def _run_zip_job(task_id: str, items: List[Tuple[str, str]]) -> None:
    """后台打包下载：下载+zip+传临时桶+presign；结果 {url, filename} 落 Redis 任务。"""
    try:
        await task_service.set_processing(task_id)
        result = await _build_and_upload_zip(items)
        await task_service.done(task_id, result)
    except Exception as e:
        await task_service.fail(task_id, str(e))


async def zip_materials(file_ids: List[str]):
    """公共素材打包下载：立即返回 {task_id}，打包在后台跑，
    前端轮询 GET /upload-tasks/{task_id} 取 {url, filename}。"""
    object_ids = [ObjectId(i) for i in file_ids]
    items = [
        (doc["filename"], doc["filename"])
        async for doc in commons.find({"_id": {"$in": object_ids}}, {"filename": 1})
    ]
    task_id = await task_service.create()
    task_service.spawn(_run_zip_job(task_id, items))
    return ApiResponse(data={"task_id": task_id})


async def list_materials(
    page: int,
    page_size: int,
    filetype: Optional[str],
    basename: Optional[str],
):
    """公共素材列表：按类型/关键词筛选，分页，created_at 倒序。
    只喂卡片渲染，详情与预览 url 由 get_by_ids 补。"""
    query: Dict[str, Any] = {}
    if filetype:
        query["filetype"] = filetype
    if basename:
        query["basename"] = {"$regex": basename, "$options": "i"}

    skip = (page - 1) * page_size
    total = await commons.count_documents(query)
    projection = {
        "file_md5": 0,
        "sha3_256": 0,
        "updated_at": 0,
        "origin_filename": 0,
        "width": 0,
        "height": 0,
        "duration": 0,
    }
    cursor = (
        commons.find(query, projection=projection)
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = []
    tags_key_name: Dict[str, str] = {}
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        await resolve_tag_titles(doc, tags_key_name)
        items.append(doc)
    return ApiResponse(
        data={"total": total, "items": items, "page": page, "page_size": page_size}
    )


async def get_by_ids(ids: List[str]):
    """公共素材详情（预览用）：对齐 GET /materials/by_ids 的形状，另带现签的 url。
    公共素材在独立集合+独立桶，materials 那条详情链路查不到，故单开。"""
    cursor = commons.find(
        {"_id": {"$in": [ObjectId(i) for i in ids]}},
        projection={
            "file_md5": 0,
            "sha3_256": 0,
            "img": 0,  # 缩略图列表已给过
            "width": 0,
            "height": 0,
            "duration": 0,
        },
    )
    items: List[Dict[str, Any]] = []
    tags_key_name: Dict[str, str] = {}
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        doc["url"] = _presign(doc["filename"])
        await attach_tags_tree(doc, tags_key_name)
        await resolve_tag_titles(doc, tags_key_name)
        items.append(doc)
    return ApiResponse(data={"total": len(items), "items": items})


async def update_tags(ids: List[str], tags_new: List[str]):
    """手动给公共素材打标签：直接覆盖 tags_new"""
    result = await commons.update_many(
        {"_id": {"$in": [ObjectId(i) for i in ids]}},
        {"$set": {"tags_new": tags_new, "updated_at": _now()}},
    )
    return ApiResponse(data={"modified_count": result.modified_count})


async def batch_delete(ids: List[str]):
    """批量删除公共素材（按文档 id）：先由 id 反查 filename 删桶对象，再删文档。"""
    object_ids = [ObjectId(i) for i in ids]
    filenames = [
        d["filename"]
        async for d in commons.find(
            {"_id": {"$in": object_ids}}, projection={"filename": 1}
        )
    ]
    if filenames:
        await asyncio.to_thread(
            lambda: list(
                minio_client.remove_objects(
                    BUCKET, [DeleteObject(f) for f in filenames]
                )
            )
        )
    result = await commons.delete_many({"_id": {"$in": object_ids}})
    return ApiResponse(data={"deleted_count": result.deleted_count})
