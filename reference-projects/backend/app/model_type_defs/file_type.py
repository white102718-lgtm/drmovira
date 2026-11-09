from enum import Enum
from pathlib import Path
from typing import Set


class FileType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"

    def get_prefix(self) -> str:
        prefix_map = {FileType.IMAGE: "P", FileType.VIDEO: "V"}
        return prefix_map[self]


class FileExtensions:
    IMAGE_EXTENSIONS: Set[str] = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".webp",
        ".svg",
        ".ico",
        ".avif",
        ".heic",
    }
    VIDEO_EXTENSIONS: Set[str] = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}

    @staticmethod
    def classify_by_extension(filename: str) -> FileType:
        ext = Path(filename).suffix.lower()

        if ext in FileExtensions.IMAGE_EXTENSIONS:
            return FileType.IMAGE
        if ext in FileExtensions.VIDEO_EXTENSIONS:
            return FileType.VIDEO
        else:
            raise ValueError(f"未识别的文件格式: {ext}")
