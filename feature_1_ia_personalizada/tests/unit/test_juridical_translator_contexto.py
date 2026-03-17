# feature_1_ia_personalizada/tests/unit/test_juridical_translator_contexto.py
"""
Testes de JuridicalTranslator.traduzir_com_contexto():

  - Claude chamado com max_tokens=400 e model haiku
  - system prompt montado contém todos os 7 campos obrigatórios do template
  - system passado como parâmetro separado (não embutido em messages)
  - Fallback retorna andamento original em caso de exceção
  - Andamento vazio ou em branco retorna early sem chamar Claude
  - tipo_acao None substituído por 'não informado'
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from feature_1_ia_personalizada.services.ai.juridical_translator import JuridicalTranslator

MODULE = "feature_1_ia_personalizada.services.ai.juridical_translator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claude_response(texto: str = "Resumo gerado pela IA") -> MagicMock:
    """Cria um mock de resposta da API Anthropic com estrutura mínima necessária."""
    bloco = MagicMock()
    bloco.text = texto

    uso = MagicMock()
    uso.input_tokens = 120
    uso.output_tokens = 60

    resposta = MagicMock()
    resposta.content = [bloco]
    resposta.usage = uso
    return resposta


def _patch_anthropic(texto: str = "Resumo ok"):
    """Context manager que substitui anthropic.Anthropic por mock e retorna o cliente mock."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_claude_response(texto)
    return patch("anthropic.Anthropic", return_value=mock_client), mock_client


# ---------------------------------------------------------------------------
# Argumentos padrão reutilizados nos testes
# ---------------------------------------------------------------------------

_ARGS = dict(
    andamento="Despacho ordinatório foi proferido pelo juiz da 3ª Vara Cível.",
    fase_atual="instrucao",
    historico="1. Petição inicial distribuída\n2. Citação realizada",
    tipo_acao="Ação de Cobrança",
    polo_cliente="autor",
    nome_escritorio="Escritório Silva Advogados",
    nome_cliente="João",
)


# ---------------------------------------------------------------------------
# Retorno e comportamento geral
# ---------------------------------------------------------------------------


class TestTraduzirComContextoRetorno:
    def test_retorna_texto_do_claude(self):
        ctx, mock_client = _patch_anthropic("Houve um despacho. Tudo normal.")
        with ctx:
            resultado = JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        assert resultado == "Houve um despacho. Tudo normal."

    def test_andamento_vazio_retorna_sem_chamar_claude(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            resultado = JuridicalTranslator.traduzir_com_contexto(
                andamento="",
                fase_atual="instrucao",
                historico="",
                tipo_acao="Cobrança",
                polo_cliente="autor",
            )
        mock_client.messages.create.assert_not_called()
        assert resultado == ""

    def test_andamento_apenas_espacos_retorna_sem_chamar_claude(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            resultado = JuridicalTranslator.traduzir_com_contexto(
                andamento="   ",
                fase_atual="instrucao",
                historico="",
                tipo_acao="Cobrança",
                polo_cliente="autor",
            )
        mock_client.messages.create.assert_not_called()

    def test_fallback_retorna_andamento_original_em_excecao(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("API offline")
        with patch("anthropic.Anthropic", return_value=mock_client):
            resultado = JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        assert resultado == _ARGS["andamento"]

    def test_fallback_retorna_andamento_em_timeout(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = TimeoutError("timeout")
        with patch("anthropic.Anthropic", return_value=mock_client):
            resultado = JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        assert resultado == _ARGS["andamento"]


# ---------------------------------------------------------------------------
# Parâmetros da chamada ao Claude
# ---------------------------------------------------------------------------


class TestTraduzirComContextoChamadaClaude:
    def test_usa_max_tokens_400(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 400

    def test_usa_modelo_haiku(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "haiku" in call_kwargs["model"]

    def test_system_passado_como_kwarg_separado(self):
        """O prompt vai em 'system=', não dentro da lista 'messages'."""
        ctx, mock_client = _patch_anthropic()
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        assert isinstance(call_kwargs["system"], str)

    def test_messages_contem_role_user(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "user"

    def test_claude_chamado_exatamente_uma_vez(self):
        ctx, mock_client = _patch_anthropic()
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**_ARGS)
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# Conteúdo do system prompt — todos os campos obrigatórios do template
# ---------------------------------------------------------------------------


class TestTraduzirComContextoPrompt:
    def _capturar_system(self, **kwargs) -> str:
        """Roda traduzir_com_contexto e retorna o system prompt capturado."""
        ctx, mock_client = _patch_anthropic()
        args = {**_ARGS, **kwargs}
        with ctx:
            JuridicalTranslator.traduzir_com_contexto(**args)
        return mock_client.messages.create.call_args.kwargs["system"]

    def test_contem_nome_escritorio(self):
        system = self._capturar_system()
        assert "Escritório Silva Advogados" in system

    def test_contem_nome_cliente(self):
        system = self._capturar_system()
        assert "João" in system

    def test_contem_tipo_acao(self):
        system = self._capturar_system()
        assert "Ação de Cobrança" in system

    def test_contem_fase_processual(self):
        system = self._capturar_system()
        assert "instrucao" in system

    def test_contem_polo_cliente(self):
        system = self._capturar_system()
        assert "autor" in system

    def test_contem_historico_andamentos(self):
        system = self._capturar_system()
        assert "Petição inicial distribuída" in system

    def test_contem_novo_andamento(self):
        system = self._capturar_system()
        assert "Despacho ordinatório foi proferido" in system

    def test_tipo_acao_none_substitui_por_nao_informado(self):
        system = self._capturar_system(tipo_acao=None)
        assert "não informado" in system

    def test_defaults_nome_escritorio_e_cliente(self):
        """Sem nome_escritorio e nome_cliente explícitos, usa defaults sem erro."""
        ctx, mock_client = _patch_anthropic()
        with ctx:
            resultado = JuridicalTranslator.traduzir_com_contexto(
                andamento="despacho",
                fase_atual="conhecimento",
                historico="Nenhum andamento anterior.",
                tipo_acao="Ação Trabalhista",
                polo_cliente="réu",
                # nome_escritorio e nome_cliente omitidos — usa defaults
            )
        # Não deve lançar exceção
        mock_client.messages.create.assert_called_once()
        system = mock_client.messages.create.call_args.kwargs["system"]
        # Defaults do método: "do escritório" e "cliente"
        assert "do escritório" in system or "cliente" in system
