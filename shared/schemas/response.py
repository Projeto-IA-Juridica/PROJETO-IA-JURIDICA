"""
shared/schemas/response.py
===========================
Schemas genéricos de resposta da API.

Usados em todos os endpoints para padronizar o formato de retorno:
- SuccessResponse  → operações que retornam um único recurso
- ErrorResponse    → erros da API
- PaginatedResponse → listagens com paginação
"""

import math
from typing import Any, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class SuccessResponse(BaseModel):
    """Resposta de sucesso para operações simples (create, update, delete)."""

    success: bool = True
    message: str
    data: Any = None


class ErrorResponse(BaseModel):
    """Resposta de erro padronizada."""

    success: bool = False
    error: str = Field(description="Mensagem de erro curta (código ou tipo)")
    detail: str | None = Field(default=None, description="Detalhes adicionais do erro")


class PaginatedResponse[T](BaseModel):
    """
    Resposta paginada genérica.

    `pages` é um computed_field — sempre derivado de `total` e `per_page`,
    nunca pode ficar inconsistente.

    Exemplo de uso:
        PaginatedResponse[EscritorioResponse](
            items=[...],
            total=42,
            page=1,
            per_page=20,
        )
    """

    items: list[T]
    total: int = Field(
        ge=0, description="Total de registros encontrados (sem paginação)"
    )
    page: int = Field(ge=1, description="Página atual (começa em 1)")
    per_page: int = Field(ge=1, le=100, description="Itens por página")

    @computed_field  # type: ignore[misc]
    @property
    def pages(self) -> int:
        """Total de páginas — calculado automaticamente."""
        return math.ceil(self.total / self.per_page) if self.per_page > 0 else 0
