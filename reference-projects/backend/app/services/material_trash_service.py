"""素材删除留痕：被删的 materials 文档快照进 trash.materials，只记录不还原
（MinIO 对象是物理删除的，本集合恢复不了素材）。"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from pymongo import ReplaceOne

from app.db.mongo import trash
from app.model_type_defs.user_models import UserModel

deleted_materials = trash.materials


async def record_deleted(
    docs: List[Dict[str, Any]], user: UserModel, source: str
) -> None:
    """写素材删除记录，必须在删 MinIO / materials 之前调用（删完就取不到快照了）。

    docs: materials 原文档，投影里排除 img（base64 缩略图，留下来副本体积翻倍）。
    source: 删除入口，batch=素材管理批量删除，folder=个人文件夹删除。
    """
    if not docs:
        return
    now = datetime.now(timezone.utc)
    # 按原 _id upsert：删 MinIO 那步失败后前端重删不会撞唯一键，记录也不会重复
    await deleted_materials.bulk_write(
        [
            ReplaceOne(
                {"_id": doc["_id"]},
                {
                    **doc,
                    "deleted_at": now,
                    "deleted_by": user.full_name,
                    "deleted_by_real_name": user.real_name,
                    "deleted_department": user.department,
                    "source": source,
                },
                upsert=True,
            )
            for doc in docs
        ],
        ordered=False,
    )
