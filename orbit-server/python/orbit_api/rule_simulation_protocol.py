"""S2显式授权/指标适配协议；没有生产issuer或默认可信实现。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from orbit_api.rule_simulation_contract import (
    SimulationIntent,
    SimulationSnapshot,
    hash_value,
    integer,
    uuid_value,
)


def transaction(session):
    if not session.in_transaction():
        raise ValueError("SIMULATION_OUTER_TRANSACTION_REQUIRED")
    result = session.sync_session.get_transaction()
    if result is None:
        raise ValueError("SIMULATION_OUTER_TRANSACTION_REQUIRED")
    return result


@dataclass(frozen=True, slots=True, repr=False)
class SimulationAuthorization:
    tenant_id: str
    actor_id: int
    rule_id: str
    current_revision: int
    auth_fingerprint: str
    _session: object = field(repr=False)
    _transaction: object = field(repr=False)
    _issuer: object = field(repr=False)


class RuleSimulationAccess(ABC):
    """root后续基于当前rules.read/Rule/owner/完整scope实现，不借monitor。"""

    def __init__(self):
        self.__issuer = object()

    def _issue(self, session, *, tenant_id, actor_id, rule_id, current_revision, auth_fingerprint):
        uuid_value(tenant_id)
        integer(actor_id, 1)
        uuid_value(rule_id)
        integer(current_revision, 1)
        hash_value(auth_fingerprint)
        return SimulationAuthorization(
            tenant_id,
            actor_id,
            rule_id,
            current_revision,
            auth_fingerprint,
            session,
            transaction(session),
            self.__issuer,
        )

    def verify_ticket(self, session, intent, value):
        if (
            type(intent) is not SimulationIntent
            or type(value) is not SimulationAuthorization
            or value._issuer is not self.__issuer
            or value._session is not session
            or value._transaction is not transaction(session)
            or value.actor_id != intent.actor_id
            or value.rule_id != intent.rule_id
        ):
            raise ValueError("SIMULATION_CURRENT_AUTHORIZATION_REQUIRED")

    @abstractmethod
    async def authorize(self, session, intent, *, snapshot=None) -> SimulationAuthorization:
        """当前原动作+对象可见性probe，不在上游来源锁前提前锁Rule head。

        仅真正新构建调用方另核current_revision==intent.revision；历史成功读取
        不能因此绑定当前head或要求最新profile。不得在此锁内做网络I/O。
        snapshot传递完整范围重验意图，但这里只签当前动作票据；完整当前
        scope/Rule锁读必须由下方联合source facade按config/profile→account
        →rule clock/head顺序完成，不能先head再倒序请求来源锁。
        """
        raise NotImplementedError


class RuleSimulationSource(ABC):
    """源适配+独立预期联合边界；仅显式root注入，无TRUSTED字符串通行证。"""

    @abstractmethod
    async def capture(self, session, authorization, intent) -> SimulationSnapshot:
        """真实完整scope/profile/原048发行与独立预期证明，不从返回行数推预期。

        联合root分配的内部scope facade，按config/profile→account/全成员
        →rule clock/head当前锁读完成完整双方scope与CAS，不信probe旧RR。
        """
        raise NotImplementedError

    @abstractmethod
    async def revalidate(self, session, authorization, snapshot) -> None:
        """同共同锁序重核当前完整双方scope/Rule CAS及精确已捕获source。

        包含cutoff/所有publication/独立预期，不重新latest；不只复读hash。
        当前未实现此正式联合facade，不能靠本ABC/DTO宣称验证已发生。
        """
        raise NotImplementedError
