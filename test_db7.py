import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def f():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    )
    async with engine.begin() as c:
        try:
            await c.execute(text("SELECT satisfacao FROM interacoes LIMIT 1"))
            print("satisfacao OK")
        except Exception as e:
            print("satisfacao MISSING", type(e).__name__)

    await engine.dispose()


asyncio.run(f())
