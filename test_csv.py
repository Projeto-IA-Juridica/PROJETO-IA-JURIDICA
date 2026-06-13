import asyncio
from fastapi.testclient import TestClient
import traceback
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from datetime import datetime, timedelta
from jose import jwt
from shared.config.settings import settings
import io

async def main():
    url = "postgresql+asyncpg://postgres.ojrrbtwivkatwitfwgao:projetoIAjuridica@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    async with engine.begin() as c:
        row = (await c.execute(text("SELECT id, escritorio_id, role FROM usuarios LIMIT 1"))).first()
    await engine.dispose()
    
    to_encode = {"sub": str(row.id), "escritorio_id": row.escritorio_id, "role": row.role}
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    from feature_1_ia_personalizada.api.app import app
    client = TestClient(app)
    
    csv_content = "nome,telefone\nJoão,5511999999999\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    
    try:
        response = client.post("/onboarding/import-processos?preview=false", headers={"Authorization": f"Bearer {token}"}, files=files)
        print("Status:", response.status_code)
        print("JSON:", response.json())
    except Exception as e:
        traceback.print_exc()

asyncio.run(main())
