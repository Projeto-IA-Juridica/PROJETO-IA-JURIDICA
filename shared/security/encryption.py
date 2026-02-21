"""
shared/security/encryption.py
==============================
Módulo de criptografia e hashing de senhas.

- Fernet (AES-256) para criptografia reversível de dados sensíveis (ex: CPF)
- Bcrypt para hash irreversível de senhas
- Funções utilitárias de mascaramento de dados
"""

import bcrypt
from cryptography.fernet import Fernet
from shared.config.settings import settings

# A chave Fernet deve ser uma string url-safe base64 de 32 bytes
# Gerada tipicamente com: Fernet.generate_key().decode()
_fernet = Fernet(settings.ENCRYPTION_KEY.encode('utf-8'))


def criptografar(texto: str) -> str:
    """
    Criptografa um texto (ex: CPF) de forma reversível.
    Útil para salvar dados sensíveis em repouso no banco.
    """
    if not texto:
        return texto
    return _fernet.encrypt(texto.encode('utf-8')).decode('utf-8')


def descriptografar(texto_cifrado: str) -> str:
    """
    Descriptografa um texto cifrado gerado por `criptografar()`.
    """
    if not texto_cifrado:
        return texto_cifrado
    return _fernet.decrypt(texto_cifrado.encode('utf-8')).decode('utf-8')


def hash_senha(senha_plana: str) -> str:
    """
    Gera um hash seguro da senha usando bcrypt.
    Este hash será salvo no banco. A senha plana NÃO deve ser salva.
    """
    salt = bcrypt.gensalt()
    # Em bcrypt, retornamos a string decodificada (que inclui o salt)
    return bcrypt.hashpw(senha_plana.encode('utf-8'), salt).decode('utf-8')


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    """
    Verifica se uma senha plana corresponde ao hash armazenado no banco.
    """
    return bcrypt.checkpw(
        senha_plana.encode('utf-8'), 
        senha_hash.encode('utf-8')
    )


def mascarar_cpf(cpf: str) -> str:
    """
    Mascaramento seguro de CPF genérico.
    Exemplo: 12345678901 -> ***.***.***-01
    Lida com CPFs com ou sem pontuação.
    """
    if not cpf:
        return cpf
    
    # Remove qualquer pontuação pro cálculo
    numeros = "".join(filter(str.isdigit, cpf))
    if len(numeros) == 11:
        # Últimos 2 dígitos reais
        return f"***.***.***-{numeros[-2:]}"
    return "***.***.***-XX"


def mascarar_telefone(tel: str) -> str:
    """
    Mascaramento seguro do telefone.
    Exemplo: 5511999999999 -> (**) *****-9999
    """
    if not tel:
        return tel
        
    numeros = "".join(filter(str.isdigit, tel))
    if len(numeros) >= 4:
        # Mostra apenas os últimos 4 dígitos
        return f"(**) *****-{numeros[-4:]}"
    return "(**) *****-XXXX"
