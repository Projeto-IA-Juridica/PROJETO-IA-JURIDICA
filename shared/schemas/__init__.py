"""
shared/schemas/__init__.py
===========================
Exporta todos os schemas Pydantic do projeto.

Uso:
    from shared.schemas import (
        EscritorioCreate, EscritorioResponse, EscritorioList,
        ClienteCreate, ClienteResponse, ClienteAceiteLGPD,
        ProcessoCreate, ProcessoResponse, ProcessoComAndamentos, AndamentoSchema,
        UsuarioCreate, UsuarioLogin, UsuarioResponse, TokenResponse,
        SuccessResponse, ErrorResponse, PaginatedResponse,
    )
"""

from shared.schemas.cliente import (
    ClienteAceiteLGPD,
    ClienteCreate,
    ClienteList,
    ClienteResponse,
    ClienteUpdate,
)
from shared.schemas.prospeccao import (
    LeadProspeccaoResponse,
    DescobertaRequest,
    LeadStatusUpdate,
    PipelineResponse,
    DNAEscritorioResponse,
)
from shared.schemas.escritorio import (
    EscritorioCreate,
    EscritorioList,
    EscritorioResponse,
    EscritorioUpdate,
)
from shared.schemas.processo import (
    AndamentoSchema,
    ProcessoComAndamentos,
    ProcessoCreate,
    ProcessoList,
    ProcessoResponse,
    ProcessoUpdate,
)
from shared.schemas.response import ErrorResponse, PaginatedResponse, SuccessResponse
from shared.schemas.usuario import (
    TokenResponse,
    UsuarioCreate,
    UsuarioLogin,
    UsuarioResponse,
)

__all__ = [
    # Escritório
    "EscritorioCreate",
    "EscritorioUpdate",
    "EscritorioResponse",
    "EscritorioList",
    # Cliente
    "ClienteCreate",
    "ClienteUpdate",
    "ClienteResponse",
    "ClienteAceiteLGPD",
    "ClienteList",
    # Processo
    "AndamentoSchema",
    "ProcessoCreate",
    "ProcessoUpdate",
    "ProcessoResponse",
    "ProcessoComAndamentos",
    "ProcessoList",
    # Usuário / Auth
    "UsuarioCreate",
    "UsuarioLogin",
    "UsuarioResponse",
    "TokenResponse",
    # Genéricos
    "SuccessResponse",
    "ErrorResponse",
    "PaginatedResponse",
]
