# shared/config/constants.py
from __future__ import annotations

import re
from typing import Final

# 1) Texto do disclaimer (OAB / jurídico)
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
MODELO_CLAUDE: Final[str] = "claude-sonnet-5"


# 4) Cache e retenção

CACHE_TTL_PROCESSO: Final[int] = 3600  # 1 hora
CACHE_TTL_ANDAMENTO: Final[int] = 1800  # 30 min

RETENCAO_DADOS_ANOS: Final[int] = 5
RETENCAO_LOGS_MESES: Final[int] = 6

# 5) Regex CNJ (número do processo)

FORMATO_NUMERO_PROCESSO: Final[str] = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
REGEX_NUMERO_PROCESSO: Final[re.Pattern[str]] = re.compile(FORMATO_NUMERO_PROCESSO)

# 6) RAG — parâmetros de busca vetorial

RAG_MAX_FILE_SIZE_MB: Final[int] = 50
RAG_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({"pdf", "docx", "txt"})

RAG_MIN_SIMILARITY: Final[float] = 0.35
RAG_TOP_K_CANDIDATOS: Final[int] = 10
RAG_TOP_K_FINAL: Final[int] = 3

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


# ---------------------------------------------------------------------------
# 8) Score de Risco Processual (Feature 2)
# ---------------------------------------------------------------------------
# Usado por ScoreRiscoCalculator em vitoria_preditor.py.
# NÃO representa probabilidade de vitória — compliance OAB Provimento 205/2021.
# ---------------------------------------------------------------------------

# Pesos da média ponderada (devem somar 1.0)
SCORE_RISCO_PESOS: Final[dict[str, float]] = {
    "complexidade_juridica": 0.25,
    "duracao_estimada": 0.25,
    "historico_vara": 0.20,
    "valor_causa": 0.15,
    "fase_processual": 0.15,
}

# Complexidade intrínseca por tipo de ação (0–100)
# Chaves em minúsculo — correspondem ao campo tipo_acao do modelo Processo
SCORE_RISCO_COMPLEXIDADE_POR_TIPO: Final[dict[str, int]] = {
    "indenização por dano moral": 35,
    "indenização por dano material": 35,
    "ação de cobrança": 30,
    "ação monitória": 30,
    "execução de título extrajudicial": 40,
    "ação trabalhista": 40,
    "reclamação trabalhista": 40,
    "dissídio coletivo": 65,
    "ação civil pública trabalhista": 65,
    "ação de obrigação de fazer": 45,
    "ação de obrigação de não fazer": 45,
    "ação contratual": 45,
    "divórcio litigioso": 35,
    "divórcio consensual": 20,
    "guarda de filhos": 55,
    "alimentos": 45,
    "benefício previdenciário": 50,
    "aposentadoria por invalidez": 50,
    "mandado de segurança": 55,
    "ação popular": 60,
    "ação de improbidade administrativa": 75,
    "execução fiscal": 50,
    "ação anulatória tributária": 70,
    "embargos à execução fiscal": 60,
    "ação penal pública": 60,
    "habeas corpus": 50,
    "ação ambiental": 75,
    "ação de desapropriação": 65,
}

# Risco de incerteza por fase processual (0–100)
# Quanto mais avançado o processo, menor a incerteza operacional
SCORE_RISCO_POR_FASE: Final[dict[str, int]] = {
    "conhecimento": 80,
    "instrucao": 65,
    "saneamento": 55,
    "julgamento": 45,
    "recurso": 60,  # recurso eleva incerteza novamente
    "execucao": 25,
    "encerrado": 0,
}

# Prazo máximo de referência para normalização do componente duração (dias)
# Equivale ao percentil ~95 do DataJud para processos de 1º grau
SCORE_RISCO_PRAZO_MAX_REFERENCIA: Final[int] = 2_000

# Salário-mínimo de referência para faixas de valor da causa
# Atualizar a cada reajuste do SM
SCORE_RISCO_SALARIO_MINIMO_REF: Final[float] = 1_518.00


# ---------------------------------------------------------------------------
# 9) Score CRM (Feature 7)
# ---------------------------------------------------------------------------
# Usado por CRMScoreCalculator em score_calculator.py.
# NÃO representa probabilidade de satisfação futura — é um indicador operacional.
# Os pesos devem somar 1.0.
# ---------------------------------------------------------------------------

CRM_SCORE_PESOS: Final[dict[str, float]] = {
    "nps": 0.40,  # satisfação direta do cliente
    "contato": 0.25,  # frequência de relacionamento
    "engajamento": 0.15,  # volume de interações com a IA
    "escalacoes": 0.20,  # reclamações e escalações abertas
}

# Pontuação por nota NPS (1–5); None → 40pts (sem dados = neutro)
CRM_NPS_PONTOS: Final[dict[int, int]] = {5: 100, 4: 80, 3: 50, 2: 20, 1: 0}
CRM_NPS_PONTOS_NULO: Final[int] = 40

# Pontuação por dias sem contato
CRM_CONTATO_PONTOS: Final[list[tuple[int, int]]] = [
    (7, 100),  # 0–7 dias
    (30, 70),  # 8–30 dias
    (60, 30),  # 31–60 dias
    (9999, 0),  # > 60 dias
]

# Pontuação por interações nos últimos 30 dias.
# Semântica: se total_30d > limite → pontos. Iterar em ordem decrescente de limite.
# >10 → 100pts | 5–10 → 70pts | 1–4 → 40pts | 0 → 0pts
CRM_ENGAJAMENTO_PONTOS: Final[list[tuple[int, int]]] = [
    (10, 100),  # > 10 interações/mês
    (4, 70),  # > 4 (ou seja, 5–10)
    (0, 40),  # > 0 (ou seja, 1–4)
]

# Mapeamento score → nível CRM
CRM_NIVEL_FAIXAS: Final[list[tuple[int, str]]] = [
    (76, "excelente"),
    (51, "satisfeito"),
    (26, "neutro"),
    (11, "em_risco"),
    (0, "critico"),
]
