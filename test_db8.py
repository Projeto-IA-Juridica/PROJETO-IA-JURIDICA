import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def f():
    engine = create_async_engine('postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres')
    async with engine.begin() as c:
        try:
            await c.execute(text('SELECT crm_nivel, crm_score, crm_resumo, crm_acao_sugerida, crm_analisado_em FROM clientes LIMIT 1'))
            print("clientes CRM fields OK")
        except Exception as e:
            print("clientes CRM fields MISSING", type(e).__name__, str(e))
            
        try:
            await c.execute(text('SELECT satisfy FROM interacoes LIMIT 1'))
        except Exception as e:
            pass # ignore intentionally bad
            
    await engine.dispose()

asyncio.run(f())
