"""图片安全解码与视频有界本机处理；未安装工具、超时或损坏均不能伪造READY。"""

import json
import shutil
import subprocess
import threading
import warnings
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from orbit_api.errors import OrbitError
from orbit_api.material_contract import verify_magic

MAX_PIXELS = 50_000_000


@dataclass(frozen=True)
class ProcessedMaterial:
    width: int
    height: int
    duration: str | None


def process_material(objects, tenant, upload, mime):
    # 从读取源对象到临时预览发布均持同一跨进程guard；不持数据库事务。
    with objects.mutation_guard(tenant, upload):
        return _process_material(objects, tenant, upload, mime)


def _process_material(objects, tenant, upload, mime):
    source = objects.original(tenant, upload)
    with source.open("rb") as stream:
        verify_magic(mime, stream.read(64))
    preview = objects.directory(tenant, upload) / "preview.jpg"
    temporary = preview.with_name("preview-" + str(uuid4()) + ".jpg")
    try:
        if mime in {"image/jpeg", "image/png"}:
            result = _image(source, temporary, mime)
        else:
            result = _video(source, temporary)
        # 原路径和衍生键均为服务端分配；衍生文件不含源文件EXIF/ICC等用户元数据。
        _verify_preview(temporary)
        temporary.replace(preview)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def _verify_preview(path: Path):
    """只有真实、有界、静态JPEG才可发布；处理器退出0不等于预览有效。"""
    try:
        from PIL import Image
    except ImportError:
        raise OrbitError(503, "IMAGE_PROCESSOR_UNAVAILABLE", "图片处理组件未配置") from None
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= 5 * 1024 * 1024:
            raise ValueError
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if (
                    image.format != "JPEG"
                    or getattr(image, "n_frames", 1) != 1
                    or not 0 < image.width <= 1024
                    or not 0 < image.height <= 1024
                ):
                    raise ValueError
                image.verify()
    except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise OrbitError(422, "PREVIEW_INVALID", "素材预览处理失败") from None


def _run_processor(command, *, timeout, output_limit=65536):
    """双管道分块计数并硬限制保留内存；超限立即终止，不记录媒体工具原始输出。"""
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    failed = threading.Event()
    output = bytearray()

    def stop():
        try:
            process.kill()
        except OSError:
            pass

    def consume(stream, retain):
        total = 0
        try:
            while block := stream.read(4096):
                total += len(block)
                if total > output_limit:
                    failed.set()
                    stop()
                    break
                if retain:
                    output.extend(block)
        except OSError:
            failed.set()
            stop()
        finally:
            stream.close()

    readers = [
        threading.Thread(target=consume, args=(process.stdout, True), daemon=True),
        threading.Thread(target=consume, args=(process.stderr, False), daemon=True),
    ]
    for reader in readers:
        reader.start()
    expired = False
    try:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True
            stop()
            process.wait(timeout=5)
    finally:
        if process.poll() is None:
            stop()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
    if any(reader.is_alive() for reader in readers):
        raise subprocess.SubprocessError("PROCESSOR_PIPE_NOT_CLOSED")
    if expired:
        raise subprocess.SubprocessError("PROCESSOR_TIMEOUT")
    if failed.is_set():
        raise subprocess.SubprocessError("PROCESSOR_OUTPUT_LIMIT")
    if process.returncode:
        raise subprocess.SubprocessError("PROCESSOR_EXIT_FAILED")
    return bytes(output)


def _image(source: Path, target: Path, mime):
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        raise OrbitError(503, "IMAGE_PROCESSOR_UNAVAILABLE", "图片处理组件未配置") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                expected = "JPEG" if mime == "image/jpeg" else "PNG"
                if image.format != expected or getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_PIXELS:
                    raise ValueError
                image.verify()
            with Image.open(source) as original:
                original.load()
                image = ImageOps.exif_transpose(original).convert("RGB")
                width, height = image.size
                image.thumbnail((1024, 1024))
                image.save(target, format="JPEG", quality=85, exif=b"")
                return ProcessedMaterial(width, height, None)
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise OrbitError(422, "IMAGE_DECODE_FAILED", "图片损坏、动画或解码尺寸超限") from None


def _video(source, target):
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise OrbitError(503, "VIDEO_PROCESSOR_UNAVAILABLE", "视频处理工具尚未配置")
    try:
        probe = _run_processor(
            [
                ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(source),
            ],
            timeout=20,
        )
        info = json.loads(probe)
        video = info["streams"][0]
        width, height = video["width"], video["height"]
        duration = Decimal(info["format"]["duration"])
        if (
            type(width) is not int
            or type(height) is not int
            or width < 1
            or height < 1
            or width * height > MAX_PIXELS
            or not duration.is_finite()
            or not Decimal("0") < duration < Decimal("100000000000000")
        ):
            raise ValueError
        _run_processor(
            [
                ffmpeg,
                "-v",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=1024:1024:force_original_aspect_ratio=decrease",
                "-map_metadata",
                "-1",
                "-y",
                str(target),
            ],
            timeout=60,
        )
        return ProcessedMaterial(width, height, format(duration.quantize(Decimal("0.000001")), "f"))
    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        InvalidOperation,
    ):
        raise OrbitError(422, "VIDEO_PROCESSING_FAILED", "视频损坏或处理超时") from None
