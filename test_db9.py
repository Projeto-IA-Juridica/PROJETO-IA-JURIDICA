import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def f():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    )
    async with engine.begin() as c:
        try:
            await c.execute(text("SELECT dna_prospeccao FROM escritorios LIMIT 1"))
            print("dna_prospeccao OK")
        except Exception as e:
            print("dna_prospeccao MISSING", type(e).__name__, str(e))
    await engine.dispose()


asyncio.run(f())
