import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import traceback

async def test_db():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            print("Checking CRM fields in clientes table...")
            await conn.execute(text("SELECT crm_nivel FROM clientes LIMIT 1;"))
            print("crm_nivel OK")
            print("Checking escalacoes table...")
            await conn.execute(text("SELECT id FROM escalacoes LIMIT 1;"))
            print("escalacoes OK")
    except Exception as e:
        print("Error:")
        traceback.print_exc()
    await engine.dispose()

asyncio.run(test_db())
