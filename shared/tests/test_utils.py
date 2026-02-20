"""
shared/tests/test_utils.py
===========================
Testes unitários para todos os módulos de shared/utils/.

Cobre:
  - validators  : CPF, CNPJ, número de processo CNJ, telefone WhatsApp
  - formatters  : data BR, data relativa, moeda BRL, número de processo
  - lgpd        : registrar_acesso, verificar_aceite_lgpd,
                  exportar_dados_cliente, anonimizar_dados_cliente
  - audio_handler: validar_duracao_audio, converter_ogg_para_mp3,
                   transcrever_audio

Dependências externas (pydub, OpenAI, SQLAlchemy) são sempre mockadas.

Nota: testes async NÃO usam @pytest.mark.asyncio — dependem de
asyncio_mode = "auto" configurado em pyproject.toml ([tool.pytest.ini_options]).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.utils.validators import (
    normalizar_cnpj,
    normalizar_cpf,
    normalizar_numero_processo,
    normalizar_telefone,
    validar_cnpj,
    validar_cpf,
    validar_numero_processo,
    validar_telefone_whatsapp,
)
from shared.utils.formatters import (
    formatar_data_br,
    formatar_data_relativa,
    formatar_moeda_brl,
    formatar_numero_processo,
)
from shared.utils.lgpd import (
    anonimizar_dados_cliente,
    exportar_dados_cliente,
    registrar_acesso,
    verificar_aceite_lgpd,
)
from shared.utils.audio_handler import (
    converter_ogg_para_mp3,
    transcrever_audio,
    validar_duracao_audio,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

# CPF válido: 529.982.247-25 (verificado com algoritmo oficial)
CPF_VALIDO = "529.982.247-25"
CPF_SEM_FORMATACAO = "52998224725"
CPF_INVALIDO = "123.456.789-00"
CPF_SEQUENCIAL = "111.111.111-11"

# CNPJ válido: 11.222.333/0001-81
CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_SEM_FORMATACAO = "11222333000181"
CNPJ_INVALIDO = "11.222.333/0001-99"
CNPJ_SEQUENCIAL = "00.000.000/0000-00"

# Telefone WhatsApp válido: 55 + DDD + 9 + 8 dígitos
TEL_VALIDO = "5511987654321"
TEL_VALIDO_FORMATADO = "+55 (11) 98765-4321"
TEL_FIXO = "551132345678"   # sem o dígito 9 obrigatório


def _make_cnj(nnnnnnn="0001234", aaaa="2024", j="8", tt="26", oooo="0100") -> str:
    """Gera número CNJ com dígito verificador correto (ISO 7064 MOD 97-10)."""
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{nnnnnnn}-{dd:02d}.{aaaa}.{j}.{tt}.{oooo}"


CNJ_VALIDO = _make_cnj()
CNJ_DIGITOS = "00012345620248260100"   # 20 dígitos do CNJ_VALIDO sem pontuação
CNJ_FORMATO_ERRADO = "1234567-890"
CNJ_DIGITO_ERRADO = "0001234-99.2024.8.26.0100"


# ===========================================================================
# validators.py
# ===========================================================================


class TestValidarCPF:
    def test_valido_com_formatacao(self):
        assert validar_cpf(CPF_VALIDO) is True

    def test_valido_sem_formatacao(self):
        assert validar_cpf(CPF_SEM_FORMATACAO) is True

    def test_invalido_digito_verificador(self):
        assert validar_cpf(CPF_INVALIDO) is False

    def test_invalido_sequencia_repetida(self):
        assert validar_cpf(CPF_SEQUENCIAL) is False

    def test_invalido_tamanho_errado(self):
        assert validar_cpf("123.456") is False

    def test_invalido_vazio(self):
        assert validar_cpf("") is False


class TestNormalizarCPF:
    def test_remove_pontuacao(self):
        assert normalizar_cpf(CPF_VALIDO) == CPF_SEM_FORMATACAO

    def test_apenas_digitos_permanece_igual(self):
        assert normalizar_cpf(CPF_SEM_FORMATACAO) == CPF_SEM_FORMATACAO


class TestValidarCNPJ:
    def test_valido_com_formatacao(self):
        assert validar_cnpj(CNPJ_VALIDO) is True

    def test_valido_sem_formatacao(self):
        assert validar_cnpj(CNPJ_SEM_FORMATACAO) is True

    def test_invalido_digito_verificador(self):
        assert validar_cnpj(CNPJ_INVALIDO) is False

    def test_invalido_sequencia_repetida(self):
        assert validar_cnpj(CNPJ_SEQUENCIAL) is False

    def test_invalido_tamanho_errado(self):
        assert validar_cnpj("11.222.333") is False


class TestNormalizarCNPJ:
    def test_remove_pontuacao(self):
        assert normalizar_cnpj(CNPJ_VALIDO) == CNPJ_SEM_FORMATACAO

    def test_apenas_digitos_permanece_igual(self):
        assert normalizar_cnpj(CNPJ_SEM_FORMATACAO) == CNPJ_SEM_FORMATACAO


class TestValidarNumeroProcesso:
    def test_valido(self):
        assert validar_numero_processo(CNJ_VALIDO) is True

    def test_valido_com_espacos(self):
        assert validar_numero_processo(f"  {CNJ_VALIDO}  ") is True

    def test_formato_errado(self):
        assert validar_numero_processo(CNJ_FORMATO_ERRADO) is False

    def test_digito_verificador_errado(self):
        assert validar_numero_processo(CNJ_DIGITO_ERRADO) is False

    def test_vazio(self):
        assert validar_numero_processo("") is False


class TestNormalizarNumeroProcesso:
    def test_formata_20_digitos(self):
        # Reconstrói o formato pontuado a partir de dígitos brutos
        resultado = normalizar_numero_processo(CNJ_DIGITOS)
        # Resultado deve ter o formato NNNNNNN-DD.AAAA.J.TT.OOOO
        assert resultado.count("-") == 1
        assert resultado.count(".") == 4

    def test_ja_formatado_reconstroi_igual(self):
        resultado = normalizar_numero_processo(CNJ_VALIDO)
        assert resultado == CNJ_VALIDO

    def test_menos_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            normalizar_numero_processo("123456")

    def test_mais_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            normalizar_numero_processo("0" * 21)


class TestValidarTelefoneWhatsapp:
    def test_valido_13_digitos(self):
        assert validar_telefone_whatsapp(TEL_VALIDO) is True

    def test_valido_com_formatacao(self):
        assert validar_telefone_whatsapp(TEL_VALIDO_FORMATADO) is True

    def test_fixo_sem_nono_digito(self):
        assert validar_telefone_whatsapp(TEL_FIXO) is False

    def test_muito_curto(self):
        assert validar_telefone_whatsapp("55119") is False

    def test_sem_prefixo_55(self):
        assert validar_telefone_whatsapp("11987654321") is False


class TestNormalizarTelefone:
    def test_com_prefixo_55_completo(self):
        assert normalizar_telefone(TEL_VALIDO) == TEL_VALIDO

    def test_11_digitos_sem_55_adiciona_prefixo(self):
        resultado = normalizar_telefone("11987654321")
        assert resultado == TEL_VALIDO

    def test_invalido_levanta_erro(self):
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("123")

    def test_fixo_levanta_erro(self):
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone(TEL_FIXO)


# ===========================================================================
# formatters.py
# ===========================================================================


class TestFormatarDataBr:
    def test_formato_basico(self):
        dt = datetime(2026, 2, 16, 14, 30)
        assert formatar_data_br(dt) == "16/02/2026 às 14:30"

    def test_meia_noite(self):
        dt = datetime(2026, 1, 1, 0, 0)
        assert formatar_data_br(dt) == "01/01/2026 às 00:00"

    def test_dia_com_zero(self):
        dt = datetime(2026, 3, 5, 9, 5)
        assert formatar_data_br(dt) == "05/03/2026 às 09:05"


class TestFormatarDataRelativa:
    def _dt_dias_atras(self, dias: int) -> datetime:
        return datetime.now(tz=timezone.utc) - timedelta(days=dias)

    def _dt_horas_atras(self, horas: int) -> datetime:
        return datetime.now(tz=timezone.utc) - timedelta(hours=horas)

    def test_hoje(self):
        assert formatar_data_relativa(self._dt_horas_atras(1)) == "hoje"

    def test_mais_de_24h_e_ontem(self):
        # 23:59 de ontem vs 00:01 de hoje — deve ser "ontem", não "hoje"
        # A comparação é por data calendário, não janela de 24h
        # Simulamos com exatamente 1 dia e 1 minuto atrás
        dt = datetime.now(tz=timezone.utc) - timedelta(days=1, minutes=1)
        assert formatar_data_relativa(dt) == "ontem"

    def test_ontem(self):
        assert formatar_data_relativa(self._dt_dias_atras(1)) == "ontem"

    def test_ha_3_dias(self):
        assert formatar_data_relativa(self._dt_dias_atras(3)) == "há 3 dias"

    def test_ha_1_semana(self):
        assert formatar_data_relativa(self._dt_dias_atras(7)) == "há 1 semana"

    def test_ha_2_semanas(self):
        assert formatar_data_relativa(self._dt_dias_atras(14)) == "há 2 semanas"

    def test_ha_1_mes(self):
        assert formatar_data_relativa(self._dt_dias_atras(30)) == "há 1 mês"

    def test_ha_3_meses(self):
        assert formatar_data_relativa(self._dt_dias_atras(90)) == "há 3 meses"

    def test_ha_1_ano(self):
        assert formatar_data_relativa(self._dt_dias_atras(365)) == "há 1 ano"

    def test_ha_2_anos(self):
        assert formatar_data_relativa(self._dt_dias_atras(730)) == "há 2 anos"

    def test_futuro(self):
        dt = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        assert formatar_data_relativa(dt) == "em breve"

    def test_naive_datetime_tratado_como_utc(self):
        # Naive datetime de 3 dias atrás deve funcionar sem erro
        dt_naive = datetime.now() - timedelta(days=3)  # naive sem tzinfo
        assert formatar_data_relativa(dt_naive) == "há 3 dias"


class TestFormatarMoedaBrl:
    def test_inteiro(self):
        assert formatar_moeda_brl(1500) == "R$ 1.500,00"

    def test_decimal(self):
        assert formatar_moeda_brl(Decimal("1500.50")) == "R$ 1.500,50"

    def test_zero(self):
        assert formatar_moeda_brl(0) == "R$ 0,00"

    def test_centavos(self):
        assert formatar_moeda_brl(Decimal("0.99")) == "R$ 0,99"

    def test_negativo(self):
        assert formatar_moeda_brl(-1500) == "R$ -1.500,00"

    def test_milhao(self):
        assert formatar_moeda_brl(1_000_000) == "R$ 1.000.000,00"

    def test_float(self):
        assert formatar_moeda_brl(99.9) == "R$ 99,90"


class TestFormatarNumeroProcesso:
    def test_de_20_digitos(self):
        digitos = normalizar_numero_processo(CNJ_VALIDO).replace("-", "").replace(".", "")
        resultado = formatar_numero_processo(digitos)
        assert "-" in resultado and resultado.count(".") == 4

    def test_ja_formatado_reconstroi_igual(self):
        assert formatar_numero_processo(CNJ_VALIDO) == CNJ_VALIDO

    def test_menos_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            formatar_numero_processo("123")

    def test_mais_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            formatar_numero_processo("0" * 25)


# ===========================================================================
# lgpd.py
# ===========================================================================


class TestRegistrarAcesso:
    def test_loga_evento_estruturado(self):
        with patch("shared.utils.lgpd.logger") as mock_logger:
            registrar_acesso(user_id=1, recurso="cliente:42", acao="leitura", ip="1.2.3.4")
            mock_logger.info.assert_called_once()
            args, kwargs = mock_logger.info.call_args
            assert args[0] == "lgpd.acesso_dados_sensiveis"
            assert kwargs["user_id"] == 1
            assert kwargs["recurso"] == "cliente:42"
            assert kwargs["acao"] == "leitura"
            assert kwargs["ip"] == "1.2.3.4"

    def test_ip_opcional(self):
        with patch("shared.utils.lgpd.logger") as mock_logger:
            registrar_acesso(user_id=2, recurso="processo:10", acao="escrita")
            _, kwargs = mock_logger.info.call_args
            assert kwargs["ip"] is None


class TestVerificarAceiteLgpd:
    async def test_aceite_true(self):
        session = AsyncMock()
        resultado_mock = MagicMock()
        resultado_mock.scalar_one_or_none.return_value = True
        session.execute.return_value = resultado_mock

        assert await verificar_aceite_lgpd(session, cliente_id=1) is True

    async def test_aceite_false(self):
        session = AsyncMock()
        resultado_mock = MagicMock()
        resultado_mock.scalar_one_or_none.return_value = False
        session.execute.return_value = resultado_mock

        assert await verificar_aceite_lgpd(session, cliente_id=1) is False

    async def test_cliente_nao_encontrado_retorna_false(self):
        session = AsyncMock()
        resultado_mock = MagicMock()
        resultado_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = resultado_mock

        assert await verificar_aceite_lgpd(session, cliente_id=999) is False


class TestExportarDadosCliente:
    def _make_cliente_mock(self) -> MagicMock:
        cliente = MagicMock()
        cliente.id = 1
        cliente.nome = "João da Silva"
        cliente.cpf = "encrypted_cpf_value"
        cliente.email = "joao@email.com"
        cliente.telefone_whatsapp = TEL_VALIDO
        cliente.data_nascimento = date(1990, 5, 15)
        cliente.profissao = "Engenheiro"
        cliente.empresa_atual = "Tech Ltda"
        cliente.cargo = "Senior"
        cliente.aceite_lgpd = True
        cliente.data_aceite_lgpd = datetime(2024, 1, 1, tzinfo=timezone.utc)
        cliente.preferencia_horario_notificacao = "comercial"
        cliente.ativo = True
        cliente.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        cliente.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return cliente

    async def test_exporta_estrutura_completa(self):
        session = AsyncMock()
        session.get.return_value = self._make_cliente_mock()

        res_proc = MagicMock()
        res_proc.scalars.return_value.all.return_value = []
        res_inter = MagicMock()
        res_inter.scalars.return_value.all.return_value = []
        session.execute.side_effect = [res_proc, res_inter]

        resultado = await exportar_dados_cliente(session, cliente_id=1)

        assert "exportado_em" in resultado
        assert resultado["cliente"]["id"] == 1
        assert resultado["cliente"]["nome"] == "João da Silva"
        assert resultado["processos"] == []
        assert resultado["interacoes"] == []

    async def test_cpf_presente_true_quando_tem_valor(self):
        session = AsyncMock()
        cliente = self._make_cliente_mock()
        cliente.cpf = "valor_criptografado"
        session.get.return_value = cliente

        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        session.execute.side_effect = [res, res]

        resultado = await exportar_dados_cliente(session, cliente_id=1)
        assert resultado["cliente"]["cpf_presente"] is True

    async def test_cpf_presente_false_quando_vazio(self):
        session = AsyncMock()
        cliente = self._make_cliente_mock()
        cliente.cpf = ""
        session.get.return_value = cliente

        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        session.execute.side_effect = [res, res]

        resultado = await exportar_dados_cliente(session, cliente_id=1)
        assert resultado["cliente"]["cpf_presente"] is False

    async def test_cliente_nao_encontrado_levanta_erro(self):
        session = AsyncMock()
        session.get.return_value = None

        with pytest.raises(ValueError, match="não encontrado"):
            await exportar_dados_cliente(session, cliente_id=999)


class TestAnonimizarDadosCliente:
    async def test_anonimiza_dados_pessoais(self):
        session = AsyncMock()
        cliente_mock = MagicMock()
        session.get.return_value = cliente_mock

        res_inter = MagicMock()
        interacao_mock = MagicMock()
        res_inter.scalars.return_value.all.return_value = [interacao_mock]
        session.execute.return_value = res_inter

        await anonimizar_dados_cliente(session, cliente_id=42)

        assert cliente_mock.nome == "TITULAR ANONIMIZADO"
        assert cliente_mock.cpf == "00000000000"
        assert cliente_mock.email is None
        assert cliente_mock.ativo is False
        assert cliente_mock.data_nascimento is None

    async def test_apaga_conteudo_das_interacoes(self):
        session = AsyncMock()
        session.get.return_value = MagicMock()

        interacao = MagicMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = [interacao]
        session.execute.return_value = res

        await anonimizar_dados_cliente(session, cliente_id=1)

        assert interacao.mensagem_cliente is None
        assert interacao.mensagem_ia is None
        assert interacao.audio_transcricao is None

    async def test_chama_flush(self):
        session = AsyncMock()
        session.get.return_value = MagicMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        session.execute.return_value = res

        await anonimizar_dados_cliente(session, cliente_id=1)

        session.flush.assert_called_once()

    async def test_registra_audit_com_solicitado_por(self):
        session = AsyncMock()
        session.get.return_value = MagicMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        session.execute.return_value = res

        with patch("shared.utils.lgpd.registrar_acesso") as mock_audit:
            await anonimizar_dados_cliente(session, cliente_id=5, solicitado_por=99)
            mock_audit.assert_called_once_with(
                user_id=99, recurso="cliente:5", acao="anonimizacao"
            )

    async def test_sem_solicitado_por_nao_chama_audit(self):
        session = AsyncMock()
        session.get.return_value = MagicMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        session.execute.return_value = res

        with patch("shared.utils.lgpd.registrar_acesso") as mock_audit:
            await anonimizar_dados_cliente(session, cliente_id=5)
            mock_audit.assert_not_called()

    async def test_cliente_nao_encontrado_levanta_erro(self):
        session = AsyncMock()
        session.get.return_value = None

        with pytest.raises(ValueError, match="não encontrado"):
            await anonimizar_dados_cliente(session, cliente_id=999)


# ===========================================================================
# audio_handler.py
# ===========================================================================


def _make_audio_mock(duracao_ms: int) -> MagicMock:
    """Cria mock de AudioSegment com duração configurável."""
    audio = MagicMock()
    audio.__len__ = MagicMock(return_value=duracao_ms)
    return audio


class TestValidarDuracaoAudio:
    def test_audio_valido_retorna_segundos(self):
        with patch("shared.utils.audio_handler.AudioSegment.from_file") as mock_read:
            mock_read.return_value = _make_audio_mock(30_000)  # 30s
            assert validar_duracao_audio(b"ogg") == 30

    def test_exatamente_120s_e_valido(self):
        with patch("shared.utils.audio_handler.AudioSegment.from_file") as mock_read:
            mock_read.return_value = _make_audio_mock(120_000)  # exato
            assert validar_duracao_audio(b"ogg") == 120

    def test_120_999ms_e_rejeitado(self):
        """120.999s deve rejeitar — comparação é em ms, não com truncamento."""
        with patch("shared.utils.audio_handler.AudioSegment.from_file") as mock_read:
            mock_read.return_value = _make_audio_mock(120_999)
            with pytest.raises(ValueError, match="muito longo"):
                validar_duracao_audio(b"ogg")

    def test_muito_longo_levanta_erro(self):
        with patch("shared.utils.audio_handler.AudioSegment.from_file") as mock_read:
            mock_read.return_value = _make_audio_mock(180_000)  # 3min
            with pytest.raises(ValueError, match="muito longo"):
                validar_duracao_audio(b"ogg")

    def test_audio_corrompido_levanta_erro(self):
        with patch(
            "shared.utils.audio_handler.AudioSegment.from_file",
            side_effect=Exception("codec error"),
        ):
            with pytest.raises(ValueError, match="Não foi possível ler"):
                validar_duracao_audio(b"corrompido")


class TestConverterOggParaMp3:
    def test_converte_com_sucesso(self):
        mp3_bytes = b"fake_mp3_content"
        audio_mock = MagicMock()

        audio_mock.export.side_effect = lambda *args, **_: args[0].write(mp3_bytes)

        with patch("shared.utils.audio_handler.AudioSegment.from_file", return_value=audio_mock):
            resultado = converter_ogg_para_mp3(b"ogg_bytes")

        assert resultado == mp3_bytes
        audio_mock.export.assert_called_once()

    def test_falha_leitura_ogg_levanta_erro(self):
        with patch(
            "shared.utils.audio_handler.AudioSegment.from_file",
            side_effect=Exception("formato inválido"),
        ):
            with pytest.raises(ValueError, match="Falha ao ler OGG"):
                converter_ogg_para_mp3(b"invalido")

    def test_falha_exportacao_mp3_levanta_erro(self):
        audio_mock = MagicMock()
        audio_mock.export.side_effect = Exception("ffmpeg não encontrado")

        with patch("shared.utils.audio_handler.AudioSegment.from_file", return_value=audio_mock):
            with pytest.raises(ValueError, match="Falha ao exportar"):
                converter_ogg_para_mp3(b"ogg_bytes")


class TestTranscreverAudio:
    async def test_transcricao_com_sucesso(self):
        resposta_mock = MagicMock()
        resposta_mock.text = "  Olá, como posso ajudar?  "

        with patch("shared.utils.audio_handler._openai_client") as mock_client:
            mock_client.audio.transcriptions.create = AsyncMock(return_value=resposta_mock)
            resultado = await transcrever_audio(b"mp3_bytes")

        assert resultado == "Olá, como posso ajudar?"

    async def test_timeout_levanta_valor_amigavel(self):
        from openai import APITimeoutError

        with patch("shared.utils.audio_handler._openai_client") as mock_client:
            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=APITimeoutError(request=MagicMock())
            )
            with pytest.raises(ValueError, match="Timeout"):
                await transcrever_audio(b"mp3_bytes")

    async def test_erro_api_levanta_com_status(self):
        from openai import APIStatusError

        with patch("shared.utils.audio_handler._openai_client") as mock_client:
            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=APIStatusError(
                    message="Internal Server Error",
                    response=MagicMock(status_code=500),
                    body=None,
                )
            )
            with pytest.raises(ValueError, match="HTTP 500"):
                await transcrever_audio(b"mp3_bytes")

    async def test_transcricao_vazia_levanta_erro(self):
        resposta_mock = MagicMock()
        resposta_mock.text = "   "  # só espaços

        with patch("shared.utils.audio_handler._openai_client") as mock_client:
            mock_client.audio.transcriptions.create = AsyncMock(return_value=resposta_mock)
            with pytest.raises(ValueError, match="vazia"):
                await transcrever_audio(b"mp3_bytes")

    async def test_arquivo_temporario_removido_apos_sucesso(self):
        resposta_mock = MagicMock()
        resposta_mock.text = "texto"

        with patch("shared.utils.audio_handler.Path.unlink") as mock_unlink:
            with patch("shared.utils.audio_handler._openai_client") as mock_client:
                mock_client.audio.transcriptions.create = AsyncMock(return_value=resposta_mock)
                await transcrever_audio(b"mp3_bytes")

        mock_unlink.assert_called_once_with(missing_ok=True)

    async def test_arquivo_temporario_removido_apos_erro(self):
        from openai import APITimeoutError

        with patch("shared.utils.audio_handler.Path.unlink") as mock_unlink:
            with patch("shared.utils.audio_handler._openai_client") as mock_client:
                mock_client.audio.transcriptions.create = AsyncMock(
                    side_effect=APITimeoutError(request=MagicMock())
                )
                with pytest.raises(ValueError):
                    await transcrever_audio(b"mp3_bytes")

        mock_unlink.assert_called_once_with(missing_ok=True)
