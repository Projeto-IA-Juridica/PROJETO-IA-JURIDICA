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

    def rpush(self, key: str, *values) -> "_FakePipeline":
        self._cmds.append(("rpush", key, values))
        return self

    def ltrim(self, key: str, start: int, end: int) -> "_FakePipeline":
        self._cmds.append(("ltrim", key, start, end))
        return self

    def expire(self, key: str, seconds: int) -> "_FakePipeline":
        self._cmds.append(("expire", key, seconds))
        return self

    def lrange(self, key: str, start: int, end: int) -> "_FakePipeline":
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
