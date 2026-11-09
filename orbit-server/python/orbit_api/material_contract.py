"""素材上传与业务元数据合同；不接受客户端路径，原文件名只用于显示。"""

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _unique, _uuid

PART_SIZE = 8 * 1024 * 1024
IMAGE_LIMIT = 20 * 1024 * 1024
VIDEO_LIMIT = 500 * 1024 * 1024
MIME_KIND = {"image/jpeg": "IMAGE", "image/png": "IMAGE", "video/mp4": "VIDEO"}
STATES = frozenset(
    {
        "INITIATED",
        "UPLOADING",
        "SCANNING",
        "PROCESSING",
        "READY",
        "UPLOAD_FAILED",
        "QUARANTINED",
        "PROCESSING_FAILED",
        "ARCHIVED",
    }
)


class StrictWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class AssetWrite(StrictWrite):
    name: str
    category_id: str
    tag_ids: list[str] = Field(max_length=20)


class UploadRequest(StrictWrite):
    metadata: AssetWrite
    mime: Literal["image/jpeg", "image/png", "video/mp4"]
    size: int = Field(ge=1, le=VIDEO_LIMIT)
    sha256: str


class CompletedPart(StrictWrite):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class CompleteUpload(StrictWrite):
    size: int = Field(ge=1, le=VIDEO_LIMIT)
    sha256: str
    parts: list[CompletedPart] = Field(min_length=1, max_length=10000)


class VersionedAsset(StrictWrite):
    id: str
    revision: int = Field(ge=1, le=9007199254740991)


class BulkDelete(StrictWrite):
    assets: list[VersionedAsset] = Field(min_length=1, max_length=500)
    reason: str


class TagWrite(StrictWrite):
    name: str
    group: str


class CategoryWrite(StrictWrite):
    name: str


class ArchiveWrite(StrictWrite):
    reason: str


def parse_material(model, raw):
    """类型/未知字段返回400，合法类型但边界不符返回422；不回显上传正文。"""
    data = _parse_json(raw)
    if model is UploadRequest and isinstance(data, dict) and "mime" in data:
        if not isinstance(data["mime"], str):
            raise OrbitError(400, "INVALID_STRUCTURE", "MIME必须为字符串", "/mime")
    try:
        value = model.model_validate(data)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        pointer = "/" + "/".join(str(p) for p in first["loc"])
        structure = first["type"] in {
            "missing",
            "extra_forbidden",
            "string_type",
            "int_type",
            "list_type",
            "model_type",
        }
        raise OrbitError(
            400 if structure else 422,
            "INVALID_STRUCTURE" if structure else "FIELD_INVALID",
            "素材请求字段无效",
            pointer,
        ) from None
    metadata = value.metadata if isinstance(value, UploadRequest) else value
    if isinstance(metadata, AssetWrite):
        metadata.name = short_text(metadata.name, 100, "/name")
        metadata.category_id = _uuid(metadata.category_id, "/category_id")
        metadata.tag_ids = _unique(metadata.tag_ids, "/tag_ids", _uuid)
    if isinstance(value, (TagWrite, CategoryWrite)):
        value.name = short_text(value.name, 30, "/name")
    if isinstance(value, TagWrite):
        value.group = short_text(value.group, 30, "/group", required=False)
    if isinstance(value, (UploadRequest, CompleteUpload)):
        if not re.fullmatch(r"[a-f0-9]{64}", value.sha256):
            raise OrbitError(422, "FIELD_INVALID", "必须提供小写SHA256摘要", "/sha256")
    if isinstance(value, UploadRequest) and value.mime != "video/mp4" and value.size > IMAGE_LIMIT:
        raise OrbitError(422, "FILE_TOO_LARGE", "图片不能超过20MiB", "/size")
    if isinstance(value, CompleteUpload):
        numbers = [p.part_number for p in value.parts]
        if sorted(numbers) != list(range(1, math.ceil(value.size / PART_SIZE) + 1)):
            raise OrbitError(422, "PARTS_INVALID", "上传分片必须完整且不可重复", "/parts")
        for part in value.parts:
            if not re.fullmatch(r"[a-f0-9]{64}", part.etag):
                raise OrbitError(422, "PARTS_INVALID", "分片摘要无效", "/parts")
        value.parts.sort(key=lambda p: p.part_number)
    if isinstance(value, (BulkDelete, ArchiveWrite)):
        value.reason = short_text(value.reason, 1000, "/reason")
    if isinstance(value, BulkDelete):
        ids = []
        for asset in value.assets:
            asset.id = _uuid(asset.id, "/assets/id")
            ids.append(asset.id)
        if len(set(ids)) != len(ids):
            raise OrbitError(422, "DUPLICATE_VALUE", "批量素材不能重复", "/assets")
        value.assets.sort(key=lambda a: a.id)
    return value


def expected_part_size(size, number):
    count = math.ceil(size / PART_SIZE)
    if type(number) is not int or not 1 <= number <= count:
        raise OrbitError(422, "PARTS_INVALID", "分片编号无效")
    return min(PART_SIZE, size - (number - 1) * PART_SIZE)


def verify_magic(mime, header):
    """魔数只是扫描第一关；解码与反恶意扫描通过前不能进入READY。"""
    valid = {
        "image/png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": header.startswith(b"\xff\xd8\xff"),
        "video/mp4": len(header) >= 12 and header[4:8] == b"ftyp",
    }
    if not valid.get(mime):
        raise OrbitError(422, "FILE_SIGNATURE_INVALID", "文件内容与声明类型不一致")
