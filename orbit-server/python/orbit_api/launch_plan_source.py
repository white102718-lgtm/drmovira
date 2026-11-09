"""配置源与状态CAS头的接力；只核持久完整性，不授予预检或执行权限。"""

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import MAX_CONFIG_BYTES

MAX_REVISION = 9_007_199_254_740_991


def unavailable():
    raise OrbitError(503, "LAUNCH_SOURCE_STATE_UNAVAILABLE", "计划配置来源不完整，请联系管理员")


def _revision(value):
    if type(value) is not int or not 1 <= value <= MAX_REVISION:
        unavailable()
    return value


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            unavailable()
    except ValueError:
        unavailable()
    return value


def _payload(value):
    """原配置最多五MiB；不得保留调用方的可变dict引用。"""
    try:
        if isinstance(value, str):
            if len(value.encode("utf-8")) > 2 * MAX_CONFIG_BYTES:
                unavailable()
            value = json.loads(value, parse_constant=lambda _: unavailable())
        if not isinstance(value, dict):
            unavailable()
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if not 0 < len(encoded) <= MAX_CONFIG_BYTES:
            unavailable()
        return value, encoded
    except (TypeError, ValueError, UnicodeError, RecursionError):
        unavailable()


@dataclass(frozen=True, repr=False)
class PlanSource:
    tenant_id: str
    plan_id: str
    source_revision: int
    head_revision: int
    payload_hash: str
    canonical_payload: bytes

    def payload(self):
        """每次显式返回新的工作副本；修改它不会改写被冻结的配置源。"""
        return json.loads(self.canonical_payload)


async def capture_plan_source(session, current, locked_head):
    """仅供已按当前动作授权并锁定Plan头的内部调用者使用。

    本函数不代替LaunchStore.row的对象范围核验，也不增加launch.read/edit权限。
    同一外层事务必须持续持有头锁；配置保存仍插入真实PlanVersion，纯状态
    流转只递增head，因此以复合主键倒序取最新配置而不猜head对应版本。
    """
    if not isinstance(current, BusinessContext) or not session.in_transaction():
        raise ValueError("配置来源读取需要当前授权context及外层事务")
    try:
        tenant = _uuid(current.tenant_id)
        plan = _uuid(locked_head["id"])
        head_revision = _revision(locked_head["revision"])
        expected_hash = locked_head["payload_hash"]
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            unavailable()
        ownership = {key: _uuid(locked_head[key]) for key in ("owner_user_id", "owner_team_id")}
        head_payload, head_bytes = _payload(locked_head["payload_json"])
        if (
            head_payload.get("ownership") != ownership
            or hashlib.sha256(head_bytes).hexdigest() != expected_hash
        ):
            unavailable()
        params = {"tenant": tenant, "plan": plan}
        metadata = (
            (
                await session.execute(
                    text(
                        "SELECT revision,payload_hash,OCTET_LENGTH(payload_json) AS storage_bytes "
                        "FROM orbit_launch_plan_version WHERE tenant_id=:tenant AND plan_id=:plan "
                        "ORDER BY revision DESC LIMIT 1 FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if metadata is None:
            unavailable()
        source_revision = _revision(metadata["revision"])
        # MySQL JSON的展示空白可能比规范JSON长；先用两倍上限保护读取，再精确校规范字节。
        if (
            source_revision > head_revision
            or metadata["payload_hash"] != expected_hash
            or type(metadata["storage_bytes"]) is not int
            or not 0 < metadata["storage_bytes"] <= 2 * MAX_CONFIG_BYTES
        ):
            unavailable()
        source = (
            (
                await session.execute(
                    text(
                        "SELECT payload_json FROM orbit_launch_plan_version "
                        "WHERE tenant_id=:tenant AND plan_id=:plan AND revision=:revision FOR SHARE"
                    ),
                    params | {"revision": source_revision},
                )
            )
            .mappings()
            .first()
        )
        if source is None:
            unavailable()
        payload, encoded = _payload(source["payload_json"])
        if (
            payload.get("ownership") != ownership
            or encoded != head_bytes
            or hashlib.sha256(encoded).hexdigest() != expected_hash
        ):
            unavailable()
        return PlanSource(tenant, plan, source_revision, head_revision, expected_hash, encoded)
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        unavailable()
