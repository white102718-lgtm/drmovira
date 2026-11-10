"""管理员显式指标口径与真实Meta账户来源的发布适配，不接受客户端证明。"""

import hashlib
import json
import re

from sqlalchemy import text

from orbit_api.authorization import require_system_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import uuid_field
from orbit_api.meta_account_sources import load_connection
from orbit_api.meta_read_adapter import MetaReadAdapter
from orbit_api.meta_read_contract import ReadPage, validate_api_version
from orbit_api.metric_profile_contract import MetricSourceProof, publication
from orbit_api.metric_profile_store import (
    MetricProfileAuthority,
    MetricProfileStore,
    one,
    validate_current_source,
)

# 官方固定SDK 24.0.0 adsinsights.py / attributionspec.py；不是推断latest。
ADAPTER_VERSION = "META_INSIGHTS_V24_EXPLICIT_V1"
WINDOW_MAPPING = {
    "1d_click": {"event_type": "CLICK_THROUGH", "window_days": 1},
    "7d_click": {"event_type": "CLICK_THROUGH", "window_days": 7},
    "1d_view": {"event_type": "VIEW_THROUGH", "window_days": 1},
}
REPORT_TIMES = ("impression", "conversion", "mixed")


def invalid(message="指标口径需完整明确配置"):
    raise OrbitError(422, "METRIC_PROFILE_CONFIGURATION_INVALID", message)


def profile_from_settings(identifier, settings, windows, report_time, maturity_days, api_version):
    """原配置动作字符串精确匹配，缺失不猜测；官方映射控制归因参数。"""
    validate_api_version(api_version)
    if not isinstance(settings, dict):
        invalid()
    version = settings.get("profileVersion")
    if not isinstance(version, str) or not 1 <= len(version) <= 64:
        invalid("原指标Profile版本必须为1至64字符")
    actions = {}
    for source, target in [
        ("registerActionType", "register_action_type"),
        ("purchaseActionType", "purchase_action_type"),
        ("valueActionType", "value_action_type"),
    ]:
        value = settings.get(source)
        if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value) is None:
            invalid("请在原METRICS配置中明确填写三个动作标识")
        actions[target] = value
    if (
        not isinstance(windows, list)
        or not windows
        or any(type(w) is not str or w not in WINDOW_MAPPING for w in windows)
        or len(set(windows)) != len(windows)
    ):
        invalid("请选择已核对的显式归因窗口，不能重复")
    if (
        report_time not in REPORT_TIMES
        or type(maturity_days) is not int
        or not 1 <= maturity_days <= 90
    ):
        invalid("报告时间和成熟天数必须明确配置")
    return (
        {
            "id": uuid_field(identifier, ("configuration_id",)),
            "version": version,
            "source": "META",
            **actions,
            "attribution_windows": windows,
            "action_report_time": report_time,
            "timezone_policy": "ACCOUNT_LOCAL",
            "breakdown": "TOTAL",
            "maturity_days": maturity_days,
            "verified": True,
        },
        [dict(WINDOW_MAPPING[w]) for w in windows],
    )


async def publisher(session, actor):
    # 发布租户共享口径沿用release.manage，另外必须有系统配置权限。
    current = await require_system_access(session, actor, 31086, "system.release.manage")
    integration = await require_system_access(session, actor, 31081, "system.integrations.manage")
    if current != integration:
        raise OrbitError(403, "PERMISSION_DENIED", "指标发布授权范围已变化")
    return current


class MetaMetricProfileAuthority(MetricProfileAuthority):
    """只有实际只读账户收据可生成准备对象；构造参数不是授信证明。"""

    def __init__(
        self, sessions, cipher, actor, selection, graph_version, *, adapter_factory=MetaReadAdapter
    ):
        self.sessions, self.cipher, self.actor = sessions, cipher, actor
        self.selection, self.graph_version = selection, graph_version
        self.adapter_factory = adapter_factory
        self.captured = None

    async def configuration(self, session, current):
        selected = self.selection
        row = await one(
            session,
            "SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant AND id=:id FOR SHARE",
            {"tenant": current.tenant_id, "id": selected["configuration_id"]},
        )
        if (
            row is None
            or row["section"] != "METRICS"
            or not row["enabled"]
            or row["revision"] != selected["configuration_revision"]
        ):
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标配置已变更或停用")
        return row

    async def capture(self, profile_id, version, adapter_version):
        selected = self.selection
        async with self.sessions() as session, session.begin():
            current = await publisher(session, self.actor)
            row = await self.configuration(session, current)
            source = await load_connection(
                session,
                self.cipher,
                current.tenant_id,
                selected["connection_id"],
                selected["connection_revision"],
                self.graph_version,
            )
            settings = (
                json.loads(row["settings_json"])
                if isinstance(row["settings_json"], str)
                else row["settings_json"]
            )
            profile, mapping = profile_from_settings(
                row["id"],
                settings,
                selected["attribution_windows"],
                selected["action_report_time"],
                selected["maturity_days"],
                self.graph_version,
            )
            if (profile_id, version, adapter_version) != (
                profile["id"],
                profile["version"],
                ADAPTER_VERSION,
            ):
                invalid("指标版本或官方适配版本不一致")
        page = await self.adapter_factory(source.configuration).account_page(selected["account_id"])
        if (
            not isinstance(page, ReadPage)
            or page.source_fingerprint != source.configuration.fingerprint
            or not page.complete
            or page.checkpoint is not None
            or len(page.items) != 1
            or page.items[0].get("account_id") != selected["account_id"]
        ):
            raise OrbitError(503, "METRIC_PROFILE_AUTHORITY_UNAVAILABLE", "账户来源读取不完整")
        evidence = hashlib.sha256(
            canonical(
                {
                    "selection": selected,
                    "profile": profile,
                    "mapping": mapping,
                    "api_version": self.graph_version,
                    "account_receipt": page.evidence_sha256,
                    "request": page.request_fingerprint,
                    "source": page.source_fingerprint,
                }
            ).encode()
        ).hexdigest()
        proof = MetricSourceProof(
            evidence,
            page.observed_at,
            "meta-profile:" + evidence,
            None,
            None,
            selected["connection_id"],
            selected["connection_revision"],
        )
        prepared = publication(profile, ADAPTER_VERSION, mapping, proof)
        self.captured = (
            current,
            row["revision"],
            hashlib.sha256(canonical(settings).encode()).hexdigest(),
            prepared,
        )
        return prepared

    async def revalidate(self, session, current, prepared):
        if self.captured is None or self.captured[0] != current or self.captured[3] != prepared:
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标来源准备记录不可用")
        row = await self.configuration(session, current)
        settings = (
            json.loads(row["settings_json"])
            if isinstance(row["settings_json"], str)
            else row["settings_json"]
        )
        if (
            row["revision"] != self.captured[1]
            or hashlib.sha256(canonical(settings).encode()).hexdigest() != self.captured[2]
        ):
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标原配置已变更")
        await validate_current_source(session, current.tenant_id, prepared.proof)
        return prepared.proof


def parse_selection(value):
    fields = {
        "configuration_id",
        "configuration_revision",
        "connection_id",
        "connection_revision",
        "account_id",
        "attribution_windows",
        "action_report_time",
        "maturity_days",
        "expected_revision",
    }
    if not isinstance(value, dict) or set(value) != fields:
        invalid("发布请求必须使用完整已定义字段，不能提交验证证明")
    for key in ("configuration_id", "connection_id"):
        uuid_field(value[key], (key,))
    for key in ("configuration_revision", "connection_revision", "expected_revision"):
        if (
            type(value[key]) is not int
            or not (0 if key == "expected_revision" else 1) <= value[key] <= 9007199254740991
        ):
            invalid()
    if (
        not isinstance(value["account_id"], str)
        or re.fullmatch(r"[0-9]{1,64}", value["account_id"]) is None
    ):
        invalid("需提供纯数字广告账户ID")
    windows = value["attribution_windows"]
    if (
        not isinstance(windows, list)
        or not 1 <= len(windows) <= 3
        or any(type(w) is not str or w not in WINDOW_MAPPING for w in windows)
        or len(set(windows)) != len(windows)
    ):
        invalid("需选择明确且不重复的归因窗口")
    if (
        value["action_report_time"] not in REPORT_TIMES
        or type(value["maturity_days"]) is not int
        or not 1 <= value["maturity_days"] <= 90
    ):
        invalid()
    return value


class MetaMetricProfileService:
    def __init__(self, sessions, cipher, graph_version, *, adapter_factory=MetaReadAdapter):
        self.sessions, self.cipher, self.graph_version = sessions, cipher, graph_version
        self.adapter_factory = adapter_factory

    async def replay(self, session, current, key, payload_hash):
        old = await one(
            session,
            "SELECT payload_hash,response_json FROM orbit_meta_profile_request WHERE "
            "tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE",
            {"tenant": current.tenant_id, "actor": current.actor_id, "key": key},
        )
        if old is None:
            return None
        if old["payload_hash"] != payload_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "相同请求标识已用于其他指标口径")
        return (
            json.loads(old["response_json"])
            if isinstance(old["response_json"], str)
            else old["response_json"]
        )

    async def publish(self, actor, value, key, request_id):
        from orbit_api.meta_connection_service import lock_account_clock

        selected = parse_selection(value)
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii():
            invalid("请求缺少有效幂等标识")
        payload_hash = hashlib.sha256(canonical(selected).encode()).hexdigest()
        async with self.sessions() as session, session.begin():
            current = await publisher(session, actor)
            await lock_account_clock(session, current.tenant_id)
            old = await self.replay(session, current, key, payload_hash)
            if old is not None:
                return old
        authority = MetaMetricProfileAuthority(
            self.sessions,
            self.cipher,
            actor,
            selected,
            self.graph_version,
            adapter_factory=self.adapter_factory,
        )
        async with self.sessions() as session, session.begin():
            current = await publisher(session, actor)
            row = await authority.configuration(session, current)
            settings = (
                json.loads(row["settings_json"])
                if isinstance(row["settings_json"], str)
                else row["settings_json"]
            )
            version = settings.get("profileVersion")
        store = MetricProfileStore(authority)
        prepared = await store.prepare(selected["configuration_id"], version, ADAPTER_VERSION)
        async with self.sessions() as session, session.begin():
            current = await publisher(session, actor)
            await lock_account_clock(session, current.tenant_id)
            old = await self.replay(session, current, key, payload_hash)
            if old is not None:
                return old
            result = await store.publish(
                session, current, prepared, selected["expected_revision"], request_id
            )
            await session.execute(
                text(
                    "INSERT INTO "
                    "orbit_meta_profile_request(tenant_id,actor_id,request_key,payload_hash,res"
                    "ponse_json) VALUES(:tenant,:actor,:key,:hash,:response)"
                ),
                {
                    "tenant": current.tenant_id,
                    "actor": actor,
                    "key": key,
                    "hash": payload_hash,
                    "response": canonical(result),
                },
            )
            return result
