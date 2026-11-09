"""S2事务持久边界第一阶段：输入捕获/重验协议，不假造READY或完整Store。

默认无source/access立即503且零SQL。实际分批staging/发布与原HTTP接线
待063审核及真实Rule/指标facade实现；本模块当前没有模拟成功入口。
"""

from dataclasses import dataclass, field

from orbit_api.errors import OrbitError
from orbit_api.rule_simulation_contract import SimulationIntent, SimulationSnapshot, unavailable
from orbit_api.rule_simulation_protocol import (
    RuleSimulationAccess,
    RuleSimulationSource,
    transaction,
)


@dataclass(frozen=True, slots=True, repr=False)
class PreparedSimulationInput:
    snapshot: SimulationSnapshot
    intent: SimulationIntent
    _authorization: object = field(repr=False)
    _session: object = field(repr=False)
    _transaction: object = field(repr=False)
    _issuer: object = field(repr=False)


class RuleSimulationStore:
    def __init__(self, *, access=None, source=None):
        if access is not None and not isinstance(access, RuleSimulationAccess):
            raise ValueError("SIMULATION_EXPLICIT_ACCESS_FACADE_REQUIRED")
        if source is not None and not isinstance(source, RuleSimulationSource):
            raise ValueError("SIMULATION_EXPLICIT_SOURCE_FACADE_REQUIRED")
        self.access, self.source, self.__issuer = access, source, object()

    def _dependencies(self):
        if self.access is None or self.source is None:
            unavailable()

    @staticmethod
    def _binding(authorization, intent, snapshot):
        if type(snapshot) is not SimulationSnapshot:
            unavailable()
        if (
            snapshot.tenant_id != authorization.tenant_id
            or snapshot.actor_id != intent.actor_id
            or snapshot.rule_id != intent.rule_id
            or snapshot.revision != intent.revision
            or snapshot.auth_fingerprint != authorization.auth_fingerprint
        ):
            raise OrbitError(409, "RULE_SIMULATION_SOURCE_CHANGED", "模拟授权或冻结输入已变化")

    async def prepare_inputs(self, session, intent):
        self._dependencies()
        if type(intent) is not SimulationIntent:
            raise ValueError("SIMULATION_PARSED_INTENT_REQUIRED")
        tx = transaction(session)
        authorization = await self.access.authorize(session, intent)
        self.access.verify_ticket(session, intent, authorization)
        if authorization.current_revision != intent.revision:
            raise OrbitError(409, "REVISION_CONFLICT", "规则版本已变化")
        snapshot = await self.source.capture(session, authorization, intent)
        self._binding(authorization, intent, snapshot)
        prepared = PreparedSimulationInput(
            snapshot, intent, authorization, session, tx, self.__issuer
        )
        await self.revalidate_inputs(session, prepared)
        return prepared

    async def revalidate_inputs(self, session, prepared):
        self._dependencies()
        if (
            type(prepared) is not PreparedSimulationInput
            or prepared._issuer is not self.__issuer
            or prepared._session is not session
            or prepared._transaction is not transaction(session)
        ):
            raise ValueError("SIMULATION_INPUT_TICKET_TRANSACTION_MISMATCH")
        authorization = await self.access.authorize(
            session, prepared.intent, snapshot=prepared.snapshot
        )
        self.access.verify_ticket(session, prepared.intent, authorization)
        if (
            authorization.current_revision != prepared.intent.revision
            or authorization != prepared._authorization
        ):
            raise OrbitError(
                409, "RULE_SIMULATION_SCOPE_CHANGED", "模拟构建期间规则或完整范围已变化"
            )
        self._binding(authorization, prepared.intent, prepared.snapshot)
        result = await self.source.revalidate(session, authorization, prepared.snapshot)
        if result is not None:
            unavailable()
        # provider不得在回调内commit后让旧票据继续通过。
        self.access.verify_ticket(session, prepared.intent, authorization)
        return prepared.snapshot
