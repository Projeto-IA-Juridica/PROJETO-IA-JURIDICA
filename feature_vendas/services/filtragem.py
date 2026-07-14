"""
Filtragem ICP (etapa 2 do playbook): quem merece os 15 minutos de abordagem.

Score puro, sem LLM — critérios objetivos da planilha. Classe C não é abordado;
desqualificados nem entram na fila de enriquecimento (não gastam busca de
processo nem token).
"""

from __future__ import annotations

from dataclasses import dataclass

_AREAS_ALVO = {
    "cível",
    "civel",
    "trabalhista",
    "previdenciário",
    "previdenciario",
    "família",
    "familia",
}

# Sinais de desqualificação (etapa 2): nem pontuar.
_AREAS_FORA = {"bancário massa", "telefonia massa", "recuperação judicial"}


@dataclass(frozen=True)
class ResultadoFiltragem:
    score: int
    classe: str  # "A" | "B" | "C"
    desqualificado: bool
    motivo: str


def pontuar(
    *,
    num_advogados: int | None,
    area: str | None,
    tem_vaga_aberta: bool = False,
    anuncia_online: bool = False,
    instagram_ativo: bool = False,
    whatsapp_publicado: bool = False,
) -> ResultadoFiltragem:
    area_norm = (area or "").strip().lower()

    if area_norm in _AREAS_FORA:
        return ResultadoFiltragem(0, "C", True, f"área fora do escopo: {area}")
    if num_advogados is not None and num_advogados < 1:
        return ResultadoFiltragem(0, "C", True, "sem advogado ativo")

    score = 0
    if num_advogados is not None:
        if 5 <= num_advogados <= 15:
            score += 3
        elif 2 <= num_advogados <= 4:
            score += 2
    if area_norm in _AREAS_ALVO:
        score += 2
    if tem_vaga_aberta:
        score += 3
    if anuncia_online:
        score += 3
    if instagram_ativo:
        score += 1
    if whatsapp_publicado:
        score += 1

    if score >= 6:
        classe = "A"
    elif score >= 3:
        classe = "B"
    else:
        classe = "C"

    return ResultadoFiltragem(score, classe, False, "")
