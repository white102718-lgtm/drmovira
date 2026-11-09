"""操作广告任务队列: 按开发者分队的 Redis list, 由 schedulers op_consumer 认领消费。"""
from app.db.clients import redis_cli_3

# 提交时不知道开发者的消息进此队列, 消费端按 account 反查后转发
ROUTE_PENDING_KEY = "ad_op:route_pending"


def _queue_key(operation_message: dict) -> str:
    app_id = (operation_message.get("dev_app") or {}).get("app_id")
    if not app_id:
        return ROUTE_PENDING_KEY
    op_type = operation_message.get("type")
    op_type = getattr(op_type, "value", op_type)
    lane = "create" if op_type == "create" else "fast"
    return f"ad_op:devq:{app_id}:{lane}"


async def push_op_message(operation_message: dict, message_bytes: bytes) -> None:
    await redis_cli_3.rpush(_queue_key(operation_message), message_bytes)
