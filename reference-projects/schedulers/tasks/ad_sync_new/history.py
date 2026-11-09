"""ad_sync_history 的共享写入逻辑,dispatcher / account_consumer 两侧都用。"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bson import ObjectId

from db.clients import mongo_client
from utils.common import RunStatus
from utils.common_util import handle_error


@handle_error(error_message="ad_sync_new 更新同步状态失败")
def update_history_status(
    history_id: str,
    status: RunStatus,
    error: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """同 ad_sync 旧版语义:写 ad_sync_history.run_status + update_time。"""
    if not history_id:
        return
    update_doc: Dict[str, Any] = {
        "run_status": status.value,
        "update_time": datetime.now(timezone.utc),
    }
    if error:
        update_doc["errors"] = error
    if additional_fields:
        update_doc.update(additional_fields)
    mongo_client["ad_sync_history"].update_one(
        {"_id": ObjectId(history_id)}, {"$set": update_doc}
    )
