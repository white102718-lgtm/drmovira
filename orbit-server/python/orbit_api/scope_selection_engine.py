"""无SQL/授权/回调的冻结七列规范hash；不决定快照可见性或事务提交。"""

import hashlib

from orbit_api.account_scope_contract import MAX_MEMBERS
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_contract import MAX_SAFE, identifier

BATCH_SIZE = 1000


class FrozenMemberRoot:
    def __init__(self):
        self.count, self.after = 0, ""
        self._root = hashlib.sha256(b"[")

    def add(self, row):
        account = identifier(row["account_id"], "/account_id")
        if account <= self.after:
            raise OrbitError(503, "SCOPE_INTEGRITY_INVALID", "账户成员顺序或完整性无效")
        if self.count >= MAX_MEMBERS:
            raise OrbitError(422, "SCOPE_ACCOUNT_LIMIT", "账户范围超过50000项，不允许截断")
        revision = row["account_revision"]
        if type(revision) is not int or not 1 <= revision <= MAX_SAFE:
            raise OrbitError(503, "SCOPE_INTEGRITY_INVALID", "账户冻结版本无效")
        owner = identifier(row["owner_user_id"], "/owner_user_id")
        team = identifier(row["owner_team_id"], "/owner_team_id")
        external, name, currency = row["external_id"], row["name"], row["currency"]
        if (
            type(external) is not str
            or not external
            or not external.isascii()
            or not external.isdigit()
            or len(external) > 64
            or type(name) is not str
            or currency is not None
            and (
                type(currency) is not str
                or len(currency) != 3
                or not currency.isascii()
                or not currency.isalpha()
                or not currency.isupper()
            )
        ):
            raise OrbitError(503, "SCOPE_INTEGRITY_INVALID", "账户冻结字段无效")
        if self.count:
            self._root.update(b",")
        self._root.update(
            canonical([account, external, name, revision, owner, team, currency]).encode()
        )
        self.count += 1
        self.after = account

    def hexdigest(self):
        copy = self._root.copy()
        copy.update(b"]")
        return copy.hexdigest()
