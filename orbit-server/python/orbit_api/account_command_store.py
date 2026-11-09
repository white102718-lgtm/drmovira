"""本人账户命令状态：当前动作与账户范围先行，不建立历史权限例外。"""

from sqlalchemy import text

from orbit_api.account_access import parameters
from orbit_api.account_actions_store import AccountActionsStore
from orbit_api.account_command_contract import diagnostic, parse_diagnostic, unavailable
from orbit_api.errors import OrbitError


class AccountCommandStore:
    async def get(self, session, actor, account_id, query):
        if not session.in_transaction():
            raise ValueError("账户命令读取必须在显式事务中")
        account_id, kind, request_id = parse_diagnostic(account_id, query)
        # 沿现有clock→account共享锁、实时动作/菜单/数据范围及到期guard。
        current, _managed, _account = await AccountActionsStore(None).lock_account(
            session, actor, account_id, kind, write=False
        )
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT id,account_id,kind,request_id,revision,state,attempt_count,"
                        "last_error_code,effective_from,next_attempt_at,created_at,updated_at,"
                        "completed_at FROM orbit_account_command "
                        "WHERE tenant_id=:tenant AND actor_id=:actor "
                        "AND actor_subject_id=:subject AND account_id=:account "
                        "AND kind=:kind AND request_id=:request LIMIT 2 FOR SHARE"
                    ),
                    parameters(current)
                    | {"account": account_id, "kind": kind, "request": request_id},
                )
            ).mappings()
        )
        if not rows:
            raise OrbitError(404, "NOT_FOUND", "命令不存在或不在当前本人账户范围")
        if len(rows) != 1:
            # 请求关联不是天然唯一键；历史重复不能按数据库偶然顺序任选。
            unavailable()
        return diagnostic(rows[0])
