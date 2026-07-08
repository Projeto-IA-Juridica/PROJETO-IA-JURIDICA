import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.config.settings import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    _async_session = async_sessionmaker(engine, expire_on_commit=False)

    # Are there any celery task results stored? (if backend is db, but it's redis)
    pass


asyncio.run(main())
