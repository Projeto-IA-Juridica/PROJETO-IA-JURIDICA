"""
shared/security/jwt.py
=======================
Gerenciamento de tokens JWT usando python-jose.

Fornece funções para criação de Access Tokens, Refresh Tokens,
validação/decodificação e revogação via blacklist no Redis.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import redis as redis_sync
from jose import JWTError, jwt

from shared.config.settings import settings

# Cliente Redis síncrono para operações de blacklist (rota /logout é async,
# mas a verificação no middleware precisa de acesso rápido).
_redis_blacklist: redis_sync.Redis | None = None


def _get_redis() -> redis_sync.Redis:
    global _redis_blacklist
    if _redis_blacklist is None:
        _redis_blacklist = redis_sync.from_url(
            settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2
        )
    return _redis_blacklist


_BLACKLIST_PREFIX = "jwt:blacklist:"


def revogar_token(token: str) -> None:
    """
    Adiciona o token na blacklist do Redis com TTL igual ao tempo restante
    de expiração. Após o TTL, o token já teria expirado naturalmente.
    Falhas silenciosas — log deve ser feito pelo chamador.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        exp = payload.get("exp")
        ttl = max(1, int(exp - datetime.now(UTC).timestamp())) if exp else 3600
        _get_redis().setex(f"{_BLACKLIST_PREFIX}{token}", ttl, "1")
    except Exception:
        pass


def token_esta_revogado(token: str) -> bool:
    """Retorna True se o token foi explicitamente revogado (logout)."""
    try:
        return bool(_get_redis().exists(f"{_BLACKLIST_PREFIX}{token}"))
    except Exception:
        # Redis indisponível: falha aberta (não bloqueia o usuário)
        return False


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
    return encoded_jwt  # type: ignore[no-any-return]


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
    return encoded_jwt  # type: ignore[no-any-return]


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
        return payload  # type: ignore[no-any-return]
    except JWTError as e:
        # Podemos criar custom exceptions depois, mas o ValueError basta no MVP
        raise ValueError(f"Token inválido ou expirado: {str(e)}") from e
