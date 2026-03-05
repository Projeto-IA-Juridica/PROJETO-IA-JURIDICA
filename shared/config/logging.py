"""
shared/config/logging.py
=========================
Configuração centralizada de logging estruturado com structlog.

Comportamento por ambiente:
  - development → saída colorida e legível no terminal (ConsoleRenderer)
  - staging / production → saída JSON por linha, pronta para ingestão
    por ferramentas como Datadog, Loki, CloudWatch, etc.

Processadores aplicados em toda mensagem (ordem importa):
  1. merge_contextvars    — injeta contexto propagado via bind_contextvars
  2. add_log_level        — adiciona o campo "level"
  3. add_logger_name      — adiciona o campo "logger"
  4. CallsiteParameterAdder — adiciona "filename", "func_name", "lineno"
  5. TimeStamper          — adiciona "timestamp" ISO-8601 UTC
  6. StackInfoRenderer    — renderiza stack_info se presente
  7. UnicodeDecoder       — garante strings UTF-8
  8. ExceptionRenderer    — serializa exc_info nos dois ambientes
  9. _mask_sensitive      — mascara CPF, CNPJ, tokens e chaves de API
 10. Renderizador final   — JSONRenderer (prod) ou ConsoleRenderer (dev)

Uso básico:
    from shared.config.logging import get_logger

    logger = get_logger("feature_1.webhook")
    logger.info("mensagem_recebida", cliente_id=42, tipo="texto")

Binding de contexto de request (por ex. em um middleware):
    from structlog.contextvars import bind_contextvars, clear_contextvars

    clear_contextvars()
    bind_contextvars(
        request_id="uuid-aqui",
        escritorio_id=1,
        cliente_id=42,
    )
    # A partir daqui, qualquer log feito no mesmo async-context
    # vai incluir esses campos automaticamente.

Uso em testes:
    cache_logger_on_first_use=True faz o logger ignorar reconfigurações
    feitas após a primeira chamada. Em fixtures pytest, chame:

        import structlog
        structlog.reset_defaults()
        # reconfigure conforme necessário para capturar logs

    Para desabilitar a inicialização automática completamente (ex: em CI
    que já configura o logging externamente), defina:

        DISABLE_LOG_INIT=1
"""

import logging
import os
import re
import sys

import structlog
from structlog.contextvars import merge_contextvars

from shared.config.settings import settings

# ---------------------------------------------------------------------------
# Mascaramento de dados sensíveis (Sprint 2 — 3.6 production-readiness.md)
# ---------------------------------------------------------------------------

# Chaves cujo VALOR é sempre mascarado por completo, independente do formato.
# Cobre CPF/telefone sem formatação, senhas, tokens e chaves de API específicas do projeto.
_SENSITIVE_KEYS = frozenset(
    {
        # Identificadores pessoais (LGPD)
        "cpf",
        "cnpj",
        "telefone",
        "phone",
        # Credenciais de autenticação
        "password",
        "senha",
        "secret",
        # Tokens e chaves de API
        "token",
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        # Chaves de criptografia específicas do projeto
        "encryption_key",
        "jwt_secret_key",
        "fernet_key",
    }
)

# Padrões regex aplicados a valores de string em chaves NÃO sensíveis
# (ex: CPF/CNPJ que aparece interpolado dentro de uma mensagem de texto).
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}"), "***.***.***-**"),  # CPF formatado
    (
        re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"),
        "**.***.***/****-**",
    ),  # CNPJ formatado
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]+"), "sk-ant-***"),  # Anthropic key
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-***"),  # OpenAI key
    (re.compile(r"Bearer [A-Za-z0-9._\-]+"), "Bearer ***"),  # JWT header
]


def _apply_patterns(value: str) -> str:
    """Aplica todos os _PATTERNS de regex a uma string."""
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _mask_value(key: str, value: object) -> object:
    """
    Mascara um valor de log de forma recursiva:
    - Se a chave está em _SENSITIVE_KEYS → retorna "***" imediatamente.
    - Se o valor é string → aplica os _PATTERNS de regex.
    - Se o valor é dict → mascara recursivamente cada par chave/valor.
    - Se o valor é list → mascara recursivamente cada elemento.
    - Outros tipos (int, float, bool, None) → retorna sem alteração.
    """
    if key.lower() in _SENSITIVE_KEYS:
        return "***"
    if isinstance(value, str):
        return _apply_patterns(value)
    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(key, item) for item in value]
    return value


def _mask_sensitive(_logger: object, _method: str, event_dict: dict) -> dict:
    """
    Processador structlog que mascara dados sensíveis antes da renderização final.

    Duas camadas de proteção:
    1. Mascaramento por nome de chave (_SENSITIVE_KEYS): qualquer campo cujo nome
       seja "cpf", "telefone", "password", etc. tem o valor substituído por "***",
       independente do formato (cobre CPF sem formatação, telefones puros, etc.).
    2. Mascaramento por regex (_PATTERNS): para strings em campos genéricos que
       contenham CPF formatado, CNPJ, chaves de API ou tokens Bearer.

    Funciona recursivamente em dicts e listas aninhados.
    """
    for key in list(event_dict.keys()):
        event_dict[key] = _mask_value(key, event_dict[key])
    return event_dict


# ---------------------------------------------------------------------------
# Tradução do nível de log configurado em settings para o módulo logging
# ---------------------------------------------------------------------------

_NIVEL_LOG = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

# ---------------------------------------------------------------------------
# Processadores compartilhados (usados em dev e prod)
# ---------------------------------------------------------------------------

_PROCESSADORES_BASE: list = [
    merge_contextvars,  # propaga bind_contextvars
    structlog.stdlib.add_log_level,  # campo "level"
    structlog.stdlib.add_logger_name,  # campo "logger"
    structlog.processors.CallsiteParameterAdder(  # caller info
        [
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.LINENO,
        ]
    ),
    structlog.processors.TimeStamper(fmt="iso", utc=True),  # "timestamp" UTC ISO-8601
    structlog.processors.StackInfoRenderer(),  # stack_info opcional
    structlog.processors.UnicodeDecoder(),  # garante strings UTF-8
    structlog.processors.ExceptionRenderer(),  # serializa exc_info nos dois ambientes
    _mask_sensitive,  # mascara CPF, tokens, chaves de API
]

# ---------------------------------------------------------------------------
# Configuração por ambiente
# ---------------------------------------------------------------------------


def _configurar_development() -> None:
    """
    Saída amigável para terminal com cores.
    Facilita leitura durante o desenvolvimento local.
    """
    structlog.configure(
        processors=_PROCESSADORES_BASE
        + [
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_NIVEL_LOG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def _configurar_producao() -> None:
    """
    Saída JSON por linha (structured logging).
    Ideal para ingestão por agregadores de log (Datadog, Loki, etc.).
    """
    structlog.configure(
        processors=_PROCESSADORES_BASE
        + [
            structlog.processors.JSONRenderer(),  # linha JSON por evento
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_NIVEL_LOG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Inicialização — executada na importação do módulo
# ---------------------------------------------------------------------------


def _inicializar() -> None:
    # Silencia loggers muito verbosos de libs externas
    for nome in ("sqlalchemy.engine", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)

    # Configura o logging padrão do Python para nível correto
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=_NIVEL_LOG,
    )

    if settings.ENVIRONMENT == "development":
        _configurar_development()
    else:
        _configurar_producao()


if not os.getenv("DISABLE_LOG_INIT"):
    _inicializar()

# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def get_logger(nome_modulo: str) -> structlog.stdlib.BoundLogger:
    """
    Retorna um logger structlog configurado para o módulo informado.

    Exemplo:
        logger = get_logger("shared.database")
        logger.info("conexao_aberta", pool_size=20)
        logger.error("query_falhou", tabela="usuarios", erro=str(e))

    Campos de contexto injetados automaticamente via bind_contextvars:
        request_id, escritorio_id, cliente_id
    """
    return structlog.get_logger(nome_modulo)
