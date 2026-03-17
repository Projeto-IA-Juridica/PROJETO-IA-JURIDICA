# shared/config/constants.py
from __future__ import annotations

import re
from typing import Final

# 1) Texto do disclaimer (OAB / jurídico)
# reformular essas mensagens
DISCLAIMER_OAB: Final[str] = (
    "Aviso: Sou uma IA e não substituo um(a) advogado(a). "
    "Posso ajudar com informações gerais e organização de ideias, "
    "mas não ofereço consultoria jurídica personalizada, estratégia processual "
    "ou previsões de resultado. Para decisões relevantes, procure um profissional habilitado."
)


# 2) Regras de comportamento (permitido / proibido)

PODE_FAZER: Final[list[str]] = [
    "Explicar conceitos jurídicos de forma geral",
    "Resumir textos e documentos fornecidos pelo usuário",
    "Gerar modelos (petições simples, e-mails, notificações) como rascunho",
    "Sugerir checklists e próximos passos administrativos",
    "Organizar fatos em linha do tempo e tópicos",
    "Apontar dúvidas para levar a um(a) advogado(a)",
]

NAO_PODE_FAZER: Final[list[str]] = [
    "Dar parecer jurídico definitivo",
    "Prever resultado de processo, sentença, recurso ou estratégia vencedora",
    "Indicar manobras para burlar regras, ocultar provas ou enganar terceiros",
    "Assinar como advogado(a) ou se passar por profissional habilitado",
]


# 3) Parâmetros de IA

MAX_TOKENS_RESPOSTA: Final[int] = 1024
TEMPERATURA_CLAUDE: Final[float] = 0.3
MODELO_CLAUDE: Final[str] = "claude-sonnet-4-20250514"


# 4) Cache e retenção

CACHE_TTL_PROCESSO: Final[int] = 3600  # 1 hora
CACHE_TTL_ANDAMENTO: Final[int] = 1800  # 30 min

RETENCAO_DADOS_ANOS: Final[int] = 5
RETENCAO_LOGS_MESES: Final[int] = 6

# 5) Regex CNJ (número do processo)
# CNJ: 0000000-00.0000.0.00.0000

FORMATO_NUMERO_PROCESSO: Final[str] = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
REGEX_NUMERO_PROCESSO: Final[re.Pattern[str]] = re.compile(FORMATO_NUMERO_PROCESSO)

# 6) RAG — parâmetros de busca vetorial

RAG_MAX_FILE_SIZE_MB: Final[int] = 50                             # limite de upload
RAG_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({"pdf", "docx", "txt"})

RAG_MIN_SIMILARITY: Final[float] = 0.75   # threshold mínimo de similaridade coseno (0-1)
# Distância coseno equivalente: 1 - RAG_MIN_SIMILARITY = 0.25
# Chunks com distância > 0.25 são descartados como irrelevantes.

RAG_TOP_K_CANDIDATOS: Final[int] = 10     # candidatos buscados antes do re-ranking
RAG_TOP_K_FINAL: Final[int] = 3           # chunks selecionados após re-ranking MMR

# 7) Mensagens de fallback (quando o provedor estiver indisponível)

MENSAGENS_FALLBACK: Final[dict[str, str]] = {
    "indisponivel": (
        "No momento o serviço de IA está temporariamente indisponível. "
        "Posso continuar te ajudando com um resumo do que você enviou, checklist, "
        "organização dos fatos e um rascunho de texto."
    ),
    "timeout": (
        "Demorou mais do que o esperado para responder. "
        "Se você quiser, posso tentar novamente ou trabalhar com um resumo do seu pedido."
    ),
    "erro_generico": (
        "Tive um erro ao processar sua solicitação. "
        "Você pode reenviar a última mensagem ou colar o trecho do documento aqui?"
    ),
}
