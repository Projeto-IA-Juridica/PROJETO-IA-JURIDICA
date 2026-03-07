"""
shared/security/permissions.py
===============================
Configuração de autorização, roles e permissionamento de rotas.
Fornece dependências (Dependencies) do FastAPI para injetar o usuário atual.
"""

from enum import StrEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_db
from shared.models.usuario import Usuario
from shared.security.jwt import validar_token

# O token url path que o Swagger UI passará para login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


class Role(StrEnum):
    """
    Perfis de usuário do sistema.
    """

    ADMIN = "admin"
    ADVOGADO = "advogado"
    ASSISTENTE = "assistente"
    ESTAGIARIO = "estagiario"


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> Usuario:
    """
    Dependency do FastAPI responsável por:
    1. Ler o token Bearer do Header de Authorization
    2. Validar a assinatura e validade do token
    3. Buscar o usuário completo no bando de dados (garante que não está desativado)
    4. Retornar este usuário para a Rota
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = validar_token(token)
        user_id_str_raw = payload.get("sub")
        if user_id_str_raw is None:
            raise ValueError("Token não contém ID do usuário")
        user_id_str: str = str(user_id_str_raw)
        user_id = int(user_id_str)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Buscando o usuário no DB para revalidação de status
    stmt = select(Usuario).where(Usuario.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário associado ao token não encontrado",
        )

    if not user.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo. Contate o administrador.",
        )

    return user


def require_role(roles_permitidas: list[Role]):
    """
    Decorator / Dependency provider para FastAPI.
    Filtra o acesso à rota apenas para usuários que tenham uma das roles permitidas.

    Exemplo de uso na Rota:
    @app.delete("/processos/{id}")
    async def deletar(user=Depends(require_role([Role.ADMIN]))):
        ...
    """

    async def role_checker(
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        # Uma conversão segura entre Enum e Str
        roles_str = [r.value for r in roles_permitidas]

        if current_user.role not in roles_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operação não permitida para o perfil: {current_user.role}",
            )
        return current_user

    return role_checker


def check_tenant(user: Usuario, resource_escritorio_id: int) -> None:
    """
    Função utilitária (não-dependency) para verificar o Multi-tenanting.
    Assegura que qualquer id de recurso retornado pelo banco
    esteja atrelado ao mesmo escritório do usuário autenticado.
    """
    if user.escritorio_id != resource_escritorio_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: Recurso pertence a outro tenant.",
        )
