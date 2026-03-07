"""
shared/security/jwt.py
=======================
Gerenciamento de tokens JWT usando python-jose.

Fornece funções para criação de Access Tokens, Refresh Tokens
e validação/decodificação para o sistema de autenticação.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from shared.config.settings import settings


def criar_token(user_id: int, escritorio_id: int, role: str) -> str:
    """
    Gera um *Access Token* JWT de curta duração.
    Payload contém:
    - sub (subject): user_id
    - escritorio_id: para Tenant isolation rápido sem query extra
    - role: para verificação de permissões rápida
    - exp: expiration time
    - iat: issued at time
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)

    payload = {
        "sub": str(user_id),
        "escritorio_id": escritorio_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    encoded_jwt = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def criar_refresh_token(user_id: int) -> str:
    """
    Gera um *Refresh Token* JWT de longa duração (ex: 7 dias).
    Usado quando o token principal expira.
    Contém menos dados no payload por segurança.
    """
    # 7 dias hardcoded para MVP, o ideal é vir de settings
    expire = datetime.now(UTC) + timedelta(days=7)

    payload = {
        "sub": str(user_id),
        "type": "refresh",  # Flag para identificar o tipo do token
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def validar_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida o JWT.

    Raises:
        ValueError: caso o token seja inválido, modificado ou expirado.
    Returns:
        Um dict com o payload decodificado.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        # Podemos criar custom exceptions depois, mas o ValueError basta no MVP
        raise ValueError(f"Token inválido ou expirado: {str(e)}") from e
