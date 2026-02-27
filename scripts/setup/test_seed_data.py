import sys
import asyncio
import pytest
from unittest.mock import MagicMock, patch

# Cria um future/coroutine mockado resolvido manualmente para evitar lock do pytest-asyncio com AsyncMock
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

# Patching preventivo
sys.modules["shared.database.connection"] = MagicMock()

from scripts.setup.seed_data import (
    seed_escritorio,
    seed_usuarios,
    seed_clientes,
    seed_processos,
    ESCRITORIO_SEED,
    USUARIOS_SEED,
    CLIENTES_SEED,
    PROCESSOS_SEED,
)
from shared.models.escritorio import Escritorio


@pytest.mark.asyncio
async def test_seed_escritorio_novo():
    session = MagicMock()
    # Mocking chain do SQLAlchemy Mapped
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = async_return(mock_result)
    session.flush.return_value = async_return(None)
    
    escritorio = await seed_escritorio(session)
    
    assert escritorio.nome == ESCRITORIO_SEED["nome"]
    assert session.add.called
    assert session.flush.called


@pytest.mark.asyncio
async def test_seed_escritorio_existente():
    session = MagicMock()
    escritorio_existente = Escritorio(**ESCRITORIO_SEED)
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = escritorio_existente
    session.execute.return_value = async_return(mock_result)
    
    escritorio = await seed_escritorio(session)
    
    assert escritorio == escritorio_existente
    assert not session.add.called
    assert not session.flush.called


@pytest.mark.asyncio
async def test_seed_usuarios():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = async_return(mock_result)
    session.flush.return_value = async_return(None)
    
    escritorio_mock = Escritorio(id=1, **ESCRITORIO_SEED)
    
    usuarios = await seed_usuarios(session, escritorio_mock)
    
    assert len(usuarios) == len(USUARIOS_SEED)
    assert session.add.call_count == len(USUARIOS_SEED)
    assert session.flush.call_count == len(USUARIOS_SEED)


@pytest.mark.asyncio
async def test_seed_clientes():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = async_return(mock_result)
    session.flush.return_value = async_return(None)
    
    escritorio_mock = Escritorio(id=1, **ESCRITORIO_SEED)
    
    with patch("scripts.setup.seed_data.criptografar", return_value="mockado"):
        clientes = await seed_clientes(session, escritorio_mock)
        assert len(clientes) == len(CLIENTES_SEED)
        assert session.add.call_count == len(CLIENTES_SEED)


@pytest.mark.asyncio
async def test_seed_processos():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = async_return(mock_result)
    session.flush.return_value = async_return(None)
    
    escritorio_mock = Escritorio(id=1)
    clientes_mock = [MagicMock(id=i) for i in range(10)]
    responsavel_mock = MagicMock(id=1)
    
    await seed_processos(session, escritorio_mock, clientes_mock, responsavel_mock)
    
    assert session.add.call_count == len(PROCESSOS_SEED)
