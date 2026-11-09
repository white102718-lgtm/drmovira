"""投放封面：视频首帧 ≤1080 大图，与素材同桶，按 posters/{basename}.jpg 寻址。

素材文档里的 img 是 120px 的列表页缩略图，拿去当 FB 视频广告封面会被放大糊掉，
所以投放封面单独存一份。老素材没有封面时调用方退回 img。
"""

import asyncio
import logging
from datetime import timedelta
from io import BytesIO

from minio.error import S3Error

from app.db.my_minio import minio_client, buckets
from app.utils.file_util import (
    convert_minio_url_to_https,
    extract_video_poster_from_path,
)

BUCKET = buckets.materials
URL_EXPIRES = timedelta(minutes=10)


def _key(basename: str) -> str:
    return f"posters/{basename}.jpg"


def store(basename: str, poster: bytes | None) -> bool:
    if not poster:
        return False
    minio_client.put_object(
        BUCKET,
        _key(basename),
        BytesIO(poster),
        length=len(poster),
        content_type="image/jpeg",
    )
    return True


def store_from_path(basename: str, path: str) -> bool:
    return store(basename, extract_video_poster_from_path(path))


async def store_quietly(
    basename: str, *, poster: bytes | None = None, path: str | None = None
) -> None:
    """入库流程里用：封面生成失败不影响素材本身入库。
    poster 传已抽好的帧，path 交给本模块从文件抽。"""
    try:
        if path is not None:
            ok = await asyncio.to_thread(store_from_path, basename, path)
        else:
            ok = await asyncio.to_thread(store, basename, poster)
        if not ok:
            logging.warning(f"未能提取视频首帧，跳过投放封面: {basename}")
    except Exception:
        logging.exception(f"生成投放封面失败: {basename}")


def exists(basename: str) -> bool:
    try:
        minio_client.stat_object(BUCKET, _key(basename))
        return True
    except S3Error:
        return False


def presigned_url(basename: str) -> str | None:
    if not exists(basename):
        return None
    return convert_minio_url_to_https(
        minio_client.presigned_get_object(BUCKET, _key(basename), expires=URL_EXPIRES)
    )
