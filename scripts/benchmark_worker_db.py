"""
Benchmark das estratégias de sessão dos workers Celery.

Mede o custo real (contra o DATABASE_URL configurado) de três modos:

  1. pooled-reuso   — engine pooled por task: N sessões no MESMO loop
                      (padrão do hot path executar_fluxo_orquestrador)
  2. nullpool-loop  — worker_session_factory global: N sessões no mesmo loop,
                      cada uma abre/fecha conexão (padrão das tasks batch)
  3. nullpool-cross — N execuções de asyncio.run, 1 sessão cada
                      (padrão worker_queries: um loop novo por chamada)

Uso:
    python -m scripts.benchmark_worker_db [n_sessoes]

Só executa SELECT 1 — seguro contra qualquer banco.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

from sqlalchemy import text


def _fmt(tempos: list[float]) -> str:
    return (
        f"total {sum(tempos) * 1000:8.1f} ms | "
        f"média {statistics.mean(tempos) * 1000:7.1f} ms | "
        f"p95 {sorted(tempos)[int(len(tempos) * 0.95) - 1] * 1000:7.1f} ms"
    )


async def _sessao_select1(factory) -> float:
    inicio = time.perf_counter()
    async with factory() as session:
        await session.execute(text("SELECT 1"))
    return time.perf_counter() - inicio


async def _modo_mesmo_loop(factory, n: int) -> list[float]:
    return [await _sessao_select1(factory) for _ in range(n)]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    from shared.database.connection import (
        create_worker_session_factory,
        worker_session_factory,
    )

    print(f"Benchmark de sessões de worker (n={n}, SELECT 1)\n")

    # 1) pooled por task — reuso dentro do loop
    async def _pooled() -> list[float]:
        factory, engine = create_worker_session_factory(pooled=True)
        try:
            return await _modo_mesmo_loop(factory, n)
        finally:
            await engine.dispose()

    tempos = asyncio.run(_pooled())
    print(f"1. pooled-reuso   (hot path)      : {_fmt(tempos)}")

    # 2) NullPool, mesmo loop — conexão nova por sessão
    tempos = asyncio.run(_modo_mesmo_loop(worker_session_factory, n))
    print(f"2. nullpool-loop  (tasks batch)   : {_fmt(tempos)}")

    # 3) NullPool, um asyncio.run por sessão — pior caso (worker_queries)
    tempos = [asyncio.run(_sessao_select1(worker_session_factory)) for _ in range(n)]
    print(f"3. nullpool-cross (worker_queries): {_fmt(tempos)}")

    print(
        "\nInterpretação: (2)−(1) ≈ custo de reconectar por query; se alto "
        "(banco remoto/TLS), mover a task para create_worker_session_factory(pooled=True)."
    )


if __name__ == "__main__":
    main()
