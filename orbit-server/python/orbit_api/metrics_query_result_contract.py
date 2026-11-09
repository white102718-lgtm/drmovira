"""原Metrics结果的内部预期流合同；结构合法不授信，不包含生产Provider。"""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_contract import MAX_SAFE_INTEGER

RESULT_DATASETS = ("ACCOUNT", "CAMPAIGN", "ADSET", "AD")
MAX_EXPECTED_BATCH = 200
EXPECTED_STREAM_VERSION = "orbit-metric-expectation-canonical-lines-v2"


def unverified():
    raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "指标结果或预期集合尚未完整核验") from None


def strict_integer(value, *, minimum=0, maximum=MAX_SAFE_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        unverified()
    return value


def strict_uuid(value):
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value)
        is None
    ):
        unverified()
    return value


def strict_hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        unverified()
    return value


def strict_day(value):
    if type(value) is not date:
        unverified()
    return value


def strict_version(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        unverified()
    try:
        value.encode("utf-8")
    except UnicodeError:
        unverified()
    return value


@dataclass(frozen=True, repr=False)
class QuerySourceIdentity:
    tenant_id: str
    publication_id: str
    generation: int
    profile_id: str
    profile_version: str
    profile_hash: str
    authority_kind: str

    def __post_init__(self):
        for value in (self.tenant_id, self.publication_id, self.profile_id):
            strict_uuid(value)
        strict_integer(self.generation, minimum=1)
        strict_version(self.profile_version)
        strict_hash(self.profile_hash)
        if type(self.authority_kind) is not str or self.authority_kind not in {
            "TRUSTED",
            "ISOLATED_TEST",
        }:
            unverified()


@dataclass(frozen=True, repr=False)
class ExpectedUnitManifest:
    """绑定完整原query/来源/当前范围的独立预期根，不从返回事实推算。"""

    source: QuerySourceIdentity
    actor_id: int
    subject_id: str
    auth_version: int
    auth_fingerprint: str
    query_hash: str
    dataset: str
    date_from: date
    date_to: date
    scope_snapshot_id: str | None
    scope_hash: str | None
    scope_count: int | None
    unit_count: int
    unit_hash: str
    membership_count: int
    membership_hash: str

    def __post_init__(self):
        if type(self.source) is not QuerySourceIdentity:
            unverified()
        strict_integer(self.actor_id, minimum=1)
        strict_integer(self.auth_version, minimum=1)
        strict_uuid(self.subject_id)
        for value in (self.auth_fingerprint, self.query_hash, self.unit_hash, self.membership_hash):
            strict_hash(value)
        if self.dataset not in RESULT_DATASETS or type(self.dataset) is not str:
            unverified()
        strict_day(self.date_from)
        strict_day(self.date_to)
        if not 1 <= (self.date_to - self.date_from).days + 1 <= 93:
            unverified()
        if self.scope_snapshot_id is None:
            if self.scope_hash is not None or self.scope_count is not None:
                unverified()
        else:
            strict_uuid(self.scope_snapshot_id)
            strict_hash(self.scope_hash)
            strict_integer(self.scope_count, maximum=50000)
        strict_integer(self.unit_count)
        strict_integer(self.membership_count)


@dataclass(frozen=True, repr=False)
class ExpectedUnitReceipt:
    tenant_id: str
    account_id: str
    business_date: date
    profile_id: str
    profile_version: str
    owner_user_id: str | None
    owner_team_id: str | None
    currency: str
    timezone_name: str
    account_snapshot_id: str
    attribution_version: int
    entity_count: int
    entity_hash: str

    def __post_init__(self):
        for value in (self.tenant_id, self.account_id, self.profile_id, self.account_snapshot_id):
            strict_uuid(value)
        for value in (self.owner_user_id, self.owner_team_id):
            if value is not None:
                strict_uuid(value)
        strict_day(self.business_date)
        strict_version(self.profile_version)
        if type(self.currency) is not str or len(self.currency) != 3:
            unverified()
        if type(self.timezone_name) is not str:
            unverified()
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            unverified()
        strict_integer(self.attribution_version, minimum=1)
        strict_integer(self.entity_count)
        strict_hash(self.entity_hash)

    def key(self):
        return (self.account_id, self.business_date)

    def record(self):
        return (
            self.tenant_id,
            self.account_id,
            self.business_date.isoformat(),
            self.profile_id,
            self.profile_version,
            self.owner_user_id,
            self.owner_team_id,
            self.currency,
            self.timezone_name,
            self.account_snapshot_id,
            self.attribution_version,
            self.entity_count,
            self.entity_hash,
        )


@dataclass(frozen=True, repr=False)
class ExpectedEntityMembership:
    tenant_id: str
    account_id: str
    business_date: date
    profile_id: str
    profile_version: str
    dataset: str
    entity_id: str
    entity_snapshot_id: str
    name_capture_sequence: int
    name_observed_at: datetime

    def __post_init__(self):
        for value in (
            self.tenant_id,
            self.account_id,
            self.profile_id,
            self.entity_id,
            self.entity_snapshot_id,
        ):
            strict_uuid(value)
        strict_day(self.business_date)
        strict_version(self.profile_version)
        strict_integer(self.name_capture_sequence, minimum=1)
        if (
            type(self.name_observed_at) is not datetime
            or self.name_observed_at.tzinfo is None
            or self.name_observed_at.utcoffset() != timedelta(0)
        ):
            unverified()
        if type(self.dataset) is not str or self.dataset not in RESULT_DATASETS:
            unverified()

    def key(self):
        # 同单元同实体不能靠换snapshotID重复计数。
        return (self.account_id, self.business_date, self.entity_id)

    def record(self):
        return (
            self.tenant_id,
            self.account_id,
            self.business_date.isoformat(),
            self.profile_id,
            self.profile_version,
            self.dataset,
            self.entity_id,
            self.entity_snapshot_id,
            self.name_capture_sequence,
            self.name_observed_at.astimezone(UTC).isoformat(timespec="microseconds"),
        )


class ExpectedUnitProvider(ABC):
    """同事务纯DB受信来源协议；禁止网络、凭原state/kind或现有cells自建预期集合。"""

    kind = "TRUSTED"

    @abstractmethod
    async def prepare_manifest(self, session, scope, query, source):
        """从独立已登记预期来源冻结完整根，返回ExpectedUnitManifest。"""

    @abstractmethod
    def iter_unit_batches(self, session, scope, query, manifest):
        """异步迭代tuple[ExpectedUnitReceipt]，每批1至200，严格有序、不截断。"""

    @abstractmethod
    def iter_membership_batches(self, session, scope, query, manifest):
        """独立异步实体集合流，避免单个account/day携带无限AD数组。"""

    @abstractmethod
    async def revalidate_manifest(self, session, scope, query, manifest):
        """当前来源/范围锁后返回同一个完整manifest；不得把新根静默替换旧意图。"""


def require_expected_provider(provider):
    if (
        not isinstance(provider, ExpectedUnitProvider)
        or type(provider.kind) is not str
        or provider.kind
        not in {
            "TRUSTED",
            "ISOLATED_TEST",
        }
    ):
        unverified()
    return provider


class ExpectedStreamVerifier:
    """常量内存核完整根/数量/顺序；不代替scope和数据库实体归属交集。"""

    def __init__(self, manifest, *, memberships=False, unit=None):
        if type(manifest) is not ExpectedUnitManifest or type(memberships) is not bool:
            unverified()
        if unit is not None:
            if not memberships or type(unit) is not ExpectedUnitReceipt:
                unverified()
            if (
                unit.tenant_id != manifest.source.tenant_id
                or unit.profile_id != manifest.source.profile_id
                or unit.profile_version != manifest.source.profile_version
                or not manifest.date_from <= unit.business_date <= manifest.date_to
            ):
                unverified()
        self.manifest = manifest
        self.memberships = memberships
        self.unit = unit
        self._count = 0
        self._last = None
        self._digest = hashlib.sha256()
        self._finished = False

    def add(self, batch):
        if self._finished or type(batch) is not tuple or not 1 <= len(batch) <= MAX_EXPECTED_BATCH:
            unverified()
        expected_type = ExpectedEntityMembership if self.memberships else ExpectedUnitReceipt
        # 整批预验证，坏记录不能留下半批hash/计数状态。
        previous = self._last
        chunks = []
        for item in batch:
            if type(item) is not expected_type:
                unverified()
            if (
                item.tenant_id != self.manifest.source.tenant_id
                or item.profile_id != self.manifest.source.profile_id
                or item.profile_version != self.manifest.source.profile_version
                or not self.manifest.date_from <= item.business_date <= self.manifest.date_to
                or (self.memberships and item.dataset != self.manifest.dataset)
                or (
                    self.unit is not None
                    and (
                        item.account_id != self.unit.account_id
                        or item.business_date != self.unit.business_date
                    )
                )
            ):
                unverified()
            key = item.key()
            if previous is not None and key <= previous:
                unverified()
            previous = key
            try:
                chunks.append(canonical(item.record()).encode() + b"\n")
            except (UnicodeError, TypeError, ValueError):
                unverified()
        expected_count = (
            self.unit.entity_count
            if self.unit is not None
            else self.manifest.membership_count
            if self.memberships
            else self.manifest.unit_count
        )
        if self._count + len(batch) > expected_count:
            unverified()
        for chunk in chunks:
            self._digest.update(chunk)
        self._count += len(batch)
        self._last = previous

    def finish(self):
        count = (
            self.unit.entity_count
            if self.unit is not None
            else self.manifest.membership_count
            if self.memberships
            else self.manifest.unit_count
        )
        digest = (
            self.unit.entity_hash
            if self.unit is not None
            else self.manifest.membership_hash
            if self.memberships
            else self.manifest.unit_hash
        )
        if self._finished or self._count != count or self._digest.hexdigest() != digest:
            unverified()
        self._finished = True
        return count
