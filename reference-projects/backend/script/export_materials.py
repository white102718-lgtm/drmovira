"""按 basename 从 MinIO 导出素材实体文件并打成 7z。

用法：DEPLOY_ENV=prod PYTHONPATH=. python -u script/export_materials.py <codes.txt> <out_dir> <包名>
codes.txt 里的编号用逗号或空白分隔。已下载的会跳过，失败后重跑即可续传。
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import py7zr

from app.db.my_minio import buckets, minio_client

WORKERS = 8
RETRIES = 3


def resolve_key(code: str) -> str | None:
    # 同名不同内容的素材会被重命名成 <code>_<4位时间戳>，优先取精确同名的
    keys = [
        o.object_name
        for o in minio_client.list_objects(buckets.materials, prefix=code)
    ]
    if not keys:
        return None
    return next((k for k in keys if Path(k).stem == code), keys[0])


def fetch(code: str, dest: Path) -> tuple[str, str | None]:
    """返回 (code, 错误信息)。跨境链路会随机断流，单个失败不能中断整批。"""
    try:
        key = resolve_key(code)
    except Exception as e:
        return code, f"list 失败: {e}"
    if key is None:
        return code, "MinIO 无此对象"

    target = dest / key
    if target.exists():
        return code, None
    for _ in range(RETRIES):
        try:
            minio_client.fget_object(buckets.materials, key, str(target))
            return code, None
        except Exception as e:
            err = e
    return code, f"下载失败: {err}"


def main(codes_file: str, out_dir: str, name: str) -> None:
    codes = Path(codes_file).read_text().replace(",", " ").split()
    files_dir = Path(out_dir) / name
    files_dir.mkdir(parents=True, exist_ok=True)
    for part in files_dir.glob("*.part.minio"):  # 上次断在半路的残片
        part.unlink()
    print(f"待导出 {len(codes)} 个素材 -> {files_dir}", flush=True)

    failed = []
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, (code, err) in enumerate(
            pool.map(lambda c: fetch(c, files_dir), codes), 1
        ):
            if err:
                failed.append((code, err))
            print(f"[{i}/{len(codes)}] {code} {err or 'ok'}", flush=True)

    print(f"\n成功 {len(codes) - len(failed)}/{len(codes)}")
    for code, err in failed:
        print(f"  失败 {code}: {err}")

    # 失败的下载会留下 .part.minio 残片，不能打进包里
    done = [f for f in sorted(files_dir.iterdir()) if f.suffix != ".minio"]
    # 素材本身已压缩，用 COPY 只打包不压缩，快得多且体积几乎一样
    archive = Path(out_dir) / f"{name}.7z"
    with py7zr.SevenZipFile(
        archive, "w", filters=[{"id": py7zr.FILTER_COPY}]
    ) as zf:
        for f in done:
            zf.write(f, f.name)
    size = archive.stat().st_size / 1024 / 1024
    print(f"已打包 {len(done)} 个文件：{archive}（{size:.1f} MB）")
    if failed:
        print("有失败项，重跑本命令续传（已下载的会跳过）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
