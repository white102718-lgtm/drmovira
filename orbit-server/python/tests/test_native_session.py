"""原若依令牌版本及请求上下文边界；真实数据库和HTTP回归由隔离运行器验证。"""

import asyncio

import pytest

from orbit_api import native_session as target
from orbit_api.errors import OrbitError


@pytest.mark.parametrize(
    "actor", [None, True, False, 0, -1, 1.2, "", "-1", "１２", "1.0", 2**63, "9" * 5000]
)
def test_invalid_actor_rejected_before_database(actor):
    from exceptions.exception import AuthException

    with pytest.raises(AuthException):
        target._actor_id({"user_id": actor})


@pytest.mark.parametrize("actor", [1, "1", 2**63 - 1, str(2**63 - 1)])
def test_valid_native_actor(actor):
    assert target._actor_id({"user_id": actor}) == int(actor)


@pytest.mark.parametrize("version", [None, True, False, "1", 0, -1, 1.2])
async def test_invalid_version_never_queries_database(monkeypatch, version):
    from exceptions.exception import AuthException

    async def forbidden(_):
        pytest.fail("无效版本不能访问数据库")

    monkeypatch.setattr(target, "_version", forbidden)
    with pytest.raises(AuthException):
        await target.validate_native_token({"user_id": 1, "auth_version": version})


async def test_database_epoch_enrichment_and_stale_validation(monkeypatch):
    from exceptions.exception import AuthException

    async def version(_):
        return 3

    monkeypatch.setattr(target, "_version", version)
    source = {"user_id": 1, "auth_version": 999}
    assert await target.enrich_native_token(source) == {"user_id": 1, "auth_version": 3}
    assert source["auth_version"] == 999
    with pytest.raises(AuthException):
        await target.validate_native_token({"user_id": 1, "auth_version": 2})


async def test_request_isolation_concurrency_and_exception_reset():
    async def app(scope, receive, send):
        assert target.current_auth_snapshot() is None
        target._snapshot.set(target.AuthSnapshot(scope["actor"], 4))
        await asyncio.sleep(0)
        target.verify_actor_snapshot(scope["actor"], 4)
        with pytest.raises(OrbitError) as error:
            target.verify_actor_snapshot(scope["actor"], 5)
        assert error.value.status == 401
        with pytest.raises(OrbitError):
            target.verify_actor_snapshot(scope["actor"] + 1, 4)
        target.verify_actor_snapshot(999, 99, acting_subject=False)
        if scope["fail"]:
            raise ValueError("模拟控制器异常")

    token = target._snapshot.set(target.AuthSnapshot(99, 1))
    try:
        boundary = target.AuthSnapshotBoundary(app)
        results = await asyncio.gather(
            boundary({"actor": 1, "fail": False}, None, None),
            boundary({"actor": 2, "fail": True}, None, None),
            return_exceptions=True,
        )
        assert results[0] is None and isinstance(results[1], ValueError)
        assert target.current_auth_snapshot().actor_id == 99
    finally:
        target._snapshot.reset(token)
