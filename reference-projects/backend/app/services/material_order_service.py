"""素材工单业务逻辑层：路由 material_orders.py 仅做依赖注入与委托，全部实现集中于此。"""

import asyncio
import base64
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from urllib.parse import quote as urlquote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from bson import ObjectId
from fastapi import UploadFile
from minio.error import S3Error
from pymongo import UpdateOne, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db.mongo import cols, user_cols
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.tag_operations import insert_materials_to_doris
from app.model_type_defs.user_models import UserModel, Roles
from app.model_type_defs.material_order_models import (
    OrderStatus,
    MaterialScope,
    MaterialReviewStatus,
    MaterialOrderCreate,
    MaterialOrderUpdate,
    BatchAssignBody,
    BatchRejectBody,
    BatchDeleteBody,
    DeliverBody,
    DeleteMaterialsBody,
    RejectMaterialsBody,
    AcceptMaterialsBody,
    AcceptBody,
    CommentBody,
    AssignMaterialsBody,
)
from app.utils.file_util import (
    convert_minio_url_to_https,
    extract_thumb_and_meta_from_path,
    hash_file,
    extract_archive_media_to_dir,
    ARCHIVE_EXTS,
)
from app.utils import feishu
from app.services import task_service
from app.services import material_link_service
from app.services import material_poster_service as poster_svc

orders = cols.material_orders
order_materials = cols.material_order_outputs
order_comments = cols.material_order_comments
order_histories = cols.material_order_histories
material_folders = cols.material_folders
BUCKET = buckets.materials

CST = timezone(timedelta(hours=8))

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
VIDEO_EXTS = {".mp4", ".mov"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS | ARCHIVE_EXTS
MAX_SIZE = 10 * 1024 * 1024 * 1024
MAX_UNZIP_SIZE = 11 * 1024 * 1024 * 1024  # 解压后总大小上限：略高于上传上限，容忍解压后比压缩包略大
# 与素材库 FileType.get_prefix 一致
FILE_PREFIXES = {"image": "P", "video": "V"}
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
}


_bg_tasks: set = set()


def _fire(coro) -> None:
    # fire-and-forget 后台任务，存引用防被 GC 回收，完成后自动清理
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _delivery_deadline(exp: Optional[datetime]) -> Optional[datetime]:
    # 交付截止固定到当天 19:00（CST，库里读出已是 CST 感知），临期预警/剩余小时都按此口径
    return exp.replace(hour=19, minute=0, second=0, microsecond=0) if exp else None


def _deadline_expr(field: str = "$expected_delivery_at") -> dict:
    # _delivery_deadline 的 Mongo 端等价：把交付时间对齐到当天 19:00（CST），供查询/聚合复用
    return {
        "$dateAdd": {
            "startDate": {
                "$dateTrunc": {"date": field, "unit": "day", "timezone": "+08:00"}
            },
            "unit": "hour",
            "amount": 19,
        }
    }


def _classify(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "archive"


def _thumb_data_uri(frame: Optional[bytes]) -> Optional[str]:
    if not frame:
        return None
    return base64.b64encode(frame).decode("utf-8")


def _parse_dt(value: Optional[str], end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip().replace("T", " ")  # 兼容前端 ISO 格式 2026-06-12T15:50:13
    if ":" not in value:
        fmt = "%Y-%m-%d"
    elif value.count(":") == 1:
        fmt = "%Y-%m-%d %H:%M"
    else:
        fmt = "%Y-%m-%d %H:%M:%S"
    dt = datetime.strptime(value, fmt).replace(tzinfo=CST)
    if end and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        # 结束时间只传日期（0 点）时补到当天末尾，保证区间含整天
        dt += timedelta(hours=23, minutes=59, seconds=59)
    return dt


def _object_exists(object_key: str) -> bool:
    try:
        minio_client.stat_object(BUCKET, object_key)
        return True
    except S3Error:
        return False


def _presign(object_key: str, download_name: Optional[str] = None) -> str:
    # download_name: 签进 content-disposition, 跨域下浏览器无视 <a download>, 只认这个头
    response_headers = (
        {
            "response-content-disposition": f"attachment; filename*=UTF-8''{urlquote(download_name)}"
        }
        if download_name
        else None
    )
    return convert_minio_url_to_https(
        minio_client.presigned_get_object(
            BUCKET,
            object_key,
            expires=timedelta(hours=1),
            response_headers=response_headers,
        )
    )


def _resign_upload_urls(node: Any) -> None:
    # 递归重签 references / description 富文本里上传附件的临时链接：入库存的是签发当时的 url，过期即失效，详情接口按 object_key 现签覆盖
    if isinstance(node, dict):
        if node.get("object_key"):
            node["url"] = _presign(node["object_key"])
        else:
            for v in node.values():
                _resign_upload_urls(v)
    elif isinstance(node, list):
        for item in node:
            _resign_upload_urls(item)


def _strip_signed_urls(node: Any) -> Any:
    # 对比字段新旧值时忽略上传附件的临时签名 url：详情接口每次现签，签名参数必然不同，不算变更
    if isinstance(node, dict):
        return {
            k: _strip_signed_urls(v)
            for k, v in node.items()
            if not (k == "url" and node.get("object_key"))
        }
    if isinstance(node, list):
        return [_strip_signed_urls(i) for i in node]
    return node


def _ensure_req_ids(description: Optional[list]) -> None:
    # 需求项补稳定 id：产出物按 id 关联需求，数组下标会随编辑增删漂移
    for item in description or []:
        if isinstance(item, dict) and not item.get("id"):
            item["id"] = uuid.uuid4().hex[:8]


def _gen_order_no() -> str:
    # 日期前缀 + 随机后缀：避免「查最大号 +1」非原子导致的并发撞号（不同用户同一时刻建单）
    return f"MR{datetime.now(CST).strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"


async def _sink_order_materials(
    order: dict,
    material_ids: List[str],
    scope: str,
    folder_id: Optional[str],
    owner: str,
    db,
) -> int:
    """把工单选中的产出素材登记进目标素材库（公共库 scope=public 或个人文件夹 scope=personal）。
    对象在上传时已落 materials 桶（object_key 即内容寻址的 filename），此处只补一条 cols.materials
    元数据，不再做桶到桶的搬运。"""
    order_id = str(order["_id"])
    n = _now()
    count = 0
    new_basenames: List[str] = []
    # 不拦 assigned_at：同一产出物可重复入库到不同个人文件夹（多对多），靠下方去重 + 幂等 link 保证安全
    async for mat in order_materials.find(
        {
            "_id": {"$in": [ObjectId(i) for i in material_ids]},
            "order_id": order_id,
        }
    ):
        filename = mat["object_key"]
        existing = await cols.materials.find_one(
            {"filename": filename}, projection={"_id": 1, "scope": 1}
        )
        if not existing:
            # 制作人取产出物自身记录的 designer（实际交付人），多素材师下避免订单级歧义
            mat_designer = mat.get("designer")
            doc = {
                "filename": filename,
                "origin_filename": mat["filename"],
                "basename": mat["basename"],
                "filetype": mat["filetype"],
                "game_platform": order.get("project") or "",
                "img": mat.get("img"),
                "file_md5": mat.get("file_md5"),
                "sha3_256": mat.get("sha3_256"),
                "user": mat_designer,
                "operator": owner,
                "creative_editor": mat_designer,
                "creative_planner": mat.get("creative_planner"),
                "tags_new": [],
                "scope": scope,
                "source": "order",
                "order_id": order_id,
                "order_no": order.get("order_no"),
                "created_at": n,
                "updated_at": n,
            }
            # 老工单没这字段，缺失就不写：null 入索引既筛不出 true 也筛不出 false
            if "is_green_material" in order:
                doc["is_green_material"] = order["is_green_material"]
            if scope != MaterialScope.PERSONAL:
                doc["published_at"] = n
            try:
                material_oid = (await cols.materials.insert_one(doc)).inserted_id
                new_basenames.append(mat["basename"])
            except DuplicateKeyError:
                # 并发入库同一内容（filename 内容寻址命中唯一索引）→ 退回复用已存在的那条
                existing = await cols.materials.find_one(
                    {"filename": filename}, projection={"_id": 1, "scope": 1}
                )
        if existing:
            # 同 key（内容寻址）已在素材库 → 复用，不重复登记
            material_oid = existing["_id"]
            # public 入库时把复用到的素材升为公共可见（personal 不降级，原属主文件夹照旧）
            if (
                scope == MaterialScope.PUBLIC
                and existing.get("scope") != MaterialScope.PUBLIC
            ):
                await cols.materials.update_one(
                    {"_id": material_oid},
                    {"$set": {"scope": MaterialScope.PUBLIC, "published_at": n, "updated_at": n}},
                )
        # 个人文件夹入库：建立素材↔文件夹归属（多对多，去重命中也照建）
        if scope == MaterialScope.PERSONAL:
            await material_link_service.link_material(
                material_oid, folder_id, "order", order_id
            )
        await order_materials.update_one(
            {"_id": mat["_id"]},
            {
                "$set": {
                    "assigned_at": n,
                    "assigned_scope": scope,
                    "material_id": str(material_oid),
                    "review_status": MaterialReviewStatus.IN_LIBRARY,
                    "updated_at": n,
                }
            },
        )
        count += 1
    if new_basenames:
        await insert_materials_to_doris(db, new_basenames)
    return count


# ==================== Page1 工单新建（operator）====================


async def _process_one_media(filename: str, path: str) -> dict:
    """单个本地文件入桶并返回附件信息。object_key 按内容寻址 {前缀}{md5[:8]}{ext}（图片 P/视频 V/压缩包 A），
    与素材库命名一致；同内容命中已有对象跳过入桶，信息照常返回并带 duplicate 标记。
    哈希/缩略图/入桶全程流式读盘，不把整文件读进内存。压缩包不解压、无缩略图。"""
    ext = Path(filename).suffix.lower()
    filetype = _classify(ext)
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    size = os.path.getsize(path)
    file_md5, sha3 = await asyncio.to_thread(hash_file, path)
    object_key = f"{FILE_PREFIXES.get(filetype, 'A')}{file_md5[:8]}{ext}"
    duplicate = await asyncio.to_thread(_object_exists, object_key)
    if filetype == "archive":
        frame, width, height, duration = None, None, None, None
    else:
        frame, width, height, duration = await asyncio.to_thread(
            extract_thumb_and_meta_from_path, path, filetype == "video"
        )
    if not duplicate:
        await asyncio.to_thread(
            minio_client.fput_object,
            BUCKET,
            object_key,
            path,
            content_type=content_type,
        )
    if filetype == "video":
        await poster_svc.store_quietly(Path(object_key).stem, path=path)
    return {
        "object_key": object_key,
        "name": filename,
        "duplicate": duplicate,
        "basename": Path(object_key).stem,
        "size": size,
        "content_type": content_type,
        "filetype": filetype,
        "file_md5": file_md5,
        "sha3_256": sha3,
        "width": width,
        "height": height,
        "duration": duration,
        "url": _presign(object_key),
        "img": _thumb_data_uri(frame),
    }


def _spool_to_temp(src, ext: str) -> str:
    """把上传流分块落到本地临时文件，返回路径。阻塞 IO，须在线程里跑。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(src, tmp, 8 * 1024 * 1024)
        return tmp.name


async def _run_attachment_job(
    task_id: str, filename: str, src_path: str, is_unzip: bool
) -> None:
    """后台跑工单附件入桶：压缩包按 is_unzip 决定解出逐个入桶或原样整包入桶，单文件直接入桶；结果落 Redis 任务。
    单文件失败记进 result.errors（整单仍 done），解压失败/致命错才 failed。
    入参是本地临时文件路径，全程流式读盘，结束在 finally 清理临时文件。"""
    extract_dir: Optional[str] = None
    try:
        await task_service.set_processing(task_id)
        ext = Path(filename).suffix.lower()
        skipped: List[str] = []
        if ext in ARCHIVE_EXTS and is_unzip:
            extract_dir = tempfile.mkdtemp()
            entries, skipped = await asyncio.to_thread(
                extract_archive_media_to_dir,
                src_path, ext, IMAGE_EXTS | VIDEO_EXTS, extract_dir, MAX_UNZIP_SIZE,
            )
            if not entries:
                await task_service.fail(task_id, "压缩包内未找到支持的图片/视频")
                return
            sources = entries
        else:
            sources = [(filename, src_path)]
        items, errors, duplicate_names = [], [], []
        for name, path in sources:
            try:
                info = await _process_one_media(name, path)
                if info["duplicate"]:
                    duplicate_names.append(name)
                items.append(info)
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        await task_service.done(
            task_id,
            {
                "items": items,
                "skipped": skipped,
                "errors": errors,
                "total": len(sources),
                "success": len(items),
                "failed": len(errors),
                "duplicate_count": len(duplicate_names),
                "duplicate_names": duplicate_names,
            },
        )
    except Exception as e:
        await task_service.fail(task_id, str(e))
    finally:
        Path(src_path).unlink(missing_ok=True)
        if extract_dir:
            shutil.rmtree(extract_dir, ignore_errors=True)


async def upload_attachment(file: UploadFile, is_unzip: bool):
    """上传图片/视频/压缩包到 materials 桶：立即返回 {task_id}，解压/入桶在后台跑，
    前端轮询 GET /upload-tasks/{task_id} 取 {items, skipped, errors,
    total, success, failed, duplicate_count, duplicate_names}。
    上传流先落本地临时文件，后台基于路径流式处理，避免大文件常驻内存。"""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return ErrResponse(message=f"不支持的文件类型: {ext}")
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_SIZE:
        return ErrResponse(message="文件超过 10GB 限制")

    src_path = await asyncio.to_thread(_spool_to_temp, file.file, ext)
    task_id = await task_service.create()
    task_service.spawn(_run_attachment_job(task_id, file.filename, src_path, is_unzip))
    return ApiResponse(data={"task_id": task_id})


async def create_order(body: MaterialOrderCreate, current_user: UserModel):
    """新建工单（投放师）：草稿或直接提交需求评审，自动生成工单号"""
    n = _now()
    doc = body.model_dump()
    _ensure_req_ids(doc.get("description"))
    doc["expected_delivery_at"] = _parse_dt(body.expected_delivery_at)
    if not doc["order_no"]:
        doc["order_no"] = _gen_order_no()
    doc["creator"] = current_user.full_name
    doc["designers"] = []
    doc["creative_planners"] = []
    doc["completed_designers"] = []
    doc["rating"] = None
    doc["created_at"] = n
    doc["updated_at"] = n
    if doc["status"] == OrderStatus.PENDING_ASSIGN:
        doc["submitted_at"] = n
    result = await orders.insert_one(doc)
    if doc["status"] == OrderStatus.PENDING_ASSIGN:
        _fire(_notify_demand_submitted(doc["creator"], current_user.department, doc.get("title")))
    return ApiResponse(
        data={
            "id": str(result.inserted_id),
            "order_no": doc["order_no"],
            "status": doc["status"],
        }
    )


# ==================== Page2 需求池调度/分配（operator_leader）====================


async def list_orders(
    page: int,
    page_size: int,
    project: Optional[str],
    priority: Optional[List[str]],
    demand_type: Optional[str],
    status: Optional[str],
    keyword: Optional[str],
    operator: Optional[str],
    department: Optional[str],
    designers: Optional[List[str]],
    creative_planners: Optional[List[str]],
    country: Optional[str],
    is_green_material: Optional[bool],
    sort: str,
    order: str,
    view: str,
    current_user: UserModel,
):
    """工单列表：视角由前端传 view 决定（pool=需求池全部 / created=投手本人提交 / assigned=素材师本人被指派）。支持按项目/优先级/类型/状态/关键词筛选分页，标记临期预警"""
    query: Dict[str, Any] = {"status": {"$ne": OrderStatus.DRAFT}}
    # created：投手本人提交（creator=自己，状态按个人视角重映射）
    # assigned：素材师或创意策划本人被指派，与 my_stats 同口径
    # 其它/pool：需求池全部，不加个人过滤
    is_operator_personal_list = view == "created"
    if is_operator_personal_list:
        query["creator"] = current_user.full_name
    elif view == "assigned":
        query["$or"] = [
            {"designers": current_user.full_name},
            {"creative_planners": current_user.full_name},
        ]
    if project:
        query["project"] = project
    if priority:
        query["priority"] = {"$in": priority}
    if demand_type:
        query["demand_type"] = demand_type
    if status:
        if status == 'is_complete':
            query["status"] = {"$in": OrderStatus.IS_COMPLETE}
        elif status == 'is_submit':
            query["status"] = OrderStatus.PENDING_ASSIGN  # 前端传 is_submit，库里存 pending_assign
        else:
            query["status"] = status
    if keyword:
        query["title"] = {"$regex": re.escape(keyword), "$options": "i"}
    if operator:
        query["creator"] = operator
    if department:
        query["department"] = department
    if designers:
        query["designers"] = {"$in": designers}
    if creative_planners:
        query["creative_planners"] = {"$in": creative_planners}
    if country:
        query["tags.country"] = {"$in": [country]}
    if is_green_material is not None:
        query["is_green_material"] = is_green_material

    skip = (page - 1) * page_size
    direction = 1 if order == "asc" else -1
    sort_spec: list = [(sort, direction)]
    # 工单数与预期素材数（quantity=该单需求项数量之和）在同一趟聚合里出，避免为素材数多扫一遍；
    # 顺带带出命中工单的 id，供下面数实际产出数复用，省一次 orders 扫描
    summary, docs = await asyncio.gather(
        orders.aggregate(
            [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": 1},
                        "material_total": {"$sum": "$quantity"},
                        "ids": {"$push": {"$toString": "$_id"}},
                    }
                },
            ]
        ).to_list(1),
        orders.find(query, projection={"references": 0, "description.attachments": 0})
        .sort(sort_spec)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size),
    )
    stat = summary[0] if summary else {}

    # 实际产出数：一趟聚合出全部命中工单的计数，行内数与合计行共用。
    # 同 basename 多版本算一个，与验收页卡片数同口径；只读 order_1_basename_1 的索引键不回表
    # （产出物文档内嵌 base64 缩略图，回表拉全量在生产库是几十秒级）
    output_counts = {
        d["_id"]: d["n"]
        async for d in order_materials.aggregate(
            [
                {"$match": {"order_id": {"$in": stat.get("ids", [])}}},
                {"$group": {"_id": {"o": "$order_id", "b": "$basename"}}},
                {"$group": {"_id": "$_id.o", "n": {"$sum": 1}}},
            ]
        )
    }

    now = _now()
    threshold = now + timedelta(hours=24)

    items = []
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
        doc["output_count"] = output_counts.get(doc["id"], 0)
        # 子需求只带 id + 描述，完整需求项走详情接口
        doc["requirements"] = [
            {"id": r.get("id"), "seq_label": r.get("seq_label")}
            for r in doc.pop("description", None) or []
            if isinstance(r, dict)
        ]
        raw_status = doc["status"]
        exp = _delivery_deadline(doc.get("expected_delivery_at"))
        doc["delivery_warning"] = bool(
            exp and exp <= threshold and raw_status in OrderStatus.UNDONE
        )
        if is_operator_personal_list:
            if raw_status in OrderStatus.IS_COMPLETE:
                doc["status"] = "is_complete"
            elif raw_status == OrderStatus.PENDING_ASSIGN:
                doc["status"] = "is_submit"  # 库里仍是 pending_assign，前端按 is_submit 展示

        # 仅预警（剩余≤1天）时给剩余整数小时（负数=已超期），否则 None
        doc["remaining_hours"] = (
            round((exp - now).total_seconds() / 3600)
            if doc["delivery_warning"]
            else None
        )
        items.append(doc)
    return ApiResponse(
        data={
            "total": stat.get("total", 0),
            "material_total": stat.get("material_total", 0),
            "material_actual_total": sum(output_counts.values()),
            "items": items,
            "page": page,
            "page_size": page_size,
        }
    )


async def order_stats():
    """需求池看板统计（组长）：全量统计已提交/制作中/待验收数量、已提交P0P1，外加临期预警明细（剩余≤1天的工单号+剩余小时）"""
    counts = {
        d["_id"]: d["count"]
        async for d in orders.aggregate(
            [
                {
                    "$match": {
                        "status": {
                            "$in": OrderStatus.kanban_statuses
                            + [OrderStatus.PARTIALLY_COMPLETED]
                        },
                    }
                },
                # 部分完成整单仍在制作阶段，计数归并进 in_production
                {
                    "$group": {
                        "_id": {
                            "$cond": [
                                {"$eq": ["$status", OrderStatus.PARTIALLY_COMPLETED]},
                                OrderStatus.IN_PRODUCTION,
                                "$status",
                            ]
                        },
                        "count": {"$sum": 1},
                    }
                },
            ]
        )
    }
    status_counts = {s: counts.get(s, 0) for s in OrderStatus.kanban_statuses}
    pending_assign_p0p1 = await orders.count_documents(
        {"status": OrderStatus.PENDING_ASSIGN, "priority": {"$in": ["P0", "P1"]}}
    )

    now = _now()
    warnings = [
        {
            "order_no": doc.get("order_no"),
            "remaining_hours": round(
                (_delivery_deadline(doc["expected_delivery_at"]) - now).total_seconds()
                / 3600
            ),
        }
        async for doc in orders.find(
            {
                "$expr": {"$lte": [_deadline_expr(), now + timedelta(hours=24)]},
                "status": {"$in": OrderStatus.UNDONE},
            },
            projection={"order_no": 1, "expected_delivery_at": 1},
        ).sort("expected_delivery_at", 1)
    ]

    return ApiResponse(
        data={
            "status_counts": status_counts,
            "pending_assign_p0p1": pending_assign_p0p1,
            "warning_count": len(warnings),
            "warnings": warnings,
        }
    )


async def batch_assign(body: BatchAssignBody):
    """批量分配工单给素材师 / 创意策划（组长）：仅对 PRE_ACCEPT 状态的工单生效。
    重新分配保留仍在新名单内素材师的完成记录：新名单全员已完成→直接转待验收，
    部分完成→部分完成，否则制作中"""
    n = _now()
    items_by_id = {item.id: item for item in body.items}
    ops = []
    to_notify: List[Tuple[str, str]] = []
    async for o in orders.find(
        {
            "_id": {"$in": [ObjectId(i) for i in items_by_id]},
            "status": {"$in": OrderStatus.PRE_ACCEPT},
        },
        projection={"completed_designers": 1, "creator": 1},
    ):
        item = items_by_id[str(o["_id"])]
        designers = item.designers
        completed = [
            d for d in o.get("completed_designers") or [] if d in designers
        ]
        if designers and set(designers) <= set(completed):
            status = OrderStatus.PENDING_ACCEPT
        elif completed:
            status = OrderStatus.PARTIALLY_COMPLETED
        else:
            status = OrderStatus.IN_PRODUCTION
        set_fields: Dict[str, Any] = {
            "designers": designers,
            "creative_planners": item.creative_planners,
            "completed_designers": completed,
            "assigned_at": n,
            "started_at": n,
            "updated_at": n,
            "status": status,
        }
        if status == OrderStatus.PENDING_ACCEPT:
            set_fields["delivered_at"] = n
        to_notify += [
            (d, o.get("creator")) for d in designers if d not in set(completed)
        ]
        ops.append(
            UpdateOne(
                {"_id": o["_id"], "status": {"$in": OrderStatus.PRE_ACCEPT}},
                {"$set": set_fields},
            )
        )
    if ops:
        res = await orders.bulk_write(ops)
        if to_notify:
            _fire(_notify_assigned(to_notify))
        return ApiResponse(data={"count": res.modified_count})
    return ApiResponse(data={"count": 0})


async def _notify_assigned(items: List[Tuple[str, str]]) -> None:
    """分配后给被指派的素材师发飞书单聊（后台任务）：每条 (素材师, 需求人) 发一条"""
    for designer, creator in items:
        await feishu.notify_by_full_name(
            designer,
            f"素材师：\n你收到了1条素材制作需求，需求人：{creator}",
        )


async def _notify_demand_submitted(
    creator: str, department: Optional[str], title: Optional[str]
) -> None:
    """投手提交需求后给素材中台群发飞书通知（后台任务）"""
    await feishu.send_text_to_chat(
        feishu.MATERIAL_GROUP_CHAT_ID,
        f"投手：{creator}\n部门：{department or ''}\n需求标题：{title or ''}\n"
        f"提交了新的素材需求，请在Adpulse尽快处理！",
    )


async def list_creators():
    """素材师列表（组长分配时选人）：返回启用中的素材师及各自制作中的工单数量。"""
    creators = await user_cols.user.find(
        # status 缺失按启用算（与 security.py 的 get("status", 1) 对齐），故用 $ne 0 而非 == 1
        {"roles": Roles.CREATOR, "status": {"$ne": 0}},
        projection={"_id": 1, "real_name": 1, "full_name": 1},
    ).to_list(length=None)
    counts = {
        d["_id"]: d["count"]
        async for d in orders.aggregate(
            [
                {
                    "$match": {
                        "status": {
                            "$in": [
                                OrderStatus.IN_PRODUCTION,
                                OrderStatus.PARTIALLY_COMPLETED,
                            ]
                        }
                    }
                },
                {"$unwind": "$designers"},
                # 部分完成单里已交付的素材师不再计入其在制负荷
                {
                    "$match": {
                        "$expr": {
                            "$not": [
                                {
                                    "$in": [
                                        "$designers",
                                        {"$ifNull": ["$completed_designers", []]},
                                    ]
                                }
                            ]
                        }
                    }
                },
                {"$group": {"_id": "$designers", "count": {"$sum": 1}}},
            ]
        )
    }
    return ApiResponse(
        data=[
            {
                "user_id": str(u["_id"]),
                "real_name": u.get("real_name"),
                "full_name": u.get("full_name"),
                "in_production_count": counts.get(u.get("full_name"), 0),
            }
            for u in creators
        ]
    )


async def batch_reject(body: BatchRejectBody):
    """批量驳回工单（组长）：把需求池里未分配/未制作的工单退回投放师并记录各自驳回理由，仅对可驳回状态生效。
    清空素材师 / 创意策划字段：驳回后重新提交需重新分配。"""
    n = _now()
    ops = [
        UpdateOne(
            {"_id": ObjectId(item.id), "status": {"$in": OrderStatus.ASSIGNABLE}},
            {
                "$set": {
                    "status": OrderStatus.DEMAND_REJECTED,
                    "reject_reason": item.reason,
                    "rejected_at": n,
                    "updated_at": n,
                    "designers": [],
                    "creative_planners": [],
                }
            },
        )
        for item in body.items
    ]
    if not ops:
        return ApiResponse(data={"count": 0})
    res = await orders.bulk_write(ops)
    return ApiResponse(data={"count": res.modified_count})


# ==================== Page3 素材师工作台（creator）====================


async def my_stats(current_user: UserModel):
    """我的工作台（素材师 / 创意策划）：本自然周视角，返回进行中卡片（本周到期的需求数/素材数/P0 且剩余≤1天的预警数）、本周已交付工单数及环比上周；任务列表走 list_orders"""
    me = current_user.full_name
    # 同一个人可能在 A 单是素材师、在 B 单是创意策划，两种身份的工单都算本人任务
    mine: Dict[str, Any] = {"$or": [{"designers": me}, {"creative_planners": me}]}
    now = _now()
    now_cst = datetime.now(CST)
    week_start = (now_cst - timedelta(days=now_cst.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=7)
    warn_threshold = now + timedelta(hours=24)

    agg = await orders.aggregate(
        [
            {
                "$match": {
                    **mine,
                    "status": {"$in": [OrderStatus.IN_PRODUCTION, OrderStatus.PARTIALLY_COMPLETED]},
                    "expected_delivery_at": {"$gte": week_start, "$lt": week_end},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "demands": {"$sum": 1},
                    "materials": {"$sum": "$quantity"},
                    "warning": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$priority", "P0"]},
                                        {"$lte": [_deadline_expr(), warn_threshold]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]
    ).to_list(1)
    ip = agg[0] if agg else {}

    delivered_count = await orders.count_documents(
        {**mine, "delivered_at": {"$gte": week_start, "$lt": week_end}}
    )
    delivered_last = await orders.count_documents(
        {
            **mine,
            "delivered_at": {"$gte": week_start - timedelta(days=7), "$lt": week_start},
        }
    )

    return ApiResponse(
        data={
            "in_progress": {
                "demands": ip.get("demands", 0),
                "materials": ip.get("materials") or 0,
                "warning": ip.get("warning", 0),
            },
            "delivered_week": {
                "count": delivered_count,
                "wow": (
                    round((delivered_count - delivered_last) / delivered_last * 100, 1)
                    if delivered_last
                    else None
                ),
            },
        }
    )


# ==================== 工单详情 / 编辑 ====================


async def get_order(order_id: str):
    """工单详情：返回单条工单，references 与 description 富文本里的上传附件每次现签临时下载链接"""
    doc = await orders.find_one({"_id": ObjectId(order_id)})
    if not doc:
        return ErrResponse(code=404, message="工单不存在")
    doc["id"] = str(doc.pop("_id"))
    _resign_upload_urls(doc.get("references"))
    _resign_upload_urls(doc.get("description"))
    return ApiResponse(data=doc)


async def update_order(order_id: str, body: MaterialOrderUpdate, current_user: UserModel):
    """编辑工单（投放师）：增量更新字段，草稿转提交评审时记录提交时间；字段变更写入修改历史"""
    update = body.model_dump(exclude_unset=True)
    _ensure_req_ids(update.get("description"))
    if "expected_delivery_at" in update:
        update["expected_delivery_at"] = _parse_dt(body.expected_delivery_at)
    update["updated_at"] = _now()
    to_submit = update.get("status") == OrderStatus.PENDING_ASSIGN
    if to_submit:
        update["submitted_at"] = _now()
    prev = await orders.find_one_and_update(
        {"_id": ObjectId(order_id)},
        {"$set": update},
    )
    if prev:
        changes = [
            {"field": k, "old": prev.get(k), "new": v}
            for k, v in update.items()
            if k not in ("updated_at", "submitted_at")
            and _strip_signed_urls(prev.get(k)) != _strip_signed_urls(v)
        ]
        if changes:
            await order_histories.insert_one(
                {
                    "order_id": order_id,
                    "operator": current_user.full_name,
                    "changes": changes,
                    "created_at": _now(),
                }
            )
    if to_submit and prev and prev.get("status") != OrderStatus.PENDING_ASSIGN:
        _fire(_notify_demand_submitted(
            prev.get("creator"),
            current_user.department,
            update.get("title") or prev.get("title"),
        ))
    return ApiResponse(data={"id": order_id})


async def list_order_histories(order_id: str):
    """工单修改历史：按时间倒序返回每次编辑的字段变更（含新旧值）"""
    items = []
    async for h in order_histories.find({"order_id": order_id}).sort("created_at", -1):
        h["id"] = str(h.pop("_id"))
        _resign_upload_urls(h.get("changes"))
        items.append(h)
    return ApiResponse(data=items)


async def batch_delete_cascade(body: BatchDeleteBody):
    """批量删除工单（投放师）：仅删草稿/已驳回状态的，其它状态剔除并返回给前端。
    连带删除其产出物记录、评论记录、修改历史；已入库素材（cols.materials）与 MinIO 对象保留。"""
    oids = [ObjectId(i) for i in body.ids]
    deletable_ids = [
        str(d["_id"])
        async for d in orders.find(
            {"_id": {"$in": oids}, "status": {"$in": OrderStatus.DELETABLE}},
            projection={"_id": 1},
        )
    ]
    skipped = [
        {"order_no": d.get("order_no"), "status": d.get("status")}
        async for d in orders.find(
            {"_id": {"$in": oids}, "status": {"$nin": OrderStatus.DELETABLE}},
            projection={"order_no": 1, "status": 1},
        )
    ]
    del_oids = [ObjectId(i) for i in deletable_ids]
    res = await orders.delete_many({"_id": {"$in": del_oids}})
    out_res = await order_materials.delete_many({"order_id": {"$in": deletable_ids}})
    cmt_res = await order_comments.delete_many({"order_id": {"$in": deletable_ids}})
    await order_histories.delete_many({"order_id": {"$in": deletable_ids}})
    return ApiResponse(data={
        "deleted_count": res.deleted_count,
        "deleted_outputs": out_res.deleted_count,
        "deleted_comments": cmt_res.deleted_count,
        "skipped": skipped,
    })


async def complete_task(order_id: str, current_user: UserModel):
    """完成制作（素材师）：记录本人已完成；部分完成落 partially_completed，全部完成整单转待验收"""
    me = current_user.full_name
    n = _now()
    doc = await orders.find_one_and_update(
        {"_id": ObjectId(order_id), "designers": me, "status": {"$in": OrderStatus.ALLOWED}},
        {"$addToSet": {"completed_designers": me}, "$set": {"updated_at": n}},
        projection={"designers": 1, "completed_designers": 1},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        return ErrResponse(message="工单不存在、非本人任务或当前状态不可完成")
    all_done = set(doc["designers"]) <= set(doc.get("completed_designers", []))
    new_status = OrderStatus.PENDING_ACCEPT if all_done else OrderStatus.PARTIALLY_COMPLETED
    set_fields: Dict[str, Any] = {"status": new_status, "updated_at": n}
    if all_done:
        set_fields["delivered_at"] = n
    # 守卫仍限 allowed（不含 pending_accept）：并发下若已被别人推进到待验收，这里不会覆盖回部分完成
    await orders.update_one(
        {"_id": ObjectId(order_id), "status": {"$in": OrderStatus.ALLOWED}},
        {"$set": set_fields},
    )
    return ApiResponse(data={"id": order_id, "status": new_status})


async def deliver(order_id: str, body: DeliverBody, current_user: UserModel):
    """上传产出物（素材师）：把产出素材加入工单，不改工单状态（提交验收走 /complete）"""
    order = await orders.find_one(
        {
            "_id": ObjectId(order_id),
            "designers": current_user.full_name,
            "status": {"$in": OrderStatus.MY_TASKS + [OrderStatus.ACCEPTED, OrderStatus.ARCHIVED]},
        },
        projection={"order_no": 1},
    )
    if not order:
        return ErrResponse(message="工单不存在、非本人任务或当前状态不可交付")
    n = _now()
    # 重新上传即视为返工：清掉本人在本单被驳回的旧产出，避免驳回件与返工件并存。
    # 按需求分开交付后只清本次涉及的需求项（req_id=None 经 $in 匹配缺失/null，兼容老数据）
    await order_materials.delete_many(
        {
            "order_id": order_id,
            "designer": current_user.full_name,
            "review_status": MaterialReviewStatus.REJECTED,
            "req_id": {"$in": list({m.req_id for m in body.materials})},
        }
    )
    docs = [
        {
            "order_id": order_id,
            "order_no": order["order_no"],
            "filename": m.filename,
            "basename": m.basename,
            "object_key": m.object_key,
            "size": m.size,
            "content_type": m.content_type,
            "filetype": m.filetype,
            "file_md5": m.file_md5,
            "sha3_256": m.sha3_256,
            "img": m.img,
            "width": m.width,
            "height": m.height,
            "duration": m.duration,
            "ai_score": None,
            "designer": body.designer,
            "creative_planner": body.creative_planner,
            "req_id": m.req_id,
            "created_at": n,
        }
        for m in body.materials
    ]
    # 同单同内容去重: file_md5 相同=相同文件(与文件名/扩展名无关); md5 缺失的不参与去重
    existing_md5s = set(
        await order_materials.distinct("file_md5", {"order_id": order_id})
    )
    existing_md5s.discard(None)
    deduped = []
    for d in docs:
        md5 = d.get("file_md5")
        if md5 and md5 in existing_md5s:
            continue
        if md5:
            existing_md5s.add(md5)
        deduped.append(d)
    if deduped:
        await order_materials.insert_many(deduped)
    await orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"updated_at": n}})
    return ApiResponse(data={"id": order_id, "count": len(deduped)})


async def blocked_material_basenames(db, basenames: List[str]) -> set:
    """返回不可删除的素材 basename：成效表有消耗，或最新广告日行仍在投(delivery=1)"""
    if not basenames:
        return set()
    placeholders = ", ".join(["%s"] * len(basenames))
    rows = await db.fetchall(
        f"""
        SELECT unique_name FROM (
            SELECT ad.unique_name, ad.delivery,
                   SUM(ad.amount_spent) OVER (PARTITION BY ad.unique_name) AS total_spent,
                   ROW_NUMBER() OVER (PARTITION BY ad.unique_name ORDER BY ad.`date` DESC) AS rn
            FROM ad_daily_detail ad
            WHERE ad.`level` = 'ad' AND ad.unique_name IN ({placeholders})
        ) t WHERE rn = 1 AND (total_spent > 0 OR delivery = 1)
        """,
        basenames,
        as_dict=True,
    )
    return {r["unique_name"] for r in rows}


async def delete_materials(
    order_id: str, body: DeleteMaterialsBody, current_user: UserModel, db
):
    """删除产出物（素材师）：从工单移除指定 basename 的产出素材，仅限本人任务且未入库的；
    有消耗或在投的素材不删（blocked 返回）"""
    order = await orders.find_one(
        {"_id": ObjectId(order_id), "designers": current_user.full_name},
        projection={"_id": 1},
    )
    if not order:
        return ErrResponse(message="工单不存在或非本人任务")
    blocked = await blocked_material_basenames(db, body.basenames)
    n = _now()
    res = await order_materials.delete_many(
        {
            "order_id": order_id,
            "basename": {"$in": [b for b in body.basenames if b not in blocked]},
        }
    )
    await orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"updated_at": n}})
    return ApiResponse(
        data={
            "id": order_id,
            "deleted_count": res.deleted_count,
            "blocked": sorted(blocked),
        }
    )


# ==================== Page4 验收页 ====================


async def list_order_materials(order_id: str):
    """工单产出素材列表（验收页）：按 素材师+创意策划+需求项 分组返回全部产出素材，附需求描述与临时预览链接。
    req_id 缺失（老数据）或需求项已被编辑删除的，requirement 为 None，前端归「未关联需求」展示"""
    order = await orders.find_one(
        {"_id": ObjectId(order_id)}, projection={"description": 1}
    )
    if not order:
        return ErrResponse(code=404, message="工单不存在")
    req_map = {
        item["id"]: item.get("seq_label")
        for item in order.get("description") or []
        if isinstance(item, dict) and item.get("id")
    }
    req_seq = {rid: i for i, rid in enumerate(req_map)}

    items = []
    # 同名多版本只取最新一版, 避免整单历史版本全量回传(单大单曾达 1200+ 条/14MB)
    pipeline = [
        {"$match": {"order_id": order_id}},
        # img(base64 缩略图)不随列表回传, 前端按需走 /materials/{id}/thumb 懒加载
        {"$unset": "img"},
        {"$sort": {"_id": -1}},
        {"$group": {"_id": "$basename", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"_id": 1}},
    ]
    async for m in order_materials.aggregate(pipeline):
        m["id"] = str(m.pop("_id"))
        m["url"] = _presign(m["object_key"])
        m["download_url"] = _presign(m["object_key"], m.get("filename") or m["object_key"])
        items.append(m)
    # in_library：按 object_key（内容寻址，等于素材库 filename）批量查素材库，标记是否已存在
    object_keys = [m["object_key"] for m in items]
    existing = {
        d["filename"]
        async for d in cols.materials.find(
            {"filename": {"$in": object_keys}}, projection={"filename": 1}
        )
    }
    # 已入库仍以内容寻址（object_key 命中素材库）为准并最优先，验收/驳回读产出物自身 review_status
    for m in items:
        m["review_status"] = (
            MaterialReviewStatus.IN_LIBRARY
            if m["object_key"] in existing
            else m.get("review_status")
        )

    grouped: Dict[tuple, list] = {}
    for m in items:
        key = (m.get("designer"), m.get("creative_planner"), m.get("req_id"))
        grouped.setdefault(key, []).append(m)
    groups = [
        {
            "designer": designer,
            "creative_planner": creative_planner,
            "req_id": req_id,
            "requirement": req_map.get(req_id),
            "materials": ms,
        }
        for (designer, creative_planner, req_id), ms in sorted(
            grouped.items(),
            # 素材师字典序，同素材师内按需求项在工单里的顺序（未关联需求的排最后），同需求项内按创意策划字典序
            key=lambda kv: (
                kv[0][0] or "",
                req_seq.get(kv[0][2], len(req_seq)),
                kv[0][1] or "",
            ),
        )
    ]
    return ApiResponse(data={"groups": groups})


async def get_material_thumbs(ids: List[str]):
    """批量取产出素材缩略图 base64（验收页视口懒加载，一批一次鉴权/往返）"""
    oids = [ObjectId(i) for i in ids[:100]]
    data: Dict[str, Optional[str]] = {}
    async for d in order_materials.find({"_id": {"$in": oids}}, projection={"img": 1}):
        data[str(d["_id"])] = d.get("img")
    return ApiResponse(data=data)


async def reject_materials(order_id: str, body: RejectMaterialsBody):
    """批量驳回工单产出素材（验收页）：可驳回的标记为已驳回供素材师返工并飞书通知；已入库（object_key 命中素材库）的不驳回并按 basename 提示；已驳回的不重复驳回也不通知，仅在 message 里提示。"""
    selected = [
        m
        async for m in order_materials.find(
            {"_id": {"$in": [ObjectId(i) for i in body.ids]}, "order_id": order_id},
            projection={"object_key": 1, "basename": 1, "review_status": 1},
        )
    ]
    in_library = {
        d["filename"]
        async for d in cols.materials.find(
            {"filename": {"$in": [m["object_key"] for m in selected]}},
            projection={"filename": 1},
        )
    }
    blocked = [m["basename"] for m in selected if m["object_key"] in in_library]
    already_rejected = [
        m["basename"]
        for m in selected
        if m["object_key"] not in in_library
        and m.get("review_status") == MaterialReviewStatus.REJECTED
    ]
    reject_ids = [
        m["_id"]
        for m in selected
        if m["object_key"] not in in_library
        and m.get("review_status") != MaterialReviewStatus.REJECTED
    ]
    res = await order_materials.update_many(
        {"_id": {"$in": reject_ids}},
        {"$set": {"review_status": MaterialReviewStatus.REJECTED, "updated_at": _now()}},
    )
    if reject_ids:
        _fire(_notify_materials_rejected(order_id, [str(i) for i in reject_ids]))
    parts = []
    if blocked:
        parts.append(f"以下素材已入库，不可驳回：{'、'.join(blocked)}")
    if already_rejected:
        parts.append(f"以下素材已驳回，无需重复驳回：{'、'.join(already_rejected)}")
    message = "；".join(parts) if parts else "Success"
    return ApiResponse(
        data={
            "id": order_id,
            "rejected_count": res.modified_count,
            "blocked_basenames": blocked,
        },
        message=message,
    )


async def accept_materials(order_id: str, body: AcceptMaterialsBody):
    """批量验收工单产出素材（验收页）：标记选中产出物为已验收，只改产出物表"""
    res = await order_materials.update_many(
        {"_id": {"$in": [ObjectId(i) for i in body.ids]}, "order_id": order_id},
        {"$set": {"review_status": MaterialReviewStatus.ACCEPTED, "updated_at": _now()}},
    )
    return ApiResponse(data={"id": order_id, "accepted_count": res.modified_count})


async def _notify_materials_rejected(order_id: str, ids: List[str]) -> None:
    """驳回产出素材后给对应素材师发飞书单聊（后台任务）：按素材师归并该单被驳回的视频，逐人一条，可一次列十多个"""
    order = await orders.find_one({"_id": ObjectId(order_id)}, projection={"title": 1})
    title = (order or {}).get("title") or ""
    by_designer: Dict[str, List[str]] = {}
    async for m in order_materials.find(
        {
            "_id": {"$in": [ObjectId(i) for i in ids]},
            "order_id": order_id,
            "review_status": MaterialReviewStatus.REJECTED,
        },
        projection={"designer": 1, "basename": 1},
    ):
        designer = m.get("designer")
        if designer:
            by_designer.setdefault(designer, []).append(m.get("basename"))
    for designer, basenames in by_designer.items():
        lines = "\n".join(basenames)
        await feishu.notify_by_full_name(designer, f"素材师：\n需求「{title}」\n素材:\n{lines}\n已驳回")


async def cancel_reject_materials(order_id: str, body: RejectMaterialsBody):
    """撤销素材驳回（验收页）：把选中的已驳回产出物恢复为待验收，不影响已验收/已入库的"""
    res = await order_materials.update_many(
        {
            "_id": {"$in": [ObjectId(i) for i in body.ids]},
            "order_id": order_id,
            "review_status": MaterialReviewStatus.REJECTED,
        },
        {"$set": {"updated_at": _now()}, "$unset": {"review_status": ""}},
    )
    return ApiResponse(data={"id": order_id, "cancelled_count": res.modified_count})


async def accept_order(order_id: str, body: AcceptBody):
    """整单验收（投放师）：整单通过→accepted 或整单打回→rejected，只改工单状态，不入库。
    连带把工单内尚未单独验收（review_status 为空）的产出物标记为对应结果，已有状态的不覆盖。"""
    order = await orders.find_one({"_id": ObjectId(order_id)}, projection={"status": 1})
    if not order:
        return ErrResponse(code=404, message="工单不存在")
    if order.get("status") != OrderStatus.PENDING_ACCEPT:
        return ErrResponse(message="工单当前状态不可验收")
    n = _now()
    set_fields: Dict[str, Any] = {"updated_at": n}
    if body.action == "pass":
        set_fields.update({"status": OrderStatus.ACCEPTED, "accepted_at": n})
        if body.rating is not None:
            set_fields["rating"] = body.rating
        material_status = MaterialReviewStatus.ACCEPTED
    else:
        set_fields.update(
            {"status": OrderStatus.REJECTED, "rejected_at": n, "completed_designers": []}
        )
        material_status = MaterialReviewStatus.REJECTED
    await orders.update_one({"_id": ObjectId(order_id)}, {"$set": set_fields})
    await order_materials.update_many(
        {"order_id": order_id, "review_status": None},
        {"$set": {"review_status": material_status, "updated_at": n}},
    )
    return ApiResponse(data={"id": order_id, "status": set_fields["status"]})


async def list_comments(order_id: str):
    """工单评论列表：按时间正序返回工单下所有沟通记录"""
    items = []
    async for c in order_comments.find({"order_id": order_id}).sort("created_at", 1):
        c["id"] = str(c.pop("_id"))
        items.append(c)
    return ApiResponse(data=items)


async def create_comment(order_id: str, body: CommentBody, current_user: UserModel):
    """发表工单评论：素材师/投放师在工单下沟通，自动标记发言角色"""
    if Roles.CREATOR in current_user.roles:
        author_role = "素材师"
    elif Roles.OPERATOR in current_user.roles:
        author_role = "投放师"
    else:
        author_role = "管理员"
    doc = {
        "order_id": order_id,
        "author": current_user.full_name,
        "author_role": author_role,
        "source": "human",
        "content": body.content,
        "event": body.event,
        "created_at": _now(),
    }
    res = await order_comments.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return ApiResponse(data=doc)


# ==================== Page5 沉淀入库（operator）====================


async def assign_materials(
    order_id: str, body: AssignMaterialsBody, current_user: UserModel, db
):
    """素材入库：把选中的产出素材登记进素材库（纯元数据，对象已在 materials 桶），
    全部分配后工单转 archived，直接返回 {assigned_count, archived}。"""
    order = await orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        return ErrResponse(code=404, message="工单不存在")

    if body.scope == MaterialScope.PERSONAL and body.folder_id:
        folder = await material_folders.find_one(
            {"_id": ObjectId(body.folder_id), "owner": current_user.full_name}
        )
        if not folder:
            return ErrResponse(message="文件夹不存在或非本人")
    count = await _sink_order_materials(
        order, body.ids, body.scope, body.folder_id, current_user.real_name, db
    )
    remaining = await order_materials.count_documents(
        {"order_id": order_id, "assigned_at": {"$exists": False}}
    )
    archived = False
    if remaining == 0:
        n = _now()
        await orders.update_one(
            {"_id": ObjectId(order_id)},
            {
                "$set": {
                    "status": OrderStatus.ARCHIVED,
                    "archived_at": n,
                    "updated_at": n,
                }
            },
        )
        archived = True
    return ApiResponse(data={"assigned_count": count, "archived": archived})


# ==================== 产出物打包下载（后台任务）====================

TMP_BUCKET = buckets.tmp
_ZIP_DOWNLOAD_WORKERS = 16


def _fetch_object(item: Tuple[str, str]) -> Tuple[str, bytes]:
    object_key, entry_name = item
    resp = minio_client.get_object(BUCKET, object_key)
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
    """打包 materials 桶里的多个产出物为 ZIP 上传临时桶，返回 {url, filename}。"""
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


async def zip_order_materials(ids: List[str]):
    """工单产出物打包下载：立即返回 {task_id}，打包在后台跑，
    前端轮询 GET /upload-tasks/{task_id} 取 {url, filename}。"""
    items = [
        (m["object_key"], m["object_key"])
        async for m in order_materials.find(
            {"_id": {"$in": [ObjectId(i) for i in ids]}},
            {"object_key": 1},
        )
    ]
    task_id = await task_service.create()
    task_service.spawn(_run_zip_job(task_id, items))
    return ApiResponse(data={"task_id": task_id})


async def zip_order_attachments(object_keys: List[str]):
    """参考资料打包下载：直接用 object_key 打包"""
    items = [(key, key) for key in object_keys if key]
    task_id = await task_service.create()
    task_service.spawn(_run_zip_job(task_id, items))
    return ApiResponse(data={"task_id": task_id})
