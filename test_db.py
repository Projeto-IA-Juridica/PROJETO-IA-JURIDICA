import asyncio

from sqlalchemy.ext.asyncio import create_async_engine


async def test_db():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    async with engine.begin() as _:
        print("Connected to DB successfully.")
    await engine.dispose()


asyncio.run(test_db())
