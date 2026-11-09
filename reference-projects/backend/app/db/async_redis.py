import redis.asyncio as redis

from app.conf import Redis


def get_redis_cli(db: int):
    pool = redis.BlockingConnectionPool(
        host=Redis.HOST,
        port=Redis.PORT,
        db=db,
        decode_responses=True,
        password=Redis.PASSWORD,
        retry_on_timeout=True,
        socket_timeout=10,
        socket_connect_timeout=30,
        max_connections=50,
        timeout=5,  # 池满时最多等 5s 取连接, 超时才抛错
    )
    redis_cli = redis.StrictRedis(connection_pool=pool)
    return redis_cli
