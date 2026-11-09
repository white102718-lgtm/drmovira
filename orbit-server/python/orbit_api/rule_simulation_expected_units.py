"""当前授权账户的日历预期流；非事实/实体清单/采集/READY证明。"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from weakref import WeakKeyDictionary, ref

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_metric_windows import (
    AccountMetricTimezone,
    RuleMetricWindowError,
    resolve_rule_metric_window,
)
from orbit_api.rule_simulation_access import RuleSimulationAccessFacade
from orbit_api.rule_simulation_protocol import transaction

CALENDAR_VERSION = "ORBIT_RULE_CALENDAR_UNITS_V1"


def _frame(value):
    raw = canonical(value).encode("utf-8")
    return len(raw).to_bytes(8, "big") + raw


def unavailable():
    raise OrbitError(503, "RULE_CALENDAR_UNAVAILABLE", "账户业务日日历参考或完整性不可用")


@dataclass(frozen=True, slots=True)
class CalendarExpectedUnit:
    account_id: str
    business_date: date | None
    timezone_name: str | None
    currency: str | None
    window: str
    status: str
    reason_code: str | None

    def record(self):
        return (
            self.account_id,
            self.business_date.isoformat() if self.business_date else None,
            self.timezone_name,
            self.currency,
            self.window,
            self.status,
            self.reason_code,
        )


@dataclass(frozen=True, slots=True, weakref_slot=True, repr=False)
class CalendarUnitBatch:
    units: tuple[CalendarExpectedUnit, ...]
    evaluated_at: datetime
    _issuer: object
    _session: object
    _transaction: object
    _ticket: object
    _parent_batch: object


@dataclass(frozen=True, slots=True, weakref_slot=True, repr=False)
class ExpectedCalendarSummary:
    evaluated_at: datetime
    account_count: int
    resolved_unit_count: int
    unresolved_account_count: int
    calendar_root: str
    calendar_complete: bool
    _issuer: object
    _session: object
    _transaction: object
    _ticket: object
    _parent_summary: object


@dataclass
class _Clock:
    busy: bool = True
    failed: bool = False
    value: datetime | None = None


class _Stream:
    def __init__(self, window):
        self.window = window
        self.active = False
        self.failed = False
        self.finished = False
        self.started = False
        self.after = ""
        self.account_count = 0
        self.resolved_unit_count = 0
        self.unresolved_account_count = 0
        self.account_hash = hashlib.sha256(b"[")
        self.unit_hash = None
        self.evaluated_at = None
        self.last_batch = None
        self.summary = None


class RuleSimulationExpectedUnits:
    def __init__(self, access_facade):
        if not isinstance(access_facade, RuleSimulationAccessFacade):
            raise ValueError("RULE_CALENDAR_ACCESS_FACADE_REQUIRED")
        self._access = access_facade
        self.__issuer = object()
        self.__clocks = WeakKeyDictionary()
        self.__streams = WeakKeyDictionary()

    async def _reference(self, session):
        tx = transaction(session)
        clock = self.__clocks.get(tx)
        if clock is not None:
            if clock.busy or clock.failed or clock.value is None:
                unavailable()
            return clock.value
        clock = _Clock()
        self.__clocks[tx] = clock
        try:
            value = (
                await session.execute(text("SELECT UTC_TIMESTAMP(6) AS evaluated_at"))
            ).scalar_one()
            if type(value) is not datetime:
                unavailable()
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            if value.utcoffset() != timedelta(0) or transaction(session) is not tx:
                unavailable()
            clock.value, clock.busy = value, False
            return value
        except BaseException:
            clock.failed, clock.busy = True, False
            raise

    def _stream(self, ticket):
        state = self.__streams.get(ticket)
        if state is None:
            # rule_json来自真实access发行的深不可变原Rule15，不能由HTTP换window。
            window = json.loads(ticket.rule_json)["window"]
            if window not in {"TODAY", "YESTERDAY", "LAST_3D", "LAST_7D"}:
                unavailable()
            state = _Stream(window)
            self.__streams[ticket] = state
        if state.failed or state.finished:
            raise ValueError("RULE_CALENDAR_STREAM_CLOSED")
        return state

    async def iter_units(self, session, rule_ticket, authorized_batch):
        # 未经真实父实例发行的batch不能触发SQL时钟或创建流。
        self._access.assert_batch(session, rule_ticket, authorized_batch)
        state = self._stream(rule_ticket)
        if state.active:
            raise ValueError("RULE_CALENDAR_STREAM_IN_PROGRESS")
        state.active = True
        complete = False
        try:
            evaluated_at = await self._reference(session)
            self._access.assert_batch(session, rule_ticket, authorized_batch)
            if state.unit_hash is None:
                state.evaluated_at = evaluated_at
                state.unit_hash = hashlib.sha256((CALENDAR_VERSION + "\0").encode())
                state.unit_hash.update(
                    _frame(
                        [
                            CALENDAR_VERSION,
                            rule_ticket.tenant_id,
                            rule_ticket.rule_id,
                            rule_ticket.revision,
                            rule_ticket.manifest_id,
                            rule_ticket.member_hash,
                            rule_ticket.expected_count,
                            evaluated_at.isoformat(timespec="microseconds"),
                            state.window,
                        ]
                    )
                )
            elif state.evaluated_at != evaluated_at:
                unavailable()
            state.started = True
            pending = []
            for account in authorized_batch.accounts:
                if (
                    account.account_id <= state.after
                    or state.account_count >= rule_ticket.expected_count
                ):
                    raise ValueError("RULE_CALENDAR_ACCOUNT_ORDER_CHANGED")
                if state.account_count:
                    state.account_hash.update(b",")
                state.account_hash.update(canonical(account.account_id).encode())
                state.account_count += 1
                state.after = account.account_id
                try:
                    resolved = resolve_rule_metric_window(
                        evaluated_at,
                        state.window,
                        AccountMetricTimezone(account.account_id, account.timezone_name),
                    )
                except RuleMetricWindowError as error:
                    if error.reason_code not in {"TIMEZONE_INVALID", "WINDOW_DATE_OVERFLOW"}:
                        raise
                    values = (
                        CalendarExpectedUnit(
                            account.account_id,
                            None,
                            account.timezone_name,
                            account.currency,
                            state.window,
                            "UNRESOLVED_WINDOW",
                            error.reason_code,
                        ),
                    )
                    state.unresolved_account_count += 1
                else:
                    # 每账户最多7天，仅此局部tuple；绝不缓存全账户全集。
                    values = tuple(
                        CalendarExpectedUnit(
                            account.account_id,
                            resolved.date_from + timedelta(days=offset),
                            account.timezone_name,
                            account.currency,
                            state.window,
                            "RESOLVED",
                            None,
                        )
                        for offset in range((resolved.date_to - resolved.date_from).days + 1)
                    )
                    state.resolved_unit_count += len(values)
                for unit in values:
                    state.unit_hash.update(_frame(unit.record()))
                    pending.append(unit)
                    if len(pending) == 200:
                        self._access.assert_batch(session, rule_ticket, authorized_batch)
                        batch = CalendarUnitBatch(
                            tuple(pending),
                            evaluated_at,
                            self.__issuer,
                            session,
                            transaction(session),
                            rule_ticket,
                            authorized_batch,
                        )
                        state.last_batch = ref(batch)
                        yield batch
                        self._access.assert_batch(session, rule_ticket, authorized_batch)
                        pending = []
                        await asyncio.sleep(0)
            if pending:
                self._access.assert_batch(session, rule_ticket, authorized_batch)
                batch = CalendarUnitBatch(
                    tuple(pending),
                    evaluated_at,
                    self.__issuer,
                    session,
                    transaction(session),
                    rule_ticket,
                    authorized_batch,
                )
                state.last_batch = ref(batch)
                yield batch
                self._access.assert_batch(session, rule_ticket, authorized_batch)
                await asyncio.sleep(0)
            complete = True
        finally:
            state.active = False
            if not complete:
                state.failed = True

    def assert_batch(self, session, rule_ticket, batch):
        if (
            type(batch) is not CalendarUnitBatch
            or batch._issuer is not self.__issuer
            or batch._session is not session
            or batch._transaction is not transaction(session)
            or batch._ticket is not rule_ticket
        ):
            raise ValueError("RULE_CALENDAR_CURRENT_BATCH_REQUIRED")
        self._access.assert_batch(session, rule_ticket, batch._parent_batch)
        state = self.__streams.get(rule_ticket)
        if (
            state is None
            or state.failed
            or state.finished
            or state.last_batch is None
            or state.last_batch() is not batch
        ):
            raise ValueError("RULE_CALENDAR_CURRENT_BATCH_REQUIRED")

    def finish(self, session, rule_ticket, verified_manifest_summary):
        self._access.assert_summary(session, rule_ticket, verified_manifest_summary)
        state = self.__streams.get(rule_ticket)
        if state is None or not state.started or state.active or state.failed or state.finished:
            raise ValueError("RULE_CALENDAR_COMPLETE_STREAM_REQUIRED")
        root = state.account_hash.copy()
        root.update(b"]")
        if (
            state.account_count != rule_ticket.expected_count
            or state.account_count != verified_manifest_summary.count
            or root.hexdigest() != rule_ticket.member_hash
            or root.hexdigest() != verified_manifest_summary.member_hash
        ):
            state.failed = True
            raise ValueError("RULE_CALENDAR_COMPLETE_ACCOUNTS_REQUIRED")
        result_hash = state.unit_hash.copy()
        result_hash.update(
            _frame(
                [
                    "EOF",
                    state.account_count,
                    state.resolved_unit_count,
                    state.unresolved_account_count,
                ]
            )
        )
        summary = ExpectedCalendarSummary(
            state.evaluated_at,
            state.account_count,
            state.resolved_unit_count,
            state.unresolved_account_count,
            result_hash.hexdigest(),
            state.unresolved_account_count == 0,
            self.__issuer,
            session,
            transaction(session),
            rule_ticket,
            verified_manifest_summary,
        )
        state.summary = ref(summary)
        state.finished = True
        return summary

    def assert_summary(self, session, rule_ticket, summary):
        if (
            type(summary) is not ExpectedCalendarSummary
            or summary._issuer is not self.__issuer
            or summary._session is not session
            or summary._transaction is not transaction(session)
            or summary._ticket is not rule_ticket
        ):
            raise ValueError("RULE_CALENDAR_VERIFIED_SUMMARY_REQUIRED")
        self._access.assert_summary(session, rule_ticket, summary._parent_summary)
        state = self.__streams.get(rule_ticket)
        if (
            state is None
            or state.failed
            or not state.finished
            or state.summary is None
            or state.summary() is not summary
        ):
            raise ValueError("RULE_CALENDAR_VERIFIED_SUMMARY_REQUIRED")
