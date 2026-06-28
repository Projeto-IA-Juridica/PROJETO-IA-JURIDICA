"""
shared/models/__init__.py
==========================
Exporta todos os models SQLAlchemy do projeto.

Importar a partir daqui garante que o Alembic detecte
todas as tabelas ao gerar migrations automáticas.

Uso:
    from shared.models import Base, Escritorio, Cliente, Processo, Usuario, Interacao
"""

from shared.models.base import Base, TenantMixin, TimestampMixin
from shared.models.cliente import Cliente
from shared.models.documento_cliente import DocumentoCliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.lead_prospeccao import LeadProspeccao
from shared.models.mensagem_agendada import MensagemAgendada
from shared.models.processo import Processo
from shared.models.sessao_advogado import SessaoAdvogado
from shared.models.usuario import Usuario

__all__ = [
    # Base e Mixins
    "Base",
    "TimestampMixin",
    "TenantMixin",
    # Models
    "Escritorio",
    "Usuario",
    "Cliente",
    "Processo",
    "Interacao",
    "LeadProspeccao",
    "MensagemAgendada",
    "SessaoAdvogado",
    "DocumentoCliente",
]
