"""把当前前后端源码导出到全新合仓目录；不修改原仓库、不复制私有配置。"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".runtime",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "target",
    "logs",
    "upload_path",
}
SERVER_ROOT_FILES = {
    "pyproject.toml",
    "LICENSE",
    "AGENTS.md",
    ".editorconfig",
    ".gitattributes",
}


def permitted(path: str, *, backend: bool) -> bool:
    """使用目录白名单和敏感文件黑名单，避免把本机运行数据带入目标仓库。"""
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    name = relative.name.lower()
    if name.startswith(".env") or name.endswith((".pem", ".key", ".p12", ".pfx", ".pyc")):
        return False
    if backend and relative.parts[0] not in {"python", "tools", "docs"}:
        return path in SERVER_ROOT_FILES
    return True


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def export(server: Path, web: Path, target: Path) -> dict:
    """只接受不存在的目标；原文件逐字节复制，记录来源提交及实际文件摘要。"""
    if target.exists():
        raise ValueError("目标目录已存在，请选用新的空路径，禁止覆盖已有代码")
    inventory = []
    sources = {}
    pending = []
    for name, repo, backend in (("backend", server, True), ("frontend", web, False)):
        sources[name] = {
            "commit": git(repo, "rev-parse", "HEAD").decode().strip(),
            "branch": git(repo, "branch", "--show-current").decode().strip(),
        }
        paths = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        for raw in sorted(set(paths.split(b"\0"))):
            if not raw:
                continue
            path = raw.decode("utf-8")
            if not permitted(path, backend=backend):
                continue
            source = repo / path
            if source.is_symlink():
                raise ValueError("不导出符号链接，请先人工核对")
            if not source.is_file():
                continue
            pending.append((name, path, source.read_bytes()))
    target.mkdir(parents=True)
    for name, path, content in pending:
        destination = target / name / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        inventory.append({"path": f"{name}/{path}", "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {"sources": sources, "files": inventory, "status": "LOCAL_STAGING_NOT_PUBLISHED"}
    (target / "SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"files": len(inventory), "target": str(target), "sources": sources}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(export(arguments.server, arguments.web, arguments.target), ensure_ascii=False))
