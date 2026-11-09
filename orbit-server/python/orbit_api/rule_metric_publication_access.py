"""Rule专属发行头只读桥；不读取事实、不发行库存或Simulation READY。"""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from weakref import WeakKeyDictionary

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError
from orbit_api.metric_profile_store import fixture_boundary
from orbit_api.metrics_query_store import (
    PublicationValidationReceipt,
    publication_validation_binding,
)
from orbit_api.rule_contract import identifier
from orbit_api.rule_profile_references import RuleProfileBinding
from orbit_api.rule_simulation_access import RuleSimulationAccessFacade
from orbit_api.rule_simulation_expected_units import RuleSimulationExpectedUnits
from orbit_api.rule_simulation_protocol import transaction

MAX_HEAD_BATCH = 200


def unavailable():
    raise OrbitError(
        503, "RULE_PUBLICATION_SOURCE_UNAVAILABLE", "规则指标发行来源尚未完整核验"
    ) from None


def strict_id(value):
    try:
        result = identifier(value, "/publication_id")
        if type(value) is not str or result != value:
            unavailable()
        return result
    except (ValueError, TypeError, OrbitError):
        unavailable()


@dataclass(frozen=True, slots=True, repr=False)
class RulePublicationBinding:
    """只含原已验证根；不是授权票据或提供者自己发行的来源证明。"""

    tenant_id: str
    actor_id: int
    rule_id: str
    revision: int
    manifest_id: str
    member_hash: str
    calendar_root: str
    evaluated_at: str
    profile_id: str
    profile_version: str
    profile_hash: str
    profile_proof_hash: str
    source_config_id: str
    source_config_revision: int


class RulePublicationAuthority(ABC):
    """由可信启动代码注入的独立登记验证；标签和输入hash不替代实际证据。"""

    kind = "TRUSTED"

    @abstractmethod
    async def verify_publications(self, session, binding, heads):
        """仅DB；同已锁来源，不新增来源锁/网络；返回完整独立登记receipt。"""


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, repr=False)
class PublicationReadTicket:
    binding: RulePublicationBinding
    anchor: tuple
    generation: int
    capture_sequence_max: int


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, repr=False)
class VerifiedPublicationBatch:
    publications: tuple[tuple, ...]


@dataclass
class _State:
    session: object
    tx: object
    rule_ticket: object
    calendar_summary: object
    authority: object
    binding: RulePublicationBinding
    anchor: tuple


class RuleMetricPublicationAccess:
    def __init__(self, access_facade, calendar, authority=None):
        if not isinstance(access_facade, RuleSimulationAccessFacade) or not isinstance(
            calendar, RuleSimulationExpectedUnits
        ):
            raise ValueError("RULE_PUBLICATION_PARENT_FACADES_REQUIRED")
        self.access = access_facade
        self.calendar = calendar
        self.authority = authority
        self.__tickets = WeakKeyDictionary()
        self.__batches = WeakKeyDictionary()

    def _authority(self):
        value = self.authority
        if (
            not isinstance(value, RulePublicationAuthority)
            or type(value.kind) is not str
            or value.kind
            not in {
                "TRUSTED",
                "ISOLATED_TEST",
            }
        ):
            unavailable()
        return value

    def _parent(self, session, rule_ticket, summary):
        self.calendar.assert_summary(session, rule_ticket, summary)
        return self.access.verified_profile(session, rule_ticket, summary._parent_summary)

    def _state(self, session, ticket):
        if type(ticket) is not PublicationReadTicket or ticket not in self.__tickets:
            raise ValueError("RULE_PUBLICATION_CURRENT_TICKET_REQUIRED")
        state = self.__tickets[ticket]
        if state.session is not session or state.tx is not transaction(session):
            raise ValueError("RULE_PUBLICATION_CURRENT_TICKET_REQUIRED")
        if self.authority is not state.authority:
            raise ValueError("RULE_PUBLICATION_AUTHORITY_CHANGED")
        self._parent(session, state.rule_ticket, state.calendar_summary)
        return state

    @staticmethod
    def _head_binding(head, binding, authority, *, generation=None, sequence=None):
        try:
            normalized = publication_validation_binding(head)
            if any(
                type(head[key]) is not type(expected) or head[key] != expected
                for key, expected in (
                    ("tenant_id", binding.tenant_id),
                    ("profile_id", binding.profile_id),
                    ("profile_version", binding.profile_version),
                    ("profile_hash", binding.profile_hash),
                    ("authority_kind", authority.kind),
                    ("source_config_id", binding.source_config_id),
                    ("source_config_revision", binding.source_config_revision),
                )
            ):
                unavailable()
            if generation is not None and head["generation"] > generation:
                unavailable()
            if sequence is not None and head["capture_sequence_max"] > sequence:
                unavailable()
            return normalized
        except (KeyError, TypeError, ValueError, OrbitError):
            unavailable()

    async def _verify(self, session, binding, authority, heads, *, generation=None, sequence=None):
        if not 1 <= len(heads) <= MAX_HEAD_BATCH:
            unavailable()
        expected = {}
        for head in heads:
            normalized = self._head_binding(
                head, binding, authority, generation=generation, sequence=sequence
            )
            if head["id"] in expected:
                unavailable()
            expected[head["id"]] = normalized
        tx = transaction(session)
        receipts = await authority.verify_publications(
            session, binding, tuple(MappingProxyType(dict(row)) for row in heads)
        )
        if transaction(session) is not tx:
            raise ValueError("RULE_PUBLICATION_CURRENT_TRANSACTION_REQUIRED")
        if type(receipts) is not tuple or len(receipts) != len(expected):
            unavailable()
        seen = set()
        for receipt in receipts:
            if type(receipt) is not PublicationValidationReceipt:
                unavailable()
            actual = receipt.binding
            key = receipt.publication_id
            if type(key) is not str or key not in expected or key in seen:
                unavailable()
            original = expected[key]
            if (
                type(actual) is not tuple
                or len(actual) != len(original)
                or any(
                    type(left) is not type(right) or left != right
                    for left, right in zip(actual, original, strict=True)
                )
            ):
                unavailable()
            seen.add(key)
        if seen != set(expected):
            unavailable()
        return tuple(expected[key] for key in sorted(expected))

    async def open(self, session, rule_ticket, calendar_summary):
        # 默认无authority在任何SQL之前失败，不偷用工具provider或旧monitor权限。
        authority = self._authority()
        profile = self._parent(session, rule_ticket, calendar_summary)
        if (
            type(profile) is not RuleProfileBinding
            or profile.source != "META"
            or profile.source_config_id is None
            or type(profile.source_config_revision) is not int
            or not 1 <= profile.source_config_revision <= 9007199254740991
        ):
            unavailable()
        strict_id(profile.source_config_id)
        rule = json.loads(rule_ticket.rule_json)
        if (profile.profile_id, profile.version, profile.profile_hash) != (
            rule["metric_profile_id"],
            rule_ticket.profile_version,
            rule_ticket.profile_hash,
        ):
            unavailable()
        binding = RulePublicationBinding(
            rule_ticket.tenant_id,
            rule_ticket.actor_id,
            rule_ticket.rule_id,
            rule_ticket.revision,
            rule_ticket.manifest_id,
            rule_ticket.member_hash,
            calendar_summary.calendar_root,
            calendar_summary.evaluated_at.isoformat(timespec="microseconds"),
            profile.profile_id,
            profile.version,
            profile.profile_hash,
            hashlib.sha256(profile.source_proof_json).hexdigest(),
            profile.source_config_id,
            profile.source_config_revision,
        )
        tx = transaction(session)
        if authority.kind == "ISOLATED_TEST":
            await fixture_boundary(session)
        # 先取精确profile最新发行，再核其来源；不能过滤掉坏新头悄悄退回旧头。
        heads = list(
            (
                await session.execute(
                    text(
                        "SELECT p.* FROM orbit_metric_publication p WHERE p.tenant_id=:tenant "
                        "AND p.profile_id=:profile AND p.profile_version=:version "
                        "AND p.profile_hash=:hash "
                        "AND p.state='PUBLISHED' ORDER BY p.generation DESC LIMIT 1 FOR SHARE"
                    ),
                    {
                        "tenant": binding.tenant_id,
                        "profile": binding.profile_id,
                        "version": binding.profile_version,
                        "hash": binding.profile_hash,
                    },
                )
            ).mappings()
        )
        if len(heads) != 1:
            unavailable()
        checked = await self._verify(session, binding, authority, heads)
        self._parent(session, rule_ticket, calendar_summary)
        if transaction(session) is not tx:
            raise ValueError("RULE_PUBLICATION_CURRENT_TRANSACTION_REQUIRED")
        anchor = checked[0]
        ticket = PublicationReadTicket(
            binding, anchor, heads[0]["generation"], heads[0]["capture_sequence_max"]
        )
        self.__tickets[ticket] = _State(
            session, tx, rule_ticket, calendar_summary, authority, binding, anchor
        )
        return ticket

    async def verify_heads(self, session, ticket, publication_ids):
        state = self._state(session, ticket)
        if type(publication_ids) is not tuple or not 1 <= len(publication_ids) <= MAX_HEAD_BATCH:
            raise ValueError("RULE_PUBLICATION_IDS_BATCH_REQUIRED")
        ids = tuple(sorted(strict_id(value) for value in publication_ids))
        if len(set(ids)) != len(ids):
            raise ValueError("RULE_PUBLICATION_DUPLICATE_IDS")
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT p.* FROM orbit_metric_publication p WHERE p.tenant_id=:tenant "
                        "AND p.id IN :ids ORDER BY p.id FOR SHARE"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {
                        "tenant": state.binding.tenant_id,
                        "ids": ids,
                    },
                )
            ).mappings()
        )
        if tuple(row["id"] for row in rows) != ids:
            unavailable()
        publications = await self._verify(
            session,
            state.binding,
            state.authority,
            rows,
            generation=ticket.generation,
            sequence=ticket.capture_sequence_max,
        )
        self._state(session, ticket)
        batch = VerifiedPublicationBatch(publications)
        self.__batches[batch] = ticket
        return batch

    def assert_batch(self, session, ticket, batch):
        self._state(session, ticket)
        if type(batch) is not VerifiedPublicationBatch or self.__batches.get(batch) is not ticket:
            raise ValueError("RULE_PUBLICATION_VERIFIED_BATCH_REQUIRED")
