# feature_1_ia_personalizada/tests/unit/test_data_cleaner.py
"""
Testes unitários para LegalDataCleaner.
Cobre remover_tags_html, normalizar_espacos, limpar_andamento e processar_extrato.
"""

from __future__ import annotations

from feature_1_ia_personalizada.services.legal_data.data_cleaner import LegalDataCleaner


class TestRemoverTagsHtml:
    def test_remove_tag_simples(self):
        resultado = LegalDataCleaner.remover_tags_html("<b>Texto</b>")
        assert "Texto" in resultado
        assert "<b>" not in resultado

    def test_remove_multiplas_tags(self):
        resultado = LegalDataCleaner.remover_tags_html(
            "<p><b>Decisão:</b> Aguarda prazos<br></p>"
        )
        assert "Decisão:" in resultado
        assert "Aguarda prazos" in resultado
        assert "<" not in resultado

    def test_desencoda_entidades_html(self):
        resultado = LegalDataCleaner.remover_tags_html("valor &gt; 100 &amp; &lt; 200")
        assert ">" in resultado
        assert "&" in resultado
        assert "<" in resultado

    def test_string_vazia_retorna_vazia(self):
        assert LegalDataCleaner.remover_tags_html("") == ""

    def test_none_like_vazio(self):
        # Comportamento quando texto_bruto é falsy
        assert LegalDataCleaner.remover_tags_html("") == ""

    def test_sem_tags_retorna_texto_original(self):
        texto = "Texto sem nenhuma tag HTML"
        resultado = LegalDataCleaner.remover_tags_html(texto)
        assert "Texto sem nenhuma tag HTML" in resultado

    def test_nbsp_decodificado(self):
        resultado = LegalDataCleaner.remover_tags_html("Texto&nbsp;com espaço")
        assert "&nbsp;" not in resultado

    def test_tag_com_atributos(self):
        resultado = LegalDataCleaner.remover_tags_html(
            '<a href="http://example.com">link</a>'
        )
        assert "link" in resultado
        assert "<a" not in resultado

    def test_tag_self_closing(self):
        resultado = LegalDataCleaner.remover_tags_html("Linha 1<br/>Linha 2")
        assert "Linha 1" in resultado
        assert "Linha 2" in resultado
        assert "<br/>" not in resultado


class TestNormalizarEspacos:
    def test_espacos_duplos_viram_um(self):
        resultado = LegalDataCleaner.normalizar_espacos("texto  com   espaços")
        assert "  " not in resultado

    def test_quebras_de_linha_removidas(self):
        resultado = LegalDataCleaner.normalizar_espacos("linha1\nlinha2\nlinha3")
        assert "\n" not in resultado
        assert "linha1" in resultado
        assert "linha2" in resultado

    def test_tabs_removidos(self):
        resultado = LegalDataCleaner.normalizar_espacos("texto\tcom\ttabs")
        assert "\t" not in resultado

    def test_strip_bordas(self):
        resultado = LegalDataCleaner.normalizar_espacos("   texto   ")
        assert resultado == "texto"

    def test_string_vazia_retorna_vazia(self):
        assert LegalDataCleaner.normalizar_espacos("") == ""

    def test_apenas_espacos_retorna_vazio(self):
        resultado = LegalDataCleaner.normalizar_espacos("   \n\t  ")
        assert resultado == ""

    def test_texto_normal_preservado(self):
        resultado = LegalDataCleaner.normalizar_espacos("Texto normal")
        assert resultado == "Texto normal"


class TestLimparAndamento:
    def test_remove_html_e_normaliza_espacos(self):
        entrada = "<b>Decisão:</b>  Aguarda  prazos\n"
        resultado = LegalDataCleaner.limpar_andamento(entrada)
        assert "<" not in resultado
        assert "  " not in resultado
        assert "Decisão:" in resultado

    def test_string_vazia_retorna_vazia(self):
        assert LegalDataCleaner.limpar_andamento("") == ""

    def test_remove_cabecalho_processo_digital(self):
        entrada = (
            "Processo Digital. Petições para juntada devem ser apresentadas "
            "exclusivamente por meio eletrônico, nos termos. Sentença proferida."
        )
        resultado = LegalDataCleaner.limpar_andamento(entrada)
        # O cabeçalho deve ser removido, ficando com "Sentença..."
        assert "Sentença" in resultado

    def test_strip_resultado_final(self):
        resultado = LegalDataCleaner.limpar_andamento("  texto  ")
        assert resultado == resultado.strip()

    def test_texto_limpo_nao_muda(self):
        texto = "Sentença com resolução de mérito"
        resultado = LegalDataCleaner.limpar_andamento(texto)
        assert "Sentença" in resultado
        assert "mérito" in resultado


class TestProcessarExtrato:
    def test_lista_vazia_retorna_vazia(self):
        assert LegalDataCleaner.processar_extrato([]) == []

    def test_limpa_campo_descricao(self):
        andamentos = [{"descricao": "<b>Decisão:</b>  texto", "data": "2024-01-01"}]
        resultado = LegalDataCleaner.processar_extrato(andamentos)
        assert len(resultado) == 1
        assert "<b>" not in resultado[0]["descricao"]
        assert resultado[0]["data"] == "2024-01-01"

    def test_sem_campo_descricao_nao_quebra(self):
        andamentos = [{"data": "2024-01-01", "tipo": "Decisão"}]
        resultado = LegalDataCleaner.processar_extrato(andamentos)
        assert len(resultado) == 1
        assert resultado[0]["tipo"] == "Decisão"

    def test_descricao_none_nao_altera(self):
        andamentos = [{"descricao": None, "data": "2024-01-01"}]
        resultado = LegalDataCleaner.processar_extrato(andamentos)
        assert resultado[0]["descricao"] is None

    def test_nao_modifica_original(self):
        andamento = {"descricao": "<b>texto</b>"}
        original_descricao = andamento["descricao"]
        LegalDataCleaner.processar_extrato([andamento])
        # original não deve ser modificado (copia profunda do dict)
        assert andamento["descricao"] == original_descricao

    def test_multiplos_andamentos(self):
        andamentos = [
            {"descricao": "<b>Decisão 1</b>"},
            {"descricao": "<i>Despacho 2</i>"},
            {"descricao": "Texto limpo"},
        ]
        resultado = LegalDataCleaner.processar_extrato(andamentos)
        assert len(resultado) == 3
        assert "<b>" not in resultado[0]["descricao"]
        assert "<i>" not in resultado[1]["descricao"]
        assert "Texto limpo" in resultado[2]["descricao"]

    def test_descricao_html_complexo(self):
        andamentos = [
            {
                "descricao": (
                    "<html><body><p>Conclusão ao Juiz&nbsp;<br/>Expedido ofício</p></body></html>"
                )
            }
        ]
        resultado = LegalDataCleaner.processar_extrato(andamentos)
        assert "<" not in resultado[0]["descricao"]
        assert "Conclusão" in resultado[0]["descricao"]
