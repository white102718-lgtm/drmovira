import hashlib
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import py7zr
from py7zr.io import BytesIOFactory

from app.conf import MinioConf
from app.model_type_defs.file_type import FileType


def calculate_hash(file_content: bytes) -> str:
    """计算文件内容的 MD5 哈希值"""
    return hashlib.md5(file_content).hexdigest()


def calculate_sha3_256(file_content: bytes) -> str:
    """计算文件内容的 SHA3-256 哈希值"""
    return hashlib.sha3_256(file_content).hexdigest()


def convert_minio_url_to_https(minio_url: str) -> str:
    """
    将 MinIO 内部 HTTP URL 转换为外部 HTTPS URL（保留原始签名）

    替换策略：只替换域名部分，保留路径和所有查询参数（包括签名）
    http://52.77.250.123:9000/bucket/file.jpg?X-Amz-...
    -> https://adpulse.biz/minio/bucket/file.jpg?X-Amz-...

    Args:
        minio_url: MinIO presigned_get_object 生成的 URL

    Returns:
        转换后的 HTTPS URL（签名参数保持不变）
    """
    if not hasattr(MinioConf, 'EXTERNAL_ENDPOINT'):
        # 如果没有配置外部地址，直接返回原 URL
        return minio_url

    # 简单的字符串替换，保留签名
    # 将 http://IP:PORT 替换为 https://domain/minio
    return minio_url.replace(
        f"http://{MinioConf.ENDPOINT}",
        MinioConf.EXTERNAL_ENDPOINT
    )


THUMB_MAX_DIMENSION = 120  # 列表页缩略图
POSTER_MAX_DIMENSION = 1080  # 投放封面


def resize_max_dimension(
    width: int, height: int, max_dimension: int = THUMB_MAX_DIMENSION
) -> tuple[int, int]:
    """
    按比例缩放图像，使得最长边不超过指定值
    Returns:
        tuple[int, int]: 缩放后的宽度和高度
    """
    longest_edge = max(width, height)
    if longest_edge <= max_dimension:
        return width, height
    scale_ratio = max_dimension / longest_edge
    new_width = int(width * scale_ratio)
    new_height = int(height * scale_ratio)
    return new_width, new_height


def _encode_scaled(frame, max_dimension: int) -> bytes | None:
    height, width = frame.shape[:2]
    ok, buffer = cv2.imencode(
        ".jpg",
        cv2.resize(
            frame,
            resize_max_dimension(width, height, max_dimension),
            interpolation=cv2.INTER_AREA,
        ),
    )
    return buffer.tobytes() if ok else None


def _decode_first_frame(bytes_: bytes, type_: FileType):
    if type_ != FileType.VIDEO:
        return cv2.imdecode(np.frombuffer(bytes_, np.uint8), cv2.IMREAD_COLOR)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        temp_file.write(bytes_)
        temp_file_path = temp_file.name
    try:
        cap = cv2.VideoCapture(temp_file_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise ValueError("无法从视频中提取帧")
        return frame
    finally:
        Path(temp_file_path).unlink(missing_ok=True)


def extract_first_frame_from_memory(
    bytes_: bytes,
    type_: FileType,
) -> bytes:
    return _encode_scaled(_decode_first_frame(bytes_, type_), THUMB_MAX_DIMENSION)


def extract_thumb_and_poster_from_memory(
    bytes_: bytes, type_: FileType
) -> tuple[bytes, bytes | None]:
    """一次解码出列表页缩略图 + 投放封面（仅视频）。整段视频落盘解码只做一遍。"""
    frame = _decode_first_frame(bytes_, type_)
    poster = (
        _encode_scaled(frame, POSTER_MAX_DIMENSION)
        if type_ == FileType.VIDEO
        else None
    )
    return _encode_scaled(frame, THUMB_MAX_DIMENSION), poster


def extract_video_poster_from_path(path: str) -> bytes | None:
    """视频首帧大图（最长边 ≤1080），投放封面用。解码失败返回 None（不抛异常）"""
    try:
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
        cap.release()
        return _encode_scaled(frame, POSTER_MAX_DIMENSION) if ret else None
    except Exception:
        return None


def extract_thumb_and_meta(bytes_: bytes, is_video: bool):
    """首帧缩略图 + 元数据，返回 (缩略图jpeg|None, width|None, height|None, duration秒|None)。
    视频可只传头部（faststart 时可解；非 faststart 时长可能取不到）。解码失败 thumb=None（不抛异常）"""
    width = height = duration = None
    try:
        if is_video:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
                f.write(bytes_)
                path = f.name
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps and fps > 0 and frames and frames > 0:
                duration = round(frames / fps)
            ret, frame = cap.read()
            cap.release()
            Path(path).unlink()
            if not ret:
                return None, width, height, duration
        else:
            frame = cv2.imdecode(np.frombuffer(bytes_, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return None, None, None, None
        height, width = frame.shape[:2]
        thumb = cv2.resize(
            frame, resize_max_dimension(width, height), interpolation=cv2.INTER_AREA
        )
        ok, buffer = cv2.imencode(".jpg", thumb)
        return (buffer.tobytes() if ok else None), int(width), int(height), duration
    except Exception:
        return None, None, None, None


def hash_file(path: str, chunk_size: int = 8 * 1024 * 1024) -> tuple[str, str]:
    """单次顺序读流式计算 (md5, sha3_256)，大文件不占内存。阻塞 IO，须在线程里跑。"""
    md5 = hashlib.md5()
    sha3 = hashlib.sha3_256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5.update(chunk)
            sha3.update(chunk)
    return md5.hexdigest(), sha3.hexdigest()


def extract_thumb_and_meta_from_path(path: str, is_video: bool):
    """同 extract_thumb_and_meta，但直接读磁盘上的完整文件：视频用 VideoCapture(path)，OpenCV 按需
    读取（首帧 + 时长所需的容器索引），不把整个文件读进 Python 内存，适配大文件。
    能否出缩略图取决于 OpenCV/FFmpeg 对该编码的支持，与传 path/bytes 无关；解码失败 thumb=None（不抛异常）"""
    width = height = duration = None
    try:
        if is_video:
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps and fps > 0 and frames and frames > 0:
                duration = round(frames / fps)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return None, width, height, duration
        else:
            frame = cv2.imread(path, cv2.IMREAD_COLOR)
            if frame is None:
                return None, None, None, None
        height, width = frame.shape[:2]
        thumb = cv2.resize(
            frame, resize_max_dimension(width, height), interpolation=cv2.INTER_AREA
        )
        ok, buffer = cv2.imencode(".jpg", thumb)
        return (buffer.tobytes() if ok else None), int(width), int(height), duration
    except Exception:
        return None, None, None, None


ARCHIVE_EXTS = {".zip", ".7z"}
MAX_ARCHIVE_ENTRIES = 500
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024  # 解压后总大小上限 2GB


def _zip_entry_name(info: zipfile.ZipInfo) -> str:
    # zip 未置 UTF-8 标志位时文件名按 cp437 解码，中文需回退 gbk
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("gbk")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename


def _is_junk(name: str) -> bool:
    base = Path(name).name
    return not base or base.startswith("._") or "__MACOSX" in name


def _check_archive_limits(
    count: int,
    total_uncompressed: int,
    max_uncompressed: int = MAX_ARCHIVE_UNCOMPRESSED,
) -> None:
    if count > MAX_ARCHIVE_ENTRIES:
        raise ValueError(f"压缩包内文件过多（上限 {MAX_ARCHIVE_ENTRIES}）")
    if total_uncompressed > max_uncompressed:
        raise ValueError(f"压缩包解压后体积超过 {max_uncompressed // (1024 ** 3)}GB 限制")


def iter_archive_media(
    content: bytes, ext: str, allowed_exts: set[str]
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """解压 archive，返回 (媒体[(文件名, bytes)], 被忽略的非媒体文件名)。
    解压前先用头部元数据校验条目数/解压后总大小，超限抛 ValueError。
    阻塞操作，须在 asyncio.to_thread 中调用。"""
    media: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    if ext == ".zip":
        with zipfile.ZipFile(BytesIO(content)) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            _check_archive_limits(len(infos), sum(i.file_size for i in infos))
            for info in infos:
                name = _zip_entry_name(info)
                if _is_junk(name):
                    continue
                base = Path(name).name
                if Path(base).suffix.lower() in allowed_exts:
                    media.append((base, zf.read(info)))
                else:
                    skipped.append(base)
    else:  # .7z：list()/extract() 用两个独立句柄，避免读 header 后内部状态影响解压
        with py7zr.SevenZipFile(BytesIO(content)) as zf:
            infos = [f for f in zf.list() if not f.is_directory]
        _check_archive_limits(len(infos), sum(f.uncompressed for f in infos))
        targets = []
        for f in infos:
            if _is_junk(f.filename):
                continue
            base = Path(f.filename).name
            if Path(base).suffix.lower() in allowed_exts:
                targets.append(f.filename)
            else:
                skipped.append(base)
        if targets:
            factory = BytesIOFactory(MAX_ARCHIVE_UNCOMPRESSED)
            with py7zr.SevenZipFile(BytesIO(content)) as zf:
                zf.extract(targets=targets, factory=factory)
            for n in targets:
                product = factory.products[n]
                product.seek(0)  # 写入后游标在末尾，读前需归零
                media.append((Path(n).name, product.read()))
    return media, skipped


def extract_archive_media_to_dir(
    archive_path: str,
    ext: str,
    allowed_exts: set[str],
    dest_dir: str,
    max_uncompressed: int = MAX_ARCHIVE_UNCOMPRESSED,
) -> tuple[list[tuple[str, str]], list[str]]:
    """流式解压 archive 到 dest_dir，返回 (媒体[(原文件名, 落盘路径)], 被忽略的非媒体文件名)。
    同 iter_archive_media 但条目落盘而非进内存，适配大压缩包。阻塞操作，须在线程里跑。"""
    media: list[tuple[str, str]] = []
    skipped: list[str] = []
    dest = Path(dest_dir)
    if ext == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            _check_archive_limits(
                len(infos), sum(i.file_size for i in infos), max_uncompressed
            )
            for idx, info in enumerate(infos):
                name = _zip_entry_name(info)
                if _is_junk(name):
                    continue
                base = Path(name).name
                if Path(base).suffix.lower() in allowed_exts:
                    out_path = dest / f"{idx}_{base}"  # idx 前缀避免同名条目落盘互相覆盖
                    with zf.open(info) as src, open(out_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    media.append((base, str(out_path)))
                else:
                    skipped.append(base)
    else:  # .7z：list()/extract() 用两个独立句柄，避免读 header 后内部状态影响解压
        with py7zr.SevenZipFile(archive_path) as zf:
            infos = [f for f in zf.list() if not f.is_directory]
        _check_archive_limits(
            len(infos), sum(f.uncompressed for f in infos), max_uncompressed
        )
        targets = []
        for f in infos:
            if _is_junk(f.filename):
                continue
            base = Path(f.filename).name
            if Path(base).suffix.lower() in allowed_exts:
                targets.append(f.filename)
            else:
                skipped.append(base)
        if targets:
            with py7zr.SevenZipFile(archive_path) as zf:
                zf.extract(path=dest_dir, targets=targets)
            for n in targets:
                media.append((Path(n).name, str(dest / n)))
    return media, skipped
