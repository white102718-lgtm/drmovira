"""主动探测只接收观察引用，设备不能自报探测成功或授予广告写能力。"""

from pydantic import Field

from orbit_api.agent_monitor_contract import MAX_SEQ, parse
from orbit_api.reference_contract import StrictInput


class ProbeCompletionInput(StrictInput):
    agent_id: str
    boot_id: str
    seq: int = Field(ge=1, le=MAX_SEQ)
    observed_at: str


def parse_completion(raw):
    """复用设备精确UUID/时间/整数规则，禁止未知字段及结果自报。"""
    return parse(raw, ProbeCompletionInput)
