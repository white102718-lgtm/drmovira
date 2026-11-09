"""规则模拟当前授权/有界成员流；不发行指标来源、Simulation或执行资格。"""

import asyncio
import hashlib
from dataclasses import dataclass
from weakref import WeakKeyDictionary, ref
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from orbit_api.account_access import clock as account_clock
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_access import (
    assert_owner,
    authorize_rule,
    owner_scope,
    readable,
    require_rule_visible,
    revalidate_owner,
    transaction,
)
from orbit_api.rule_contract import MAX_SAFE, identifier
from orbit_api.rule_editor_definition import definition_response
from orbit_api.rule_profile_references import RuleProfileBinding, lock_rule_profile

MAX_ACCOUNTS = 50000


def unavailable():
    raise OrbitError(503, "RULE_SIMULATION_ACCESS_UNAVAILABLE", "规则定义或完整授权范围不完整")


def changed():
    raise OrbitError(409, "RULE_ACCOUNT_SCOPE_CHANGED", "规则完整账户范围或当前双方权限已变化")


def _id(value):
    try:
        result = identifier(value, "/simulation_account")
        if result != value:
            unavailable()
        return result
    except (OrbitError, TypeError, ValueError):
        unavailable()


def _currency(value):
    if value is not None and (
        type(value) is not str
        or len(value) != 3
        or not value.isascii()
        or not value.isupper()
        or not value.isalpha()
    ):
        unavailable()
    return value


def _timezone(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        return "TIMEZONE_INVALID"
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return "TIMEZONE_INVALID"
    return None


@dataclass(frozen=True, slots=True)
class CurrentRuleAccount:
    account_id: str
    owner_user_id: str
    owner_team_id: str
    currency: str | None
    revision: int
    timezone_name: str | None
    timezone_error: str | None


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, repr=False)
class RuleSimulationReadTicket:
    tenant_id: str
    actor_id: int
    rule_id: str
    revision: int
    manifest_id: str
    expected_count: int
    member_hash: str
    rule_json: str
    profile_version: str
    profile_hash: str
    _session: object
    _transaction: object
    _issuer: object


@dataclass(frozen=True, slots=True, weakref_slot=True, repr=False)
class AuthorizedAccountBatch:
    accounts: tuple[CurrentRuleAccount, ...]
    _ticket: RuleSimulationReadTicket
    _issuer: object
    _session: object
    _transaction: object


@dataclass(frozen=True, slots=True, weakref_slot=True, repr=False)
class VerifiedManifestSummary:
    count: int
    member_hash: str
    timezone_invalid_count: int
    currency_unknown_count: int
    _ticket: RuleSimulationReadTicket
    _issuer: object
    _session: object
    _transaction: object


@dataclass
class _State:
    access: object
    owner: object
    head: dict
    version: dict
    manifest: dict
    profile: object
    started: bool = False
    eof: bool = False
    failed: bool = False
    finished: bool = False
    finishing: bool = False
    count: int = 0
    timezone_invalid_count: int = 0
    currency_unknown_count: int = 0
    computed_hash: str | None = None
    last_batch: object = None
    summary: object = None


class RuleSimulationAccessFacade:
    def __init__(self):
        self.__issuer = object()
        self.__states = WeakKeyDictionary()

    def _state(self, session, ticket):
        if (
            type(ticket) is not RuleSimulationReadTicket
            or ticket._issuer is not self.__issuer
            or ticket._session is not session
            or ticket._transaction is not transaction(session)
            or ticket not in self.__states
        ):
            raise ValueError("RULE_SIMULATION_CURRENT_TRANSACTION_TICKET_REQUIRED")
        state = self.__states[ticket]
        if state.failed or state.finished:
            raise ValueError("RULE_SIMULATION_ACCOUNT_STREAM_CLOSED")
        assert_owner(session, state.access, state.owner)
        return state

    async def _one(self, session, statement, params):
        return (await session.execute(text(statement), params)).mappings().first()

    async def _definition(self, session, params, *, current):
        suffix = " FOR SHARE" if current else ""
        head = await self._one(
            session,
            "SELECT * FROM orbit_rule_head WHERE tenant_id=:tenant AND id=:id" + suffix,
            params,
        )
        if head is None:
            return None, None
        version = await self._one(
            session,
            "SELECT * FROM orbit_rule_version WHERE tenant_id=:tenant "
            "AND rule_id=:id AND revision=:revision" + suffix,
            params | {"revision": head["revision"]},
        )
        return head, version

    @staticmethod
    def _same_definition(before_head, before_version, head, version):
        if (
            head is None
            or version is None
            or dict(head) != dict(before_head)
            or dict(version) != dict(before_version)
        ):
            raise OrbitError(409, "RULE_SOURCE_CHANGED", "规则当前定义与读取来源已变化")

    async def open(self, session, actor, rule_id, expected_revision):
        tx = transaction(session)
        if type(actor) is not int or not 1 <= actor <= MAX_SAFE:
            raise ValueError("RULE_SIMULATION_ACTOR_REQUIRED")
        if type(expected_revision) is not int or not 1 <= expected_revision <= MAX_SAFE:
            raise ValueError("RULE_SIMULATION_REVISION_REQUIRED")
        rule_id = _id(rule_id)
        access = await authorize_rule(session, actor, "rules.read")
        params = {"tenant": access.current.tenant_id, "id": rule_id}
        probe, version = await self._definition(session, params, current=False)
        require_rule_visible(access, probe)
        if version is None:
            unavailable()
        if probe["revision"] != expected_revision:
            raise OrbitError(409, "REVISION_CONFLICT", "规则版本已变化")
        owner = await owner_scope(
            session,
            access,
            {"owner_user_id": probe["owner_user_id"], "owner_team_id": probe["owner_team_id"]},
        )
        # 明确本期限制：helper仅当前head==原绑定version；绝不静默升级或用于历史receipt。
        profile = await lock_rule_profile(
            session,
            access,
            owner,
            probe["metric_profile_id"],
            expected_version=version["metric_profile_version"],
        )
        if (
            profile.profile_hash != version["metric_profile_hash"]
            or hashlib.sha256(profile.source_proof_json).hexdigest()
            != version["profile_proof_hash"]
        ):
            raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "规则绑定指标证明已变化")
        await account_clock(session, access.current)
        manifest = await self._one(
            session,
            "SELECT * FROM orbit_rule_scope_manifest WHERE tenant_id=:tenant "
            "AND rule_id=:id AND id=:manifest FOR SHARE",
            params | {"manifest": probe["manifest_id"]},
        )
        # 原写方profile→account/source/member→rule；此处账户clock后才锁rule，避免倒序。
        clock = (
            await session.execute(
                text("SELECT revision FROM orbit_rule_clock WHERE tenant_id=:tenant FOR SHARE"),
                params,
            )
        ).scalar_one_or_none()
        if type(clock) is not int or not 1 <= clock <= MAX_SAFE:
            unavailable()
        head, current_version = await self._definition(session, params, current=True)
        require_rule_visible(access, head)
        self._same_definition(probe, version, head, current_version)
        value = definition_response(head, current_version, manifest)
        count = manifest["member_count"]
        ticket = RuleSimulationReadTicket(
            access.current.tenant_id,
            actor,
            rule_id,
            expected_revision,
            manifest["id"],
            count,
            manifest["member_ids_hash"],
            canonical(value["rule"]),
            profile.version,
            profile.profile_hash,
            session,
            tx,
            self.__issuer,
        )
        if transaction(session) is not tx:
            raise ValueError("RULE_SIMULATION_CURRENT_TRANSACTION_TICKET_REQUIRED")
        self.__states[ticket] = _State(
            access, owner, dict(head), dict(current_version), dict(manifest), profile
        )
        return ticket

    async def iter_account_batches(self, session, ticket, *, batch_size=200):
        if type(batch_size) is not int or batch_size not in {200, 1000}:
            raise ValueError("RULE_SIMULATION_ACCOUNT_BATCH_REQUIRED")
        state = self._state(session, ticket)
        if state.started:
            raise ValueError("RULE_SIMULATION_ACCOUNT_STREAM_ALREADY_CONSUMED")
        state.started = True
        root, after = hashlib.sha256(b"["), ""
        try:
            while True:
                self._state(session, ticket)
                rows = (
                    (
                        await session.execute(
                            text(
                                "SELECT m.account_id,m.frozen_owner_user_id,"
                                "m.frozen_owner_team_id,m.frozen_currency,"
                                "m.frozen_revision,a.id,a.owner_user_id,a.owner_team_id,"
                                "a.currency,a.revision,a.timezone_id "
                                "FROM orbit_rule_scope_member m LEFT JOIN orbit_ad_account a ON "
                                "a.tenant_id=m.tenant_id "
                                "AND a.id=m.account_id WHERE m.tenant_id=:tenant AND "
                                "m.manifest_id=:manifest "
                                "AND m.account_id>:after ORDER BY m.account_id LIMIT :limit FOR "
                                "SHARE OF m,a"
                            ),
                            {
                                "tenant": ticket.tenant_id,
                                "manifest": ticket.manifest_id,
                                "after": after,
                                "limit": batch_size,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                if not rows:
                    root.update(b"]")
                    if (
                        state.count != ticket.expected_count
                        or root.hexdigest() != ticket.member_hash
                    ):
                        changed()
                    state.computed_hash, state.eof = root.hexdigest(), True
                    return
                if len(rows) > batch_size:
                    unavailable()
                accounts = []
                for row in rows:
                    account_id = _id(row["account_id"])
                    if (
                        account_id <= after
                        or row["id"] != account_id
                        or state.count >= MAX_ACCOUNTS
                        or state.count >= ticket.expected_count
                    ):
                        changed()
                    if not readable(
                        state.access.current, state.access.managed_team_ids, row
                    ) or not readable(state.owner.current, state.owner.managed_team_ids, row):
                        changed()
                    for key in (
                        "frozen_owner_user_id",
                        "frozen_owner_team_id",
                        "owner_user_id",
                        "owner_team_id",
                    ):
                        _id(row[key])
                    for key in ("revision", "frozen_revision"):
                        if type(row[key]) is not int or not 1 <= row[key] <= MAX_SAFE:
                            unavailable()
                    _currency(row["frozen_currency"])
                    currency = _currency(row["currency"])
                    timezone_error = _timezone(row["timezone_id"])
                    if state.count:
                        root.update(b",")
                    root.update(canonical(account_id).encode())
                    state.count += 1
                    state.timezone_invalid_count += int(timezone_error is not None)
                    state.currency_unknown_count += int(currency is None)
                    after = account_id
                    accounts.append(
                        CurrentRuleAccount(
                            account_id,
                            row["owner_user_id"],
                            row["owner_team_id"],
                            currency,
                            row["revision"],
                            row["timezone_id"],
                            timezone_error,
                        )
                    )
                batch = AuthorizedAccountBatch(
                    tuple(accounts), ticket, self.__issuer, session, ticket._transaction
                )
                state.last_batch = ref(batch)
                yield batch
                await asyncio.sleep(0)
        finally:
            if not state.eof:
                state.failed = True

    def assert_batch(self, session, ticket, batch):
        state = self._state(session, ticket)
        if (
            state.last_batch is None
            or state.last_batch() is not batch
            or type(batch) is not AuthorizedAccountBatch
            or batch._ticket is not ticket
            or batch._issuer is not self.__issuer
            or batch._session is not session
            or batch._transaction is not transaction(session)
        ):
            raise ValueError("RULE_SIMULATION_CURRENT_ACCOUNT_BATCH_REQUIRED")

    async def finish(self, session, ticket):
        state = self._state(session, ticket)
        if (
            not state.eof
            or state.computed_hash != ticket.member_hash
            or state.count != ticket.expected_count
        ):
            raise ValueError("RULE_SIMULATION_COMPLETE_MANIFEST_REQUIRED")
        if state.finishing:
            raise ValueError("RULE_SIMULATION_FINISH_IN_PROGRESS")
        state.finishing = True
        params = {"tenant": ticket.tenant_id, "id": ticket.rule_id}
        try:
            head, version = await self._definition(session, params, current=True)
            require_rule_visible(state.access, head)
            self._same_definition(state.head, state.version, head, version)
            await revalidate_owner(session, state.access, state.owner)
            self._state(session, ticket)
            summary = VerifiedManifestSummary(
                state.count,
                state.computed_hash,
                state.timezone_invalid_count,
                state.currency_unknown_count,
                ticket,
                self.__issuer,
                session,
                ticket._transaction,
            )
            state.summary = ref(summary)
            state.finished = True
            return summary
        except BaseException:
            state.failed = True
            raise
        finally:
            state.finishing = False

    def assert_summary(self, session, ticket, summary):
        if (
            type(ticket) is not RuleSimulationReadTicket
            or ticket._issuer is not self.__issuer
            or ticket._session is not session
            or ticket._transaction is not transaction(session)
            or ticket not in self.__states
            or not self.__states[ticket].finished
            or self.__states[ticket].failed
            or self.__states[ticket].summary is None
            or self.__states[ticket].summary() is not summary
            or type(summary) is not VerifiedManifestSummary
            or summary._ticket is not ticket
            or summary._issuer is not self.__issuer
            or summary._session is not session
            or summary._transaction is not transaction(session)
        ):
            raise ValueError("RULE_SIMULATION_VERIFIED_MANIFEST_REQUIRED")

    def verified_profile(self, session, ticket, summary):
        """返回本票据已锁的不可变配置；不重查、换版或补锁任何来源。"""
        self.assert_summary(session, ticket, summary)
        profile = self.__states[ticket].profile
        if (
            type(profile) is not RuleProfileBinding
            or profile.version != ticket.profile_version
            or profile.profile_hash != ticket.profile_hash
        ):
            unavailable()
        return profile
