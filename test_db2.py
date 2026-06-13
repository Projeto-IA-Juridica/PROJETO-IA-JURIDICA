import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_db():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        print("Connected to DB successfully.")
        result = await conn.execute(text("SELECT email FROM usuarios;"))
        for row in result:
            print(row.email)
    await engine.dispose()


asyncio.run(test_db())
