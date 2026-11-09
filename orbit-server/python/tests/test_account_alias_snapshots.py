"""020独立写入边界单测；替身不代替业务事务与MySQL真实验收。"""

from types import SimpleNamespace

import pytest

from orbit_api.account_alias_snapshots import append_account_alias_snapshot
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"


class Session:
    def __init__(self, transaction=True):
        self.transaction, self.calls = transaction, []

    def in_transaction(self):
        return self.transaction

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))


def arguments():
    return {
        "resource_type": "IMPORT",
        "resource_id": ID,
        "resource_revision": 1,
        "request_id": ID,
        "permission": "accounts.import",
    }


def vendor():
    return {"id": ID, "revision": 2, "value_json": {"name": "完整资料名不能充作代称"}}


@pytest.mark.parametrize(
    "source,alias", [("UNSET", None), ("VENDOR_ALIAS", None), ("VENDOR_ALIAS", "真实代称")]
)
async def test_explicit_null_source_and_real_alias_are_inserted_without_name_fallback(
    monkeypatch, source, alias
):
    import orbit_api.account_alias_snapshots as module

    recorded = []

    async def freeze(session, context, vendors, **kwargs):
        recorded.append(kwargs)
        return {ID: {"alias": alias, "alias_revision": 7, "source": source}}

    monkeypatch.setattr(module, "freeze_vendor_alias_snapshots", freeze)
    session = Session()
    await append_account_alias_snapshot(
        session, SimpleNamespace(tenant_id=ID), vendor(), **arguments()
    )
    assert len(session.calls) == 1
    sql, params = session.calls[0]
    assert "INSERT INTO orbit_account_vendor_alias_snapshot" in sql and "UPDATE" not in sql
    assert params["alias"] == alias and params["source"] == source and params["alias_revision"] == 7
    assert params["name"] == "完整资料名不能充作代称"
    assert recorded == [{"permission": "accounts.import", "acting_subject": True}]


async def test_worker_uses_explicit_actor_check_without_subject_session_inheritance(monkeypatch):
    import orbit_api.account_alias_snapshots as module

    async def freeze(session, context, vendors, **kwargs):
        assert kwargs == {"permission": "accounts.import", "acting_subject": False}
        return {ID: {"alias": None, "alias_revision": 1, "source": "UNSET"}}

    monkeypatch.setattr(module, "freeze_vendor_alias_snapshots", freeze)
    await append_account_alias_snapshot(
        Session(),
        SimpleNamespace(tenant_id=ID),
        vendor(),
        **(arguments() | {"resource_type": "ACCOUNT_BINDING", "acting_subject": False}),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"permission": "accounts.read"},
        {"resource_type": "ASSIGNMENT"},
        {"resource_revision": True},
        {"resource_id": "bad"},
    ],
)
async def test_wrong_action_or_bad_identifiers_fail_before_database(changes):
    session = Session()
    with pytest.raises(OrbitError):
        await append_account_alias_snapshot(
            session, SimpleNamespace(tenant_id=ID), vendor(), **(arguments() | changes)
        )
    assert not session.calls


async def test_source_reauthorization_failure_does_not_write_snapshot(monkeypatch):
    import orbit_api.account_alias_snapshots as module

    async def denied(*args, **kwargs):
        raise OrbitError(403, "PERMISSION_DENIED", "原动作权限已撤销")

    monkeypatch.setattr(module, "freeze_vendor_alias_snapshots", denied)
    session = Session()
    with pytest.raises(OrbitError):
        await append_account_alias_snapshot(
            session, SimpleNamespace(tenant_id=ID), vendor(), **arguments()
        )
    assert not session.calls


async def test_no_explicit_transaction_is_rejected():
    with pytest.raises(ValueError, match="显式事务"):
        await append_account_alias_snapshot(
            Session(False), SimpleNamespace(tenant_id=ID), vendor(), **arguments()
        )
