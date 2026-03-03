"""
shared/database/__init__.py
============================
Exporta os componentes principais do módulo de banco de dados.

Com isso, podemos importar apenas usando:
    from shared.database import get_db, engine
"""

from shared.database.connection import async_session_factory, engine
from shared.database.session import get_db

__all__ = [
    "engine",
    "async_session_factory",
    "get_db",
]
