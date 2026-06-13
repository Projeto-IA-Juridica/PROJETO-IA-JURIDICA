import asyncio
import traceback

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_db():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            print("Checking prospects table...")
            await conn.execute(text("SELECT id FROM prospects LIMIT 1;"))
            print("prospects OK")
    except Exception:
        print("Error:")
        traceback.print_exc()
    await engine.dispose()


asyncio.run(test_db())
