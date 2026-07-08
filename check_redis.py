import asyncio

import redis.asyncio as redis

from shared.config.settings import settings


async def main():
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    length = await r.llen("celery")
    print(f"Tasks in queue: {length}")
    keys = await r.keys("*")
    print(f"Keys: {keys}")
    await r.aclose()


asyncio.run(main())
