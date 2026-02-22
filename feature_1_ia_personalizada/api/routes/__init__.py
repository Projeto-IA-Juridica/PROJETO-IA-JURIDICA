"""
feature_1_ia_personalizada/api/routes/__init__.py
=================================================
Exporta de forma limpa todos os roteadores para que
sejam incluídos em `api/app.py`.
"""

from .auth import router as auth
from .health import router as health
from .processos import router as processos
from .chat import router as chat
from .webhook_whatsapp import router as webhook_whatsapp

__all__ = [
    "auth",
    "health",
    "processos",
    "chat",
    "webhook_whatsapp",
]
