"""
shared/database/session.py
===========================
Módulo responsável por fornecer dependências de banco de dados para o FastAPI.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from shared.database.connection import async_session_factory

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency (Injeção de Dependência) criada para as rotas do FastAPI.
    
    1. Abre uma nova sessão assíncrona com o banco.
    2. Usando o comando `yield`, devolve a sessão para a rota rodar suas queries.
    3. Se a rota terminar com sucesso, faz o `commit` automaticamente para salvar!
    4. Se ocorrer qualquer erro (exception) na rota, faz o `rollback` antes de fechar.
       Assim, garante que o banco não receba dados quebrados ou pela metade.
    5. No final do bloco `async with`, a sessão é garantidamente fechada e
       devolvida para o connection pool (connection.py).
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
