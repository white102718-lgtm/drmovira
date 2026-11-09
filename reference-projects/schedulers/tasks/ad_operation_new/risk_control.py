RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _release_lock(redis_cli, lock_key: str, token: str):
    redis_cli.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, token)
