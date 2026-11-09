from enum import Enum
from typing import TypedDict


class OpType(str, Enum):
    BUDGET = "budget"
    PAUSE = "pause"
    START = "start"
    DELETE = "delete"
    CREATE = "create"


class _OperationFieldsReq(TypedDict):
    auto_run: bool
    dev_app: dict | None
    is_send: bool
    type: OpType


class _OperationFields(TypedDict, total=False):
    ext_info: dict
    id: str
    level: str
    time: int
    timezone_name: str
    value: int
    # 后来操作mongo加上的字段
    _id: str  # 当前操作记录的_id
    dev: dict  # 开发者信息
    create_config: list  # 创建广告时的配置
    batch_id: str  # 一次批量创建的稳定标识，贯穿系列/组/广告三阶段
    real_name: str
    user_id: str
    api_key: str
    game_platform: str
    agent_line: str


class OperationFields(_OperationFieldsReq, _OperationFields):
    pass
