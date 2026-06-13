import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def f():
    engine = create_async_engine('postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres')
    async with engine.begin() as c:
        try:
            await c.execute(text('SELECT tipo_lead FROM leads_prospeccao LIMIT 1'))
            print("tipo_lead OK")
        except Exception as e:
            print("tipo_lead MISSING", type(e).__name__)
        
        try:
            await c.execute(text("SELECT metadata_json FROM interacoes LIMIT 1"))
            print("metadata_json OK")
        except Exception as e:
            print("metadata_json MISSING", type(e).__name__)

    await engine.dispose()

asyncio.run(f())
