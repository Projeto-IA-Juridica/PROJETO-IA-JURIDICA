# feature_1_ia_personalizada/tests/conftest.py
"""
Configuração de ambiente para testes da feature_1.
Define env vars FAKE antes de qualquer import de módulo de aplicação.
"""
from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()

_FAKE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
    "OPENAI_API_KEY": "sk-test-openai-key",
    "EVOLUTION_API_URL": "http://localhost:8080",
    "EVOLUTION_API_KEY": "test-evolution-key",
    "JUSBRASIL_API_KEY": "test-jusbrasil-key",
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-unit-tests-only",
    "ENCRYPTION_KEY": _TEST_FERNET_KEY,
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
}

for _key, _value in _FAKE_ENV.items():
    os.environ.setdefault(_key, _value)


# ---------------------------------------------------------------------------
# FakeRedis — simula Redis em memória sem dependência externa
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        self.lists: dict[str, list] = {}
        self.ttls: dict[str, int] = {}

    def _ltrim_impl(self, key: str, start: int, end: int) -> None:
        items = self.lists.get(key, [])
        n = len(items)
        s = start if start >= 0 else max(0, n + start)
        e = end if end >= 0 else n + end
        if e >= n:
            e = n - 1
        if s > e:
            self.lists[key] = []
        else:
            self.lists[key] = items[s : e + 1]

    def _lrange_impl(self, key: str, start: int, end: int) -> list:
        items = self.lists.get(key, [])
        n = len(items)
        s = start if start >= 0 else max(0, n + start)
        e = end if end >= 0 else n + end
        if e >= n:
            e = n - 1
        if n == 0 or s > e or s >= n:
            return []
        return items[s : e + 1]


class _FakePipeline:
    def __init__(self, store: _FakeStore) -> None:
        self._store = store
        self._cmds: list = []

    def rpush(self, key: str, *values) -> _FakePipeline:
        self._cmds.append(("rpush", key, values))
        return self

    def ltrim(self, key: str, start: int, end: int) -> _FakePipeline:
        self._cmds.append(("ltrim", key, start, end))
        return self

    def expire(self, key: str, seconds: int) -> _FakePipeline:
        self._cmds.append(("expire", key, seconds))
        return self

    def lrange(self, key: str, start: int, end: int) -> _FakePipeline:
        self._cmds.append(("lrange", key, start, end))
        return self

    async def execute(self) -> list:
        results = []
        for cmd in self._cmds:
            op = cmd[0]
            if op == "rpush":
                _, key, values = cmd
                lst = self._store.lists.setdefault(key, [])
                lst.extend(values)
                results.append(len(lst))
            elif op == "ltrim":
                _, key, start, end = cmd
                self._store._ltrim_impl(key, start, end)
                results.append(b"OK")
            elif op == "expire":
                _, key, seconds = cmd
                self._store.ttls[key] = seconds
                results.append(1)
            elif op == "lrange":
                _, key, start, end = cmd
                results.append(self._store._lrange_impl(key, start, end))
        self._cmds.clear()
        return results


class FakeRedis:
    """Redis em memória para testes — sem conexão de rede."""

    def __init__(self) -> None:
        self._store = _FakeStore()

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self._store)

    async def llen(self, key: str) -> int:
        return len(self._store.lists.get(key, []))

    async def delete(self, key: str) -> int:
        existed = key in self._store.lists
        self._store.lists.pop(key, None)
        self._store.ttls.pop(key, None)
        return 1 if existed else 0

    # Helpers de inspeção para testes
    def _list(self, key: str) -> list:
        return self._store.lists.get(key, [])

    def _ttl(self, key: str) -> int | None:
        return self._store.ttls.get(key)

    def _reset_ttl(self, key: str) -> None:
        self._store.ttls.pop(key, None)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


# ---------------------------------------------------------------------------
# Database e API Mocks
# ---------------------------------------------------------------------------

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Dependências reais/modelos
from shared.database.session import get_db
from shared.models.base import Base
from shared.models.escritorio import Escritorio
from shared.models.usuario import Usuario
from shared.security.encryption import hash_senha
from shared.security.jwt import criar_token

fake = Faker("pt_BR")

# Engine in-memory para SQLite Async
# Como o Postgres exigiria um banco de dados real rodando e limpar as tabelas,
# o SQLite:memory: é o padrao de ouro pra rodar pytest super rapido,
# porém precisamos do driver aiosqlite (que vamos instalar agora).
# Aqui vamos usar o esquema do sqlite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session")
def engine():
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield _engine
    _engine.sync_engine.dispose()


@pytest.fixture(scope="function")
async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def db_session(engine, init_db) -> AsyncSession:
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session


# Factory para Escritório
@pytest.fixture
async def escritorio_factory(db_session):
    async def _criar_escritorio(**kwargs):
        escritorio = Escritorio(
            nome=kwargs.get("nome", fake.company()),
            cnpj=kwargs.get("cnpj", fake.cnpj()),
            telefone=kwargs.get("telefone", "5511999999999"),
            email=kwargs.get("email", fake.company_email()),
            oab_responsavel=kwargs.get("oab_responsavel", "SP123456"),
            nome_responsavel=kwargs.get("nome_responsavel", fake.name()),
        )
        db_session.add(escritorio)
        await db_session.commit()
        await db_session.refresh(escritorio)
        return escritorio

    return _criar_escritorio


# Factory para Usuário
@pytest.fixture
async def usuario_factory(db_session):
    async def _criar_usuario(
        escritorio_id: int, senha_plana: str = "Senha123!", **kwargs
    ):
        hashed = hash_senha(senha_plana)
        usuario = Usuario(
            escritorio_id=escritorio_id,
            nome=kwargs.get("nome", fake.name()),
            email=kwargs.get("email", fake.email()),
            senha_hash=hashed,
            role=kwargs.get("role", "admin"),
        )
        db_session.add(usuario)
        await db_session.commit()
        await db_session.refresh(usuario)
        return usuario

    return _criar_usuario


# Token de autenticação válido
@pytest.fixture
def auth_token():
    def _gerar_token(user_id: int, escritorio_id: int, role: str = "admin"):
        # usa _TEST_FERNET_KEY de teste definida no topo
        return criar_token(user_id=user_id, escritorio_id=escritorio_id, role=role)

    return _gerar_token


# AsyncClient (TestClient) para bater nas rotas da API
@pytest.fixture
async def async_client(db_session):
    from httpx import ASGITransport, AsyncClient

    from feature_1_ia_personalizada.api.app import app

    # Override the get_db dependency to use our isolated test transaction
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
