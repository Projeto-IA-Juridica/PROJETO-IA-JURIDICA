"""
shared/security/__init__.py
============================
Exporta as funções principais do módulo de segurança.
"""

from shared.security.encryption import (
    criptografar,
    descriptografar,
    hash_senha,
    verificar_senha,
    mascarar_cpf,
    mascarar_telefone,
)
from shared.security.jwt import criar_token, criar_refresh_token, validar_token
from shared.security.permissions import Role, get_current_user, require_role, check_tenant

__all__ = [
    # Encryption
    "criptografar",
    "descriptografar",
    "hash_senha",
    "verificar_senha",
    "mascarar_cpf",
    "mascarar_telefone",
    
    # JWT
    "criar_token",
    "criar_refresh_token",
    "validar_token",
    
    # Permissions
    "Role",
    "get_current_user",
    "require_role",
    "check_tenant",
]
