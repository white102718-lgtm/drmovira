"""元数据读取失效按精确连接版本CAS；权限拒绝不等同Token失效。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from orbit_api.meta_account_sources import MetaAccountSource, invalidate_meta_read_source
from orbit_api.meta_read_contract import MetaReadConfiguration


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["META_READ_FORBIDDEN", "ACCOUNT_PLATFORM_FORBIDDEN"])
async def test_permission_denied_never_revokes_token(code):
    source = MetaAccountSource(
        MetaReadConfiguration(str(uuid4()), 1, "v24.0", "isolated-token"), "LOGIN", None
    )
    assert not await invalidate_meta_read_source(object(), object(), source, code, str(uuid4()))


@pytest.mark.asyncio
@pytest.mark.parametrize("current_revision,revoked", [(2, True), (3, False)])
async def test_auth_error_cas_cannot_revoke_new_authorization(
    monkeypatch, current_revision, revoked
):
    import orbit_api.meta_account_sources as module

    events = []
    connection = str(uuid4())
    source = MetaAccountSource(
        MetaReadConfiguration(connection, 2, "v24.0", "isolated-token"), "LOGIN", None
    )

    class Session:
        def in_transaction(self):
            return True

        async def execute(self, statement, params):
            assert params["id"] == connection and params["revision"] == 2
            sql = str(statement)
            assert "revision=:revision" in sql and "status='ACTIVE'" in sql
            assert "token_envelope=NULL" in sql
            return SimpleNamespace(rowcount=int(current_revision == params["revision"]))

    async def event(*args):
        events.append(args)

    monkeypatch.setattr(module, "event", event)
    assert (
        await invalidate_meta_read_source(
            Session(),
            SimpleNamespace(tenant_id=str(uuid4())),
            source,
            "META_AUTH_FAILED",
            str(uuid4()),
        )
        is revoked
    )
    assert len(events) == int(revoked)
