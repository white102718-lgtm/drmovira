"""只读核对交接快照和原始需求字节，不初始化数据库或读取私有配置。"""

import hashlib
import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "HANDOFF_MANIFEST.json").read_text(encoding="utf-8"))
    problems = []
    line_ending_only = 0
    for item in manifest["files"]:
        relative = Path(item["path"])
        path = root / relative
        if relative.is_absolute() or ".." in relative.parts:
            problems.append("invalid manifest path")
            continue
        if not path.is_file() or path.is_symlink():
            problems.append(item["path"] + ": missing or symbolic")
            continue
        data = path.read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            if item.get("sha256_lf") == hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest():
                line_ending_only += 1
            else:
                problems.append(item["path"] + ": changed since handoff snapshot")
    original = root / "data/ORBIT_Codex开发PRD"
    baseline = root / "orbit-server/docs/orbit/baseline"
    count = 0
    for path in original.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        other = baseline / path.relative_to(original)
        if not other.is_file() or path.read_bytes() != other.read_bytes():
            problems.append(path.relative_to(root).as_posix() + ": baseline differs")
    if count != 43:
        problems.append("original PRD package must have 43 files")
    references = root / "reference-projects/SNAPSHOT_MANIFEST.json"
    reference_count = 0
    if references.is_file():
        snapshot = json.loads(references.read_text(encoding="utf-8"))
        projects = snapshot["projects"]
        if {p["project"] for p in projects} != {
            "ai-ad-platform-vben", "adpulse-power-system", "backend", "schedulers"
        }:
            problems.append("four historical reference snapshots required")
        forbidden = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".runtime", "target", "dist", "logs"}
        for project in projects:
            for item in project["files"]:
                path = Path(item["path"])
                if path.is_absolute() or ".." in path.parts or set(path.parts) & forbidden:
                    problems.append("forbidden reference artifact path")
                    continue
                exported = root / "reference-projects" / project["project"] / path
                if not exported.is_file() or hashlib.sha256(exported.read_bytes()).hexdigest() != item["sha256"]:
                    problems.append(str(path) + ": reference snapshot differs")
                reference_count += 1
    print(json.dumps({
        "result": "FAIL" if problems else "PASS",
        "scope": "handoff material integrity only; not product acceptance",
        "verified_manifest_files": len(manifest["files"]),
        "original_requirement_files": count,
        "line_ending_only_files": line_ending_only,
        "committed_reference_source_files": reference_count,
        "problems": problems,
    }, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
