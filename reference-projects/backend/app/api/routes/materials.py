import asyncio
import base64
import json
import re
import tempfile
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Dict, Any, TypedDict, Tuple

from bson import ObjectId
from fastapi import UploadFile, File, Form, Query, APIRouter, Depends
from minio.deleteobjects import DeleteObject
from pydantic import BaseModel, Field

from app.api.routes.department import get_department_subtree
from app.core.security import require_roles, auth_current_user, skip_ip_auth
from app.db.clients import redis_cli, redis_cli_2, get_db
from app.db.mongo import cols, user_cols
from app.db.my_minio import minio_client, buckets
from app.model_type_defs.common_models import (
    ApiResponse,
    ErrResponse,
    DayFormat,
    HourFormat,
)
from app.model_type_defs.file_type import FileExtensions, FileType
from app.model_type_defs.sql_constants import get_ad_stat_columns
from app.model_type_defs.tag_operations import (
    add_tags_to_doris,
    build_ad_where_conditions,
    build_select_fields,
    insert_material_to_doris,
    remove_tags_from_doris,
)
from app.model_type_defs.user_models import Roles, UserModel
from app.model_type_defs.material_order_models import (
    MATERIAL_LIST_PROJECTION,
    MaterialScope,
)
from app.services.material_order_service import blocked_material_basenames
from app.services import fb_common
from app.services import task_service
from app.services import material_link_service as link_svc
from app.services import material_poster_service as poster_svc
from app.services import material_trash_service as trash_svc
from app.services.material_tag_service import attach_tags_tree, resolve_tag_titles
from app.utils.file_util import (
    extract_thumb_and_poster_from_memory,
    convert_minio_url_to_https,
    calculate_hash,
    calculate_sha3_256,
    iter_archive_media,
    ARCHIVE_EXTS,
)

router = APIRouter(prefix="/materials", tags=["materials"])

collection = cols.materials
ad_creatives_collection = cols.ad_creatives
material_folders_collection = cols.material_folders  # list_materials 的 personal 分支要查
order_outputs_collection = cols.material_order_outputs  # 按 basename 查未入库素材的兜底

bucket_name = buckets.materials
tmp_bucket_name = buckets.tmp
REDIS_KEY = "materials:extract:description"
VIEW_ROLES = [Roles.OPERATOR, Roles.OPERATOR_LEADER, Roles.CREATOR]
CREATOR_DEPT = "素材中台"  # 唯一不受公共库部门过滤的部门


class FileListResponse(BaseModel):
    total: int
    items: List[Dict[str, Any]]
    page: int
    page_size: int


async def store_file_metadata(file_data: dict) -> str:
    result = await collection.insert_one(file_data)
    return str(result.inserted_id)


async def get_file_data(file_id: str) -> Optional[dict]:
    return await collection.find_one({"_id": ObjectId(file_id)})


async def update_file_data(file_id: str, update_data: dict) -> None:
    await collection.update_one({"_id": ObjectId(file_id)}, {"$set": update_data})


async def check_duplicate_file(file_name: str, sha3_256: str):
    while True:
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-4:]
        file_ext = Path(file_name).suffix.lower()
        file_base = file_name[: -len(file_ext)]
        new_file_name = f"{file_base}_{timestamp}{file_ext}"
        existing_new_file = await cols.materials.find_one({"filename": new_file_name})
        if not existing_new_file:
            return new_file_name, None
        if existing_new_file.get("sha3_256") == sha3_256:
            return None, existing_new_file


class FileMaterialDataRequired(TypedDict):
    filename: str
    basename: str
    filetype: FileType
    img: str  # base64编码的缩略图
    file_md5: str
    sha3_256: str
    created_at: datetime
    updated_at: datetime
    tags_new: List[str]
    scope: Optional[str]


class FileMaterialData(FileMaterialDataRequired, total=False):
    user: str | None
    country: str
    operator: str
    creative_editor: str
    game_platform: str
    origin_filename: str


async def _process_material_upload(
    file_content: bytes,
    original_filename: str,
    db,
    country: Optional[str] = None,
    operator: Optional[str] = None,
    creative_editor: Optional[str] = None,
    game_platform: Optional[str] = None,
    tags_new: Optional[List[str]] = None,
    user: Optional[str] = None,
    folder_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> Tuple[FileMaterialData, str]:
    """
    核心处理函数：处理素材上传的完整流程

    Args:
        file_content: 文件二进制内容
        original_filename: 原始文件名（用于检测文件类型）
        country: 国家（可选）
        operator: 分类（可选）
        creative_editor: 创意编辑器（可选）
        game_platform: 游戏平台（可选）
        tags: 标签列表（可选）
        user: 用户名

    Returns:
        成功时返回文件元数据字典

    Raises:
        ValueError: 文件已存在或处理失败
    """
    # 计算 MD5 和文件类型信息（hash 放线程池，hashlib 计算时释放 GIL，可多核并行）
    file_md5 = await asyncio.to_thread(calculate_hash, file_content)
    filetype = FileExtensions.classify_by_extension(original_filename)
    file_suffix = Path(original_filename).suffix.lower()
    file_name = f"{filetype.get_prefix()}{file_md5[:8]}{file_suffix}"
    basename = Path(file_name).stem

    # 生成缩略图 + 投放封面（仅视频）
    frame_bytes, poster_bytes = await asyncio.to_thread(
        extract_thumb_and_poster_from_memory,
        file_content,
        filetype,
    )

    sha3_256 = await asyncio.to_thread(calculate_sha3_256, file_content)

    # 检查重复文件
    existing_file = await cols.materials.find_one({"filename": file_name})
    if not existing_file:  # 没有数据, 第一次写入
        new_file_name = file_name
    elif existing_file.get("sha3_256") == sha3_256:  # 内容和现有的一模一样, 直接返回
        if folder_id:  # 去重命中也要把素材挂进目标文件夹
            await link_svc.link_material(existing_file["_id"], folder_id, "upload")
        return {k: v for k, v in existing_file.items() if k != "_id"}, "文件重复"
    else:  # 有同名不同内容, 重命名
        new_file_name, data = await check_duplicate_file(file_name, sha3_256)
        if new_file_name is None:
            if folder_id:
                await link_svc.link_material(data["_id"], folder_id, "upload")
            return {k: v for k, v in data.items() if k != "_id"}, "文件重复"
    # 准备文件元数据
    file_data: FileMaterialData = {
        "filename": new_file_name,
        "origin_filename": original_filename,
        "basename": basename,
        "filetype": filetype,
        "img": base64.b64encode(frame_bytes).decode("utf-8"),
        "file_md5": file_md5,
        "sha3_256": sha3_256,
        "user": user,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    # 添加可选字段
    if country:
        file_data["country"] = country
    if operator:
        file_data["operator"] = operator
    if creative_editor:
        file_data["creative_editor"] = creative_editor
    if game_platform:
        file_data["game_platform"] = game_platform

    if folder_id:
        file_data["scope"] = MaterialScope.PERSONAL

    if scope:
        file_data["scope"] = scope

    if tags_new:
        file_data["tags_new"] = tags_new
    else:
        file_data["tags_new"] = []

    # 上传到 MinIO
    await asyncio.to_thread(
        minio_client.put_object,
        bucket_name,
        new_file_name,
        BytesIO(file_content),
        length=len(file_content),
        content_type=(
            f"image/{file_suffix[1:]}"
            if filetype.value == "image"
            else f"video/{file_suffix[1:]}"
        ),
    )

    if filetype == FileType.VIDEO:
        await poster_svc.store_quietly(basename, poster=poster_bytes)

    inserted_id = await store_file_metadata(file_data)
    if folder_id:
        await link_svc.link_material(ObjectId(inserted_id), folder_id, "upload")
    asyncio.create_task(
        insert_material_to_doris(
            db, file_data["basename"], file_data.get("tags_new", [])
        )
    )

    file_data.pop("_id", None)
    return file_data, ""


async def _run_material_upload_job(
    task_id: str, file_content: bytes, filename: str, common: dict
) -> None:
    """后台跑素材入库：压缩包逐个解出入库，单文件直接入库；结果落 Redis 任务。
    单文件失败记进 result.errors（整单仍 done），解压失败/致命错才 failed。"""
    try:
        await task_service.set_processing(task_id)
        ext = Path(filename).suffix.lower()
        skipped: List[str] = []
        if ext in ARCHIVE_EXTS:
            entries, skipped = await asyncio.to_thread(
                iter_archive_media,
                file_content,
                ext,
                FileExtensions.IMAGE_EXTENSIONS | FileExtensions.VIDEO_EXTENSIONS,
            )
            if not entries:
                await task_service.fail(task_id, "压缩包内未找到支持的图片/视频")
                return
            sources = entries
        else:
            sources = [(filename, file_content)]
        items, errors = [], []
        for name, data in sources:
            try:
                fd, msg = await _process_material_upload(
                    file_content=data, original_filename=name, **common
                )
                items.append({**fd, "message": msg})
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        await task_service.done(
            task_id, {"items": items, "skipped": skipped, "errors": errors}
        )
    except Exception as e:
        await task_service.fail(task_id, str(e))


@router.post(
    "/", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL + [Roles.CREATOR]))]
)
async def create_material(
    file: UploadFile = File(...),
    country: Optional[str] = Form(None),
    operator: Optional[str] = Form(None),
    creative_editor: Optional[str] = Form(None),
    game_platform: Optional[str] = Form(None),
    tags_new: Optional[List[str]] = Form(None),
    folder_id: Optional[str] = Form(None),
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    """用户上传素材（需要认证）：压缩包(zip/7z)解压后内部图片/视频逐个入库。
    立即返回 {task_id}，处理在后台跑，前端轮询 GET /upload-tasks/{task_id} 取结果。"""
    file_content = await file.read()
    common = dict(
        db=db,
        country=country,
        operator=operator,
        creative_editor=creative_editor,
        game_platform=game_platform,
        tags_new=tags_new,
        user=current_user.real_name,
        folder_id=folder_id,
    )
    task_id = await task_service.create()
    task_service.spawn(
        _run_material_upload_job(task_id, file_content, file.filename, common)
    )
    return ApiResponse(code=0, data={"task_id": task_id})


async def _run_ad_creative_job(
    task_id: str, file_content: bytes, filename: str, user: str, db
) -> None:
    """后台跑广告创意入库：文件入 materials，ad_creatives 记录引用；结果落 Redis 任务。"""
    try:
        await task_service.set_processing(task_id)
        now = datetime.now(timezone.utc)
        file_data, _ = await _process_material_upload(
            file_content=file_content,
            original_filename=filename,
            db=db,
            user=user,
            scope=MaterialScope.TMP,
        )
        sha3_256 = file_data["sha3_256"]
        # ad_creatives 已有记录则更新 updated_at 后返回
        existing = await ad_creatives_collection.find_one({"sha3_256": sha3_256})
        if existing:
            await ad_creatives_collection.update_one(
                {"sha3_256": sha3_256}, {"$set": {"updated_at": now}}
            )
            existing["updated_at"] = now
            existing["id"] = str(existing.pop("_id"))
            await task_service.done(task_id, existing)
            return
        ad_creative_record = {
            **file_data,
            "user": user,
            "created_at": now,
            "updated_at": now,
        }
        result = await ad_creatives_collection.insert_one(ad_creative_record)
        ad_creative_record["id"] = str(result.inserted_id)
        ad_creative_record.pop("_id", None)
        await task_service.done(task_id, ad_creative_record)
    except Exception as e:
        await task_service.fail(task_id, str(e))


@router.post("/ad-creatives")
async def upload_ad_creative(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    """上传广告创意素材：立即返回 {task_id}，处理在后台跑，
    前端轮询 GET /upload-tasks/{task_id} 取 ad_creatives 记录。"""
    file_content = await file.read()
    task_id = await task_service.create()
    task_service.spawn(
        _run_ad_creative_job(
            task_id, file_content, file.filename, current_user.real_name, db
        )
    )
    return ApiResponse(code=0, data={"task_id": task_id})


@router.get("/ad-creatives")
async def list_ad_creatives(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    current_user: UserModel = Depends(auth_current_user),
    filetype: Optional[FileType] = Query(None),
    updated_at_start: Optional[str] = Query(
        None, description="updated_at 起始，格式 %Y-%m-%d %H"
    ),
    updated_at_end: Optional[str] = Query(
        None, description="updated_at 结束，格式 %Y-%m-%d %H"
    ),
):
    """查询广告创意素材，支持按 updated_at 范围过滤"""
    skip = (page - 1) * page_size
    query: Dict[str, Any] = {}

    if current_user:
        query["user"] = current_user.real_name
    if filetype:
        query["filetype"] = filetype
    if updated_at_start or updated_at_end:
        time_filter: Dict[str, Any] = {}
        if updated_at_start:
            time_filter["$gte"] = datetime.strptime(updated_at_start, HourFormat)
        if updated_at_end:
            end_dt = datetime.strptime(updated_at_end, HourFormat)
            time_filter["$lt"] = end_dt + timedelta(hours=1)
        query["updated_at"] = time_filter

    total = await ad_creatives_collection.count_documents(query)
    cursor = (
        ad_creatives_collection.find(query, projection={"sha3_256": 0, "file_md5": 0})
        .sort("updated_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        items.append(doc)

    return ApiResponse(
        data={"total": total, "items": items, "page": page, "page_size": page_size}
    )


@router.post("/internal")
@skip_ip_auth("127.0.0.1", "172.*")
async def create_material_internal(
    file: UploadFile = File(...),
    filename: str = Form(...),
    country: Optional[str] = Form(None),
    operator: Optional[str] = Form(None),
    creative_editor: Optional[str] = Form(None),
    game_platform: Optional[str] = Form(None),
    db=Depends(get_db),
):
    """
    内部素材上传接口（IP 白名单验证，供 scheduler 调用）
    所有参数（除 file 和 filename）都是可选的
    """
    file_content = await file.read()
    file_data = await _process_material_upload(
        file_content=file_content,
        original_filename=filename,
        db=db,
        country=country,
        operator=operator,
        creative_editor=creative_editor,
        game_platform=game_platform,
        tags_new=None,
        user=None,
    )
    return ApiResponse(code=0, data=file_data)


async def _public_dept_condition(current_user: UserModel) -> Optional[Dict[str, Any]]:
    """公共库的部门可见条件，None=不限部门（只有素材中台，不看角色）。
    素材归属部门 = 需求方 operator 的部门，operator 为空回退上传人 user，与素材看板同口径。
    operator 存量混 full_name/real_name（工单入库写 real_name），两者都进匹配集合。"""
    dept = current_user.department
    if dept and dept in await get_department_subtree(CREATOR_DEPT):
        return None

    names: set = set()
    reals: set = set()
    if dept:
        async for u in user_cols.user.find(
            {"department": {"$in": await get_department_subtree(dept)}},
            {"_id": 0, "real_name": 1, "full_name": 1},
        ):
            if u.get("full_name"):
                names.add(u["full_name"])
            if u.get("real_name"):
                names.add(u["real_name"])
                reals.add(u["real_name"])
    return {
        "$or": [
            {"operator": {"$in": list(names)}},
            {"operator": {"$in": [None, ""]}, "user": {"$in": list(reals)}},
        ]
    }


def _order_output_as_material(doc: Dict[str, Any]) -> Dict[str, Any]:
    """把工单产出物映射成素材库的字段口径，让未入库素材在素材库里也能搜到、预览。
    filename 取 object_key：素材库的 filename 存的就是桶里的对象名（入库时也是这么落的），
    /materials/url/{filename} 才换得到预签名；产出物自己的 filename 是原始上传名，对应 origin_filename。
    这条不在 cols.materials 里，打标签/删除/加文件夹等按 id 写库的操作对它无效。"""
    return {
        "id": str(doc["_id"]),
        "basename": doc.get("basename"),
        "filename": doc.get("object_key"),
        "origin_filename": doc.get("filename"),
        "filetype": doc.get("filetype"),
        "img": doc.get("img"),
        "created_at": doc.get("created_at"),
        # 产出物没有需求方/游戏平台/标签，制作人用素材师顶上，其余留空
        "user": doc.get("designer"),
        "creative_editor": doc.get("designer"),
        "operator": None,
        "game_platform": None,
        "tags_new": [],
        "order_no": doc.get("order_no"),
        "is_order_output": True,
    }


async def _order_output_items(basenames: List[str]) -> List[Dict[str, Any]]:
    """按 basename 从工单产出物取素材，同名多版本只取最新一版（与验收页同口径）。
    调用方只传素材库里查不到的名字，命中量有限，这里一次取完不分页。"""
    return [
        _order_output_as_material(doc)
        async for doc in order_outputs_collection.aggregate(
            [
                {"$match": {"basename": {"$in": basenames}}},
                {"$sort": {"_id": -1}},
                {"$group": {"_id": "$basename", "doc": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$doc"}},
                {"$sort": {"created_at": -1, "_id": -1}},
            ]
        )
    ]


async def _resolve_missing_basenames(
    query: Dict[str, Any], basenames: List[str], dept_cond: Optional[Dict[str, Any]]
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """按 basename 精确查的场景，给没命中的挨个标原因，前端据此提示；
    其中素材库里彻底没有、但工单产出物里有的（工单素材没入库），取回来补进列表而不算未查到。
    命中集合要跨全部页算，所以走 distinct 而不是当前页的 items。"""
    found = set(await collection.distinct("basename", query))
    missing = [b for b in basenames if b not in found]
    if not missing:
        return [], []
    scoped = {"basename": {"$in": missing}}
    in_db = set(await collection.distinct("basename", scoped))
    not_in_db = [b for b in missing if b not in in_db]
    output_items = await _order_output_items(not_in_db) if not_in_db else []
    in_order = {i["basename"] for i in output_items}
    out_of_dept: set = set()
    if dept_cond:
        out_of_dept = in_db - set(
            await collection.distinct("basename", {**scoped, **dept_cond})
        )
    out_of_range: set = set()
    if time_cond := query.get("created_at"):
        out_of_range = (
            in_db
            - out_of_dept
            - set(
                await collection.distinct(
                    "basename", {**scoped, "created_at": time_cond}
                )
            )
        )
    reasons = []
    for b in missing:
        if b in in_order:
            continue  # 已作为结果项补进列表，不算未查到
        if b not in in_db:
            reason = "素材不存在"
        elif b in out_of_dept:
            reason = "不在本部门"
        elif b in out_of_range:
            reason = "不在所选时间范围内"
        else:
            reason = "不符合其他筛选条件"
        reasons.append({"basename": b, "reason": reason})
    return reasons, output_items


@router.get("/")
async def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=400),
    sort: Optional[str] = Query(None),
    order: Optional[str] = Query(None),
    basename: Optional[List[str]] = Query(None, description="素材名，可传多个取并集"),
    game_platform: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    operator: Optional[str] = Query(None),
    creative_editor: Optional[str] = Query(None),
    user: Optional[str] = Query(None),
    filetype: Optional[FileType] = Query(None),
    tags_new: Optional[List[str]] = Query(None),
    origin_filename: Optional[str] = Query(None),
    is_green_material: Optional[bool] = Query(None, description="绿通素材，不传=不限"),
    start_time: Optional[List[str]] = Query(None),
    end_time: Optional[List[str]] = Query(None),
    scope: Optional[str] = Query(
        None, description="personal=个人文件夹(仅本人)，默认只看公共库"
    ),
    folder_id: Optional[str] = Query(
        None, description="个人文件夹id，scope=personal 时必传"
    ),
    current_user: UserModel = Depends(auth_current_user),
):
    skip = (page - 1) * page_size

    query = {}
    dept_cond = None
    # 无上传人的素材(scheduler 采集)谁都不给查，admin 也一样
    query["user"] = {"$exists": True, "$ne": None}
    if scope == MaterialScope.PERSONAL:
        # 个人文件夹已按 owner 收敛到本人，不再叠部门条件
        folder = await material_folders_collection.find_one(
            {"_id": ObjectId(folder_id), "owner": current_user.full_name}
        )
        if not folder:
            return ErrResponse(message="文件夹不存在或非本人")
        material_ids = await link_svc.folder_material_ids(folder_id)
        query["_id"] = {"$in": material_ids}
    else:
        # 只挡临时广告素材；个人文件夹素材照查，可见范围由下面的部门条件兜
        query["scope"] = {"$ne": MaterialScope.TMP}
        # operator/creative_editor 等人名筛选与本条件取交集，跨部门的人自然查不出东西
        if dept_cond := await _public_dept_condition(current_user):
            query.update(dept_cond)
    basenames = list(dict.fromkeys(b.strip() for b in basename or [] if b.strip()))
    if basenames:
        query["basename"] = {"$in": basenames}
    if game_platform:
        query["game_platform"] = game_platform
    if country:
        query["country"] = country
    if operator:
        query["operator"] = operator
    if filetype:
        query["filetype"] = filetype
    if creative_editor:
        query["creative_editor"] = creative_editor
    if user:
        query["user"] = user
    if is_green_material is not None:
        # 布尔等值本身隐含存在性：无该字段的直传/存量素材两个方向都不会命中
        query["is_green_material"] = is_green_material
    if tags_new:
        query["tags_new"] = {"$all": tags_new}
    if origin_filename:
        query["origin_filename"] = {"$regex": re.escape(origin_filename), "$options": "i"}

    # 处理时间范围查询
    if start_time and end_time:
        start_dt = datetime.strptime(start_time[0], HourFormat)
        end_dt = datetime.strptime(end_time[0], HourFormat)
        # 如果start和end相同，end需要加1天
        if start_dt == end_dt:
            end_dt = end_dt + timedelta(days=1)
        query["created_at"] = {"$gte": start_dt, "$lt": end_dt}

    total = await collection.count_documents(query)
    missing_basenames: List[Dict[str, str]] = []
    output_items: List[Dict[str, Any]] = []
    if basenames:
        missing_basenames, output_items = await _resolve_missing_basenames(
            query, basenames, dept_cond
        )

    direction = {"asc": 1, "desc": -1}.get(order) or -1
    # 同批入库的素材共用一个 created_at，并列项不补次级键翻页会串位
    sort_field = sort or "created_at"
    sort_spec = [(sort_field, direction)]
    if sort_field != "_id":
        sort_spec.append(("_id", direction))
    # 未入库的工单素材整段接在素材库结果之后，当前页跨两段切；
    # 段内各自有序，两段之间不做全局排序（basename 精确查，条数有限）
    lib_skip = min(skip, total)
    lib_limit = max(0, min(page_size, total - lib_skip))
    items = []
    tags_key_name: Dict[str, str] = {}
    if lib_limit:
        cursor = (
            collection.find(query, projection=MATERIAL_LIST_PROJECTION)
            .sort(sort_spec)
            .skip(lib_skip)
            .limit(lib_limit)
        )
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            await resolve_tag_titles(doc, tags_key_name)
            items.append(doc)
    out_skip = max(0, skip - total)
    items.extend(output_items[out_skip : out_skip + page_size - len(items)])
    return ApiResponse(
        data={
            "total": total + len(output_items),
            "items": items,
            "page": page,
            "page_size": page_size,
            "missing_basenames": missing_basenames,
        }
    )


@router.get("/with_tag_titles")
async def list_materials_with_tag_titles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    country: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(
        None, description="过滤 materials.tags_new 的标签"
    ),
    tag_filter_condition: Optional[str] = Query(
        "contains", description="标签筛选条件: contains 或 excludes"
    ),
    real_name: Optional[str] = Query(None),
    game_platform: Optional[List[str]] = Query(None),
    departments: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    date_field: Optional[str] = Query(
        "create_time", description="时间筛选字段: create_time 或 date"
    ),
    min_spent: Optional[int] = Query(None),
    db=Depends(get_db),
):
    skip = (page - 1) * page_size
    mysql_params = []
    placer_ids = set()

    # 校验 date_field
    if date_field not in ("create_time", "date"):
        date_field = "create_time"

    if departments:
        users = await user_cols.user.find(
            {"department": {"$in": departments}},
            projection={"_id": 0, "placer_id": 1},
        ).to_list(length=None)
        placer_ids.update(user["placer_id"] for user in users if user.get("placer_id"))

    if real_name:
        users = await user_cols.user.find(
            {"real_name": real_name},
            projection={"_id": 0, "placer_id": 1},
        ).to_list(length=None)
        placer_ids.update(user["placer_id"] for user in users if user.get("placer_id"))

    # 根据是否有 tags 决定查询逻辑
    mysql_query = """
                SELECT ad.unique_name, SUM(ad.amount_spent) as total_spent
                FROM ad_daily_detail ad
                INNER JOIN ad_materials m ON ad.unique_name = m.unique_name
                WHERE ad.`level`='ad'
            """
    # 解析 tags
    if tags:
        # 有 tags 时，需要 JOIN ad_materials 表
        # 构建标签数组字面量：['tag1', 'tag2', 'tag3']
        tags_literal = ", ".join(f"'{tag}'" for tag in tags)

        # 根据 tag_filter_condition 决定是包含还是排除
        if tag_filter_condition == "excludes":
            # 处理 NULL 的情况：NULL 或者不包含指定标签的记录都应该被保留
            arrays_overlap_condition = f"(m.tags IS NULL OR NOT arrays_overlap(CAST(m.tags AS ARRAY<STRING>), [{tags_literal}]))"
        else:  # contains
            # 只保留包含指定标签的记录（NULL 会被自动过滤掉）
            arrays_overlap_condition = (
                f"arrays_overlap(CAST(m.tags AS ARRAY<STRING>), [{tags_literal}])"
            )
        mysql_query = f"""{mysql_query} AND {arrays_overlap_condition}"""
    # 添加其他过滤条件
    if game_platform:
        placeholders = ", ".join(["%s"] * len(game_platform))
        mysql_query += f" AND ad.game_platform IN ({placeholders})"
        mysql_params.extend(game_platform)
    if placer_ids:
        placeholders = ", ".join(["%s"] * len(placer_ids))
        mysql_query += f" AND ad.placer_id IN ({placeholders})"
        mysql_params.extend(placer_ids)

    if start_date and end_date:
        if date_field == "create_time" and start_date == end_date:
            end_date = (
                datetime.strptime(end_date, DayFormat) + timedelta(days=1)
            ).strftime(DayFormat)
        mysql_query += f" AND (ad.`{date_field}` <= %s AND ad.`{date_field}` >= %s)"
        mysql_params += [end_date, start_date]
    mysql_query += " GROUP BY ad.unique_name"
    if min_spent is not None:
        mysql_query += f" HAVING SUM(ad.amount_spent) > {min_spent}"
    # 执行计数查询
    count = (
        await db.fetchone(
            f"SELECT COUNT(*) AS unique_name_cnt from ({mysql_query}) t", mysql_params
        )
    )[0]

    # 执行数据查询
    data_query = (
        mysql_query + f" ORDER BY total_spent DESC LIMIT {page_size} OFFSET {skip}"
    )
    mysql_results = await db.fetchall(data_query, mysql_params)
    # 保持顺序：使用 list 而不是 set，同时保存消耗数据
    basenames_ordered = [row[0] for row in mysql_results]
    basenames_set = set(basenames_ordered)
    # 创建 basename 到消耗的映射
    basename_to_spent = {row[0]: row[1] for row in mysql_results}

    # 组装 MongoDB 查询条件（公共库视图，排除个人文件夹素材和临时广告素材）
    query: Dict[str, Any] = {
        "scope": {"$nin": [MaterialScope.PERSONAL, MaterialScope.TMP]}
    }
    # if country:
    #     query["country"] = country
    query["basename"] = {"$in": list(basenames_set)}
    # Doris 层面已经过滤了 tags，这里不再需要 tags_new 过滤
    # 列表视图只返回基本字段，不返回 tags_new、tags_tree、filename、updated_at 等详情字段
    mongo_results = await collection.find(
        query,
        projection={
            "sha3_256": 0,
            "file_md5": 0,
            "analysis_description": 0,
            "tag_description": 0,
            "tags_new_docs": 0,
            "filename": 0,  # 列表不需要完整文件名
            "updated_at": 0,  # 列表不需要更新时间
        },
    ).to_list()

    # 创建 basename 到文档的映射
    basename_to_doc = {}
    tags_key_name: Dict[str, str] = {}

    for doc in mongo_results:
        doc["id"] = str(doc.pop("_id"))
        await resolve_tag_titles(doc, tags_key_name)
        basename_to_doc[doc["basename"]] = doc

    # 按照 MySQL 返回的顺序重新排序，并添加消耗数据
    result = []
    for basename in basenames_ordered:
        if basename in basename_to_doc:
            doc = basename_to_doc[basename]
            doc["total_spent"] = round(basename_to_spent.get(basename) or 0, 2)
            result.append(doc)

    return ApiResponse(
        data={"total": count, "items": result, "page": page, "page_size": page_size}
    )


@router.get("/by_ids")
async def get_materials_by_ids(
    ids: Optional[List[str]] = Query(None, description="前端传回的ID列表"),
    basenames: Optional[List[str]] = Query(None, description="前端传回的ID列表"),
    fields: Optional[str] = Query(
        None,
        description="需要返回的额外字段，逗号分隔，如：tags_tree,filename,updated_at",
    ),
):
    """
    根据ID列表批量查询素材

    参数:
        ids: 素材ID列表
        fields: 可选的额外字段，逗号分隔，支持：
            - tags_tree: 返回树形结构的标签（需要额外计算）
            - filename: 返回完整文件名
            - updated_at: 返回更新时间
    """
    # 解析 fields 为列表
    fields_list = fields.split(",") if fields else []

    # 判断是否需要 tags_tree
    need_tags_tree = "tags_tree" in fields_list

    # 基础 projection：排除敏感字段
    projection = {
        "analysis_description": 0,
        "tag_description": 0,
        "sha3_256": 0,
        "file_md5": 0,
    }

    # 如果不需要某些字段，也排除掉
    if "filename" not in fields_list:
        projection["filename"] = 0
    if "updated_at" not in fields_list:
        projection["updated_at"] = 0

    # 查询基础数据
    condition = (
        {"_id": {"$in": [ObjectId(id_) for id_ in ids]}}
        if ids
        else {"basename": {"$in": basenames}}
    )
    cursor = collection.find(condition, projection=projection)

    items: List[Dict[str, Any]] = []
    tags_key_name = {}  # 用于缓存标签ID到标题的映射

    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if need_tags_tree:
            await attach_tags_tree(doc, tags_key_name)
        items.append(doc)

    # 素材库里没有的，兜底查工单产出物：未入库的工单素材也能查详情/预览
    wanted = ids or basenames or []
    key = "id" if ids else "basename"
    if missing := [w for w in wanted if w not in {i.get(key) for i in items}]:
        if ids:
            items.extend(
                [
                    _order_output_as_material(doc)
                    async for doc in order_outputs_collection.find(
                        {"_id": {"$in": [ObjectId(i) for i in missing]}}
                    )
                ]
            )
        else:
            items.extend(await _order_output_items(missing))

    return ApiResponse(data={"total": len(items), "items": items})


@router.get("/url/{filename}")
async def get_material_url(filename: str):
    url = minio_client.presigned_get_object(
        bucket_name, filename, expires=timedelta(minutes=1)
    )
    url = convert_minio_url_to_https(url)
    return ApiResponse(data={"url": url, "filename": filename})


@router.get("/img/{basename}")
async def get_material_img(basename: str):
    """根据basename获取缩略图"""
    doc = await collection.find_one(
        {"basename": basename},
        projection={"img": 1, "_id": 0, "filename": 1, "filetype": 1},
    )
    if doc:
        return ApiResponse(
            data={
                "img": doc["img"],
                "filetype": doc["filetype"],
                "filename": doc["filename"],
            }
        )
    else:
        return ErrResponse(code=404, message=f"[{basename}]图片未上传")


@router.get("/url_by_basename/{basename}")
@skip_ip_auth("127.0.0.1", "172.*")
async def get_material_url_by_basename(basename: str):
    """根据basename获取minio Url"""
    doc = await collection.find_one(
        {"basename": basename},
        projection={"_id": 0, "filename": 1, "filetype": 1, "img": 1},
    )
    if doc:
        url = minio_client.presigned_get_object(
            bucket_name, doc["filename"], expires=timedelta(minutes=10)
        )
        url = convert_minio_url_to_https(url)
        poster_url = (
            await asyncio.to_thread(poster_svc.presigned_url, basename)
            if doc["filetype"] == FileType.VIDEO
            else None
        )
        return ApiResponse(
            data={
                "filetype": doc["filetype"],
                "url": url,
                "img": doc["img"],
                "poster_url": poster_url,
                "filename": doc["filename"],
            }
        )
    else:
        return ErrResponse(code=404, message=f"未找到basename[{basename}]图片url")


class BatchImgRequest(BaseModel):
    basenames: List[str]


@router.post("/batch_img")
async def get_batch_material_img(data: BatchImgRequest):
    """批量获取素材缩略图"""
    if not data.basenames:
        return ApiResponse(data={})

    proj = {"basename": 1, "img": 1, "_id": 0, "filename": 1, "filetype": 1}

    cursor = collection.find({"basename": {"$in": data.basenames}}, projection=proj)
    result = {}
    async for doc in cursor:
        result[doc["basename"]] = {
            "img": doc["img"],
            "filetype": doc["filetype"],
            "filename": doc["filename"],
        }

    found_basenames = set(result.keys())
    missing_basenames = [name for name in data.basenames if name not in found_basenames]

    return ApiResponse(
        data={
            "images": result,
            "missing": missing_basenames,
            "found_count": len(result),
            "missing_count": len(missing_basenames),
        }
    )


_ZIP_DOWNLOAD_WORKERS = 16


def _fetch_object(item: Tuple[str, str]) -> Tuple[str, bytes]:
    filename, entry_name = item
    resp = minio_client.get_object(bucket_name, filename)
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
    minio_client.fput_object(tmp_bucket_name, obj_name, str(zip_path))
    zip_path.unlink()
    return obj_name


async def _build_and_upload_zip(items: List[Tuple[str, str]]) -> Dict[str, str]:
    """将 MinIO 中的多个文件打包成 ZIP 并上传到临时桶，返回下载信息。
    items: List of (minio_filename, zip_entry_name)
    """
    obj_name = await asyncio.to_thread(_zip_to_minio, items)
    url = minio_client.presigned_get_object(
        tmp_bucket_name, obj_name, expires=timedelta(days=1)
    )
    url = convert_minio_url_to_https(url)
    return {"url": url, "filename": obj_name}


async def _run_zip_job(task_id: str, items: List[Tuple[str, str]]) -> None:
    """后台打包下载：下载+zip+传临时桶+presign；结果 {url, filename} 落 Redis 任务。"""
    try:
        await task_service.set_processing(task_id)
        result = await _build_and_upload_zip(items)
        await task_service.done(task_id, result)
    except Exception as e:
        await task_service.fail(task_id, str(e))


@router.post("/zip", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def download_files_as_zip(file_ids: List[str]):
    """立即返回 {task_id}，打包在后台跑，前端轮询 GET /upload-tasks/{task_id} 取 {url, filename}。"""
    object_ids = [ObjectId(id_) for id_ in file_ids]
    cursor = collection.find({"_id": {"$in": object_ids}}, {"filename": 1})
    items = [(doc["filename"], doc["filename"]) async for doc in cursor]
    task_id = await task_service.create()
    task_service.spawn(_run_zip_job(task_id, items))
    return ApiResponse(data={"task_id": task_id})


@router.post("/zip_named", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def download_files_as_zip_named(file_ids: List[str]):
    """文件名规则：系统唯一命名-产品名-投手名字-剪辑师名字-国家"""
    object_ids = [ObjectId(id_) for id_ in file_ids]
    cursor = collection.find(
        {"_id": {"$in": object_ids}},
        {
            "filename": 1,
            "game_platform": 1,
            "operator": 1,
            "creative_editor": 1,
            "country": 1,
        },
    )
    items = []
    async for doc in cursor:
        filename = doc["filename"]
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        parts = [stem]
        for field in ("game_platform", "operator", "creative_editor", "country"):
            if doc.get(field):
                parts.append(doc[field])
        items.append((filename, "-".join(parts) + suffix))
    task_id = await task_service.create()
    task_service.spawn(_run_zip_job(task_id, items))
    return ApiResponse(data={"task_id": task_id})


class BatchUpdateRequest(BaseModel):
    ids: List[str]
    basenames: Optional[List[str]] = Field(None, description="必须和ids顺序1对1")
    country: Optional[str] = None
    operator: Optional[str] = None
    creative_editor: Optional[str] = None
    user: Optional[str] = None
    game_platform: Optional[str] = None
    origin_filename: Optional[str] = None
    tags_new: Optional[List[str]] = None
    tags_remove: Optional[List[str]] = None


@router.put("/batch_update", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
@skip_ip_auth("172.(1[6-9]|2[0-9]|3[0-1]).*")
async def batch_update_materials(data: BatchUpdateRequest, db=Depends(get_db)):
    update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if data.game_platform is not None:
        update_data["game_platform"] = data.game_platform
    if data.country is not None:
        update_data["country"] = data.country
    if data.operator is not None:
        update_data["operator"] = data.operator
    if data.creative_editor is not None:
        update_data["creative_editor"] = data.creative_editor
    if data.user is not None:
        update_data["user"] = data.user
    if data.origin_filename is not None:
        update_data["origin_filename"] = data.origin_filename
    if data.tags_new is not None:
        update_data["tags_new"] = data.tags_new

    update_query = {"$set": update_data}

    if data.tags_remove:
        update_query["$pull"] = {"tags_new": {"$in": data.tags_remove}}

    ids = data.ids
    no_ads = set()
    if data.basenames:
        if data.tags_new is not None:
            no_ads = await add_tags_to_doris(db, data.basenames, data.tags_new)
        elif data.tags_remove:
            no_ads = await remove_tags_from_doris(db, data.basenames, data.tags_remove)
        indices = {data.basenames.index(x) for x in no_ads if x in data.basenames}
        ids = [val for idx, val in enumerate(ids) if idx not in indices]
    object_ids = [ObjectId(id_) for id_ in ids]
    result = await collection.update_many({"_id": {"$in": object_ids}}, update_query)
    return ApiResponse(data={"object_ids": ids, "no_exist": no_ads})


class BatchDeleteRequest(BaseModel):
    filenames: List[str]


@router.post("/batch_delete")
async def batch_delete_materials(
    data: BatchDeleteRequest,
    current_user: UserModel = Depends(
        require_roles(Roles.OPERATOR_ALL + [Roles.CREATOR])
    ),
    db=Depends(get_db),
):
    try:
        docs = await collection.find(
            {"filename": {"$in": data.filenames}}, projection={"img": 0}
        ).to_list(length=None)
        blocked = await blocked_material_basenames(
            db, list({doc["basename"] for doc in docs})
        )
        to_delete = [doc for doc in docs if doc["basename"] not in blocked]
        filenames = [doc["filename"] for doc in to_delete]
        # 留痕在真删之前：这步失败素材还在，反过来删完再记就永远查不到是谁删的
        await trash_svc.record_deleted(to_delete, current_user, "batch")
        errors = await asyncio.to_thread(
            lambda: list(
                minio_client.remove_objects(
                    bucket_name, [DeleteObject(filename) for filename in filenames]
                )
            )
        )
        result = await collection.delete_many({"filename": {"$in": filenames}})

        return ApiResponse(
            data={
                "deleted_count": result.deleted_count,
                "errors": errors,
                "blocked": sorted(blocked),
            }
        )
    except Exception as e:
        return ErrResponse(message=f"批量删除失败: {str(e)}")


class FileNames(BaseModel):
    filenames: List[str]


@router.post(
    "/analysis_desc", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def analysis_desc(file_data: FileNames):
    values = await redis_cli.lrange(REDIS_KEY, 0, -1)
    values = set(values)
    for filename in file_data.filenames:
        if filename not in values:
            await redis_cli.rpush(REDIS_KEY, filename)
    return ApiResponse(data=None)


@router.get("/analysis_desc")
async def analysis_desc_list():
    values = await redis_cli.lrange(REDIS_KEY, 0, -1)
    return ApiResponse(data=values)


# =============== 新增：树状数据接口相关函数 ===============


def get_all_parent_tag_ids(tag_ids: List[str]) -> List[str]:
    """
    根据标签ID列表，获取所有父级标签ID

    Args:
        tag_ids: 标签ID列表，如 ['1-2-3', '2-1']

    Returns:
        包含所有父级的标签ID列表，如 ['1', '1-2', '1-2-3', '2', '2-1']
    """
    all_tag_ids = set()

    for tag_id in tag_ids:
        # 拆分标签ID，获取所有父级
        parts = tag_id.split("-")
        for i in range(1, len(parts) + 1):
            parent_id = "-".join(parts[:i])
            all_tag_ids.add(parent_id)

    return list(all_tag_ids)


@router.get("/ads_by_tag")
async def get_ads_by_tag(
    tag_id: str = Query(..., description="标签ID"),
    origin: bool = Query(
        True,
        description="True:清洗前数据(ad_daily_detail), False:清洗后数据(ad_daily_cleaned)",
    ),
    game_platform: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    min_spent: Optional[int] = Query(None),
    date_field: str = Query(
        "date", description="日期过滤字段：date(统计日期) 或 create_time(广告创建时间)"
    ),
    db=Depends(get_db),
):
    """
    获取指定标签下的所有广告数据
    - 返回广告列表，每个广告包含统计指标
    - origin参数控制数据源：True为清洗前，False为清洗后
    """
    # 根据 origin 参数选择表名
    table_name = "ad_daily_detail" if origin else "ad_daily_cleaned"

    # 使用公共的统计字段定义
    stat_columns = get_ad_stat_columns("ad")

    # 使用公共函数构建 WHERE 条件和 SELECT 字段
    where_clause = build_ad_where_conditions(
        base_conditions=[f"array_contains(m.tags, '{tag_id}')"],
        game_platform=game_platform,
        start_date=start_date,
        end_date=end_date,
        date_field=date_field,
    )
    select_fields = build_select_fields(stat_columns)

    # 构建 SQL 查询
    sql = f"""
    SELECT
        ad.unique_name,
        {', '.join(select_fields)}
    FROM ad_materials m
    JOIN {table_name} ad ON m.unique_name = ad.unique_name
    WHERE {where_clause}
    GROUP BY ad.unique_name
    """

    # 添加 min_spent 过滤
    if min_spent is not None:
        sql += f" HAVING SUM(ad.amount_spent) > {min_spent}"

    sql += " ORDER BY SUM(ad.amount_spent) DESC"

    # 执行查询
    ads_data = await db.fetchall(sql, as_dict=True)

    # 为每个广告添加标识
    for ad in ads_data:
        ad["is_tag"] = False
        ad["key"] = ad["unique_name"]
        ad["title"] = ad["unique_name"]

    return ApiResponse(
        data={
            "ads": ads_data,
            "total": len(ads_data),
        }
    )


# =============== 素材推送 FB 素材库（户/BM）===============


class FbPushRequest(BaseModel):
    target_id: str = Field(description="户ID(纯数字)")
    personal_id: str = Field(description="个号ID")
    order_id: Optional[str] = Field(
        None, description="素材工单ID，传了则把推送状态写到工单 fb_push_status"
    )
    basenames: List[str]


@router.post("/fb_push")
async def create_fb_push_task(
    body: FbPushRequest, current_user: UserModel = Depends(auth_current_user)
):
    """推送素材到 FB 广告账户素材库：立即返回 {task_id}，上传由 schedulers 消费者执行，
    前端轮询 GET /materials/fb_push/{task_id} 取进度。
    同户一天内已推过的素材跳过；同户同批素材的任务一天内不重建（返回原 task_id）。"""
    access_token, app_id, app_secret, proxy, err = await fb_common.resolve_token_proxy(
        body.personal_id, fb_common.TokenType.PERSONAL
    )
    if err:
        return ErrResponse(message=err)

    target_type = "account"  # 预留 BM(business)，当前个号无 BM 素材库权限
    basenames = list(dict.fromkeys(body.basenames))
    fp_key = fb_common.material_push_fp_key(target_type, body.target_id, basenames)
    existing_task = await redis_cli_2.get(fp_key)
    if existing_task:
        return ApiResponse(data={"task_id": existing_task, "duplicated": True})

    docs = {
        d["basename"]: d
        async for d in collection.find(
            {"basename": {"$in": basenames}}, {"basename": 1, "filetype": 1}
        )
    }
    pipe = redis_cli_2.pipeline()
    for b in basenames:
        pipe.exists(fb_common.material_push_dedup_key(target_type, body.target_id, b))
    dedup_flags = await pipe.execute()

    items, to_push, skipped_names = [], [], []
    for b, pushed in zip(basenames, dedup_flags):
        if b not in docs:
            items.append({"basename": b, "status": "failed", "error": "素材不存在"})
        elif pushed:
            rec = await cols.fb_material_uploads.find_one(
                {
                    "target_type": target_type,
                    "target_id": body.target_id,
                    "basename": b,
                },
                {"fb_asset_id": 1},
            )
            items.append(
                {
                    "basename": b,
                    "status": "skipped",
                    "fb_asset_id": rec.get("fb_asset_id") if rec else None,
                }
            )
            skipped_names.append(b)
        else:
            to_push.append({"basename": b, "filetype": docs[b]["filetype"]})

    skipped_msg = (
        f"素材 {'、'.join(skipped_names)} 24小时内已推送过该户，已跳过"
        if skipped_names
        else ""
    )
    task_id = uuid.uuid4().hex
    progress = {
        "status": "pending" if to_push else "done",
        "total": len(to_push),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": skipped_msg,
        "items": items,
    }
    await redis_cli_2.set(
        fb_common.material_push_task_key(task_id),
        json.dumps(progress, ensure_ascii=False),
        ex=fb_common.MATERIAL_PUSH_TTL,
    )
    if body.order_id:
        # 初始状态；入队后的终态(done/partial/failed)由消费者回写
        await cols.material_orders.update_one(
            {"_id": ObjectId(body.order_id)},
            {"$set": {"fb_push_status": "processing"}},
        )
    if to_push:
        message = {
            "task_id": task_id,
            "target_type": target_type,
            "target_id": body.target_id,
            "order_id": body.order_id,
            "personal_id": body.personal_id,
            "app_id": app_id,
            "app_secret": app_secret,
            "access_token": access_token,
            "proxy": proxy,
            "materials": to_push,
            "fp_key": fp_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await redis_cli_2.rpush(
            fb_common.MATERIAL_PUSH_QUEUE_KEY, json.dumps(message, ensure_ascii=False)
        )
        await redis_cli_2.set(fp_key, task_id, ex=fb_common.MATERIAL_PUSH_TTL)
    return ApiResponse(data={"task_id": task_id, "skipped": skipped_msg})


@router.get("/fb_push/{task_id}")
async def get_fb_push_task(task_id: str):
    """查询素材推送 FB 任务进度"""
    raw = await redis_cli_2.get(fb_common.material_push_task_key(task_id))
    if not raw:
        return ErrResponse(code=404, message="任务不存在或已过期")
    return ApiResponse(data=json.loads(raw))
