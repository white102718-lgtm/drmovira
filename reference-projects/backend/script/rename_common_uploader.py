"""
material_commons.uploader → user

公共素材原本把上传人存成 uploader，与 materials.user 不同名，前端卡片统一读 operator/user
时取不到值（恒显示 '-'）。新写入已改为 user，本脚本把存量文档改名。

用法：DEPLOY_ENV=prod PYTHONPATH=. python -u script/rename_common_uploader.py
（默认 dry-run，确认无误后把末行 dry_run 改成 False 再跑）
"""

import asyncio

from app.db.mongo import cols


async def main(dry_run: bool = True):
    print(f"dry-run: {dry_run}\n")

    stale = await cols.material_commons.count_documents({"uploader": {"$exists": True}})
    conflict = await cols.material_commons.count_documents(
        {"uploader": {"$exists": True}, "user": {"$exists": True}}
    )
    print(f"待改名文档: {stale}")
    if conflict:
        # $rename 在目标字段已存在时会覆盖，两个都有值说明改名跑过一半或有别的写入路径
        print(f"[警告] 其中 {conflict} 条同时有 uploader 和 user，改名会以 uploader 覆盖 user")

    if not stale:
        print("\n[完成] 无需更新")
        return
    if dry_run:
        print("\n[dry-run] 以上为预览，未执行任何写入操作")
        return

    res = await cols.material_commons.update_many(
        {"uploader": {"$exists": True}}, {"$rename": {"uploader": "user"}}
    )
    print(f"\n[完成] 已改名 {res.modified_count} 条")


if __name__ == "__main__":
    asyncio.run(main(dry_run=True))
