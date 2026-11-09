"""密码策略批量读取的原生协议回归，不连接 Redis/数据库。"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from redis.asyncio.client import Pipeline
from redis.exceptions import ResponseError

from common.context import RequestContext
from config.env import AppConfig
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from utils.jwt_util import JwtUtil
from utils.time_util import TimezoneUtil

NOW = datetime(2026, 11, 9, 8, tzinfo=UTC)
KEYS = [
    'sys_config:sys.account.chrtype',
    'sys_config:sys.account.initPasswordModify',
    'sys_config:sys.account.passwordValidateDays',
]


class PolicyRedis(SimpleNamespace):
    """记录真实非事务队列协议，执行结果由测试传入。"""

    def pipeline(self, *, transaction: bool) -> 'PolicyPipeline':
        assert transaction is False
        return PolicyPipeline(self)


class PolicyPipeline:
    def __init__(self, redis: PolicyRedis) -> None:
        self.redis = redis
        self.keys: list[str] = []

    async def __aenter__(self) -> 'PolicyPipeline':
        return self

    async def __aexit__(self, *args: object) -> None:
        assert self.keys == KEYS
        self.redis.context_exits = getattr(self.redis, 'context_exits', 0) + 1
        self.keys.clear()

    def get(self, key: str) -> 'PolicyPipeline':
        self.keys.append(key)
        return self

    async def execute(self) -> list[str | None]:
        assert self.keys == KEYS
        return await self.redis.batch_execute()


def request_for(redis: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))


@pytest.mark.parametrize('char', [None, '', '0', '4', 'unrecognized'])
@pytest.mark.parametrize('modify', [None, '', '0', '1', 'true'])
@pytest.mark.parametrize('updated', [None, NOW])
async def test_batch_matches_independent_helpers(
    monkeypatch: pytest.MonkeyPatch, char: str | None, modify: str | None, updated: datetime | None
) -> None:
    values = [char, modify, '0']
    redis = PolicyRedis(batch_execute=AsyncMock(return_value=values), get=AsyncMock(side_effect=values))
    request = request_for(redis)
    monkeypatch.setattr(TimezoneUtil, 'utc_now', lambda: NOW)
    actual = await LoginService._read_password_policy(request, updated)
    expected = (
        await LoginService.get_sys_account_chrtype(request),
        await LoginService._LoginService__init_password_is_modify(request, updated),
        await LoginService._LoginService__password_is_expired(request, updated),
    )
    assert actual == expected
    redis.batch_execute.assert_awaited_once_with()
    assert [call.args[0] for call in redis.get.await_args_list] == KEYS


@pytest.mark.parametrize('days', [None, '', '0', '-1', '1', '30', ' 1 ', '+1'])
@pytest.mark.parametrize('updated', [None, NOW, NOW - timedelta(days=1), NOW - timedelta(days=1, microseconds=1)])
async def test_expiry_matches_original_utc_strict_boundary(
    monkeypatch: pytest.MonkeyPatch, days: str | None, updated: datetime | None
) -> None:
    monkeypatch.setattr(TimezoneUtil, 'utc_now', lambda: NOW)
    redis = PolicyRedis(batch_execute=AsyncMock(return_value=[None, None, days]), get=AsyncMock(return_value=days))
    actual = (await LoginService._read_password_policy(request_for(redis), updated))[2]
    original = await LoginService._LoginService__password_is_expired(request_for(redis), updated)
    assert actual is original
    enabled = bool(days) and int(days) > 0
    expected = enabled and (updated is None or updated + timedelta(days=int(days)) < NOW)
    assert actual is bool(expected)


@pytest.mark.parametrize('days', ['bad', '1.5', ' '])
async def test_invalid_days_keep_value_error(days: str) -> None:
    redis = PolicyRedis(batch_execute=AsyncMock(return_value=['0', '1', days]), get=AsyncMock(return_value=days))
    with pytest.raises(ValueError):
        await LoginService._read_password_policy(request_for(redis), None)
    with pytest.raises(ValueError):
        await LoginService._LoginService__password_is_expired(request_for(redis), None)


@pytest.mark.parametrize('updated', [datetime(2026, 11, 9), datetime.max.replace(tzinfo=UTC)])
async def test_invalid_date_failures_match_original(monkeypatch: pytest.MonkeyPatch, updated: datetime) -> None:
    monkeypatch.setattr(TimezoneUtil, 'utc_now', lambda: NOW)
    redis = PolicyRedis(batch_execute=AsyncMock(return_value=['0', '0', '1']), get=AsyncMock(return_value='1'))
    error_type = TypeError if updated.tzinfo is None else OverflowError
    with pytest.raises(error_type):
        await LoginService._read_password_policy(request_for(redis), updated)
    with pytest.raises(error_type):
        await LoginService._LoginService__password_is_expired(request_for(redis), updated)


@pytest.fixture
def resolver(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(JwtUtil, 'decode', lambda token: {'user_id': '7', 'session_id': 'session-a'})
    monkeypatch.setattr(AppConfig, 'app_same_time_login', True)
    validator = AsyncMock()
    monkeypatch.setattr(LoginService, '_token_validators', (validator,))
    user = SimpleNamespace(user=SimpleNamespace(pwd_update_date=None))
    snapshot = AsyncMock(return_value=user)
    monkeypatch.setattr(LoginService, '_get_current_user_snapshot', snapshot)
    publish = Mock()
    monkeypatch.setattr(RequestContext, 'set_current_user', publish)
    redis = PolicyRedis(
        get=AsyncMock(return_value='test-token'),
        batch_execute=AsyncMock(return_value=['4', '1', '30']),
        eval=AsyncMock(return_value=1),
    )
    return SimpleNamespace(
        redis=redis, request=request_for(redis), user=user, snapshot=snapshot, publish=publish, validator=validator
    )


@pytest.mark.parametrize('refresh', [False, True])
async def test_resolver_preserves_order_and_session_fence(resolver: SimpleNamespace, refresh: bool) -> None:
    r = resolver
    order = []

    async def get(key: str) -> str:
        order.append('token')
        return 'test-token'

    async def snapshot(*args: object) -> SimpleNamespace:
        order.append('snapshot')
        return r.user

    async def batch_execute() -> list[str]:
        order.append('policy')
        return ['4', '1', '30']

    async def renew(*args: object) -> int:
        order.append('renew')
        return 1

    r.redis.get.side_effect = get
    r.snapshot.side_effect = snapshot
    r.redis.batch_execute.side_effect = batch_execute
    r.redis.eval.side_effect = renew
    result = await LoginService._resolve_current_user(r.request, 'test-token', object(), refresh_session=refresh)
    assert order == ['token', 'snapshot', 'policy', 'renew' if refresh else 'token']
    assert (result.pwd_chrtype, result.is_default_modify_pwd, result.is_password_expired) == ('4', True, True)
    r.validator.assert_awaited_once()
    r.publish.assert_called_once_with(result)


@pytest.mark.parametrize('refresh', [False, True])
@pytest.mark.parametrize('when', ['before', 'after', 'validator'])
async def test_revocation_never_publishes_or_renews_invalid_session(
    resolver: SimpleNamespace, refresh: bool, when: str
) -> None:
    r = resolver
    if when == 'before':
        r.redis.get.return_value = 'replacement'
    elif when == 'after':
        r.redis.get.side_effect = ['test-token', 'replacement']
        r.redis.eval.return_value = 0
    else:
        r.validator.side_effect = AuthException(data='', message='已撤销')
    with pytest.raises(AuthException):
        await LoginService._resolve_current_user(r.request, 'test-token', object(), refresh_session=refresh)
    r.publish.assert_not_called()
    if when != 'after':
        r.redis.batch_execute.assert_not_awaited()
        r.redis.eval.assert_not_awaited()


@pytest.mark.parametrize('refresh', [False, True])
@pytest.mark.parametrize('failure', [RuntimeError('unavailable'), asyncio.CancelledError()])
async def test_batch_execute_failure_or_cancel_is_not_hidden(
    resolver: SimpleNamespace, refresh: bool, failure: BaseException
) -> None:
    r = resolver
    r.redis.batch_execute.side_effect = failure
    with pytest.raises(type(failure)) as caught:
        await LoginService._resolve_current_user(r.request, 'test-token', object(), refresh_session=refresh)
    assert caught.value is failure
    r.publish.assert_not_called()
    r.redis.eval.assert_not_awaited()
    assert r.redis.get.await_count == 1


async def test_concurrent_requests_each_read_current_policy_without_cache(resolver: SimpleNamespace) -> None:
    r = resolver
    concurrent_requests = 8
    entered = 0
    ready = asyncio.Event()

    async def policy() -> list[str]:
        nonlocal entered
        entered += 1
        if entered == concurrent_requests:
            ready.set()
        await ready.wait()
        return ['4', '1', '30']

    r.redis.batch_execute.side_effect = policy
    await asyncio.gather(
        *[
            LoginService._resolve_current_user(r.request, 'test-token', object(), refresh_session=False)
            for _ in range(concurrent_requests)
        ]
    )
    assert r.redis.batch_execute.await_count == concurrent_requests
    assert r.redis.get.await_count == concurrent_requests * 2
    r.redis.batch_execute.side_effect = None
    r.redis.batch_execute.return_value = ['2', '0', '0']
    result = await LoginService._resolve_current_user(r.request, 'test-token', object(), refresh_session=False)
    assert (result.pwd_chrtype, result.is_default_modify_pwd, result.is_password_expired) == ('2', False, False)
    assert r.redis.batch_execute.await_count == concurrent_requests + 1


async def test_cancelling_inflight_batch_execute_keeps_context_unpublished(resolver: SimpleNamespace) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked() -> list[str]:
        entered.set()
        await release.wait()
        return ['4', '1', '30']

    resolver.redis.batch_execute.side_effect = blocked
    pending = asyncio.create_task(
        LoginService._resolve_current_user(resolver.request, 'test-token', object(), refresh_session=True)
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    resolver.publish.assert_not_called()
    resolver.redis.eval.assert_not_awaited()
    assert resolver.redis.get.await_count == 1


@pytest.mark.parametrize('error_index', [0, 1, 2])
async def test_real_pipeline_preserves_wrongtype_and_releases_connection(error_index: int) -> None:

    async def retry_call(operation: Callable[[], Awaitable[object]], *args: object, **kwargs: object) -> object:
        return await operation()

    connection = SimpleNamespace(
        retry=SimpleNamespace(call_with_retry=retry_call),
        pack_commands=Mock(return_value=b'fixed-test-wire'),
        send_packed_command=AsyncMock(),
        host='unit',
        port=0,
        db=0,
    )
    pool = SimpleNamespace(get_connection=AsyncMock(return_value=connection), release=AsyncMock())
    pipeline = Pipeline(pool, {}, transaction=False, shard_hint=None)
    failure = ResponseError('WRONGTYPE test key type')
    responses = ['4', '1', '30']
    responses[error_index] = failure
    pipeline.parse_response = AsyncMock(side_effect=responses)
    factory = Mock(return_value=pipeline)
    request = request_for(SimpleNamespace(pipeline=factory))
    with pytest.raises(ResponseError) as caught:
        await LoginService._read_password_policy(request, None)
    assert caught.value is failure
    factory.assert_called_once_with(transaction=False)
    assert pipeline.parse_response.await_count == len(KEYS)
    assert connection.pack_commands.call_args.args[0] == [('GET', key) for key in KEYS]
    connection.send_packed_command.assert_awaited_once()
    pool.release.assert_awaited_once_with(connection)
    assert pipeline.connection is None
    assert pipeline.command_stack == []


@pytest.mark.parametrize('failure', [RuntimeError('transport failed'), asyncio.CancelledError()])
async def test_real_pipeline_error_cleanup_keeps_failure(failure: BaseException) -> None:

    async def retry_call(operation: Callable[[], Awaitable[object]], *args: object, **kwargs: object) -> object:
        return await operation()

    connection = SimpleNamespace(
        retry=SimpleNamespace(call_with_retry=retry_call),
        pack_commands=Mock(return_value=b'fixed-test-wire'),
        send_packed_command=AsyncMock(side_effect=failure),
        host='unit',
        port=0,
        db=0,
    )
    pool = SimpleNamespace(get_connection=AsyncMock(return_value=connection), release=AsyncMock())
    pipeline = Pipeline(pool, {}, transaction=False, shard_hint=None)
    request = request_for(SimpleNamespace(pipeline=Mock(return_value=pipeline)))
    with pytest.raises(type(failure)) as caught:
        await LoginService._read_password_policy(request, None)
    assert caught.value is failure
    pool.release.assert_awaited_once_with(connection)
    assert pipeline.connection is None
    assert pipeline.command_stack == []
