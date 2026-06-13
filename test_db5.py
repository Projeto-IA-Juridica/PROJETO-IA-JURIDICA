import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def f():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    )
    try:
        async with engine.begin() as c:
            await c.execute(text("SELECT id FROM leads_prospeccao LIMIT 1"))
            print("leads_prospeccao OK")
    except Exception:
        print("leads_prospeccao MISSING")

    try:
        async with engine.begin() as c:
            await c.execute(text("SELECT id FROM escalacoes LIMIT 1"))
            print("escalacoes OK")
    except Exception:
        print("escalacoes MISSING")

    await engine.dispose()


asyncio.run(f())
