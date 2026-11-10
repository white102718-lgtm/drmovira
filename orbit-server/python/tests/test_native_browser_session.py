import pytest

from orbit_api.browser_session_store import BrowserSessionStore
from orbit_api.errors import OrbitError


class Result:
    def mappings(self):
        return self

    def first(self):
        return self.row


class Session:
    def __init__(self, row):
        self.row = row

    async def execute(self, query, params):
        assert "orbit_external_identity" not in str(query)
        r = Result()
        r.row = self.row
        return r


@pytest.mark.asyncio
async def test_native_session_checks_active_local_identity_without_fake_oidc():
    assert hasattr(BrowserSessionStore, "native_principal")
    row = dict(subject_id="person", auth_version=3)
    assert await BrowserSessionStore.native_principal(Session(row), "tenant", 1) == row
    with pytest.raises(OrbitError):
        await BrowserSessionStore.native_principal(Session(None), "tenant", 1)
