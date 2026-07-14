"""
Testes do motor de humanização.

O que estamos protegendo:
  - nenhum tique de LLM chega ao lead (emoji, markdown, travessão, textão)
  - o timing nunca é determinístico (timing constante = bot na hora)
  - rajada de mensagens vira UMA resposta, com N workers concorrentes
  - a regra de identidade continua no prompt (não pode sumir num refactor)
"""

from __future__ import annotations

import asyncio

import pytest

from feature_vendas.services.humanizacao.buffer import BufferMensagens
from feature_vendas.services.humanizacao.cadencia import calcular_ritmo
from feature_vendas.services.humanizacao.chunker import limpar, quebrar
from feature_vendas.services.humanizacao.estilo import REGRA_IDENTIDADE, system_prompt_clara

# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


def test_remove_tiques_de_llm():
    texto = "**Olá!** Vamos lá — o processo andou 😊\n- item um\n- item dois"
    limpo = limpar(texto)
    assert "*" not in limpo
    assert "—" not in limpo
    assert "😊" not in limpo
    assert "- item" not in limpo


def test_resposta_curta_fica_em_um_balao():
    assert quebrar("opa, me manda o número do processo que eu te mostro") == [
        "opa, me manda o número do processo que eu te mostro"
    ]


def test_textao_vira_rajada_curta():
    textao = (
        "O seu processo teve um despacho importante nesta semana. "
        "O juiz determinou a intimação da parte contrária para se manifestar. "
        "Isso significa que a outra parte tem 15 dias para responder. "
        "Depois disso, o processo segue para a fase de instrução, onde as provas são analisadas."
    )
    chunks = quebrar(textao)
    assert 2 <= len(chunks) <= 3, "textão deve virar rajada, nunca 1 balão gigante"
    assert all(len(c) <= 220 for c in chunks), "nenhum balão pode ser um textão"


def test_nunca_parte_palavra_ao_meio():
    texto = "palavra " * 80
    for chunk in quebrar(texto):
        assert not chunk.startswith(" ") and not chunk.endswith(" ")
        for palavra in chunk.split():
            assert palavra in {"palavra"}


def test_sobra_minuscula_nao_vira_balao_solto():
    texto = (
        "O processo teve movimentação relevante e a parte contrária foi intimada agora. "
        "O prazo corre a partir da publicação oficial no diário de justiça eletrônico. Certo."
    )
    chunks = quebrar(texto)
    assert all(len(c) >= 25 for c in chunks), "balão de 6 chars parece nervosismo, não fala"


def test_texto_vazio_nao_gera_balao():
    assert quebrar("") == []
    assert quebrar("   \n  ") == []


def test_quebra_de_linha_vira_balao_novo():
    """
    Regressão: gente manda ideia nova em mensagem nova. Quando o modelo pula
    linha, ele mudou de assunto — não pode sair tudo colado num balão só.
    """
    resposta = (
        "opa doutor, sim! foi a IA que escreveu sozinha\n"
        "quer que eu faça o mesmo com outro processo seu?"
    )
    chunks = quebrar(resposta)
    assert len(chunks) == 2, "quebra de linha é fronteira dura entre balões"
    assert "\n" not in chunks[0] and "\n" not in chunks[1]


def test_uma_linha_curta_continua_um_balao():
    """O caso mais comum não pode virar metralhadora."""
    assert len(quebrar("opa, me manda o número do processo")) == 1


# ---------------------------------------------------------------------------
# Cadência
# ---------------------------------------------------------------------------


def test_timing_nunca_e_deterministico():
    """O tique nº 1 de bot: responder sempre no mesmo tempo."""
    chunks = ["oi, tudo bem?"]
    ritmos = [calcular_ritmo("oi", chunks).total for _ in range(30)]
    assert len({round(r, 3) for r in ritmos}) > 25, "timing repetido demais = detectável"


def test_digitacao_proporcional_ao_tamanho():
    curto = calcular_ritmo("oi", ["ok"]).digitacao[0]
    longo = calcular_ritmo("oi", ["x" * 200]).digitacao[0]
    assert longo > curto, "balão maior tem que levar mais tempo digitando"


def test_baloes_longos_nao_tem_delay_identico():
    """
    Regressão: balões que batem no teto de digitação NÃO podem sair todos com
    exatamente o mesmo delay (6.5s, 6.5s, 6.5s). Repetição exata de timing é o
    tique de bot mais fácil de perceber, mesmo com o texto perfeito.
    """
    longo = "x" * 200  # estoura o teto de digitação
    delays = [calcular_ritmo("oi", [longo]).digitacao[0] for _ in range(20)]
    assert len({round(d, 3) for d in delays}) > 15, "delay do teto precisa de jitter"


def test_baloes_curtos_nao_tem_delay_identico():
    curtos = [calcular_ritmo("oi", ["ok"]).digitacao[0] for _ in range(20)]
    assert len({round(d, 3) for d in curtos}) > 15, "delay do piso precisa de jitter"


def test_latencia_total_nao_estoura_o_razoavel():
    """Naturalidade não pode custar a experiência: resposta tem que chegar."""
    chunks = quebrar(
        "O processo teve um despacho e a parte contrária foi intimada para se manifestar "
        "no prazo legal. Depois disso o feito segue para a fase seguinte normalmente."
    )
    for _ in range(50):
        total = calcular_ritmo("tem novidade no meu processo?", chunks).total
        assert total <= 35.0, f"latência de {total:.1f}s deixa o lead esperando demais"


# ---------------------------------------------------------------------------
# Buffer (debounce concorrente) — o coração da "espera a pessoa terminar"
# ---------------------------------------------------------------------------


class FakeRedis:
    """Redis in-memory suficiente para o debounce (pipeline, incr, get, lrange, delete)."""

    def __init__(self) -> None:
        self.listas: dict[str, list[str]] = {}
        self.valores: dict[str, int] = {}

    def pipeline(self):  # noqa: ANN201
        return FakePipeline(self)

    async def get(self, k):  # noqa: ANN001, ANN201
        return self.valores.get(k)


class FakePipeline:
    def __init__(self, r: FakeRedis) -> None:
        self._r = r
        self._ops: list = []

    def rpush(self, k, v):  # noqa: ANN001
        self._ops.append(("rpush", k, v))

    def expire(self, k, ttl):  # noqa: ANN001
        self._ops.append(("expire", k, ttl))

    def incr(self, k):  # noqa: ANN001
        self._ops.append(("incr", k))

    def lrange(self, k, a, b):  # noqa: ANN001
        self._ops.append(("lrange", k, a, b))

    def delete(self, k):  # noqa: ANN001
        self._ops.append(("delete", k))

    async def execute(self):  # noqa: ANN201
        out = []
        for op in self._ops:
            if op[0] == "rpush":
                self._r.listas.setdefault(op[1], []).append(op[2])
                out.append(len(self._r.listas[op[1]]))
            elif op[0] == "incr":
                self._r.valores[op[1]] = self._r.valores.get(op[1], 0) + 1
                out.append(self._r.valores[op[1]])
            elif op[0] == "lrange":
                out.append(list(self._r.listas.get(op[1], [])))
            elif op[0] == "delete":
                self._r.listas.pop(op[1], None)
                out.append(1)
            else:
                out.append(True)
        self._ops = []
        return out


@pytest.mark.asyncio
async def test_rajada_vira_uma_resposta_so():
    """
    3 mensagens picadas → 3 invocações concorrentes → só a ÚLTIMA responde,
    com o texto das três concatenado. As outras devolvem None.
    """
    buf = BufferMensagens(FakeRedis())  # type: ignore[arg-type]

    async def chega(texto: str, atraso: float):
        await asyncio.sleep(atraso)
        return await buf.aguardar_e_consolidar(1, 42, texto)

    resultados = await asyncio.gather(
        chega("boa tarde", 0.0),
        chega("doutor, uma dúvida", 0.3),
        chega("o processo do meu irmão saiu alguma coisa?", 0.6),
    )

    respostas = [r for r in resultados if r is not None]
    assert len(respostas) == 1, "só uma invocação pode responder a uma rajada"
    consolidado = respostas[0]
    assert "boa tarde" in consolidado
    assert "doutor, uma dúvida" in consolidado
    assert "o processo do meu irmão saiu alguma coisa?" in consolidado


@pytest.mark.asyncio
async def test_mensagem_unica_passa_direto():
    buf = BufferMensagens(FakeRedis())  # type: ignore[arg-type]
    resultado = await buf.aguardar_e_consolidar(1, 7, "quanto custa?")
    assert resultado == "quanto custa?"


# ---------------------------------------------------------------------------
# Regra de identidade — não pode sumir num refactor
# ---------------------------------------------------------------------------


def test_regra_de_identidade_esta_no_prompt():
    prompt = system_prompt_clara()
    assert REGRA_IDENTIDADE in prompt
    baixo = prompt.lower()
    assert "responde a verdade" in baixo
    assert "nunca afirma ser humana" in baixo
    assert "nunca nega ser uma ia" in baixo


def test_prompt_proibe_os_tiques():
    baixo = system_prompt_clara().lower()
    for proibicao in ("sem emoji", "sem markdown", "textão", "travessão"):
        assert proibicao in baixo
