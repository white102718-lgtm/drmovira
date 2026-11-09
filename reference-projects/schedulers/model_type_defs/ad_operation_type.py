from enum import Enum
from typing import NotRequired, TypedDict


class OpType(str, Enum):
    BUDGET = "budget"
    PAUSE = "pause"
    START = "start"
    DELETE = "delete"
    CREATE = "create"


class CampaignType(str, Enum):
    SALES = "OUTCOME_SALES"
    ENGAGEMENT = "OUTCOME_ENGAGEMENT"
    APP_PROMOTION = "OUTCOME_APP_PROMOTION"


class CreateMode(str, Enum):
    CAMPAIGN_ONLY = "campaign_only"
    ADSET_ONLY = "adset_only"
    AD_ONLY = "ad_only"
    CAMPAIGN_THEN_ADSET = "campaign_then_adset"
    ADSET_THEN_AD = "adset_then_ad"
    FULL = "full"


class RetryableOperationError(Exception):
    pass


class _OperationFieldsReq(TypedDict):
    auto_run: bool
    dev_app: dict | None
    is_send: bool
    type: OpType


class _OperationFields(TypedDict, total=False):
    ext_info: str
    id: str
    level: str
    time: int
    timezone_name: str
    value: int
    _id: str
    create_config: list[dict]
    batch_id: NotRequired[str]
    api_key: NotRequired[str]
    real_name: NotRequired[str]
    user_id: NotRequired[str]


class OperationFields(_OperationFieldsReq, _OperationFields):
    pass


def validate_operation_fields(data: OperationFields) -> None:
    """校验 api_key 和 real_name 必须至少存在一个"""
    if not data.get("api_key") and not data.get("real_name"):
        raise ValueError("OperationFields 校验失败: api_key 和 real_name 必须至少存在一个")
