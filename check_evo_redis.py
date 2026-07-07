import asyncio
import redis.asyncio as redis
from shared.config.settings import settings

async def main():
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    val = await r.hgetall('evolution-cache:instance:6bb82ebb-ded9-463d-b312-90b4c8456822')
    print(val)
    await r.aclose()

asyncio.run(main())
