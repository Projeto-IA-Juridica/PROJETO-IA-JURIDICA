import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import traceback

async def f():
    engine = create_async_engine('postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres')
    try:
        async with engine.begin() as c:
            await c.execute(text('SELECT id FROM leads_prospeccao LIMIT 1'))
            print("leads_prospeccao OK")
    except Exception as e:
        print("leads_prospeccao MISSING")
    
    try:
        async with engine.begin() as c:
            await c.execute(text('SELECT id FROM escalacoes LIMIT 1'))
            print("escalacoes OK")
    except Exception as e:
        print("escalacoes MISSING")

    await engine.dispose()

asyncio.run(f())
