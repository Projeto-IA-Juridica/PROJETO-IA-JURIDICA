import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def f():
    engine = create_async_engine('postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres')
    async with engine.begin() as c:
        rows = await c.execute(text('SELECT * FROM alembic_version'))
        print(rows.fetchall())
    await engine.dispose()

asyncio.run(f())
