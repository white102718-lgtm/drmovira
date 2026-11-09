"""公共业务授权的菜单与动作分离；SQL/撤权仍须独立MySQL集成复验。"""

from unittest.mock import AsyncMock

import pytest

from orbit_api.authorization import require_business_access, require_system_access
from orbit_api.errors import OrbitError
from orbit_api.role_bridge import compiled_menu_ids


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def session(parent=31070, leaf=31071, permission="channels.read"):
    scope = dict(
        tenant_id="tenant",
        data_role="TEAM_ADMIN",
        subject_id="subject",
        team_id="team",
        auth_version=1,
    )
    grants = [
        dict(menu_id=31000, parent_id=0, perms=""),
        dict(menu_id=parent, parent_id=31000, perms="channels.read"),
        dict(menu_id=leaf, parent_id=parent, perms=permission),
    ]
    value = AsyncMock()
    value.execute.side_effect = [Rows([scope]), Rows(grants)]
    return value, scope, grants


@pytest.fixture(autouse=True)
def identity_boundary(monkeypatch):
    monkeypatch.setattr("orbit_api.authorization.verify_actor_snapshot", lambda *_a, **_k: None)
    verify = AsyncMock()
    monkeypatch.setattr("orbit_api.cookie_identity.ensure_cookie_current", verify)
    return verify


@pytest.mark.asyncio
async def test_business_access_rechecks_identity_and_exact_menu(identity_boundary):
    db, _, _ = session()
    context = await require_business_access(db, 2, "channels", "channels.read")
    assert (context.actor_id, context.tenant_id, context.team_id) == (2, "tenant", "team")
    identity_boundary.assert_awaited_once_with(db, 2, acting_subject=True)
    query, binds = db.execute.call_args.args
    assert binds["parent"] == 31070 and binds["leaf"] == 31071
    assert binds["menu_code"] == "channels" and "FOR SHARE" in str(query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["missing_root", "missing_parent", "wrong_parent", "wrong_action", "system_parent"]
)
async def test_partial_or_wrong_native_grants_do_not_authorize(mutation):
    db, _, grants = session()
    if mutation == "missing_root":
        grants.pop(0)
    elif mutation == "missing_parent":
        grants.pop(1)
    elif mutation == "wrong_parent":
        grants[2]["parent_id"] = 31050
    elif mutation == "wrong_action":
        grants[2]["perms"] = "channels.assign"
    else:
        grants[1]["perms"] = "system.read"
    with pytest.raises(OrbitError) as failure:
        await require_business_access(db, 2, "channels", "channels.read")
    assert failure.value.status == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "menu,permission",
    [("materials", "assets.read"), ("channels", "assets.read"), ("assets", "categories.read")],
)
async def test_unregistered_menu_action_pair_never_queries_database(menu, permission):
    db = AsyncMock()
    with pytest.raises(OrbitError):
        await require_business_access(db, 2, menu, permission)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cookie_revocation_precedes_menu_grants(identity_boundary):
    db, _, _ = session()
    identity_boundary.side_effect = OrbitError(401, "SESSION_REQUIRED", "会话失效")
    with pytest.raises(OrbitError) as failure:
        await require_business_access(db, 2, "channels", "channels.read")
    assert failure.value.status == 401 and db.execute.await_count == 1


@pytest.mark.asyncio
async def test_system_wrapper_keeps_registered_dictionary_number():
    db, scope, grants = session(31080, 31089, "system.dictionaries.manage")
    scope["data_role"] = "SUPER_ADMIN"
    grants[1]["perms"] = "system.read"
    await require_system_access(db, 2, 31089, "system.dictionaries.manage", super_admin=True)
    assert db.execute.call_args.args[1]["menu_code"] == "system"


def test_role_compilation_does_not_infer_menu_from_action_or_action_from_menu():
    assert compiled_menu_ids(["channels"], []) == [31000, 31070]
    assert compiled_menu_ids([], ["channels.read"]) == [31071]
    assert compiled_menu_ids(["assets"], ["tags.archive"]) == [31000, 31050, 31058]
