# -*- coding:utf-8 -*-
# @Time : 2023/06/19
# @Author : York

import redis

from conf import Redis

# db0 连接池上限。消费侧线程各占一条连接,业务并发上限不得超过它
# (见 tasks.ad_sync_new.consts.DEV_INFLIGHT_CAP)。
REDIS_DB0_POOL_SIZE = 120


def get_redis_cli(db: int, max_connections: int = 16):
    pool = redis.ConnectionPool(
        host=Redis.HOST,
        port=Redis.PORT,
        db=db,
        decode_responses=True,
        password=Redis.PASSWORD,
        retry_on_timeout=True,
        socket_timeout=60,
        socket_connect_timeout=30,
        max_connections=max_connections,
    )
    redis_cli = redis.StrictRedis(connection_pool=pool)
    return redis_cli
