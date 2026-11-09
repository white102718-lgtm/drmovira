import re
from model_type_defs.ad_operation_type import CampaignType, OpType


# 按开发者分队的操作队列(Redis list): ad_op:devq:{app_id}:{fast|create}
AD_OP_DEV_QUEUE_PREFIX = "ad_op:devq:"
# 提交侧不知道开发者时先进此队列,消费端反查后转发
AD_OP_ROUTE_PENDING_KEY = "ad_op:route_pending"
AD_OP_DEV_CLAIM_TEMPLATE = "ad_op:dev_claim:{app_id}"
# 操作成功后待定向同步的系列,由 campaign_sync_consumer 消费
AD_OP_CAMPAIGN_SYNC_QUEUE_KEY = "ad_op:campaign_sync_queue"


def dev_lane_key(app_id: str, lane: str) -> str:
    return f"{AD_OP_DEV_QUEUE_PREFIX}{app_id}:{lane}"


def dev_queue_key(app_id: str, op_type: str) -> str:
    lane = "create" if op_type == OpType.CREATE.value else "fast"
    return dev_lane_key(app_id, lane)


def normalize_campaign_type(campaign_type: str | None) -> str:
    campaign_type = campaign_type or CampaignType.SALES.value
    valid_types = {item.value for item in CampaignType}
    if campaign_type not in valid_types:
        raise ValueError(f"不支持的广告系列类型: {campaign_type}")
    return campaign_type


def compact_for_log(text: str, max_len: int = 5000) -> str:
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}...(truncated,len={len(text)})"


def extract_error_message(error: Exception | str) -> str:
    """
    提取关键错误信息
    - Facebook接口错误：提取 "message" 字段
    - 普通异常：取最后一行
    """
    error_str = str(error)

    # 尝试提取Facebook错误的message字段
    match = re.search(r'"message"\s*:\s*"([^"]+)"', error_str)
    if match:
        return match.group(1)

    # 普通异常：取最后一行
    lines = error_str.strip().split("\n")
    return lines[-1].strip() if lines else error_str
