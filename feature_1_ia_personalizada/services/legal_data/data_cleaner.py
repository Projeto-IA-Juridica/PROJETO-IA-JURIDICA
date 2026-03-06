"""
feature_1_ia_personalizada/services/legal_data/data_cleaner.py

Módulo responsável por higienizar textos e andamentos brutos extraídos
de fontes jurídicas (Jusbrasil, DataJud, Diários Oficiais) antes de
serem enviados para processamento pela IA (Claude) ou exibição ao usuário.

Isso é essencial para:
1. Economizar Tokens (removendo lixo de HTML e cabeçalhos inúteis).
2. Evitar que a IA se confunda com caracteres de controle.
3. Padronizar a formatação para o RAG (Retrieval-Augmented Generation).
"""

import html
import re
from typing import Any


class LegalDataCleaner:
    @staticmethod
    def remover_tags_html(texto_bruto: str) -> str:
        """
        Remove todas as tags HTML de uma string.
        Ex: "<b>Decisão:</b> Aguarda prazos<br>" -> "Decisão: Aguarda prazos"
        """
        if not texto_bruto:
            return ""

        # Desencoda entidades HTML (ex: &nbsp;, &gt;)
        texto = html.unescape(texto_bruto)

        # Expressão regular para remover tudo que estiver entre < e >
        texto_limpo = re.sub(r"<[^>]+>", " ", texto)

        return texto_limpo

    @staticmethod
    def normalizar_espacos(texto: str) -> str:
        """
        Remove quebras de linha excessivas, tabs e espaços duplos.
        """
        if not texto:
            return ""

        # Substitui múltiplos espaços em branco (incluindo quebras de linha/tabs) por um único espaço
        texto = re.sub(r"\s+", " ", texto)

        # Strip final
        return texto.strip()

    @staticmethod
    def limpar_andamento(andamento_texto: str) -> str:
        """
        Aplica todas as regras de higienização de uma vez só em um andamento único.
        """
        if not andamento_texto:
            return ""

        t = LegalDataCleaner.remover_tags_html(andamento_texto)
        t = LegalDataCleaner.normalizar_espacos(t)

        # Opcional: Remover cabeçalhos inúteis comuns em Diários Oficiais
        t = re.sub(
            r"^(Processo Digital\. Petições para juntada devem ser apresentadas.*?)(?=[A-Z])",
            "",
            t,
            flags=re.IGNORECASE,
        )

        return t.strip()

    @staticmethod
    def processar_extrato(andamentos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Recebe a lista suja do Client (ex: JusbrasilClient) e devolve a lista pronta pro banco e IA.
        """
        andamentos_limpos = []
        for andamento in andamentos:
            andamento_limpo = andamento.copy()
            if "descricao" in andamento_limpo and andamento_limpo["descricao"]:
                andamento_limpo["descricao"] = LegalDataCleaner.limpar_andamento(
                    andamento_limpo["descricao"]
                )
            andamentos_limpos.append(andamento_limpo)

        return andamentos_limpos
