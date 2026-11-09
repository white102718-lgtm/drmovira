import json
import logging
import random
import time
import uuid


BASE_INTERVAL = 2
INTERVAL_FACTOR = 0.1
MAX_INTERVAL = 12
RESET_WINDOW = 30
STATE_TTL = 60
LOCK_TTL = 5
LOCK_WAIT = 0.05
STATE_KEY_TEMPLATE = "ad_op:risk:interval:{app_id}:state"
LOCK_KEY_TEMPLATE = "ad_op:risk:interval:{app_id}:lock"
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _build_keys(dev_app: dict) -> tuple[str, str, str]:
    app_id = dev_app["app_id"]
    return (
        app_id,
        STATE_KEY_TEMPLATE.format(app_id=app_id),
        LOCK_KEY_TEMPLATE.format(app_id=app_id),
    )


def _acquire_lock(redis_cli, lock_key: str, token: str):
    while not redis_cli.set(lock_key, token, nx=True, ex=LOCK_TTL):
        time.sleep(LOCK_WAIT)


def _release_lock(redis_cli, lock_key: str, token: str):
    redis_cli.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, token)


def _build_interval(count: int) -> float:
    return min(MAX_INTERVAL, BASE_INTERVAL + INTERVAL_FACTOR * (count - 1) ** 2)


def reserve_operation_slot(redis_cli, dev_app: dict) -> float:
    app_id, state_key, lock_key = _build_keys(dev_app)
    token = uuid.uuid4().hex
    _acquire_lock(redis_cli, lock_key, token)
    now = time.time()
    raw = redis_cli.get(state_key)

    if raw:
        state = json.loads(raw)
        last_execute_at = state["last_execute_at"]
        if now - last_execute_at > RESET_WINDOW:
            count = 1
            interval = 0
            execute_at = now
        else:
            count = state["count"] + 1
            interval = _build_interval(count) * random.uniform(0.9, 1.3)
            execute_at = max(now, last_execute_at + interval)
    else:
        count = 1
        interval = 0
        execute_at = now

    redis_cli.set(
        state_key,
        json.dumps(
            {"count": count, "last_execute_at": execute_at},
            ensure_ascii=False,
        ),
        ex=STATE_TTL,
    )
    _release_lock(redis_cli, lock_key, token)
    logging.info(
        f"操作间隔计算完成 app_id={app_id} count={count} "
        f"interval={interval:.2f}s wait_seconds={max(0, execute_at - now):.2f}s "
        f"execute_at={execute_at:.3f}"
    )
    return execute_at
