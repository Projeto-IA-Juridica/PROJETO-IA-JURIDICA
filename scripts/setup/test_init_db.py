from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.setup.init_db import run_migrations, verify_tables

TABELAS_ESPERADAS = [
    "escritorios",
    "usuarios",
    "clientes",
    "processos",
    "interacoes",
]


@pytest.mark.asyncio
async def test_verify_tables_sucesso():
    # Mock da conexao que sera retornada pelo context manager
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    mock_conn.execute.return_value = mock_result

    class MockContextManager:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_engine = MagicMock()
    mock_engine.connect.return_value = MockContextManager()
    mock_engine.dispose = AsyncMock()

    with patch("scripts.setup.init_db.engine", mock_engine):
        with patch("sys.stdout", new=MagicMock()) as fake_stdout:
            await verify_tables()

        # Vemos se o execute foi chamado o numero de vezes correto
        assert mock_conn.execute.call_count == len(TABELAS_ESPERADAS)

        output = "".join([call.args[0] for call in fake_stdout.write.call_args_list])
        for tabela in TABELAS_ESPERADAS:
            assert f"[OK] {tabela}" in output


def test_run_migrations():
    # Testa se a funcao de executar as migracoes chama o alembic corretamente
    with patch("scripts.setup.init_db.command.upgrade") as mock_upgrade:
        with patch("scripts.setup.init_db.Config") as mock_config_class:
            mock_config_instance = MagicMock()
            mock_config_class.return_value = mock_config_instance

            run_migrations()

            mock_config_class.assert_called_once()
            mock_upgrade.assert_called_once_with(mock_config_instance, "head")
