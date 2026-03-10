from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from prometheus_client import Counter

_fact_check_corrections_total = Counter(
    "fact_check_corrections_total",
    "Total de correções aplicadas pelo FactChecker (status, prazo ou linguagem)",
)

# Tipos auxiliares
BuscarDadosProcessoFn = Callable[[str], Awaitable[dict[str, Any]]]
UtcNowFn = Callable[[], datetime]


class FactChecker:
    """
    FactChecker:
      - Confere afirmações da IA com dados reais do processo (via "buscar_dados_processo")
      - Valida plausibilidade de prazos
      - Filtra linguagem que soe como parecer jurídico/promessa
      - Se houver correção, LOGA em interacao.metadata_json
    """

    def __init__(
        self,
        buscar_dados_processo: BuscarDadosProcessoFn,
        utcnow: UtcNowFn | None = None,
    ) -> None:
        self._buscar_dados_processo = buscar_dados_processo
        self._utcnow = utcnow or datetime.utcnow

        # Frases/padrões que soam como parecer jurídico ou promessa de resultado
        self._padroes_proibidos: list[re.Pattern] = [
            re.compile(r"\bvocê deve\b", re.IGNORECASE),
            re.compile(r"\brecomendo que\b", re.IGNORECASE),
            re.compile(r"\ba estratégia é\b", re.IGNORECASE),
            re.compile(r"\bvocê vai ganhar\b", re.IGNORECASE),
            # Guards específicos para EstatisticaProcessual:
            # Impedem que Claude converta dados históricos em predição individual.
            re.compile(r"\bvocê tem\s+\d+\s*%", re.IGNORECASE),           # "você tem 72%..."
            re.compile(r"\bseu processo tem\s+\d+\s*%", re.IGNORECASE),   # "seu processo tem 80%..."
            re.compile(r"\bsua probabilidade\b", re.IGNORECASE),           # "sua probabilidade é de..."
            re.compile(r"\b\d+\s*%\s*de\s*chance\s*de\s*(ganhar|vencer|procedência)\b", re.IGNORECASE),  # "80% de chance de ganhar"
            re.compile(r"\bchance de (ganhar|vencer|procedência)\b", re.IGNORECASE),  # "chance de ganhar"
        ]

        # Disclaimer — aparece apenas quando um padrão proibido é corrigido
        self._disclaimer = (
            "Qualquer dúvida sobre os próximos passos, fale com seu advogado(a). 😊"
        )

    # 1) Status do processo

    async def verificar_status_processo(
        self,
        processo_id: str,
        afirmacao_ia: str,
        interacao: Any,
    ) -> dict[str, Any]:
        """
        Compara o que a IA disse com dados reais do processo.

        Retorna:
          {
            "verificado": bool,
            "correcoes": list[str],
            "dados_reais_resumo": dict
          }

        Também: se houver divergência, registra em interacao.metadata_json.
        """
        dados_reais = await self._buscar_dados_processo(processo_id)

        numero_cnj = (dados_reais.get("numero_cnj") or "").strip()
        tribunal = (dados_reais.get("tribunal") or "").strip()
        ultimo_andamento = (dados_reais.get("ultimo_andamento") or "").strip()

        correcoes: list[str] = []

        # Checagens simples por presença textual (você pode sofisticar depois)
        if numero_cnj and numero_cnj not in afirmacao_ia:
            correcoes.append("Número CNJ não confere com o cadastro do processo.")
        if tribunal and tribunal not in afirmacao_ia:
            correcoes.append(
                "Tribunal mencionado não confere com o cadastro do processo."
            )
        if ultimo_andamento and ultimo_andamento not in afirmacao_ia:
            correcoes.append(
                "Último andamento mencionado não confere com o cadastro do processo."
            )

        resultado = {
            "verificado": len(correcoes) == 0,
            "correcoes": correcoes,
            "dados_reais_resumo": {
                "numero_cnj": numero_cnj or None,
                "tribunal": tribunal or None,
                "ultimo_andamento": ultimo_andamento or None,
            },
        }

        # LOG em metadata_json se houver correção
        if correcoes:
            self._logar_metadata_json(
                interacao=interacao,
                evento="fact_checker_status_processo",
                payload={
                    "processo_id": processo_id,
                    "afirmacao_ia": afirmacao_ia,
                    "resultado": resultado,
                },
            )

        return resultado

    # 2) Prazo

    async def verificar_prazo(
        self,
        processo_id: str,
        prazo_mencionado: str,
        interacao: Any,
    ) -> dict[str, Any]:
        """
        Verifica se o prazo mencionado é factível comparando com o prazo real (se existir).
        """
        dados_reais = await self._buscar_dados_processo(processo_id)
        prazo_real = (dados_reais.get("prazo") or "").strip()

        correcoes: list[str] = []

        if prazo_real:
            # Checagem simples: string igual (você pode evoluir para datas/regex)
            if prazo_mencionado.strip() != prazo_real:
                correcoes.append(
                    "Prazo mencionado não corresponde ao prazo real cadastrado."
                )
        # Se não há prazo real, não reprova (apenas não verifica)
        resultado = {
            "verificado": len(correcoes) == 0,
            "correcoes": correcoes,
            "prazo_real": prazo_real or None,
        }

        if correcoes:
            self._logar_metadata_json(
                interacao=interacao,
                evento="fact_checker_prazo",
                payload={
                    "processo_id": processo_id,
                    "prazo_mencionado": prazo_mencionado,
                    "resultado": resultado,
                },
            )

        return resultado

    # 3) Filtro de linguagem

    def filtrar_resposta(
        self,
        resposta_ia: str,
        interacao: Any,
        adicionar_disclaimer: bool = True,
    ) -> str:
        """
        Remove/neutraliza linguagem que soe como parecer jurídico/promessa.
        Se alterar, LOGA em interacao.metadata_json.
        """
        original = resposta_ia
        ajustada = resposta_ia

        motivos: list[str] = []

        # Substitui padrões proibidos por linguagem neutra
        for padrao in self._padroes_proibidos:
            if padrao.search(ajustada):
                motivos.append(f"Padrão proibido detectado: '{padrao.pattern}'")
                ajustada = padrao.sub("é recomendado considerar", ajustada)

        # Adiciona disclaimer SOMENTE se um padrão proibido foi corrigido
        # e o chamador pediu (adicionar_disclaimer=True).
        # Não aparece em toda mensagem — apenas quando a IA usou linguagem inadequada.
        if adicionar_disclaimer and motivos:
            ajustada = ajustada.rstrip() + "\n\n" + self._disclaimer

        houve_correcao = ajustada != original

        if houve_correcao:
            self._logar_metadata_json(
                interacao=interacao,
                evento="fact_checker_filtrar_resposta",
                payload={
                    "houve_correcao": True,
                    "motivos": motivos or ["Ajuste de linguagem aplicado."],
                    "antes": original,
                    "depois": ajustada,
                },
            )

        return ajustada

    # 4) Logger em metadata_json

    def _logar_metadata_json(
        self, interacao: Any, evento: str, payload: dict[str, Any]
    ) -> None:
        """
        Registra dados em interacao.metadata_json.

        Regras:
          - Garante dict
          - Cria lista de eventos em metadata_json["auditoria_fact_checker"]
          - Não quebra se metadata_json estiver None
        """
        agora = self._utcnow().isoformat() + "Z"

        # Garante que metadata_json existe e é dict
        metadata = getattr(interacao, "metadata_json", None)
        if metadata is None or not isinstance(metadata, dict):
            metadata = {}

        auditoria = metadata.get("auditoria_fact_checker")
        if auditoria is None or not isinstance(auditoria, list):
            auditoria = []

        auditoria.append(
            {
                "evento": evento,
                "timestamp_utc": agora,
                "payload": payload,
            }
        )

        metadata["auditoria_fact_checker"] = auditoria
        metadata["fact_check_corrigido"] = True

        _fact_check_corrections_total.inc()

        # grava de volta no objeto
        interacao.metadata_json = metadata
