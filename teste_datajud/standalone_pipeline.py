import logging
import sys
from pathlib import Path
from typing import Any

# Garante acesso à raiz do projeto para importar os serviços já existentes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os

from dotenv import load_dotenv

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.prompts import SYSTEM_PROMPT_STATUS_PROCESSO
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.legal_data.data_cleaner import LegalDataCleaner
from teste_datajud.datajud_real_client import DataJudRealClient

load_dotenv()

logger = logging.getLogger(__name__)


class DatajudTesterPipeline:
    """
    Simula uma pipeline isolada rodando com a API Real do Datajud.
    Usa o DataCleaner oficial e a IA oficial do projeto para testes íntegros.
    """

    def __init__(self, datajud_api_key: str):
        self.datajud_client = DataJudRealClient(api_key=datajud_api_key)
        self.cleaner = LegalDataCleaner()
        self.translator = JuridicalTranslator()

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.ai_client = ClaudeClient(api_key=anthropic_key)

    async def executar_teste_processo(self, numero_cnj: str) -> dict[str, Any]:
        """
        Executa os três passos visuais da nossa sandbox:
        1. Busca Oficial.
        2. Limpeza / Formatação.
        3. Tradução via IA.
        """
        resultado = {
            "status": "sucesso",
            "bruto": None,
            "limpo": None,
            "traducao_ia": None,
            "erro": None,
        }

        try:
            # 1. Busca Bruta na Nuvem do CNJ
            raw_data = await self.datajud_client.consultar_numero_cnj(numero_cnj)
            resultado["bruto"] = raw_data

            if "erro" in raw_data:
                resultado["status"] = "erro"
                resultado["erro"] = raw_data["erro"]
                return resultado

            # 2. Limpeza pelos algoritmos do projeto original (DataCleaner)
            movimentos = raw_data.get("movimentos", [])
            titulo_classe = raw_data.get("classe", {}).get("nome", "Desconhecida")

            lista_andamentos = []
            for m in movimentos:
                # O formato do CNJ varia muito. Tentamos pegar a data e o nome do movimento básico
                data_iso = m.get("dataHora", "N/A")
                nome_movimento = m.get("nome", "Movimentação Sem Nome")

                # Aqui o Datajud carece de descrição longa! Ele coloca resumos nas tabelas complementares
                detalhes = ""
                for comp in m.get("complementosTabelados", []):
                    if comp.get("valor"):
                        detalhes += f" {comp.get('valor')}"

                texto_final = f"{nome_movimento}. {detalhes}".strip()
                lista_andamentos.append({"data": data_iso, "descricao": texto_final})

            historico_limpo = self.cleaner.processar_extrato(lista_andamentos)
            resultado["limpo"] = {"classe": titulo_classe, "historico": historico_limpo}

            # 3. Dispara a IA com a memória "curta" sobre essa ação
            # O sistema injeta o Histórico Limpo pra IA resumir
            prompt_teste = f"""
            Você é um assistente jurídico simulando o fluxo de leitura do CNJ.
            Chegou a seguinte atualização do Processo da Classe: {titulo_classe}.
            Histórico de andamentos:
            {historico_limpo}

            Com base EXCLUSIVAMENTE nos dados acima, qual o resumo do que aconteceu nesse processo para o cliente (em português leigo)?
            Diga que esses dados vieram do CNJ (Datajud) e comente se há ou não o "texto do Diário Oficial completo" nessa leitura.
            """

            # Integração Real da IA Tradutora igual ao Orchestrator Oficial do Projeto
            ultimo_andamento = ""
            if historico_limpo:
                ultimo_andamento = historico_limpo[0].get("descricao", "")

            termos_detectados = self.translator.identificar_termos_tecnicos(
                ultimo_andamento
            )
            glossario_andamento = {}
            for termo in termos_detectados:
                trad = self.translator.traduzir_termo(termo)
                if trad:
                    glossario_andamento[termo] = trad.split("\n\n")[0]

            system_prompt = self.parametrizar_system_prompt_chat(
                numero_cnj, ultimo_andamento, glossario_andamento
            )

            resposta_ia = await self.ai_client.enviar_mensagem(
                system_prompt=system_prompt,
                mensagens_historico=[],
                mensagem_usuario=prompt_teste,
            )

            return {
                "status": "sucesso",
                "bruto": raw_data,
                "limpo": {"classe": titulo_classe, "historico": historico_limpo},
                "traducao_ia": resposta_ia["resposta"],
            }

        except Exception as e:
            logger.error(f"Erro na Pipeline Teste: {e}")
            return {"status": "erro", "erro": str(e)}

    def parametrizar_system_prompt_chat(
        self, cnj: str, andamento: str, glossario: dict = None
    ) -> str:
        if glossario is None:
            glossario = {}
            termos_detectados = self.translator.identificar_termos_tecnicos(andamento)
            for termo in termos_detectados:
                trad = self.translator.traduzir_termo(termo)
                if trad:
                    glossario[termo] = trad.split("\n\n")[0]

        system_prompt = SYSTEM_PROMPT_STATUS_PROCESSO.format(
            nome_escritorio="Escritório Teste (Datajud Sandbox)",
            numero_cnj=cnj or "N/D",
            tribunal="N/D",
            vara="N/D",
            ultimo_andamento=andamento or "sem movimentação recente",
            data_ultimo_andamento="N/D",
            polo_cliente="N/D",
        )

        if glossario:
            linhas = "\n".join(
                f"- {termo}: {definicao}" for termo, definicao in glossario.items()
            )
            system_prompt += f"\n\n<glossario_termos>\n{linhas}\n</glossario_termos>"

        return system_prompt
