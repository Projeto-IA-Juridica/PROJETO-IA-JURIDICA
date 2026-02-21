"""
shared/tests/conftest.py
=========================
Configuração de ambiente para testes de shared/.

Define variáveis de ambiente FAKE antes de qualquer import de módulo,
evitando que Settings() falhe por campos obrigatórios ausentes.

⚠️  Os valores aqui são EXCLUSIVAMENTE para testes unitários.
    Nenhuma conexão real é feita — todas as dependências externas
    (banco, Redis, APIs) são mockadas nos próprios testes.
"""

import os

from cryptography.fernet import Fernet

# Chave Fernet válida gerada dinamicamente para testes.
# Fernet exige exatamente 32 bytes em URL-safe base64 (44 chars com padding).
# NÃO usar em produção — apenas para testes unitários.
_TEST_FERNET_KEY = Fernet.generate_key().decode()

# Define vars ANTES de qualquer import de módulo de aplicação.
# os.environ.setdefault preserva valores reais se já existirem (ex: CI com .env).
_FAKE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
    "OPENAI_API_KEY": "sk-test-openai-key",
    "EVOLUTION_API_URL": "http://localhost:8080",
    "EVOLUTION_API_KEY": "test-evolution-key",
    "JUSBRASIL_API_KEY": "test-jusbrasil-key",
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-unit-tests-only",
    "ENCRYPTION_KEY": _TEST_FERNET_KEY,  # chave Fernet real (32 bytes base64url)
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
}

for _key, _value in _FAKE_ENV.items():
    os.environ.setdefault(_key, _value)
