import asyncio
from datetime import datetime, timedelta

from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config.settings import settings


async def main():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    async with engine.begin() as c:
        row = (
            await c.execute(text("SELECT id, escritorio_id, role FROM usuarios LIMIT 1"))
        ).first()
    await engine.dispose()

    if not row:
        print("No user found")
        return

    to_encode = {"sub": str(row.id), "escritorio_id": row.escritorio_id, "role": row.role}
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    print("TOKEN:", token)


asyncio.run(main())
