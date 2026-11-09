"""分配候选合同/范围控制替身；SQL实际索引/鉴权需主线真实HTTP专项复验。"""

from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.account_assignment_options import AccountAssignmentOptions, parse_options
from orbit_api.errors import OrbitError

TENANT, ACCOUNT, OWNER, TEAM = (str(UUID(int=index)) for index in range(1, 5))


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"kind": "unknown"},
        {"kind": "OWNER", "owner_user_id": OWNER},
        {"kind": "VENDOR"},
        {"kind": "VENDOR", "owner_user_id": "bad"},
        {"kind": "OWNER", "page_size": "201"},
        {"kind": "OWNER", "page_size": "050"},
        {"kind": "OWNER", "q": "尾部换行\n"},
        {"kind": "OWNER", "q": "\u200b"},
        {"kind": "OWNER", "q": "字" * 101},
        {"kind": "OWNER", "cursor": ""},
        {"kind": "OWNER", "cursor": "a" * 2049},
    ],
)
def test_options_reject_invalid_linkage_and_limits(values):
    with pytest.raises(OrbitError) as error:
        parse_options(values)
    assert error.value.status == 422


def test_normalize_prefix_and_strict_page():
    assert parse_options(
        {"kind": "VENDOR", "owner_user_id": OWNER.upper(), "q": "  e\u0301  ", "page_size": "200"}
    ) == {
        "kind": "VENDOR",
        "owner_user_id": OWNER,
        "q": "é",
        "page_size": 200,
        "cursor": None,
    }


def test_team_admin_requires_explicit_manager_and_user_only_self():
    own = AccountAssignmentOptions.owner_clause(SimpleNamespace(data_role="USER"))
    team = AccountAssignmentOptions.owner_clause(SimpleNamespace(data_role="TEAM_ADMIN"))
    assert own == "b.id=:subject"
    assert "b.id=:subject OR EXISTS" in team and "tm.enabled=1" in team
    assert "team_id=:team" not in team
    assert AccountAssignmentOptions.owner_clause(SimpleNamespace(data_role="SUPER_ADMIN")) == "1=1"


class Result:
    def __init__(self, rows=(), scalar=None):
        self.rows, self.scalar = rows, scalar

    def scalar_one(self):
        return self.scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


@pytest.mark.asyncio
async def test_owner_cursor_authorization_binding_and_no_extra_permission(monkeypatch):
    import orbit_api.account_assignment_options as module

    current = SimpleNamespace(
        actor_id=1, tenant_id=TENANT, subject_id=OWNER, team_id=TEAM, data_role="USER"
    )
    source = {"id": ACCOUNT, "revision": 1, "unbound_at": None}
    calls, issued, owner_calls = [], [], []

    async def lock(_self, session, actor, account, kind, *, write):
        calls.append((actor, account, kind, write))
        return current, [], source

    async def scope(*args):
        return 9

    async def catalog(*args):
        return {"revision": 3}

    class Session:
        async def execute(self, statement, params):
            assert "sys_identity_subject" in str(statement)
            return Result(scalar=7)

    class Tokens:
        def issue(self, purpose, claims):
            issued.append((purpose, claims))
            return "signed-cursor"

        def verify(self, purpose, token):
            assert token == "signed-cursor" and purpose == issued[0][0]
            return issued[0][1]

    async def owners(_session, _current, params):
        owner_calls.append(params)
        return [
            {
                "id": str(UUID(int=index)),
                "name": f"人员{index}",
                "team_id": TEAM,
                "team_name": "团队",
            }
            for index in range(20, 41)
        ]

    monkeypatch.setattr(module.AccountActionsStore, "lock_account", lock)
    monkeypatch.setattr(module, "scope_version", scope)
    monkeypatch.setattr(module, "reference_clock", catalog)
    options = AccountAssignmentOptions(Tokens())
    monkeypatch.setattr(options, "owners", owners)
    query = parse_options({"kind": "OWNER", "page_size": "20", "q": "_%!"})
    result = await options.list(Session(), 1, ACCOUNT, query)
    assert calls == [(1, ACCOUNT, "ASSIGNMENT", False)]
    assert len(result["items"]) == 20 and result["next_cursor"] == "signed-cursor"
    assert owner_calls[0]["query"] == "!_!%!!%" and owner_calls[0]["limit"] == 21
    source["revision"] = 2
    with pytest.raises(OrbitError) as error:
        await options.list(Session(), 1, ACCOUNT, query | {"cursor": "signed-cursor"})
    assert error.value.code == "SCOPE_CHANGED"
    assert len(owner_calls) == 1


@pytest.mark.asyncio
async def test_vendor_batch_real_alias_never_name_fallback(monkeypatch):
    import orbit_api.account_assignment_options as module

    current = SimpleNamespace(
        actor_id=1, tenant_id=TENANT, subject_id=OWNER, team_id=TEAM, data_role="TEAM_ADMIN"
    )
    rows = [
        {
            "id": str(UUID(int=index)),
            "kind": "VENDOR",
            "revision": 1,
            "catalog_revision": 2,
            "updated_at": None,
            "value_json": {
                "name": "目录完整名称",
                "owner_team_id": TEAM,
                "data_owner_user_ids": [OWNER],
                "availability": "AVAILABLE",
            },
        }
        for index in range(10, 211)
    ]
    alias_calls, ownership_calls = [], []

    class Session:
        async def execute(self, statement, params):
            sql = str(statement)
            if "SELECT b.team_id" in sql:
                assert "tm.enabled=1" in sql and "u.status='0'" in sql and "b.invited=0" in sql
                return Result(rows=[{"team_id": TEAM}])
            assert "r.availability='AVAILABLE'" in sql
            assert "o.user_id=:owner" in sql and "orbit_business_team_manager" in sql
            assert params["team"] == TEAM and params["owner"] == OWNER
            return Result(rows=rows)

    async def ownership(_session, _current, value):
        ownership_calls.append(value)

    async def aliases(_session, _current, vendors, *, permission):
        assert permission == "accounts.assign" and len(vendors) == 200
        alias_calls.append(vendors)
        return {
            identifier: {"alias": None if index == 0 else "真实代称"}
            for index, identifier in enumerate(vendors)
        }

    monkeypatch.setattr(module, "validate_ownership", ownership)
    monkeypatch.setattr(module, "freeze_vendor_alias_snapshots", aliases)
    values = await AccountAssignmentOptions(None).vendors(
        Session(),
        current,
        OWNER,
        {"tenant": TENANT, "actor": 1, "subject": OWNER, "after": "", "query": "%", "limit": 201},
    )
    assert len(values) == 201 and len(alias_calls) == 1
    assert values[0] == {"id": rows[0]["id"], "name": "目录完整名称", "alias": None}
    assert values[1]["alias"] == "真实代称"
    assert ownership_calls == [{"owner_team_id": TEAM, "data_owner_user_ids": [OWNER]}]
