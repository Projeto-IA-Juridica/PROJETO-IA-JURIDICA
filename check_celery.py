import asyncio

import redis.asyncio as redis

from shared.config.settings import settings


async def main():
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    # Check connected clients or pubsub channels
    channels = await r.pubsub_channels("*")
    print(f"Channels: {channels}")
    await r.aclose()


asyncio.run(main())
