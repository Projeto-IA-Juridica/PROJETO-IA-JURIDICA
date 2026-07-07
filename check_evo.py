import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.config.settings import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            text("SELECT webhook_whatsapp_instance FROM escritorios LIMIT 1;")
        )
        for row in result:
            print(f"Instance: {row[0]}")


asyncio.run(main())
