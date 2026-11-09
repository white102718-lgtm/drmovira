# import os
#
#
# os.environ["w_env"] = "prod"


import asyncio
from app.db.clients import redis_cli
from app.api.routes.materials import collection, REDIS_KEY


async def a():
    cursor = collection.find(
        {"analysis_description": {"$exists": False}}, {"filename": 1}
    )
    async for doc in cursor:
        await redis_cli.rpush(REDIS_KEY, doc["filename"])


asyncio.run(a())
