"""Cookie账户补充工具护栏纯测；替身结果不是HTTP/数据库验收。"""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

core = importlib.import_module("tools.account_read_cookie_checks")
DATABASE = "orbit_py_it_" + "b" * 32
TENANT = str(UUID(int=1))
OWNER = str(UUID(int=2))
TEAM = str(UUID(int=3))
PEER = str(UUID(int=4))


class Admin:
    host = "127.0.0.1"
    port = 13306

    def __init__(self):
        self.current = DATABASE
        self.own = (TENANT, OWNER, TEAM, "USER", "user_directory_22", "0", "0", 1, 0)
        self.peer = (PEER, TEAM)
        self.queries = []
        self.rowcount = 1

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        self.last = sql
        self.rowcount = 1

    def fetchone(self):
        if self.last == "SELECT DATABASE()":
            return (self.current,)
        if "s.data_role" in self.last:
            return self.own
        if "native_role_id" in self.last:
            return (7654321,)
        return self.peer


@pytest.mark.parametrize("field,value", [("host", "example.org"), ("port", 3306)])
def test_nonlocal_guard_before_any_sql(field, value):
    admin = Admin()
    setattr(admin, field, value)
    with pytest.raises(ValueError, match="FIXTURE_BOUNDARY"):
        core.guard_account_cookie_fixture(admin, DATABASE, 980022)
    assert admin.queries == []


@pytest.mark.parametrize(
    "database,actor",
    [("orbit_real", 980022), (DATABASE, True), (DATABASE, 980021), (DATABASE.upper(), 980022)],
)
def test_database_and_exact_fixture_actor_guard_before_sql(database, actor):
    admin = Admin()
    with pytest.raises(ValueError, match="FIXTURE_BOUNDARY"):
        core.guard_account_cookie_fixture(admin, database, actor)
    assert admin.queries == []


def test_actual_database_mismatch_rejected_before_identity_or_mutation():
    admin = Admin()
    admin.current = "orbit_py_it_" + "c" * 32
    with pytest.raises(ValueError, match="DATABASE_MISMATCH"):
        core.guard_account_cookie_fixture(admin, DATABASE, 980022)
    assert len(admin.queries) == 1


@pytest.mark.parametrize(
    "index,value", [(3, "SUPER_ADMIN"), (4, "other"), (5, "1"), (7, 0), (8, 1)]
)
def test_actor_current_identity_mismatch_is_closed(index, value):
    admin = Admin()
    row = list(admin.own)
    row[index] = value
    admin.own = tuple(row)
    with pytest.raises(ValueError, match="ACTOR_MISMATCH"):
        core.guard_account_cookie_fixture(admin, DATABASE, 980022)
    assert all(sql.startswith("SELECT ") for sql, params in admin.queries)


def test_peer_missing_rejected_without_mutation():
    admin = Admin()
    admin.peer = None
    with pytest.raises(ValueError, match="PEER_MISMATCH"):
        core.guard_account_cookie_fixture(admin, DATABASE, 980022)
    assert all(sql.startswith("SELECT ") for sql, params in admin.queries)


def test_guard_returns_exact_current_and_foreign_owner_without_creating_role():
    assert core.guard_account_cookie_fixture(Admin(), DATABASE, 980022) == (
        TENANT,
        OWNER,
        TEAM,
        PEER,
        TEAM,
    )
    assert (
        len(core.ACCOUNT_READ_COOKIE_CASES) == 2 and len(set(core.ACCOUNT_READ_COOKIE_CASES)) == 2
    )


def payload():
    account = dict.fromkeys(core.ACCOUNT_KEYS)
    account.update(
        id=OWNER,
        ownership={"owner_user_id": OWNER, "owner_team_id": TEAM},
        auth_status="UNKNOWN",
        account_status="UNKNOWN",
        currency="USD",
        spend={"amount": None},
        balance={"amount": None},
    )
    return {
        "account": account,
        "details": {"account_id": OWNER, "identity_status": "UNSYNCED", "identity_count": None},
    }


def test_payload_keeps_unknown_values_instead_of_verified_zero():
    core.check_cookie_account_payload(payload(), OWNER, OWNER, TEAM)


@pytest.mark.parametrize(
    "mutation", ["extra", "owner", "zero_spend", "identity_zero", "wrong_account"]
)
def test_payload_rejects_extra_wrong_scope_or_fake_zero(mutation):
    value = payload()
    if mutation == "extra":
        value["account"]["unexpected"] = True
    elif mutation == "owner":
        value["account"]["ownership"]["owner_user_id"] = PEER
    elif mutation == "zero_spend":
        value["account"]["spend"]["amount"] = "0"
    elif mutation == "identity_zero":
        value["details"]["identity_count"] = 0
    else:
        value["details"]["account_id"] = PEER
    with pytest.raises(AssertionError):
        core.check_cookie_account_payload(value, OWNER, OWNER, TEAM)


@pytest.mark.asyncio
async def test_guard_stops_all_http_and_issue_before_bad_target():
    client = Mock()
    issue = AsyncMock()
    with pytest.raises(ValueError, match="FIXTURE_BOUNDARY"):
        await core.run_account_read_cookie_checks(
            client,
            Admin(),
            object(),
            object(),
            issue,
            "nonsecret-test-binding",
            980022,
            {},
            [],
            database="not-isolated",
        )
    assert client.mock_calls == []
    issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_http_failure_cleans_only_new_binding_and_random_seed():
    admin = Admin()

    class Client:
        def get(self, path, **kwargs):
            if path == "/api/v1/roles/capabilities":
                return SimpleNamespace(status_code=200, json=lambda: {"csrf_token": "test-csrf"})
            return SimpleNamespace(status_code=500)

        def post(self, path, **kwargs):
            assert path == "/api/v1/roles"
            assert kwargs["json"]["menu_codes"] == ["accounts"]
            assert kwargs["json"]["permission_codes"] == ["accounts.read"]
            return SimpleNamespace(status_code=201, json=lambda: {"id": str(UUID(int=99))})

    issue = AsyncMock(return_value=("test-cookie", SimpleNamespace(csrf_token="test-csrf")))
    cases = []
    with pytest.raises(AssertionError, match="LIST_200"):
        await core.run_account_read_cookie_checks(
            Client(),
            admin,
            object(),
            object(),
            issue,
            "test-binding",
            980022,
            {"Authorization": "Bearer test-only"},
            cases,
            database=DATABASE,
        )
    assert cases == []
    deletes = [(sql, params) for sql, params in admin.queries if sql.startswith("DELETE ")]
    assert len(deletes) == 2
    assert deletes[0] == (
        "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
        (980022, 7654321),
    )
    assert deletes[1][0] == "DELETE FROM orbit_ad_account WHERE tenant_id=%s AND id IN(%s,%s)"
    assert deletes[1][1][0] == TENANT
    assert len(set(deletes[1][1][1:])) == 2
    assert not any(
        "auth_version" in sql or "DELETE FROM orbit_business_role" in sql
        for sql, params in admin.queries
    )
