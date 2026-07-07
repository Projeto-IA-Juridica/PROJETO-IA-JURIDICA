import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from shared.config.settings import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(text("SELECT id, nome, webhook_whatsapp_instance FROM escritorios LIMIT 5;"))
        for row in result:
            print(row)

asyncio.run(main())
