"""
PIJ-193 — Testes unitários das funções de banco em send_notifications.py.

As três funções (buscar_processo_e_cliente, buscar_processos_sem_movimentacao,
buscar_clientes_para_pesquisa) já existem em worker_queries.py com lógica real.
Os testes cobrem o comportamento de cada uma usando mocks do async_session_factory.

Arquitetura testada:
    send_notifications.py
        → worker_queries.py (async via asyncio.run)
            → async_session_factory (mockado aqui)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from shared.database.worker_queries import (
    ClienteWorker,
    ProcessoWorker,
    query_clientes_para_pesquisa,
    query_processo_e_cliente,
    query_processos_sem_movimentacao,
)

# --------------------------------------------------------------------------- #
# Fábrica de objetos ORM mock
# --------------------------------------------------------------------------- #


def _make_processo(
    *,
    id: int = 1,
    numero_cnj: str = "1234567-00.2024.8.26.0000",
    cliente_id: int = 10,
    escritorio_id: int = 2,
    monitoramento_ativo: bool = True,
    status: str = "ativo",
    data_ultimo_andamento: datetime | None = None,
    cliente=None,
) -> MagicMock:
    p = MagicMock()
    p.id = id
    p.numero_cnj = numero_cnj
    p.cliente_id = cliente_id
    p.escritorio_id = escritorio_id
    p.monitoramento_ativo = monitoramento_ativo
    p.status = status
    p.data_ultimo_andamento = data_ultimo_andamento
    p.cliente = cliente
    return p


def _make_cliente(
    *,
    id: int = 10,
    nome: str = "Ana Lima",
    telefone: str = "5511999991111",
    escritorio_id: int = 2,
    ativo: bool = True,
    aceite_lgpd: bool = True,
) -> MagicMock:
    c = MagicMock()
    c.id = id
    c.nome = nome
    c.telefone_whatsapp = telefone
    c.escritorio_id = escritorio_id
    c.ativo = ativo
    c.aceite_lgpd = aceite_lgpd
    return c


def _mock_session(scalar_result=None, scalars_result=None):
    """Constrói um AsyncMock de sessão para qualquer execute()."""
    session = AsyncMock()
    execute_result = MagicMock()

    # Sempre definir o retorno — inclusive quando é None (sem o if, o MagicMock
    # criaria um sub-mock automaticamente em vez de retornar None)
    execute_result.scalar_one_or_none.return_value = scalar_result

    if scalars_result is not None:
        execute_result.scalars.return_value.all.return_value = scalars_result

    session.execute.return_value = execute_result
    return session


# --------------------------------------------------------------------------- #
# 1. query_processo_e_cliente
# --------------------------------------------------------------------------- #


def test_query_processo_e_cliente_retorna_tupla(monkeypatch):
    """Quando processo e cliente existem, retorna (ProcessoWorker, ClienteWorker)."""
    cliente_orm = _make_cliente()
    processo_orm = _make_processo(cliente=cliente_orm)
    session = _mock_session(scalar_result=processo_orm)

    # Precisamos mockar o async_session_factory como gerenciador de contexto
    async def _fake_session_factory():
        return session

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processo_e_cliente(1)

    assert resultado is not None
    processo_w, cliente_w = resultado
    assert isinstance(processo_w, ProcessoWorker)
    assert isinstance(cliente_w, ClienteWorker)
    assert processo_w.id == 1
    assert processo_w.numero_cnj == "1234567-00.2024.8.26.0000"
    assert cliente_w.id == 10
    assert cliente_w.telefone == "5511999991111"


def test_query_processo_e_cliente_retorna_none_quando_nao_existe(monkeypatch):
    """Quando o processo não está no banco, deve retornar None."""
    session = _mock_session(scalar_result=None)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processo_e_cliente(999)

    assert resultado is None


def test_query_processo_e_cliente_retorna_none_sem_cliente(monkeypatch):
    """Mesmo que o processo exista, se cliente for None retorna None."""
    processo_orm = _make_processo(cliente=None)
    session = _mock_session(scalar_result=processo_orm)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processo_e_cliente(1)

    assert resultado is None


# --------------------------------------------------------------------------- #
# 2. query_processos_sem_movimentacao
# --------------------------------------------------------------------------- #


def test_query_processos_sem_movimentacao_retorna_lista(monkeypatch):
    """Retorna lista de ProcessoWorker para processos sem andamento há > 30 dias."""
    data_antiga = datetime.now(UTC) - timedelta(days=45)
    cliente_orm = _make_cliente()
    processo_orm = _make_processo(
        data_ultimo_andamento=data_antiga, cliente=cliente_orm
    )

    session = _mock_session(scalars_result=[processo_orm])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processos_sem_movimentacao()

    assert len(resultado) == 1
    assert isinstance(resultado[0], ProcessoWorker)
    assert resultado[0].id == 1
    # cliente embutido no ProcessoWorker
    assert resultado[0].cliente is not None
    assert resultado[0].cliente.telefone == "5511999991111"


def test_query_processos_sem_movimentacao_ignora_sem_cliente(monkeypatch):
    """Processos sem cliente associado não devem aparecer no resultado."""
    processo_sem_cliente = _make_processo(cliente=None)

    session = _mock_session(scalars_result=[processo_sem_cliente])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processos_sem_movimentacao()

    assert resultado == []


def test_query_processos_sem_movimentacao_lista_vazia(monkeypatch):
    """Quando banco não retorna processos, resultado é lista vazia."""
    session = _mock_session(scalars_result=[])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_processos_sem_movimentacao()

    assert resultado == []


# --------------------------------------------------------------------------- #
# 3. query_clientes_para_pesquisa
# --------------------------------------------------------------------------- #


def test_query_clientes_para_pesquisa_retorna_clientes(monkeypatch):
    """Retorna ClienteWorker para clientes ativos com aceite_lgpd=True."""
    cliente_orm = _make_cliente()
    session = _mock_session(scalars_result=[cliente_orm])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_clientes_para_pesquisa()

    assert len(resultado) == 1
    assert isinstance(resultado[0], ClienteWorker)
    assert resultado[0].id == 10
    assert resultado[0].nome == "Ana Lima"
    assert resultado[0].telefone == "5511999991111"


def test_query_clientes_para_pesquisa_lista_vazia(monkeypatch):
    """Quando nenhum cliente elegível existe, retorna lista vazia."""
    session = _mock_session(scalars_result=[])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_clientes_para_pesquisa()

    assert resultado == []


def test_query_clientes_para_pesquisa_multiplos(monkeypatch):
    """Múltiplos clientes são retornados corretamente."""
    clientes = [
        _make_cliente(id=1, nome="João", telefone="5511111111111"),
        _make_cliente(id=2, nome="Maria", telefone="5522222222222"),
        _make_cliente(id=3, nome="Carlos", telefone="5533333333333"),
    ]
    session = _mock_session(scalars_result=clientes)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "shared.database.worker_queries.async_session_factory",
        return_value=ctx,
    ):
        resultado = query_clientes_para_pesquisa()

    assert len(resultado) == 3
    nomes = {r.nome for r in resultado}
    assert nomes == {"João", "Maria", "Carlos"}


# --------------------------------------------------------------------------- #
# 4. Integração rasa: send_notifications delega corretamente
# --------------------------------------------------------------------------- #


def test_send_notifications_delega_para_worker_queries():
    """
    Garante que as funções de send_notifications são apenas wrappers
    sobre as funções de worker_queries (sem lógica extra).
    """
    from feature_1_ia_personalizada.workers.send_notifications import (
        buscar_clientes_para_pesquisa,
        buscar_processo_e_cliente,
        buscar_processos_sem_movimentacao,
    )

    with patch(
        "feature_1_ia_personalizada.workers.send_notifications.query_processo_e_cliente",
        return_value=None,
    ) as mock_q:
        buscar_processo_e_cliente(42)
        mock_q.assert_called_once_with(42)

    with patch(
        "feature_1_ia_personalizada.workers.send_notifications.query_processos_sem_movimentacao",
        return_value=[],
    ) as mock_q:
        buscar_processos_sem_movimentacao()
        mock_q.assert_called_once()

    with patch(
        "feature_1_ia_personalizada.workers.send_notifications.query_clientes_para_pesquisa",
        return_value=[],
    ) as mock_q:
        buscar_clientes_para_pesquisa()
        mock_q.assert_called_once()
