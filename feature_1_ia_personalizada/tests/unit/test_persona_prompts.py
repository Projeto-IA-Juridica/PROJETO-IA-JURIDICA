"""
Testes unitários — Feature 4: Persona nos prompts
Critério de aceite (TASKS.md 4.6):
    - Tom formal gera linguagem diferente de amigável
    - Persona injetada no prompt
"""

from __future__ import annotations

import pytest


class TestGerarInstrucaoPersona:
    def test_retorna_bloco_xml(self):
        """Deve retornar uma string com tags <persona>."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        resultado = gerar_instrucao_persona("Dra. Ana", "formal")
        assert "<persona>" in resultado
        assert "</persona>" in resultado

    def test_nome_injetado(self):
        """O nome da persona deve aparecer no bloco."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        resultado = gerar_instrucao_persona("Dra. Maria", "neutro")
        assert "Dra. Maria" in resultado

    def test_tom_formal_usa_senhor(self):
        """Tom formal deve mencionar tratamento formal ('senhor'/'senhora')."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        resultado = gerar_instrucao_persona("Assistente", "formal")
        assert "senhor" in resultado.lower() or "senhora" in resultado.lower()

    def test_tom_amigavel_usa_voce(self):
        """Tom amigável deve mencionar 'você' e ser mais casual."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        resultado = gerar_instrucao_persona("Assistente", "amigavel")
        assert "você" in resultado.lower() or "voce" in resultado.lower()

    def test_tom_formal_diferente_de_amigavel(self):
        """Instrução do tom formal deve ser diferente da instrução do tom amigável."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        formal = gerar_instrucao_persona("Assistente", "formal")
        amigavel = gerar_instrucao_persona("Assistente", "amigavel")
        assert formal != amigavel

    def test_tom_invalido_usa_neutro(self):
        """Tom desconhecido deve silenciosamente usar o tom neutro."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        resultado_invalido = gerar_instrucao_persona("Assistente", "INVALIDO")
        resultado_neutro = gerar_instrucao_persona("Assistente", "neutro")
        assert resultado_invalido == resultado_neutro

    def test_persona_prefixada_no_prompt_base(self):
        """A instrução de persona deve poder ser prefixada ao SYSTEM_PROMPT_BASE."""
        from feature_1_ia_personalizada.services.ai.prompts import (
            SYSTEM_PROMPT_BASE,
            gerar_instrucao_persona,
        )

        persona = gerar_instrucao_persona("Dra. Carla", "amigavel")
        prompt_formatado = SYSTEM_PROMPT_BASE.format(
            nome_escritorio="Escritório Teste",
            nome_cliente="João",
        )
        prompt_final = persona + prompt_formatado

        assert "<persona>" in prompt_final
        assert "Dra. Carla" in prompt_final
        assert "Escritório Teste" in prompt_final
        assert "João" in prompt_final

    def test_todos_os_tons_geram_saida_nao_vazia(self):
        """Todos os valores válidos de tom devem gerar instrução não-vazia."""
        from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona

        for tom in ("formal", "amigavel", "neutro"):
            resultado = gerar_instrucao_persona("Assistente", tom)
            assert resultado.strip(), f"Tom '{tom}' gerou string vazia"


class TestCarregarTemplates:
    @pytest.mark.asyncio
    async def test_retorna_defaults_sem_db(self):
        """Sem DB nem Redis, deve retornar os templates padrão."""
        from feature_1_ia_personalizada.services.messaging.templates import carregar_templates

        resultado = await carregar_templates(escritorio_id=99, redis_client=None, db=None)

        assert "boas_vindas" in resultado
        assert "atualizacao" in resultado
        assert "sem_novidade" in resultado

    @pytest.mark.asyncio
    async def test_usa_template_customizado_do_banco(self):
        """Quando escritório tem template customizado, deve usar esse ao invés do default."""
        from unittest.mock import AsyncMock, MagicMock
        from feature_1_ia_personalizada.services.messaging.templates import carregar_templates

        # Simula DB retornando templates customizados
        mock_row = MagicMock()
        mock_row.template_boas_vindas = "Oi {nome_cliente}, bem-vindo!"
        mock_row.template_atualizacao = None
        mock_row.template_sem_novidade = None

        mock_result = MagicMock()
        mock_result.one_or_none = MagicMock(return_value=mock_row)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        resultado = await carregar_templates(escritorio_id=1, redis_client=None, db=db)

        assert resultado["boas_vindas"] == "Oi {nome_cliente}, bem-vindo!"
        # Os demais devem usar o default
        from feature_1_ia_personalizada.services.messaging.templates import _DEFAULT_ATUALIZACAO
        assert resultado["atualizacao"] == _DEFAULT_ATUALIZACAO

    @pytest.mark.asyncio
    async def test_usa_cache_redis_quando_disponivel(self):
        """Quando há cache Redis, não deve consultar o banco."""
        import json
        from unittest.mock import AsyncMock
        from feature_1_ia_personalizada.services.messaging.templates import carregar_templates

        cached_templates = {
            "boas_vindas": "Olá {nome_cliente} do cache!",
            "atualizacao": "Atualização do cache",
            "sem_novidade": "Sem novidade do cache",
        }

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=json.dumps(cached_templates))

        db = AsyncMock()

        resultado = await carregar_templates(
            escritorio_id=1,
            redis_client=redis_client,
            db=db,
        )

        assert resultado["boas_vindas"] == "Olá {nome_cliente} do cache!"
        # DB não deve ter sido consultado
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_salva_resultado_no_redis(self):
        """Após consultar o banco, deve salvar resultado no Redis."""
        import json
        from unittest.mock import AsyncMock, MagicMock
        from feature_1_ia_personalizada.services.messaging.templates import carregar_templates

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)  # cache miss
        redis_client.set = AsyncMock()

        mock_row = MagicMock()
        mock_row.template_boas_vindas = None
        mock_row.template_atualizacao = None
        mock_row.template_sem_novidade = None
        mock_result = MagicMock()
        mock_result.one_or_none = MagicMock(return_value=mock_row)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        await carregar_templates(escritorio_id=5, redis_client=redis_client, db=db)

        redis_client.set.assert_called_once()
        call_args = redis_client.set.call_args
        assert "escritorio_templates:5" in call_args[0][0]
        assert call_args[1]["ex"] == 3600  # TTL 1h
