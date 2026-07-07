"""
Extração de prazos processuais a partir dos andamentos persistidos.

O sistema não possui tabela dedicada de prazos: os andamentos vivem em
`Processo.estado_atual["ultimos_andamentos"]` (list[str]) e no cache
`Processo.ultimo_andamento`. Este módulo varre esses textos procurando
menções a prazo com data ("prazo ... 10/07", "contestação até 15/08/2026")
e devolve pares (data, descrição) para:

  - o AgendamentoDetector evitar sugerir slots no dia (ou véspera) de prazo;
  - o card de aprovação do Hub e a notificação WhatsApp alertarem o advogado;
  - a aba Agenda exibir a linha vermelha de prazos da semana.

Extração best-effort: texto sem data reconhecível é ignorado silenciosamente.
Conflito de prazo NUNCA bloqueia — apenas gera aviso (regra de negócio).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.processo import Processo

# Frase contendo "prazo" (ou construções "até DD/MM" comuns em intimações)
_RE_PRAZO = re.compile(
    r"\bprazos?\b|\bcontesta[çc][aã]o\b|\bintima[çc][aã]o\b"
    r"|\bmanifesta[çc][aã]o\b|\bembargos\b|\bvenc(?:e|imento)\b",
    re.IGNORECASE,
)
_RE_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")

# Prazo relativo: "prazo de 15 dias", "no prazo de 15 (quinze) dias úteis",
# "prazo: 5 dias corridos". CPC art. 219: prazos processuais contam em dias
# ÚTEIS por padrão; "corridos" só quando explícito.
_RE_PRAZO_RELATIVO = re.compile(
    r"\bprazos?\s*(?:de|:|em)?\s*(\d{1,3})\s*(?:\([^)]{1,30}\))?\s*dias?"
    r"(\s*[úu]teis|\s*corridos)?\b",
    re.IGNORECASE,
)
_MAX_DIAS_RELATIVO = 120

# Janela de sanidade: datas fora de [hoje-30, hoje+365] são descartadas
_JANELA_PASSADO_DIAS = 30
_JANELA_FUTURO_DIAS = 365

_MAX_DESCRICAO = 160


@dataclass(frozen=True)
class PrazoDetectado:
    data: date
    descricao: str
    processo_id: int
    cliente_id: int
    numero_cnj: str | None
    # True quando a data foi CALCULADA a partir de um prazo relativo
    # ("15 dias a contar da intimação") — exibida como aproximação (≈)
    estimado: bool = False


def _resolver_ano(dia: int, mes: int, ano_raw: str | None, hoje: date) -> date | None:
    """Monta a data; sem ano explícito, escolhe o ano que a coloca na janela válida."""
    try:
        if ano_raw:
            ano = int(ano_raw)
            if ano < 100:
                ano += 2000
            return date(ano, mes, dia)
        candidata = date(hoje.year, mes, dia)
        if candidata < hoje - timedelta(days=_JANELA_PASSADO_DIAS):
            candidata = date(hoje.year + 1, mes, dia)
        return candidata
    except ValueError:
        return None


def extrair_prazos_do_texto(texto: str, hoje: date) -> list[tuple[date, str]]:
    """Retorna [(data, trecho)] para cada data válida em texto que menciona prazo."""
    if not texto or not _RE_PRAZO.search(texto):
        return []

    resultados: list[tuple[date, str]] = []
    for m in _RE_DATA.finditer(texto):
        dia, mes, ano_raw = int(m.group(1)), int(m.group(2)), m.group(3)
        data_prazo = _resolver_ano(dia, mes, ano_raw, hoje)
        if data_prazo is None:
            continue
        if not (
            hoje - timedelta(days=_JANELA_PASSADO_DIAS)
            <= data_prazo
            <= hoje + timedelta(days=_JANELA_FUTURO_DIAS)
        ):
            continue
        descricao = texto.strip()
        if len(descricao) > _MAX_DESCRICAO:
            descricao = descricao[: _MAX_DESCRICAO - 1] + "…"
        resultados.append((data_prazo, descricao))
    return resultados


def _somar_dias_uteis(base: date, n: int) -> date:
    """Avança n dias úteis (seg–sex) a partir de base — CPC art. 219.

    Aproximação: feriados não são considerados (não há calendário forense
    no sistema); o resultado é marcado como estimado."""
    atual = base
    restantes = n
    while restantes > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            restantes -= 1
    return atual


def extrair_prazos_relativos(texto: str, base: date | None, hoje: date) -> list[tuple[date, str]]:
    """
    Detecta prazos SEM data explícita ("prazo de 15 dias") e calcula a data
    a partir da âncora fornecida (data do andamento). Sem âncora confiável,
    não arrisca — retorna vazio (precisão > recall aqui: uma data errada no
    detector de conflitos é pior que nenhuma).
    """
    if not texto:
        return []

    # Se o próprio texto traz uma data explícita, ela serve de âncora
    # ("Intimação em 01/07 — prazo de 15 dias"); senão usa a data do andamento.
    m_data = _RE_DATA.search(texto)
    if m_data:
        ancora = _resolver_ano(int(m_data.group(1)), int(m_data.group(2)), m_data.group(3), hoje)
        # datas futuras não são âncora de contagem — já são o prazo em si
        if ancora is not None and ancora > hoje:
            ancora = base
    else:
        ancora = base
    if ancora is None:
        return []

    resultados: list[tuple[date, str]] = []
    for m in _RE_PRAZO_RELATIVO.finditer(texto):
        n_dias = int(m.group(1))
        if not (0 < n_dias <= _MAX_DIAS_RELATIVO):
            continue
        qualificador = (m.group(2) or "").strip().lower()
        if qualificador == "corridos":
            data_prazo = ancora + timedelta(days=n_dias)
        else:
            # padrão CPC: dias úteis
            data_prazo = _somar_dias_uteis(ancora, n_dias)
        if not (
            hoje - timedelta(days=_JANELA_PASSADO_DIAS)
            <= data_prazo
            <= hoje + timedelta(days=_JANELA_FUTURO_DIAS)
        ):
            continue
        descricao = texto.strip()
        if len(descricao) > _MAX_DESCRICAO:
            descricao = descricao[: _MAX_DESCRICAO - 1] + "…"
        resultados.append((data_prazo, descricao))
    return resultados


def _textos_do_processo(processo: Processo) -> list[tuple[str, date | None]]:
    """
    Retorna [(texto, data_base)] — data_base é a âncora para prazos relativos.
    Só o último andamento tem data confiável (data_ultimo_andamento); os
    demais itens do histórico ficam sem âncora (prazo relativo é ignorado).
    """
    ultimo = processo.ultimo_andamento
    data_base = processo.data_ultimo_andamento.date() if processo.data_ultimo_andamento else None

    textos: list[tuple[str, date | None]] = []
    estado: dict[str, Any] | None = processo.estado_atual
    if isinstance(estado, dict):
        for item in estado.get("ultimos_andamentos", []) or []:
            if isinstance(item, str):
                textos.append((item, data_base if item == ultimo else None))
    if ultimo and all(t != ultimo for t, _ in textos):
        textos.append((ultimo, data_base))
    return textos


async def buscar_prazos_escritorio(
    db: AsyncSession,
    escritorio_id: int,
    cliente_id: int | None = None,
    hoje: date | None = None,
) -> list[PrazoDetectado]:
    """
    Varre os processos ativos do escritório (ou de um cliente específico)
    e retorna os prazos detectados, deduplicados por (processo, data).
    """
    hoje = hoje or datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    stmt = select(Processo).where(
        Processo.escritorio_id == escritorio_id,
        Processo.status == "ativo",
    )
    if cliente_id is not None:
        stmt = stmt.where(Processo.cliente_id == cliente_id)

    processos = (await db.execute(stmt)).scalars().all()

    vistos: set[tuple[int, date]] = set()
    prazos: list[PrazoDetectado] = []

    def _adicionar(proc: Processo, data_prazo: date, descricao: str, estimado: bool) -> None:
        chave = (proc.id, data_prazo)
        if chave in vistos:
            return
        vistos.add(chave)
        prazos.append(
            PrazoDetectado(
                data=data_prazo,
                descricao=descricao,
                processo_id=proc.id,
                cliente_id=proc.cliente_id,
                numero_cnj=proc.numero_cnj,
                estimado=estimado,
            )
        )

    for proc in processos:
        for texto, data_base in _textos_do_processo(proc):
            # Data explícita no texto ("prazo até 10/07") — precisão máxima
            explicitos = extrair_prazos_do_texto(texto, hoje)
            for data_prazo, descricao in explicitos:
                _adicionar(proc, data_prazo, descricao, estimado=False)
            # Prazo relativo ("prazo de 15 dias") — calculado da âncora;
            # só quando o texto não tinha data futura explícita
            if not explicitos:
                for data_prazo, descricao in extrair_prazos_relativos(texto, data_base, hoje):
                    _adicionar(proc, data_prazo, descricao, estimado=True)

    prazos.sort(key=lambda p: p.data)
    return prazos


def datas_a_evitar(prazos: list[PrazoDetectado]) -> set[date]:
    """Dia do prazo E o dia anterior (regra: reunião na véspera pressiona o advogado)."""
    datas: set[date] = set()
    for p in prazos:
        datas.add(p.data)
        datas.add(p.data - timedelta(days=1))
    return datas


def descrever_conflito(data_local: date, prazos: list[PrazoDetectado]) -> str | None:
    """Retorna a descrição do prazo que conflita com a data (dia ou véspera), se houver."""
    for p in prazos:
        if data_local in (p.data, p.data - timedelta(days=1)):
            cnj = f" (proc. {p.numero_cnj})" if p.numero_cnj else ""
            aprox = "≈ " if p.estimado else ""
            return f"Prazo processual {aprox}em {p.data.strftime('%d/%m')}{cnj}: {p.descricao}"
    return None
