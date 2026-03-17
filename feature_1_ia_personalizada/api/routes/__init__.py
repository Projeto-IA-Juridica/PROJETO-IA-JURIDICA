"""
feature_1_ia_personalizada/api/routes/__init__.py
=================================================
Exporta de forma limpa todos os roteadores para que
sejam incluídos em `api/app.py`.
"""

from .admin_import import router as admin_import
from .auth import router as auth
from .chat import router as chat
from .health import router as health
from .metrics import router as metrics
from .processos import router as processos
from .rag import router as rag
from .webhook_whatsapp import router as webhook_whatsapp

__all__ = [
    "admin_import",
    "auth",
    "health",
    "metrics",
    "processos",
    "chat",
    "rag",
    "webhook_whatsapp",
]
