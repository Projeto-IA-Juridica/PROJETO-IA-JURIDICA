import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import traceback

async def test_db():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            print("Checking escritorios...")
            await conn.execute(text("SELECT onboarding_etapa FROM escritorios LIMIT 1;"))
            print("onboarding_etapa OK")
    except Exception:
        traceback.print_exc()
    await engine.dispose()

asyncio.run(test_db())
